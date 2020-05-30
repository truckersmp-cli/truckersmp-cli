"""
Module for truckersmp-cli main script.

Licensed under MIT.
"""

import argparse
import ctypes
import hashlib
import html.parser
import http.client
import io
import json
import locale
import logging
import os
import platform
import shutil
import signal
import subprocess as subproc
import sys
import tarfile
import time
import urllib.parse
import urllib.request
from getpass import getuser
from gettext import ngettext

vdf_is_available = False
try:
    import vdf
    vdf_is_available = True
except ImportError:
    pass


class URL:
    """URLs."""

    dlurl = "download.ets2mp.com"
    dlurlalt = "failover.truckersmp.com"
    listurl = "https://update.ets2mp.com/files.json"
    issueurl = "https://github.com/lhark/truckersmp-cli/issues"
    steamcmdurl = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    raw_github = "raw.githubusercontent.com"
    d3dcompilerpath = "/ImagingSIMS/ImagingSIMS/master/Redist/x64/d3dcompiler_47.dll"
    truckersmp_api = "https://api.truckersmp.com/v2/version"
    truckersmp_stats = "https://stats.truckersmp.com"
    truckersmp_downgrade_help = "https://truckersmp.com/kb/26"


class Dir:
    """Directories."""

    XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    default_gamedir = {
        "ats": os.path.join(
          XDG_DATA_HOME, "truckersmp-cli/American Truck Simulator/data"),
        "ets2": os.path.join(
          XDG_DATA_HOME, "truckersmp-cli/Euro Truck Simulator 2/data"),
    }
    default_prefixdir = {
        "ats": os.path.join(
          XDG_DATA_HOME, "truckersmp-cli/American Truck Simulator/prefix"),
        "ets2": os.path.join(
          XDG_DATA_HOME, "truckersmp-cli/Euro Truck Simulator 2/prefix"),
    }
    default_moddir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/TruckersMP")
    default_protondir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/Proton")
    steamcmddir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/steamcmd")
    dllsdir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/dlls")
    scriptdir = os.path.dirname(os.path.realpath(__file__))


class File:
    """Files."""

    loginvdf_inner = "config/loginusers.vdf"
    # known paths for [steam installation directory]/config/loginusers.vdf
    loginusers_paths = [
        # Official (Valve) version
        os.path.join(Dir.XDG_DATA_HOME, "Steam", loginvdf_inner),
        # Debian-based systems, old path
        os.path.join(os.path.expanduser("~/.steam"), loginvdf_inner),
        # Debian-based systems, new path
        os.path.join(os.path.expanduser("~/.steam/debian-installation"), loginvdf_inner),
    ]
    proton_json = os.path.join(Dir.scriptdir, "proton.json")
    inject_exe = os.path.join(Dir.scriptdir, "truckersmp-cli.exe")
    overlayrenderer_inner = "ubuntu12_64/gameoverlayrenderer.so"
    d3dcompiler_47 = os.path.join(Dir.dllsdir, "d3dcompiler_47.dll")
    d3dcompiler_47_md5 = "b2cc65e1930e75f563078c6a20221b37"
    sdl2_soname = "libSDL2-2.0.so.0"


class AppId:
    """Steam AppIds."""

    game = {
        "ats":          270880,        # https://steamdb.info/app/270880/
        "ets2":         227300,        # https://steamdb.info/app/227300/
    }
    proton = {}


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
        ctypes.cdll.LoadLibrary(File.sdl2_soname)
        return True
    except OSError:
        return False


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


