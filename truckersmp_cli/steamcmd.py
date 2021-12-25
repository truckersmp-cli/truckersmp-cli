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
from .variables import AppId, Args, Dir, URL


class SteamCMD:
    """SteamCMD command."""

    def __init__(self, path, wine=None, env=None):
        """
        Initialize SteamCMD object.

        path: Path to "steamcmd.sh" or "steamcmd.exe"
        wine: Path to "wine" command (can be None when native SteamCMD is used)
        env: "env" argument for subprocess.Popen
        """
        self._path = path
        self._wine = wine
        self._env = env

    @staticmethod
    def download_steamcmd(dest, url):
        """
        Download SteamCMD if it doesn't exist in our data directory.

        dest: SteamCMD destination path
        url: SteamCMD download URL
        """
        os.makedirs(Dir.steamcmddir, exist_ok=True)
        if not os.path.isfile(dest):
            logging.debug("Retrieving SteamCMD")
            try:
                with urllib.request.urlopen(url) as f_in:
                    archive = f_in.read()
            except OSError as ex:
                sys.exit(f"Failed to retrieve SteamCMD: {ex}")
            logging.debug("Extracting SteamCMD")
            try:
                if Args.proton:
                    with tarfile.open(
                            fileobj=io.BytesIO(archive), mode="r:gz") as f_in:
                        f_in.extractall(Dir.steamcmddir)
                else:
                    with ZipFile(io.BytesIO(archive)) as f_in:
                        with f_in.open("steamcmd.exe") as f_exe:
                            with open(dest, "wb") as f_out:
                                f_out.write(f_exe.read())
            except (OSError, tarfile.TarError) as ex:
                sys.exit(f"Failed to extract SteamCMD: {ex}")
        logging.info("SteamCMD: %s", dest)

    @staticmethod
    def install_via_steamcmd(steamcmd_path, gamedir, wine, env):
        """
        Install Proton, Steam Runtime, and the specified game via SteamCMD.

        steamcmd_path: Path to SteamCMD
        gamedir: Game directory
                 (DOS/Windows style path when using Wine, otherwise UNIX style path)
        wine: Wine command, not used when using Proton
        env: A dict of environment variables for Wine, not used when using Proton
        """
        steamcmd = SteamCMD(
            steamcmd_path,
            wine=wine if not Args.proton else None,
            env=env if not Args.proton else None,
        )

        if Args.proton:
            if Args.skip_update_proton:
                logging.info("Skipping updating Proton and Steam Runtime")
            else:
                if not Args.disable_steamruntime:
                    # download/update Steam Runtime and Proton
                    os.makedirs(Args.steamruntimedir, exist_ok=True)
                    # Proton and Steam Linux Runtime work only on Linux systems
                    appid_steamruntime = AppId.steamruntime["Linux"]
                    logging.debug("Updating Steam Runtime (AppID:%s)", appid_steamruntime)
                    steamcmd.run(
                        [
                            "+force_install_dir", Args.steamruntimedir,
                            "+login", "anonymous",
                            "+app_update", str(appid_steamruntime), "validate",
                            "+quit",
                        ]
                    )
                os.makedirs(Args.protondir, exist_ok=True)
                logging.debug("Updating Proton (AppID:%s)", Args.proton_appid)
                steamcmd.run(
                    [
                        "+force_install_dir", Args.protondir,
                        "+login", "anonymous",
                        "+app_update", str(Args.proton_appid), "validate",
                        "+quit",
                    ]
                )

        # determine game branch
        branch = determine_game_branch()
        logging.info("Game branch: %s", branch)

        # use SteamCMD to update the chosen game
        os.makedirs(Args.gamedir, exist_ok=True)
        logging.debug("Updating Game (AppID:%s)", Args.steamid)
        steamcmd.run(
            [
                "+@sSteamCmdForcePlatformType", "windows",
                "+force_install_dir", gamedir,
                "+login", Args.account,
                "+app_update", Args.steamid, "-beta", branch, "validate",
                "+quit",
            ]
        )

    def run(self, args):
        """
        Run SteamCMD using given command line.

        When it fails, sys.exit() is called and the program exits abnormally.
        args: SteamCMD arguments (list)
        """
        cmdline = []
        if self._wine is not None:
            cmdline.append(self._wine)
        cmdline.append(self._path)
        if Args.download_throttle > 0:
            cmdline += ["+set_download_throttle", str(Args.download_throttle)]
        cmdline += args
        env_str = ""
        if self._env is not None:
            env_print = ("WINEDEBUG", "WINEARCH", "WINEPREFIX", "WINEDLLOVERRIDES")
            name_value_pairs = []
            for name in env_print:
                name_value_pairs.append(f"{name}={self._env[name]}")
            env_str += "\n  ".join(name_value_pairs) + "\n  "
        cmd_str = ""
        for i, arg in enumerate(cmdline):
            if arg.startswith("+"):
                # add newline before SteamCMD commands (e.g. "+login")
                cmd_str += "\n    "
            elif i > 0:
                cmd_str += " "
            cmd_str += arg
        logging.info("Running SteamCMD:\n  %s%s", env_str, cmd_str)

        try:
            subproc.check_call(cmdline, env=self._env)
        except subproc.CalledProcessError:
            sys.exit("SteamCMD exited abnormally")


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
    env = os.environ.copy()
    env.update(WINEDEBUG="-all", WINEARCH="win64")
    env_steam = env.copy()
    # Proton's "prefix" is for STEAM_COMPAT_DATA_PATH that contains
    # the directory "pfx" for WINEPREFIX
    env_steam["WINEPREFIX"] = os.path.join(Args.prefixdir, "pfx") if Args.proton \
        else Args.prefixdir
    env.update(
        # use a prefix only for SteamCMD to avoid every-time authentication
        WINEPREFIX=Dir.steamcmdpfx,
        # don't show "The Wine configuration is being updated" dialog
        # or install Gecko/Mono
        WINEDLLOVERRIDES="winex11.drv=",
    )

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
        # see https://github.com/truckersmp-cli/truckersmp-cli/issues/43
        steamcmd_path = os.path.join(Dir.steamcmddir, "steamcmd.sh")
        steamcmd_url = URL.steamcmdlnx
        gamedir = Args.gamedir
    else:
        if not wine:
            sys.exit(f"Wine ({wine}) is not available.")

        # steamcmd.exe uses Windows path, not UNIX path
        try:
            gamedir = subproc.check_output(
                (wine, "winepath", "-w", Args.gamedir), env=env).decode("utf-8").rstrip()
        except (OSError, subproc.CalledProcessError) as ex:
            sys.exit(f"Failed to convert game directory to Windows path: {ex}")

        steamcmd_path = os.path.join(Dir.steamcmddir, "steamcmd.exe")
        steamcmd_url = URL.steamcmdwin

    # fetch SteamCMD if not in our data directory
    SteamCMD.download_steamcmd(steamcmd_path, steamcmd_url)

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

    # install via SteamCMD
    SteamCMD.install_via_steamcmd(steamcmd_path, gamedir, wine, env)
