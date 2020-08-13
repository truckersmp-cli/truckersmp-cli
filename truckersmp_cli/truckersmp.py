"""
TruckersMP handler for truckersmp-cli main script.

Licensed under MIT.
"""

import hashlib
import html.parser
import json
import logging
import os
import sys
import urllib.parse
import urllib.request

from .utils import check_hash, download_files
from .variables import Args, URL


class DowngradeHTMLParser(html.parser.HTMLParser):
    """Extract downgrade information from HTML code at stats.truckersmp.com."""

    _data = {"ets2": False, "ats": False}
    _is_downgrade_node = False

    def error(self, message):
        """Error handler."""
        raise NotImplementedError("Error handler is not implemented")

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
        with urllib.request.urlopen(URL.truckersmp_stats) as f_in:
            parser.feed(f_in.read().decode("utf-8"))

        if parser.data[game_name]:
            version = get_supported_game_versions()[game_name].split(".")
            return "temporary_{}_{}".format(version[0], version[1])
        return None
    except (OSError, TypeError):
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
        with urllib.request.urlopen(URL.truckersmp_api) as f_in:
            data = json.load(f_in)

        return {
            "ets2": data["supported_game_version"].replace("s", ""),
            "ats": data["supported_ats_game_version"].replace("s", "")
        }
    except (OSError, ValueError):
        return None


def update_mod():
    """Download missing or outdated "multiplayer mod" files."""
    # pylint: disable=too-many-branches

    if not os.path.isdir(Args.moddir):
        logging.debug("Creating directory %s", Args.moddir)
        os.makedirs(Args.moddir, exist_ok=True)

    # get the fileinfo from the server
    try:
        with urllib.request.urlopen(URL.listurl) as f_in:
            files_json = f_in.read()
    except OSError as ex:
        sys.exit("Failed to download files.json: {}".format(ex))

    # extract md5sums and filenames
    modfiles = []
    try:
        for item in json.JSONDecoder().decode(str(files_json, "ascii"))["Files"]:
            modfiles.append((item["Md5"], item["FilePath"]))
        if len(modfiles) == 0:
            raise ValueError("File list is empty")
    except ValueError as ex:
        sys.exit("""Failed to parse files.json: {}
Please report an issue: {}""".format(ex, URL.issueurl))

    # compare existing local files with md5sums
    # and remember missing/wrong files
    dlfiles = []
    for md5, jsonfilepath in modfiles:
        modfilepath = os.path.join(Args.moddir, jsonfilepath[1:])
        if not os.path.isfile(modfilepath):
            dlfiles.append(("/files" + jsonfilepath, modfilepath, md5))
            continue
        try:
            if not check_hash(modfilepath, md5, hashlib.md5()):
                dlfiles.append(("/files" + jsonfilepath, modfilepath, md5))
        except OSError as ex:
            sys.exit("Failed to read {}: {}".format(modfilepath, ex))
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