def activate_native_d3dcompiler_47(prefix, wine):
    """Download/activate native 64-bit version of d3dcompiler_47."""
    # check whether DLL is already downloaded
    md5hash = hashlib.md5()
    need_download = True
    try:
        with open(File.d3dcompiler_47, "rb") as f:
            while True:
                buf = f.read(md5hash.block_size * 4096)
                if not buf:
                    break
                md5hash.update(buf)
        if md5hash.hexdigest() == File.d3dcompiler_47_md5:
            logging.debug("d3dcompiler_47.dll is present, MD5 is OK.")
            need_download = False
    except Exception:
        pass

    # download 64-bit d3dcompiler_47.dll from ImagingSIMS' repo
    # https://github.com/ImagingSIMS/ImagingSIMS
    if need_download:
        logging.debug("Downloading d3dcompiler_47.dll")
        os.makedirs(Dir.dllsdir, exist_ok=True)
        if not download_files(
          URL.raw_github,
          [(URL.d3dcompilerpath, File.d3dcompiler_47, File.d3dcompiler_47_md5), ]):
            sys.exit("Failed to download d3dcompiler_47.dll")

    # copy into system32
    destdir = os.path.join(prefix, "drive_c/windows/system32")
    logging.debug("Copying d3dcompiler_47.dll into {}".format(destdir))
    shutil.copy(File.d3dcompiler_47, destdir)

    # add DLL override setting
    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEPREFIX"] = prefix
    exename = "eurotrucks2.exe" if args.ets2 else "amtrucks.exe"
    logging.debug("Adding DLL override setting for {}".format(exename))
    subproc.call(
      [wine, "reg", "add",
       "HKCU\\Software\\Wine\\AppDefaults\\{}\\DllOverrides".format(exename),
       "/v", "d3dcompiler_47", "/t", "REG_SZ", "/d", "native"],
      env=env)


