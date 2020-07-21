"""
Utilities for truckersmp-cli main script.

Licensed under MIT.
"""

import ctypes
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess as subproc
import sys
import time
import urllib.parse
import urllib.request

from getpass import getuser
from gettext import ngettext
from truckersmp_cli import downloads
from truckersmp_cli import variables

vdf_is_available = False
try:
    import vdf
    vdf_is_available = True
except ImportError:
    pass


def get_current_steam_user(wine=False, wine_steam_dir=""):
    """
    Get the current AccountName with saved login credentials.

    If successful this returns the AccountName of the user with saved credentials.
    Otherwise this returns None.

    This function depends on the package "vdf".
    """
    loginvdf_paths = variables.File.loginusers_paths.copy()
    # try Wine Steam directory first when Wine is used
    if wine:
        loginvdf_paths.insert(0, os.path.join(wine_steam_dir,
                              variables.File.loginvdf_inner))
    for path in loginvdf_paths:
        try:
            with open(path) as f:
                login_vdf = vdf.parse(f)

            for info in login_vdf["users"].values():
                remember = "RememberPassword" in info and info["RememberPassword"] == "1"
                recent_uc = "MostRecent" in info and info["MostRecent"] == "1"
                recent_lc = "mostrecent" in info and info["mostrecent"] == "1"
                if remember and (recent_lc or recent_uc) and "AccountName" in info:
                    return info["AccountName"]
        except Exception:
            pass
    return None


def get_beta_branch_name(game_name="ets2"):
    """
    Get the current required beta branch name to comply with TruckersMP.

    If downgrade is needed, this returns a branch name that can be used
    to install TruckersMP-compatible versions of games (e.g. "temporary_1_36")
    on success or None on error.
    If downgrade is not needed, this returns None.
    """
    try:
        parser = downloads.DowngradeHTMLParser()
        with urllib.request.urlopen(variables.URL.truckersmp_stats) as f:
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
        with urllib.request.urlopen(variables.URL.truckersmp_api) as f:
            data = json.load(f)

        return {
            "ets2": data["supported_game_version"].replace("s", ""),
            "ats": data["supported_ats_game_version"].replace("s", "")
        }
    except Exception:
        return None


def check_libsdl2():
    """
    Check whether SDL2 shared object file is present.

    If SDL2 is detected, this function returns True.
    Otherwise, this returns False.

    Currently the check is done only on Linux systems.
    """
    if platform.system() != "Linux":
        return True

    try:
        ctypes.cdll.LoadLibrary(variables.File.sdl2_soname)
        return True
    except OSError:
        return False


def activate_native_d3dcompiler_47(prefix, wine, ets2):
    """Download/activate native 64-bit version of d3dcompiler_47."""
    # check whether DLL is already downloaded
    md5hash = hashlib.md5()
    need_download = True
    try:
        with open(variables.File.d3dcompiler_47, "rb") as f:
            while True:
                buf = f.read(md5hash.block_size * 4096)
                if not buf:
                    break
                md5hash.update(buf)
        if md5hash.hexdigest() == variables.File.d3dcompiler_47_md5:
            logging.debug("d3dcompiler_47.dll is present, MD5 is OK.")
            need_download = False
    except Exception:
        pass

    # download 64-bit d3dcompiler_47.dll from ImagingSIMS' repo
    # https://github.com/ImagingSIMS/ImagingSIMS
    if need_download:
        logging.debug("Downloading d3dcompiler_47.dll")
        os.makedirs(variables.Dir.dllsdir, exist_ok=True)
        if not downloads.download_files(
          variables.URL.raw_github,
          [(variables.URL.d3dcompilerpath,
                variables.File.d3dcompiler_47,
                variables.File.d3dcompiler_47_md5), ]):
            sys.exit("Failed to download d3dcompiler_47.dll")

    # copy into system32
    destdir = os.path.join(prefix, "drive_c/windows/system32")
    logging.debug("Copying d3dcompiler_47.dll into {}".format(destdir))
    shutil.copy(variables.File.d3dcompiler_47, destdir)

    # add DLL override setting
    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEPREFIX"] = prefix
    exename = "eurotrucks2.exe" if ets2 else "amtrucks.exe"
    logging.debug("Adding DLL override setting for {}".format(exename))
    subproc.call(
      [wine, "reg", "add",
       "HKCU\\Software\\Wine\\AppDefaults\\{}\\DllOverrides".format(exename),
       "/v", "d3dcompiler_47", "/t", "REG_SZ", "/d", "native"],
      env=env)


