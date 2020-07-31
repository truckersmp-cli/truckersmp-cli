"""
TruckersMP handler for truckersmp-cli main script.

Licensed under MIT.
"""

import hashlib
import html.parser
import http.client
import json
import logging
import os
import platform
import subprocess as subproc
import sys
import time
import urllib.parse
import urllib.request

from .variables import URL


class DowngradeHTMLParser(html.parser.HTMLParser):
    """Extract downgrade information from HTML code at stats.truckersmp.com."""

    _data = {"ets2": False, "ats": False}
    _is_downgrade_node = False

    def handle_starttag(self, tag, attrs):
        """HTML start tag handler."""
        for attr in attrs:
            if (attr[0] == "href"
                    and len(attr) > 1
                    and attr[1] == URL.truckersmp_downgrade_help):
                self._is_downgrade_node = True
                break

    def handle_endtag(self, tag):
        """HTML end tag handler."""
        self._is_downgrade_node = False

    def handle_data(self, data):
        """HTML data handler."""
        if self._is_downgrade_node:
            if "ETS2" in data:
                self._data["ets2"] = True
            if "ATS" in data:
                self._data["ats"] = True

    @property
    def data(self):
        """Return downgrade information."""
        return self._data


def download_files(host, files_to_download, progress_count=None):
    """Download files."""
    file_count = progress_count[0] if progress_count else 1
    num_of_files = progress_count[1] if progress_count else len(files_to_download)
    conn = http.client.HTTPSConnection(host)
    try:
        while len(files_to_download) > 0:
            path, dest, md5 = files_to_download[0]
            md5hash = hashlib.md5()
            bufsize = md5hash.block_size * 256
            name = os.path.basename(path)
            destdir = os.path.dirname(dest)
            name_getting = "[{}/{}] Get: {}".format(file_count, num_of_files, name)
            logging.debug(
              "Downloading file https://{}{} to {}".format(host, path, destdir))

            # make file hierarchy
            os.makedirs(destdir, exist_ok=True)

            # download file
            conn.request("GET", path, headers={"Connection": "keep-alive"})
            res = conn.getresponse()

            if (res.status == 301
                    or res.status == 302
                    or res.status == 303
                    or res.status == 307
                    or res.status == 308):
                # HTTP redirection
                u = urllib.parse.urlparse(res.getheader("Location"))
                if not download_files(
                  u.netloc, [(u.path, dest, md5), ], (file_count, num_of_files)):
                    return False
                # downloaded successfully from redirected URL
                del files_to_download[0]
                file_count += 1
                conn = http.client.HTTPSConnection(host)
                continue
            elif res.status != 200:
                logging.error(
                  "Server {} responded with status code {}.".format(host, res.status))
                return False

            lastmod = res.getheader("Last-Modified")
            content_len = res.getheader("Content-Length")

            with open(dest, "wb") as f:
                downloaded = 0
                while True:
                    buf = res.read(bufsize)
                    if not buf:
                        break
                    downloaded += len(buf)
                    f.write(buf)
                    md5hash.update(buf)
                    if content_len:
                        progress = "{:,} / {:,}".format(downloaded, int(content_len))
                    else:
                        progress = "{:,}".format(downloaded)
                    print("\r{:40}{:>40}".format(name_getting, progress), end="")

            if md5hash.hexdigest() != md5:
                print("\r{:40}{:>40}".format(name, "MD5 MISMATCH"))
                logging.error("MD5 mismatch for {}".format(dest))
                return False

            # wget-like timestamping for downloaded files
            if lastmod:
                timestamp = time.mktime(
                  time.strptime(lastmod, "%a, %d %b %Y %H:%M:%S GMT")) - time.timezone
                try:
                    os.utime(dest, (timestamp, timestamp))
                except Exception:
                    pass

            # downloaded successfully
            print("\r{:40}{:>40}".format(name, "OK"))

            # skip already downloaded files
            # when trying to download from URL.dlurlalt
            del files_to_download[0]

            file_count += 1
    except Exception as e:
        logging.error("Failed to download https://{}{}: {}".format(host, path, e))
        return False
    finally:
        conn.close()

    return True


def get_beta_branch_name(game_name="ets2"):
    """
    Get the current required beta branch name to comply with TruckersMP.

    If downgrade is needed, this returns a branch name that can be used
    to install TruckersMP-compatible versions of games (e.g. "temporary_1_36")
    on success or None on error.
    If downgrade is not needed, this returns None.
    """
    try:
        parser = DowngradeHTMLParser()
        with urllib.request.urlopen(URL.truckersmp_stats) as f:
            parser.feed(f.read().decode("utf-8"))

        if parser.data[game_name]:
            version = get_supported_game_versions()[game_name].split(".")
            return "temporary_{}_{}".format(version[0], version[1])
        return None
    except Exception:
        return None


def get_supported_game_versions():
    """
    Get TruckersMP-supported game versions via TruckersMP Web API.

    Returns a dict of 'game: version' pairs:
    {
        "ets2": "1.36.2.55",
        "ats": "1.36.1.40"
    }
    """
    try:
        with urllib.request.urlopen(URL.truckersmp_api) as f:
            data = json.load(f)

        return {
            "ets2": data["supported_game_version"].replace("s", ""),
            "ats": data["supported_ats_game_version"].replace("s", "")
        }
    except Exception:
        return None


def update_mod(moddir):
    """Download missing or outdated "multiplayer mod" files."""
    if not os.path.isdir(moddir):
        logging.debug("Creating directory {}".format(moddir))
        os.makedirs(moddir, exist_ok=True)

    # get the fileinfo from the server
    try:
        with urllib.request.urlopen(URL.listurl) as f:
            files_json = f.read()
    except Exception as e:
        sys.exit("Failed to download files.json: {}".format(e))

    # extract md5sums and filenames
    modfiles = []
    try:
        for item in json.JSONDecoder().decode(str(files_json, "ascii"))["Files"]:
            modfiles.append((item["Md5"], item["FilePath"]))
        if len(modfiles) == 0:
            raise Exception("File list is empty")
    except Exception as e:
        sys.exit("""Failed to parse files.json: {}
Please report an issue: {}""".format(e, URL.issueurl))

    # compare existing local files with md5sums
    # and remember missing/wrong files
    dlfiles = []
    for md5, jsonfilepath in modfiles:
        md5hash = hashlib.md5()
        modfilepath = os.path.join(moddir, jsonfilepath[1:])
        if not os.path.isfile(modfilepath):
            dlfiles.append(("/files" + jsonfilepath, modfilepath, md5))
        else:
            try:
                with open(modfilepath, "rb") as f:
                    while True:
                        buf = f.read(md5hash.block_size * 4096)
                        if not buf:
                            break
                        md5hash.update(buf)
                if md5hash.hexdigest() != md5:
                    dlfiles.append(("/files" + jsonfilepath, modfilepath, md5))
            except Exception as e:
                sys.exit("Failed to read {}: {}".format(modfilepath, e))
    if len(dlfiles) > 0:
        message_dlfiles = "Files to download:\n"
        for path, _, _ in dlfiles:
            message_dlfiles += "  {}\n".format(path)
        logging.info(message_dlfiles.rstrip())
    else:
        logging.debug("No files to download")

    # download missing/wrong files
    if not download_files(URL.dlurl, dlfiles):
        if not download_files(URL.dlurlalt, dlfiles):
            # something went wrong
            sys.exit("Failed to download mod files.")
