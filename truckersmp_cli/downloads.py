"""
Download handler for truckersmp-cli main script.

Licensed under MIT.
"""

import hashlib
import html.parser
import http.client
import io
import json
import logging
import os
import platform
import subprocess as subproc
import sys
import tarfile
import time
import urllib.parse
import urllib.request

from zipfile import ZipFile

from truckersmp_cli import utils
from truckersmp_cli import variables


class DowngradeHTMLParser(html.parser.HTMLParser):
    """Extract downgrade information from HTML code at stats.truckersmp.com."""

    _data = {"ets2": False, "ats": False}
    _is_downgrade_node = False

    def handle_starttag(self, tag, attrs):
        """HTML start tag handler."""
        for attr in attrs:
            if (attr[0] == "href"
                    and len(attr) > 1
                    and attr[1] == variables.URL.truckersmp_downgrade_help):
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


def perform_self_update():
    """
    Update files to latest release. Do nothing for Python package.

    This function checks the latest GitHub release first.
    If local version is not up-to-date, this function retrieves the latest
    GitHub release asset (.tar.xz) and replaces existing files with extracted files.
    """
    # we don't update when Python package is used
    try:
        with open(os.path.join(os.path.dirname(variables.Dir.scriptdir), "RELEASE")) as f:
            current_release = f.readline().rstrip()
    except Exception:
        sys.exit("'RELEASE' file doesn't exist. Self update aborted.")

    # get latest release
    logging.info("Retrieving RELEASE from master")
    try:
        with urllib.request.urlopen(variables.URL.release) as f:
            release = f.readline().rstrip().decode("ascii")
    except Exception as e:
        sys.exit("Failed to retrieve RELEASE file: {}".format(e))

    # do nothing if the installed version is latest
    if release == current_release:
        logging.info("Already up-to-date.")
        return

    # retrieve the release asset
    archive_url = variables.URL.rel_tarxz_tmpl.format(release)
    logging.info("Retrieving release asset {}".format(archive_url))
    try:
        with urllib.request.urlopen(archive_url) as f:
            asset_archive = f.read()
    except Exception as e:
        sys.exit("Failed to retrieve release asset file: {}".format(e))

    # unpack the archive
    logging.info("Unpacking archive {}".format(archive_url))
    topdir = os.path.dirname(variables.Dir.scriptdir)
    try:
        with tarfile.open(fileobj=io.BytesIO(asset_archive), mode="r:xz") as f:
            f.extractall(topdir)
    except Exception as e:
        sys.exit("Failed to unpack release asset file: {}".format(e))

    # update files
    archive_dir = os.path.join(topdir, "truckersmp-cli-" + release)
    for root, _dirs, files in os.walk(archive_dir, topdown=False):
        inner_root = root[len(archive_dir):]
        destdir = topdir + inner_root
        logging.debug("Creating directory {}".format(destdir))
        os.makedirs(destdir, exist_ok=True)
        for f in files:
            srcpath = os.path.join(root, f)
            dstpath = os.path.join(destdir, f)
            logging.info("Copying {} as {}".format(srcpath, dstpath))
            os.replace(srcpath, dstpath)
        os.rmdir(root)

    # done
    logging.info("Self update complete")


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
            # when trying to download from variables.URL.dlurlalt
            del files_to_download[0]

            file_count += 1
    except Exception as e:
        logging.error("Failed to download https://{}{}: {}".format(host, path, e))
        return False
    finally:
        conn.close()

    return True