def wait_for_steam(use_proton, loginvdf_paths, wine=None, wine_steam_dir="", env=None):
    """
    Wait for Steam to be running.

    If use_proton is True, this function also detects
    the Steam installation directory for Proton and returns it.

    On user login the timestamp in
    [steam installation directory]/config/loginusers.vdf gets updated.
    We can detect the timestamp update with comparing timestamps.

    use_proton: True if Proton is used, False if Wine is used
    loginvdf_paths: loginusers.vdf paths
    wine: Wine command (path or name)
         (can be None if use_proton is True)
    env: A dictionary that contains environment variables
         (can be None if use_proton is True)
    """
    steamdir = None
    loginusers_timestamps = []
    for path in loginvdf_paths:
        try:
            st = os.stat(path)
            loginusers_timestamps.append(st.st_mtime)
        except OSError:
            loginusers_timestamps.append(0)
    if not check_steam_process(use_proton=use_proton, wine=wine, env=env):
        logging.debug("Starting Steam...")
        if use_proton:
            subproc.Popen(
              ("nohup", "steam"), stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
        else:
            subproc.Popen(
              ("nohup",
               wine, os.path.join(wine_steam_dir, "steam.exe"), "-no-cef-sandbox"),
              env=env, stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
        waittime = 99
        while waittime > 0:
            print(ngettext(
              "\rWaiting {} second for steam to start up. ",
              "\rWaiting {} seconds for steam to start up. ",
              waittime).format(waittime), end="")
            time.sleep(1)
            waittime -= 1
            for i, path in enumerate(loginvdf_paths):
                try:
                    st = os.stat(path)
                    if st.st_mtime > loginusers_timestamps[i]:
                        print("\r{}".format(" " * 70))  # clear "Waiting..." line
                        logging.debug(
                          "Steam should now be up and running and the user logged in.")
                        steamdir = os.path.dirname(
                          os.path.dirname(loginvdf_paths[i]))
                        break
                except OSError:
                    pass
            else:
                continue
            break
        else:
            # waited 99 seconds without detecting timestamp change
            print("\r{}".format(" " * 70))
            logging.debug("Steam should be up now.")
            if use_proton:
                # could not detect steam installation directory
                # fallback to $XDG_DATA_HOME/Steam
                steamdir = os.path.join(variables.Dir.XDG_DATA_HOME, "Steam")
    else:
        # Steam is running
        logging.debug("Steam is running")
        if use_proton:
            # detect most recently updated "loginusers.vdf" file
            max_mtime = max(loginusers_timestamps)
            for i, path in enumerate(loginvdf_paths):
                if loginusers_timestamps[i] == max_mtime:
                    steamdir = os.path.dirname(os.path.dirname(loginvdf_paths[i]))
                    break
    return steamdir


def check_steam_process(use_proton, wine=None, env=None):
    """
    Check whether Steam client is already running.

    If Steam is running, this function returns True.
    Otherwise this returns False.

    use_proton: True if Proton is used, False if Wine is used
    wine: Wine command (path or name)
         (can be None if use_proton is True)
    env: A dictionary that contains environment variables
         (can be None if use_proton is True)
    """
    if use_proton:
        try:
            subproc.check_call(
              ("pgrep", "-u", getuser(), "-x", "steam"), stdout=subproc.DEVNULL)
            return True
        except Exception:
            return False
    else:
        steam_is_running = False
        argv = (wine, "winedbg", "--command", "info process")
        env_wine = env.copy()
        env_wine["WINEDLLOVERRIDES"] = "winex11.drv="
        try:
            output = subproc.check_output(argv, env=env_wine, stderr=subproc.DEVNULL)
            for line in output.decode("utf-8").splitlines():
                line = line[:-1]  # strip last "'" for rindex()
                try:
                    exename = line[line.rindex("'") + 1:]
                except ValueError:
                    continue
                if exename.lower().endswith("steam.exe"):
                    steam_is_running = True
                    break
        except subproc.CalledProcessError as e:
            sys.exit("Failed to get Wine process list: " + e.output.decode("utf-8"))
        return steam_is_running


def check_args_errors(args):
    """Check command-line arguments."""
    # checks for updating and/or starting
    if not args.update and not args.start:
        logging.info("--update/--start not specified, doing both.")
        args.start = True
        args.update = True

    # make sure only one game is chosen
    if args.ats and args.ets2:
        sys.exit("It's only possible to use one game at a time.")
    elif not args.ats and not args.ets2:
        logging.info("--ats/--ets2 not specified, choosing ETS2.")
        args.ets2 = True

    game = "ats" if args.ats else "ets2"
    args.steamid = str(variables.AppId.game[game])
    if not args.prefixdir:
        args.prefixdir = variables.Dir.default_prefixdir[game]
    if not args.gamedir:
        args.gamedir = variables.Dir.default_gamedir[game]

    # checks for starting
    if args.start:
        # make sure proton and wine aren't chosen at the same time
        if args.proton and args.wine:
            sys.exit("Start with Proton (-p) or Wine (-w)?")
        elif not args.proton and not args.wine:
            if platform.system() == "Linux":
                logging.info("Platform is Linux, use Proton")
                args.proton = True
            else:
                logging.info("Platform is not Linux, use Wine")
                args.wine = True

    # make sure proton and wine are using the same default
    if args.wine:
        if (args.prefixdir == variables.Dir.default_prefixdir["ats"]
           or args.prefixdir == variables.Dir.default_prefixdir["ets2"]):
            logging.debug("""Prefix directory is the default while using Wine,
making sure it's the same directory as Proton""")
            args.prefixdir = os.path.join(args.prefixdir, "pfx")

    # default Steam directory for Wine
    if not args.wine_steam_dir:
        args.wine_steam_dir = os.path.join(
          args.prefixdir,
          "" if args.wine else "pfx",
          "dosdevices/c:/Program Files (x86)/Steam")

    # checks for starting while not updating
    if args.start and not args.update:
        # check for game
        if (not os.path.isfile(
              os.path.join(args.gamedir, "bin/win_x64/eurotrucks2.exe"))
            and not os.path.isfile(
              os.path.join(args.gamedir, "bin/win_x64/amtrucks.exe"))):
            sys.exit("""Game not found in {}
Need to download (-u) the game?""".format(args.gamedir))

        # check for proton
        if not os.path.isfile(os.path.join(args.protondir, "proton")) and args.proton:
            sys.exit("""Proton and no update wanted but Proton not found in {}
Need to download (-u) Proton?""".format(args.protondir))

    # checks for updating
    if args.update and not args.account:
        if vdf_is_available:
            args.account = get_current_steam_user(args.proton, args.wine_steam_dir)
        if not args.account:
            logging.info("Unable to find logged in steam user automatically.")
            sys.exit("Need the steam account name (-n name) to update.")

    # info
    logging.info("AppID/GameID: {} ({})".format(args.steamid, game))
    logging.info("Game directory: " + args.gamedir)
    logging.info("Prefix: " + args.prefixdir)
    if args.proton:
        logging.info("Proton directory: " + args.protondir)