def start_with_proton():
    """Start game with Proton."""
    # make sure steam is started
    # It's probably safe to assume steam is up and running completely started
    # when the user is logged in. On user login the timestamp in
    # [steam installation directory]/config/loginusers.vdf gets updated.
    # We can detect the timestamp update with comparing timestamps.
    loginusers_timestamps = []
    for path in File.loginusers_paths:
        try:
            st = os.stat(path)
            loginusers_timestamps.append(st.st_mtime)
        except OSError:
            loginusers_timestamps.append(0)
    try:
        subproc.check_call(
          ["pgrep", "-u", getuser(), "-x", "steam"], stdout=subproc.DEVNULL)
    except Exception:
        logging.debug("Starting Steam…")
        subproc.Popen(["nohup", "steam"], stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
        waittime = 99
        while waittime > 0:
            print(ngettext(
              "\rWaiting {} second for steam to start up. ",
              "\rWaiting {} seconds for steam to start up. ",
              waittime).format(waittime), end="")
            time.sleep(1)
            waittime -= 1
            for i, path in enumerate(File.loginusers_paths):
                try:
                    st = os.stat(path)
                    if st.st_mtime > loginusers_timestamps[i]:
                        print("\r{}".format(" " * 70))  # clear "Waiting..." line
                        logging.debug(
                          "Steam should now be up and running and the user logged in.")
                        steamdir = os.path.dirname(
                          os.path.dirname(File.loginusers_paths[i]))
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
            # could not detect steam installation directory
            # fallback to $XDG_DATA_HOME/Steam
            steamdir = os.path.join(Dir.XDG_DATA_HOME, "Steam")
    else:
        # Steam is running
        # detect most recently updated "loginusers.vdf" file
        logging.debug("Steam is running")
        max_mtime = max(loginusers_timestamps)
        for i, path in enumerate(File.loginusers_paths):
            if loginusers_timestamps[i] == max_mtime:
                steamdir = os.path.dirname(os.path.dirname(File.loginusers_paths[i]))
                break
    logging.info("Steam installation directory: " + steamdir)

    if not os.path.isdir(args.prefixdir):
        logging.debug("Creating directory {}".format(args.prefixdir))
    os.makedirs(args.prefixdir, exist_ok=True)

    # activate native d3dcompiler_47
    wine = os.path.join(args.protondir, "dist/bin/wine")
    if args.activate_native_d3dcompiler_47:
        activate_native_d3dcompiler_47(os.path.join(args.prefixdir, "pfx"), wine)

    env = os.environ.copy()
    env["SteamGameId"] = args.steamid
    env["SteamAppId"] = args.steamid
    env["STEAM_COMPAT_DATA_PATH"] = args.prefixdir
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steamdir
    env["PROTON_USE_WINED3D"] = "1" if args.use_wined3d else "0"
    env["PROTON_NO_D3D11"] = "1" if not args.enable_d3d11 else "0"
    # enable Steam Overlay unless "--disable-proton-overlay" is specified
    if args.disable_proton_overlay:
        ld_preload = ""
    else:
        overlayrenderer = os.path.join(steamdir, File.overlayrenderer_inner)
        if "LD_PRELOAD" in env:
            env["LD_PRELOAD"] += ":" + overlayrenderer
        else:
            env["LD_PRELOAD"] = overlayrenderer
        ld_preload = "LD_PRELOAD={}\n  ".format(env["LD_PRELOAD"])
    proton = os.path.join(args.protondir, "proton")
    # check whether singleplayer or multiplayer
    argv = [sys.executable, proton, "run"]
    if args.singleplayer:
        exename = "eurotrucks2.exe" if args.ets2 else "amtrucks.exe"
        gamepath = os.path.join(args.gamedir, "bin/win_x64", exename)
        argv += gamepath, "-nointro", "-64bit"
    else:
        argv += File.inject_exe, args.gamedir, args.moddir
    logging.info("""Startup command:
  SteamGameId={}
  SteamAppId={}
  STEAM_COMPAT_DATA_PATH={}
  STEAM_COMPAT_CLIENT_INSTALL_PATH={}
  PROTON_USE_WINED3D={}
  PROTON_NO_D3D11={}
  {}{} {}
  run
  {} {} {}""".format(
      env["SteamGameId"], env["SteamAppId"],
      env["STEAM_COMPAT_DATA_PATH"], env["STEAM_COMPAT_CLIENT_INSTALL_PATH"],
      env["PROTON_USE_WINED3D"],
      env["PROTON_NO_D3D11"],
      ld_preload,
      sys.executable, proton, argv[-3], argv[-2], argv[-1]))
    try:
        output = subproc.check_output(argv, env=env, stderr=subproc.STDOUT)
        logging.info("Proton output:\n" + output.decode("utf-8"))
    except subproc.CalledProcessError as e:
        logging.error("Proton output:\n" + e.output.decode("utf-8"))


def start_with_wine():
    """Start game with Wine."""
    wine = os.environ["WINE"] if "WINE" in os.environ else "wine"
    if args.activate_native_d3dcompiler_47:
        activate_native_d3dcompiler_47(args.prefixdir, wine)

    print("""
    ###################################################################
    #                                                                 #
    #  Please check wine steam is running or the launcher won't work  #
    #                                                                 #
    ###################################################################

    Press enter if you are good to go: """, end="")
    sys.stdin.readline()

    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEARCH"] = "win64"
    env["WINEPREFIX"] = args.prefixdir
    env["WINEDLLOVERRIDES"] = "d3d11=;dxgi=" if not args.enable_d3d11 else ""
    argv = [wine, ]
    if args.singleplayer:
        exename = "eurotrucks2.exe" if args.ets2 else "amtrucks.exe"
        gamepath = os.path.join(args.gamedir, "bin/win_x64", exename)
        argv += gamepath, "-nointro", "-64bit"
    else:
        argv += File.inject_exe, args.gamedir, args.moddir
    logging.info("""Startup command:
  WINEDEBUG=-all
  WINEARCH=win64
  WINEPREFIX={}
  WINEDLLOVERRIDES="{}"
  {} {} {} {}""".format(
      env["WINEPREFIX"], env["WINEDLLOVERRIDES"], wine, argv[-3], argv[-2], argv[-1]))
    try:
        output = subproc.check_output(argv, env=env, stderr=subproc.STDOUT)
        logging.info("Wine output:\n" + output.decode("utf-8"))
    except subproc.CalledProcessError as e:
        logging.error("Wine output:\n" + e.output.decode("utf-8"))


def update_mod():
    """Download missing or outdated "multiplayer mod" files."""
    # update the script itself when origin/master is checked out
    try:
        out = subproc.check_output(
          ["git", "-C", Dir.scriptdir,
           "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        if out == b"origin/master\n":
            logging.debug(
              "This script is checked out with git, upstream is origin/master")
            logging.debug("Running git pull")
            subproc.check_call(
              ["git", "-C", Dir.scriptdir, "pull"],
              stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
        else:
            raise Exception
    except Exception:
        logging.debug("Better not to do self update")

    if not os.path.isdir(args.moddir):
        logging.debug("Creating directory {}".format(args.moddir))
        os.makedirs(args.moddir, exist_ok=True)

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
        modfilepath = os.path.join(args.moddir, jsonfilepath[1:])
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


def get_current_steam_user():
    """
    Get the current AccountName with saved login credentials.

    If successful this returns the AccountName of the user with saved credentials.
    Otherwise this returns None.

    This function depends on the package "vdf".
    """
    for path in File.loginusers_paths:
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


def update_game():
    """Update game and Proton."""
    # make sure steam is closed before updating
    # it's possible to update with the steam client open but the client looses
    # all connectivity and asks for password and steam guard code after restart
    try:
        subproc.check_call(
          ["pgrep", "-u", getuser(), "-x", "steam"], stdout=subproc.DEVNULL)
        logging.debug("Closing Steam")
        subproc.call(["steam", "-shutdown"])
    except Exception:
        pass

    if not os.path.isdir(args.gamedir):
        logging.debug("Creating directory {}".format(args.gamedir))
        os.makedirs(args.gamedir, exist_ok=True)

    # fetch steamcmd if not in our data directory
    # we don't use system steamcmd because something goes wrong in some cases
    # see https://github.com/lhark/truckersmp-cli/issues/43
    steamcmd = os.path.join(Dir.steamcmddir, "steamcmd.sh")
    if not os.path.isfile(steamcmd):
        logging.debug("Downloading steamcmd")
        os.makedirs(Dir.steamcmddir, exist_ok=True)
        try:
            with urllib.request.urlopen(URL.steamcmdurl) as f:
                steamcmd_targz = f.read()
        except Exception as e:
            sys.exit("Failed to download steamcmd: {}".format(e))
        with tarfile.open(fileobj=io.BytesIO(steamcmd_targz), mode="r:gz") as f:
            f.extractall(Dir.steamcmddir)
    logging.info("Steamcmd: " + steamcmd)

    # download/update Proton
    if args.proton:
        logging.debug("Updating Proton (AppId:{})".format(args.proton_appid))

        if not os.path.isdir(args.protondir):
            logging.debug("Creating directory {}".format(args.protondir))
            os.makedirs(args.protondir, exist_ok=True)

        logging.info("""Command:
  {}
    +login {}
    +force_install_dir {}
    +app_update {} validate
    +quit""".format(steamcmd, args.account, args.protondir, args.proton_appid))
        subproc.call(
          [steamcmd,
           "+login", args.account,
           "+force_install_dir", args.protondir,
           "+app_update", str(args.proton_appid), "validate",
           "+quit"])

    branch = "public"
    if args.beta:
        branch = args.beta
    else:
        game = "ats" if args.ats else "ets2"
        beta_branch_name = get_beta_branch_name(game)
        if beta_branch_name:
            branch = beta_branch_name

    # use steamcmd to update the chosen game
    logging.debug("Updating Game (AppId:{})".format(args.steamid))
    logging.info("""Command:
  {}
    +@sSteamCmdForcePlatformType windows
    +login {}
    +force_install_dir {}
    +app_update {} -beta {} validate
    +quit""".format(
      steamcmd, args.account, args.gamedir, args.steamid, branch))
    cmdline = [
        steamcmd,
        "+@sSteamCmdForcePlatformType", "windows",
        "+login", args.account,
        "+force_install_dir", args.gamedir,
        "+app_update", args.steamid,
        "-beta", branch,
        "validate",
        "+quit"
    ]
    subproc.call(cmdline)


def check_args_errors():
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
    args.steamid = str(AppId.game[game])
    if not args.prefixdir:
        args.prefixdir = Dir.default_prefixdir[game]
    if not args.gamedir:
        args.gamedir = Dir.default_gamedir[game]

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
            if (args.prefixdir == Dir.default_prefixdir["ats"]
               or args.prefixdir == Dir.default_prefixdir["ets2"]):
                logging.debug("""prefixdir is the default while using wine,
make sure it uses the same folder as proton""")
                args.prefixdir = os.path.join(args.prefixdir, "pfx")

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
            args.account = get_current_steam_user()
        if not args.account:
            logging.info("Unable to find logged in steam user automatically.")
            sys.exit("Need the steam account name (-n name) to update.")

    # info
    logging.info("AppId/GameId: {} ({})".format(args.steamid, game))
    logging.info("Game directory: " + args.gamedir)
    logging.info("Prefix: " + args.prefixdir)
    if args.proton:
        logging.info("Proton directory: " + args.protondir)


def create_arg_parser():
    """Create ArgumentParser for this program."""
    desc = """
truckersmp-cli is an easy to use script to download TruckersMP and start
the game afterwards.
It can install and update the windows version of
American Truck Simulator (-a, --ats) or Euro Truck Simulator 2 (-e, --ets2)
with steamcmd (-u, --update) and handles starting (-s, --start) the mod
through Proton aka. Steam Play (-p, --proton) or Wine (-w, --wine).
It needs a working Steam installation for starting through Proton or to update
the game files. It will stop all running Steam processes while updating to
prevent Steam asking for password and guard code at the next startup.
When using standard Wine you should start the windows version of Steam first.
"""
    epilog = "Proton AppId list:\n"
    for k, v in AppId.proton.items():
        default_mark = ""
        if k == AppId.proton["default"]:
            default_mark += " (Default)"
        if k != "default":
            epilog += "    Proton {:13}: {:>10}{}\n".format(k, v, default_mark)
    ap = argparse.ArgumentParser(
      description=desc, epilog=epilog,
      formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
      "-a", "--ats",
      help="use American Truck Simulator", action="store_true")
    ap.add_argument(
      "-e", "--ets2",
      help="""use Euro Truck Simulator 2
              [Default if neither ATS or ETS2 are specified] """,
      action="store_true")
    ap.add_argument(
      "-p", "--proton",
      help="""start the game with Proton
              [Default on Linux if neither Proton or Wine are specified] """,
      action="store_true")
    ap.add_argument(
      "-w", "--wine",
      help="""start the game with Wine
              [Default on other systems if neither Proton or Wine are specified]""",
      action="store_true")
    ap.add_argument(
      "-s", "--start",
      help="""start the game
              [Default if neither start or update are specified]""",
      action="store_true")
    ap.add_argument(
      "-u", "--update",
      help="""update the game
              [Default if neither start or update are specified]""",
      action="store_true")
    ap.add_argument(
      "-v", "--verbose",
      help="verbose output (none:error, once:info, twice or more:debug)",
      action="count")
    ap.add_argument(
      "-g", "--gamedir", metavar="DIR", type=str,
      help="""choose a different directory for the game files
              [Default: $XDG_DATA_HOME/truckersmp-cli/(Game name)/data]""")
    ap.add_argument(
      "-i", "--proton-appid", metavar="APPID", type=int,
      default=AppId.proton[AppId.proton["default"]],
      help="""choose a different AppId for Proton (Needs an update for changes)
              [Default: {}]""".format(AppId.proton[AppId.proton["default"]]))
    ap.add_argument(
      "-m", "--moddir", metavar="DIR", type=str,
      help="""choose a different directory for the mod files
              [Default: $XDG_DATA_HOME/truckersmp-cli/TruckersMP,
              Fallback: ./truckersmp]""")
    ap.add_argument(
      "-n", "--account", metavar="NAME", type=str,
      help="""steam account name to use
              (This account should own the game and ideally is logged in
              with saved credentials)""")
    ap.add_argument(
      "-o", "--protondir", metavar="DIR", type=str,
      default=Dir.default_protondir,
      help="""choose a different Proton directory
              [Default: $XDG_DATA_HOME/truckersmp-cli/Proton]
              While updating any previous version in this folder gets changed
              to the given (-i) or default Proton version""")
    ap.add_argument(
      "-l", "--logfile", metavar="LOG", type=str,
      default="",
      help="""write log into LOG, "-vv" option is recommended
              [Default: Empty string (only stderr)]
              Note: Messages from Steam/steamcmd won't be written,
              only from this script (Game logs are written into
              "My Documents/{ETS2,ATS}MP/logs/client_*.log")""")
    ap.add_argument(
      "-x", "--prefixdir", metavar="DIR", type=str,
      help="""choose a different directory for the prefix
              [Default: $XDG_DATA_HOME/truckersmp-cli/(Game name)/prefix]""")
    ap.add_argument(
      "-c", "--activate-native-d3dcompiler-47",
      help="""activate native 64-bit d3dcompiler_47.dll when starting
              (Needed for D3D11 renderer)""",
      action="store_true")
    ap.add_argument(
      "--use-wined3d",
      help="use OpenGL-based D3D11 instead of DXVK when using Proton",
      action="store_true")
    ap.add_argument(
      "--enable-d3d11",
      help="use Direct3D 11 instead of OpenGL",
      action="store_true")
    ap.add_argument(
      "--disable-proton-overlay",
      help="disable Steam Overlay when using Proton",
      action="store_true")
    ap.add_argument(
      "--beta", metavar="VERSION", type=str,
      help="""set game version to VERSION,
              useful for downgrading (e.g. "temporary_1_35")""")
    ap.add_argument(
      "--singleplayer",
      help="""start singleplayer game, useful for save editing,
              using/testing DXVK in singleplayer, etc.""",
      action="store_true")

    return ap


def main():
    """truckersmp-cli main function."""
    global args

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    locale.setlocale(locale.LC_MESSAGES, "")
    locale.setlocale(locale.LC_TIME, "C")

    # load Proton AppId info from "proton.json":
    #     {"X.Y": AppId, ... , "default": "X.Y"}
    # example:
    #     {"5.0": 1245040, "4.11": 1113280, "default": "5.0"}
    try:
        with open(File.proton_json) as f:
            AppId.proton = json.load(f)
    except Exception as e:
        sys.exit("Failed to load proton.json: {}".format(e))

    # parse options
    arg_parser = create_arg_parser()
    args = arg_parser.parse_args()

    # initialize logging
    formatter = logging.Formatter("** {levelname} **  {message}", style="{")
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    logger = logging.getLogger()
    if args.verbose:
        logger.setLevel(logging.INFO if args.verbose == 1 else logging.DEBUG)
    logger.addHandler(stderr_handler)
    if args.logfile != "":
        file_handler = logging.FileHandler(args.logfile, mode="w")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # fallback to old local folder
    if not args.moddir:
        if os.path.isdir(os.path.join(Dir.scriptdir, "truckersmp")):
            logging.debug("No moddir set and fallback found")
            args.moddir = os.path.join(Dir.scriptdir, "truckersmp")
        else:
            logging.debug("No moddir set, setting to default")
            args.moddir = Dir.default_moddir
    logging.info("Mod directory: " + args.moddir)

    # check for errors
    check_args_errors()

    # download/update ATS/ETS2 and Proton
    if args.update:
        logging.debug("Updating game files")
        update_game()

    # update truckersmp when starting multiplayer
    if not args.singleplayer:
        logging.debug("Updating mod files")
        update_mod()

    # start truckersmp with proton or wine
    if args.start:
        if not check_libsdl2():
            sys.exit("SDL2 was not found on your system.")
        start_functions = (("Proton", start_with_proton), ("Wine", start_with_wine))
        i = 0 if args.proton else 1
        compat_tool, start_game = start_functions[i]
        logging.debug("Starting game with {}".format(compat_tool))
        start_game()

    sys.exit()
