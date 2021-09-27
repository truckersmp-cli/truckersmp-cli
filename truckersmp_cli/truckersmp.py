"""
TruckersMP handler for truckersmp-cli main script.

Licensed under MIT.
"""

import hashlib
import json
import logging
import os
import sys
import urllib.parse
import urllib.request

from .utils import check_hash, download_files
from .variables import Args, URL


def determine_game_branch():
    """
    Determine Steam game branch name.

    When "--beta" option is specified, this returns the specified branch.
    Otherwise, this tries to determine the branch using TruckersMP Web API:
    If "--downgrade" option is specified, this tries to get
    the TruckersMP-compatible branch name (e.g. "temporary_1_39")
    and returns it if succeeded.
    If neither of them is specified, this returns the name "public"
    for using the latest version.
    """
    if Args.beta:
        return Args.beta

    branch = "public"
    game_name = "ats" if Args.ats else "ets2"
    try:
        if Args.downgrade:
            version = get_supported_game_versions()[game_name].split(".")
            branch = f"temporary_{version[0]}_{version[1]}"
    except (OSError, TypeError):
        pass

    return branch


def get_supported_game_versions():
    """
    Get TruckersMP-supported game versions via TruckersMP Web API.

    If this successfully gets the supported versions,
    this returns a dict of 'game: version' pairs
    (e.g. { "ets2": "1.36.2.55", "ats": "1.36.1.40" } ).
    Otherwise, this returns None.
    """
    result = None
    try:
        with urllib.request.urlopen(URL.truckersmp_api) as f_in:
            data = json.load(f_in)

        key_ets2_compat = "supported_game_version"
        key_ats_compat = "supported_ats_game_version"
        if key_ets2_compat in data and key_ats_compat in data:
            result = dict(
                ets2=data[key_ets2_compat].replace("s", ""),
                ats=data[key_ats_compat].replace("s", ""),
            )
        else:
            logging.warning("\
TruckersMP Web API returned the JSON that doesn't contain supported game versions.")
    except (OSError, ValueError) as ex:
        logging.warning("Failed to get information via TruckersMP Web API: %s", ex)

    return result


def update_mod():
    """Download missing or outdated "multiplayer mod" files."""
    # pylint: disable=too-many-branches

    logging.debug("Creating directory %s if it doesn't exist", Args.moddir)
    os.makedirs(Args.moddir, exist_ok=True)

    # get the fileinfo from the server
    try:
        with urllib.request.urlopen(URL.listurl) as f_in:
            files_json = f_in.read()
    except OSError as ex:
        sys.exit(f"Failed to download files.json: {ex}")

    # extract md5sums and filenames
    modfiles = []
    try:
        for item in json.JSONDecoder().decode(str(files_json, "ascii"))["Files"]:
            modfiles.append((item["Md5"], item["FilePath"]))
        if len(modfiles) == 0:
            raise ValueError("File list is empty")
    except ValueError as ex:
        sys.exit(f"Failed to parse files.json: {ex}\n"
                 f"Please report an issue: {URL.issueurl}")

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
            sys.exit(f"Failed to read {modfilepath}: {ex}")
    if len(dlfiles) > 0:
        message_dlfiles = "Files to download:\n"
        for path, _, _ in dlfiles:
            message_dlfiles += f"  {path}\n"
        logging.info(message_dlfiles.rstrip())
    else:
        logging.debug("No files to download")

    # download missing/wrong files
    if not download_files(URL.dlurl, dlfiles):
        if not download_files(URL.dlurlalt, dlfiles):
            # something went wrong
            sys.exit("Failed to download mod files.")
