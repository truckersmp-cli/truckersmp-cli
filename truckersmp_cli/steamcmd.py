"""
SteamCMD handler for truckersmp-cli main script.

Licensed under MIT.
"""

import io
import logging
import os
import platform
import subprocess as subproc
import sys
import tarfile
import urllib.parse
import urllib.request
from zipfile import ZipFile

from .truckersmp import determine_game_branch
from .utils import check_steam_process
from .variables import Args, Dir, URL


def update_game():
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
    # pylint: disable=too-many-branches,too-many-statements

    steamcmd_prolog = ""
    steamcmd_cmd = []

    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEARCH"] = "win64"
    env_steam = env.copy()
    if Args.proton:
        # Proton's "prefix" is for STEAM_COMPAT_DATA_PATH that contains
        # the directory "pfx" for WINEPREFIX
        env_steam["WINEPREFIX"] = os.path.join(Args.prefixdir, "pfx")
    else:
        env_steam["WINEPREFIX"] = Args.prefixdir
    # use a prefix only for SteamCMD to avoid every-time authentication
    env["WINEPREFIX"] = Dir.steamcmdpfx
    # don't show "The Wine configuration is being updated" dialog
    # or install Gecko/Mono
    env["WINEDLLOVERRIDES"] = "winex11.drv="

    wine = env["WINE"] if "WINE" in env else "wine"
    os.makedirs(Dir.steamcmdpfx, exist_ok=True)
    if Args.check_windows_steam:
        try:
            subproc.check_call((wine, "--version"), stdout=subproc.DEVNULL, env=env)
            logging.debug("Wine (%s) is available", wine)
        except subproc.CalledProcessError:
            logging.debug("Wine is not available")
            wine = None
    if Args.proton:
        # we don't use system SteamCMD because something goes wrong in some cases
        # see https://github.com/lhark/truckersmp-cli/issues/43
        steamcmd = os.path.join(Dir.steamcmddir, "steamcmd.sh")
        steamcmd_url = URL.steamcmdlnx
        gamedir = Args.gamedir
    else:
        if not wine:
            sys.exit("Wine ({}) is not available.".format(wine))
        steamcmd_prolog += """WINEDEBUG=-all
  WINEARCH=win64
  WINEPREFIX={}
  WINEDLLOVERRIDES=winex11.drv=
  {} """.format(Dir.steamcmdpfx, wine)

        # steamcmd.exe uses Windows path, not UNIX path
        try:
            gamedir = subproc.check_output(
                (wine, "winepath", "-w", Args.gamedir), env=env).decode("utf-8").rstrip()
        except (OSError, subproc.CalledProcessError) as ex:
            sys.exit(
                "Failed to convert game directory to Windows path: {}".format(ex))

        steamcmd = os.path.join(Dir.steamcmddir, "steamcmd.exe")
        steamcmd_cmd.append(wine)
        steamcmd_url = URL.steamcmdwin
    steamcmd_cmd.append(steamcmd)

    # fetch SteamCMD if not in our data directory
    os.makedirs(Dir.steamcmddir, exist_ok=True)
    if not os.path.isfile(steamcmd):
        logging.debug("Retrieving SteamCMD")
        try:
            with urllib.request.urlopen(steamcmd_url) as f_in:
                steamcmd_archive = f_in.read()
        except OSError as ex:
            sys.exit("Failed to retrieve SteamCMD: {}".format(ex))
        logging.debug("Extracting SteamCMD")
        try:
            if Args.proton:
                with tarfile.open(
                        fileobj=io.BytesIO(steamcmd_archive), mode="r:gz") as f_in:
                    f_in.extractall(Dir.steamcmddir)
            else:
                with ZipFile(io.BytesIO(steamcmd_archive)) as f_in:
                    with f_in.open("steamcmd.exe") as f_exe:
                        with open(steamcmd, "wb") as f_out:
                            f_out.write(f_exe.read())
        except (OSError, tarfile.TarError) as ex:
            sys.exit("Failed to extract SteamCMD: {}".format(ex))

    logging.info("SteamCMD: %s", steamcmd)

    # Linux version of Steam
    if platform.system() == "Linux" and check_steam_process(use_proton=True):
        logging.debug("Closing Linux version of Steam")
        subproc.call(("steam", "-shutdown"))
    # Windows version of Steam
    if (Args.check_windows_steam
            and wine
            and check_steam_process(use_proton=False, wine=wine, env=env_steam)):
        logging.debug("Closing Windows version of Steam in %s", Args.wine_steam_dir)
        subproc.call(
            (wine, os.path.join(Args.wine_steam_dir, "steam.exe"), "-shutdown"),
            env=env_steam)

    if Args.proton:
        # download/update Proton
        os.makedirs(Args.protondir, exist_ok=True)
        logging.debug("Updating Proton (AppID:%s)", Args.proton_appid)
        logging.info(
            """Command:
  %s
    +login %s
    +force_install_dir %s
    +app_update %s validate
    +quit""",
            steamcmd, Args.account, Args.protondir, Args.proton_appid)
        try:
            subproc.check_call(
                (steamcmd,
                 "+login", Args.account,
                 "+force_install_dir", Args.protondir,
                 "+app_update", str(Args.proton_appid), "validate",
                 "+quit"))
        except subproc.CalledProcessError:
            sys.exit("SteamCMD exited abnormally")

    # determine game branch
    branch = determine_game_branch()
    logging.info("Game branch: %s", branch)

    # use SteamCMD to update the chosen game
    os.makedirs(Args.gamedir, exist_ok=True)
    logging.debug("Updating Game (AppID:%s)", Args.steamid)
    logging.info(
        """Command:
  %s%s
    +@sSteamCmdForcePlatformType windows
    +login %s
    +force_install_dir %s
    +app_update %s -beta %s validate
    +quit""",
        steamcmd_prolog, steamcmd, Args.account, gamedir, Args.steamid, branch)
    steamcmd_args = [
        "+@sSteamCmdForcePlatformType", "windows",
        "+login", Args.account,
        "+force_install_dir", gamedir,
        "+app_update", Args.steamid,
        "-beta", branch,
        "validate",
        "+quit",
    ]
    try:
        subproc.check_call(steamcmd_cmd + steamcmd_args, env=env)
    except subproc.CalledProcessError:
        sys.exit("SteamCMD exited abnormally")