def update_mod(moddir):
    """Download missing or outdated "multiplayer mod" files."""
    if not os.path.isdir(moddir):
        logging.debug("Creating directory {}".format(moddir))
        os.makedirs(moddir, exist_ok=True)

    # get the fileinfo from the server
    try:
        with urllib.request.urlopen(variables.URL.listurl) as f:
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
Please report an issue: {}""".format(e, variables.URL.issueurl))

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
    if not download_files(variables.URL.dlurl, dlfiles):
        if not download_files(variables.URL.dlurlalt, dlfiles):
            # something went wrong
            sys.exit("Failed to download mod files.")


def update_game(args):
    """
    Update game and Proton via SteamCMD.

    We make sure Steam is closed before updating.
    On Linux, we make sure both Windows and Linux version of Steam are closed.
    It's possible to update with the Steam client open but the client looses
    all connectivity and asks for password and Steam Guard code after restart.

    When "--wine" is specified, this function retrieves/uses Windows version of
    SteamCMD. When "--proton" is specified, this retrieves/uses
    Linux version of SteamCMD.
    """
    steamcmd_prolog = ""
    steamcmd_cmd = []

    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEARCH"] = "win64"
    env_steam = env.copy()
    if args.proton:
        # Proton's "prefix" is for STEAM_COMPAT_DATA_PATH that contains
        # the directory "pfx" for WINEPREFIX
        env_steam["WINEPREFIX"] = os.path.join(args.prefixdir, "pfx")
    else:
        env_steam["WINEPREFIX"] = args.prefixdir
    # use a prefix only for SteamCMD to avoid every-time authentication
    env["WINEPREFIX"] = variables.Dir.steamcmdpfx
    # don't show "The Wine configuration is being updated" dialog
    # or install Gecko/Mono
    env["WINEDLLOVERRIDES"] = "winex11.drv="

    wine = env["WINE"] if "WINE" in env else "wine"
    os.makedirs(variables.Dir.steamcmdpfx, exist_ok=True)
    try:
        subproc.check_call((wine, "--version"), stdout=subproc.DEVNULL, env=env)
        logging.debug("Wine ({}) is available".format(wine))
    except subproc.CalledProcessError:
        logging.debug("Wine is not available")
        wine = None
    if args.proton:
        # we don't use system SteamCMD because something goes wrong in some cases
        # see https://github.com/lhark/truckersmp-cli/issues/43
        steamcmd = os.path.join(variables.Dir.steamcmddir, "steamcmd.sh")
        steamcmd_url = variables.URL.steamcmdlnx
        gamedir = args.gamedir
    else:
        if not wine:
            sys.exit("Wine ({}) is not available.".format(wine))
        steamcmd_prolog += """WINEDEBUG=-all
  WINEARCH=win64
  WINEPREFIX={}
  WINEDLLOVERRIDES=winex11.drv=
  {} """.format(variables.Dir.steamcmdpfx, wine)

        # steamcmd.exe uses Windows path, not UNIX path
        try:
            gamedir = subproc.check_output(
              (wine, "winepath", "-w", args.gamedir), env=env).decode("utf-8").rstrip()
        except Exception as e:
            sys.exit(
              "Failed to convert game directory to Windows path: {}".format(e))

        steamcmd = os.path.join(variables.Dir.steamcmddir, "steamcmd.exe")
        steamcmd_cmd.append(wine)
        steamcmd_url = variables.URL.steamcmdwin
    steamcmd_cmd.append(steamcmd)

    # fetch SteamCMD if not in our data directory
    os.makedirs(variables.Dir.steamcmddir, exist_ok=True)
    if not os.path.isfile(steamcmd):
        logging.debug("Retrieving SteamCMD")
        try:
            with urllib.request.urlopen(steamcmd_url) as f:
                steamcmd_archive = f.read()
        except Exception as e:
            sys.exit("Failed to retrieve SteamCMD: {}".format(e))
        logging.debug("Extracting SteamCMD")
        try:
            if args.proton:
                with tarfile.open(
                  fileobj=io.BytesIO(steamcmd_archive), mode="r:gz") as f:
                    f.extractall(variables.Dir.steamcmddir)
            else:
                with ZipFile(io.BytesIO(steamcmd_archive)) as f:
                    with f.open("steamcmd.exe") as f_exe:
                        with open(steamcmd, "wb") as f_out:
                            f_out.write(f_exe.read())
        except Exception as e:
            sys.exit("Failed to extract SteamCMD: {}".format(e))

    logging.info("SteamCMD: " + steamcmd)

    # Linux version of Steam
    if platform.system() == "Linux" and utils.check_steam_process(use_proton=True):
        logging.debug("Closing Linux version of Steam")
        subproc.call(("steam", "-shutdown"))
    # Windows version of Steam
    if wine and utils.check_steam_process(use_proton=False, wine=wine, env=env_steam):
        logging.debug("Closing Windows version of Steam in " + args.wine_steam_dir)
        subproc.call(
          (wine, os.path.join(args.wine_steam_dir, "steam.exe"), "-shutdown"),
          env=env_steam)

    if args.proton:
        # download/update Proton
        os.makedirs(args.protondir, exist_ok=True)
        logging.debug("Updating Proton (AppID:{})".format(args.proton_appid))
        logging.info("""Command:
  {}
    +login {}
    +force_install_dir {}
    +app_update {} validate
    +quit""".format(steamcmd, args.account, args.protondir, args.proton_appid))
        try:
            subproc.check_call(
              (steamcmd,
               "+login", args.account,
               "+force_install_dir", args.protondir,
               "+app_update", str(args.proton_appid), "validate",
               "+quit"))
        except subproc.CalledProcessError:
            sys.exit("SteamCMD exited abnormally")

    # determine game branch
    branch = "public"
    if args.beta:
        branch = args.beta
    else:
        game = "ats" if args.ats else "ets2"
        beta_branch_name = utils.get_beta_branch_name(game)
        if beta_branch_name:
            branch = beta_branch_name
    logging.info("Game branch: " + branch)

    # use SteamCMD to update the chosen game
    os.makedirs(args.gamedir, exist_ok=True)
    logging.debug("Updating Game (AppID:{})".format(args.steamid))
    logging.info("""Command:
  {}{}
    +@sSteamCmdForcePlatformType windows
    +login {}
    +force_install_dir {}
    +app_update {} -beta {} validate
    +quit""".format(
      steamcmd_prolog, steamcmd, args.account, gamedir, args.steamid, branch))
    steamcmd_args = [
        "+@sSteamCmdForcePlatformType", "windows",
        "+login", args.account,
        "+force_install_dir", gamedir,
        "+app_update", args.steamid,
        "-beta", branch,
        "validate",
        "+quit",
    ]
    try:
        subproc.check_call(steamcmd_cmd + steamcmd_args, env=env)
    except subproc.CalledProcessError:
        sys.exit("SteamCMD exited abnormally")
