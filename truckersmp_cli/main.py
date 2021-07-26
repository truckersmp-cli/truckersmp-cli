"""
Main module for truckersmp-cli main script.

Licensed under MIT.
"""

import json
import logging
import os
import shutil
import signal
import subprocess as subproc
import sys
import tempfile
import time

from .args import check_args_errors, create_arg_parser, process_actions_gamenames
from .configfile import ConfigFile
from .steamcmd import update_game
from .truckersmp import update_mod
from .utils import (
    activate_native_d3dcompiler_47, check_libsdl2, find_discord_ipc_sockets,
    get_proton_version, get_steam_library_dirs, is_d3dcompiler_setup_skippable,
    log_info_formatted_envars_and_args, perform_self_update, print_child_output,
    set_wine_desktop_registry, setup_wine_discord_ipc_bridge, wait_for_steam,
)
from .variables import AppId, Args, Dir, File, URL

PKG_RESOURCES_IS_AVAILABLE = False
try:
    import pkg_resources
    PKG_RESOURCES_IS_AVAILABLE = True
except ImportError:
    pass


class GameStarterInterface:
    """The interface of game starter classes."""

    def run(self):
        """Start the specified game."""
        raise NotImplementedError

    @property
    def runner_name(self):
        """Return the name of runner (Wine or Proton)."""
        raise NotImplementedError


class StarterProton(GameStarterInterface):
    """A game starter that uses Proton."""

    def __init__(self, cfg):
        """
        Initialize StarterProton object.

        cfg: A ConfigFile object
        """
        self._cfg = cfg
        self._steamruntime_usr_tempdir = None
        self._discord_sockets = find_discord_ipc_sockets()

        major, minor = get_proton_version(Args.protondir)
        logging.info("Proton version is (major=%d, minor=%d)", major, minor)
        self._use_steam_runtime = (
            not Args.without_steam_runtime
            and (major >= 6 or (major == 5 and minor >= 13)))
        logging.info(
            # use Steam Runtime container for Proton 5.13+
            "Using Steam Runtime container" if self._use_steam_runtime
            # don't use Steam Runtime container for older Proton
            else "Not using Steam Runtime container")

    def _cleanup(self):
        """Do cleanup tasks."""
        # cleanup temporary directory when used
        if self._steamruntime_usr_tempdir is not None:
            with self._steamruntime_usr_tempdir:
                pass

    def _determine_steamruntime_shared_paths(self, steamdir):
        """
        Determine and return paths that are shared with Steam Runtime.

        steamdir: Path to Steam installation
        """
        # pylint: disable=consider-using-with

        if not self._use_steam_runtime:
            return []

        # share directories with Steam Runtime container
        shared_paths = [Args.gamedir, Args.protondir, Args.prefixdir]
        if Args.singleplayer:
            # workshop mods may be loaded from other steam libraries
            # despite they are also present in our gamedir library
            shared_paths += get_steam_library_dirs(steamdir)
        else:
            shared_paths += Args.moddir, Dir.truckersmp_cli_data
        if Dir.scriptdir.startswith("/usr/"):
            logging.info("System-wide installation detected: %s", Dir.scriptdir)
            # when truckersmp-cli is installed system-wide,
            # the Steam Runtime helper (singleplayer/multiplayer) and
            # the inject program (multiplayer) need to be
            # temporarily copied because /usr cannot be shared
            self._steamruntime_usr_tempdir = tempfile.TemporaryDirectory(
                prefix="truckersmp-cli-steamruntime-sharing-workaround-")
            logging.debug(
                "Copying Steam Runtime helper to %s",
                self._steamruntime_usr_tempdir.name)
            shutil.copy(
                File.steamruntime_helper, self._steamruntime_usr_tempdir.name)
            if not Args.singleplayer:
                logging.debug(
                    "Copying inject program to %s", self._steamruntime_usr_tempdir.name)
                shutil.copy(File.inject_exe, self._steamruntime_usr_tempdir.name)
            shared_paths.append(self._steamruntime_usr_tempdir.name)
        else:
            shared_paths.append(Dir.scriptdir)
        if len(self._discord_sockets) > 0:
            shared_paths += self._discord_sockets
        logging.debug("Shared paths: %s", shared_paths)
        return shared_paths

    def _init_args(self, args, steamdir):
        """
        Initialize command line arguments (for Wine, Proton, and Steam Runtime).

        args: A dict for arguments
        steamdir: Path to Steam installation
        """
        if self._use_steam_runtime:
            python = "python3"
            args["steamrt"].append(os.path.join(Args.steamruntimedir, "run"))
            shared_paths = self._determine_steamruntime_shared_paths(steamdir)
            for shared_path in shared_paths:
                args["steamrt"] += "--filesystem", shared_path
            args["steamrt"].append("--")
        else:
            python = sys.executable
        args["wine"] = args["steamrt"].copy()
        args["steamrt"].append(python)  # helper
        args["proton"].append(python)   # Proton
        args["proton"] += os.path.join(Args.protondir, "proton"), "run"

    def _setup_helper_args(self, args):
        """
        Set up command line for running the Steam Runtime helper.

        args: Command line for executing Steam Runtime
        """
        args.append(
            File.steamruntime_helper if self._steamruntime_usr_tempdir is None
            else os.path.join(
                self._steamruntime_usr_tempdir.name,
                os.path.basename(File.steamruntime_helper)))
        if (not Args.singleplayer
                and not Args.without_wine_discord_ipc_bridge
                # don't start wine-discord-ipc-bridge when no Discord sockets found
                and len(self._discord_sockets) > 0):
            args += "--executable", File.ipcbridge
        for executable in self._cfg.thirdparty_executables:
            args += "--executable", executable
        args += "--wait-before-start", str(self._cfg.thirdparty_wait)
        if Args.verbose:
            args.append("-v" if Args.verbose == 1 else "-vv")
        return args

    def _setup_proton_args(self, proton_args):
        """
        Set up command line for running the game with Proton.

        proton_args: A list of command line for Proton
        """
        # check whether singleplayer or multiplayer
        if Args.singleplayer:
            exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
            gamepath = os.path.join(Args.gamedir, "bin/win_x64", exename)
            proton_args.append(gamepath)
        else:
            proton_args.append(
                File.inject_exe if self._steamruntime_usr_tempdir is None
                else os.path.join(
                    self._steamruntime_usr_tempdir.name,
                    os.path.basename(File.inject_exe))
            )
            proton_args += Args.gamedir, Args.moddir

        # game options
        for opt in Args.game_options.split(" "):
            if opt != "":
                proton_args.append(opt)

    def run(self):
        """Start the specified game with Proton."""
        args = dict(wine=[], proton=[], steamrt=[])
        prefix = os.path.join(Args.prefixdir, "pfx")
        env = os.environ.copy()
        steamdir = wait_for_steam(use_proton=True, loginvdf_paths=File.loginusers_paths)
        logging.info("Steam installation directory: %s", steamdir)

        logging.debug("Creating directory %s if it doesn't exist", Args.prefixdir)
        os.makedirs(Args.prefixdir, exist_ok=True)

        env["STEAM_COMPAT_DATA_PATH"] = Args.prefixdir
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steamdir

        self._init_args(args, steamdir)

        do_d3dcompiler_setup = (Args.activate_native_d3dcompiler_47
                                or (not Args.singleplayer
                                    and Args.enable_d3d11
                                    and not is_d3dcompiler_setup_skippable()))
        logging.debug("Whether to setup native d3dcompiler_47: %s", do_d3dcompiler_setup)

        # Proton's "dist" directory tree is missing until first run
        # make sure it's present for using "dist/bin/wine" directly
        wine_command = os.path.join(
            Args.protondir,
            # if proton-tkg (files/bin/wine) is installed, use it
            "files" if os.access(
                os.path.join(Args.protondir, "files/bin/wine"),
                os.R_OK | os.X_OK,
            ) else "dist",
            "bin/wine")
        args["wine"].append(wine_command)

        if (not os.access(wine_command, os.R_OK)
                # native d3dcompiler_47 is removed when the prefix is downgraded
                # make sure the prefix is already upgraded/downgraded
                or do_d3dcompiler_setup):
            try:
                subproc.check_output(
                    args["proton"] + ["wineboot", ], env=env, stderr=subproc.STDOUT)
            except OSError as ex:
                sys.exit("Failed to run wineboot: {}".format(ex))
            except subproc.CalledProcessError as ex:
                sys.exit("wineboot failed:\n{}".format(ex.output.decode("utf-8")))

        # activate native d3dcompiler_47
        if do_d3dcompiler_setup:
            activate_native_d3dcompiler_47(prefix, args["wine"])

        # enable Wine desktop if requested
        if Args.wine_desktop:
            set_wine_desktop_registry(prefix, args["wine"], True)

        setup_game_env(env, steamdir)
        self._setup_proton_args(args["proton"])

        log_info_formatted_envars_and_args(
            runner="Steam Runtime helper",
            env_print=determine_env_print(env),
            env=env,
            args=args["proton"])
        try:
            with subproc.Popen(
                    self._setup_helper_args(args["steamrt"])
                    + ["--", ] + args["proton"],
                    env=env, stdout=subproc.PIPE, stderr=subproc.STDOUT) as proc:
                if Args.verbose:
                    print_child_output(proc)
        except subproc.CalledProcessError as ex:
            logging.error(
                "Steam Runtime helper exited abnormally:\n%s", ex.output.decode("utf-8"))

        # disable Wine desktop if enabled
        if Args.wine_desktop:
            set_wine_desktop_registry(prefix, args["wine"], False)

        self._cleanup()

    @property
    def runner_name(self):
        """Return the name of runner (Proton)."""
        return "Proton"


class StarterWine(GameStarterInterface):
    """A game starter that uses Wine."""

    def __init__(self, cfg):
        """
        Initialize StarterWine object.

        cfg: A ConfigFile object
        """
        self._cfg = cfg
        self._thirdparty_processes = []

    def _cleanup(self):
        """Do cleanup tasks."""
        for proc in self._thirdparty_processes:
            with proc:
                if proc.poll() is None:
                    proc.kill()
                proc.wait()

    def run(self):
        """Start the specified game with Wine."""
        # pylint: disable=consider-using-with

        env = os.environ.copy()
        env["WINEDEBUG"] = "-all"
        env["WINEARCH"] = "win64"
        env["WINEPREFIX"] = Args.prefixdir
        wine_command = os.getenv("WINE", "wine")
        wine_args = [wine_command, ]

        if (Args.activate_native_d3dcompiler_47
                or (not Args.singleplayer
                    and Args.enable_d3d11
                    and not is_d3dcompiler_setup_skippable())):
            activate_native_d3dcompiler_47(Args.prefixdir, wine_args)

        wait_for_steam(
            use_proton=False,
            loginvdf_paths=(os.path.join(Args.wine_steam_dir, File.loginvdf_inner), ),
            wine=wine_command,
            env=env,
        )

        executables = self._cfg.thirdparty_executables.copy()
        if not Args.singleplayer and not Args.without_wine_discord_ipc_bridge:
            executables.append(setup_wine_discord_ipc_bridge())

        for path in executables:
            self._thirdparty_processes.append(
                subproc.Popen(
                    [wine_command, ] + [path, ], env=env, stderr=subproc.STDOUT))

        time.sleep(self._cfg.thirdparty_wait)

        if "WINEDLLOVERRIDES" not in env:
            env["WINEDLLOVERRIDES"] = ""
        if not Args.enable_d3d11:
            env["WINEDLLOVERRIDES"] += ";d3d11=;dxgi="

        if Args.wine_desktop:
            wine_args += "explorer", "/desktop=TruckersMP,{}".format(
                Args.wine_desktop)
        if Args.singleplayer:
            exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
            gamepath = os.path.join(Args.gamedir, "bin/win_x64", exename)
            wine_args.append(gamepath)
        else:
            wine_args += File.inject_exe, Args.gamedir, Args.moddir

        for opt in Args.game_options.split(" "):
            if opt != "":
                wine_args.append(opt)

        log_info_formatted_envars_and_args(
            runner="Wine",
            env_print=("WINEARCH", "WINEDEBUG", "WINEDLLOVERRIDES", "WINEPREFIX"),
            env=env,
            args=wine_args)
        try:
            with subproc.Popen(
                    wine_args,
                    env=env, stdout=subproc.PIPE, stderr=subproc.STDOUT) as proc:
                if Args.verbose:
                    print("Wine output:")
                    print_child_output(proc)
        except subproc.CalledProcessError as ex:
            logging.error("Wine output:\n%s", ex.output.decode("utf-8"))

        self._cleanup()

    @property
    def runner_name(self):
        """Return the name of runner (Wine)."""
        return "Wine"


def determine_env_print(env):
    """
    Determine environment variable names to print.

    env: A dict of environment variables
    """
    env_print = ["SteamAppId", "SteamGameId"]
    if "LD_PRELOAD" in env:
        env_print.append("LD_PRELOAD")
    env_print += [
        "PROTON_NO_D3D11",
        "PROTON_USE_WINED3D",
        "STEAM_COMPAT_CLIENT_INSTALL_PATH",
        "STEAM_COMPAT_DATA_PATH",
    ]
    return env_print


def get_version_string():
    """
    Get the version of this program and return it in string format.

    This first tries to load "RELEASE" file
    for GitHub release assets or cloned git repo directory.
    If succeeded, it additionally tries to get git commit hash and append it.
    Otherwise, it tries to get version from Python package
    only when "pkg_resources" module is available.
    If the version is still unknown, this returns "unknown".
    """
    version = ""
    try:
        # try to load "RELEASE" file for release assets or cloned git directory
        with open(os.path.join(os.path.dirname(Dir.scriptdir), "RELEASE")) as f_in:
            version += f_in.readline().rstrip()
    except OSError:
        pass
    if version:
        try:
            # try to get git commit hash, and append it if succeeded
            version += subproc.check_output(
                ("git", "log", "-1", "--format= (%h)")).decode("utf-8").rstrip()
        except (OSError, subproc.CalledProcessError):
            pass
    else:
        # try to get version from Python package
        try:
            if PKG_RESOURCES_IS_AVAILABLE:
                version += pkg_resources.get_distribution(__package__).version
        except pkg_resources.DistributionNotFound:
            pass
    return version if version else "unknown"


def main():
    """truckersmp-cli main function."""
    # pylint: disable=too-many-branches,too-many-statements
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # load Proton AppID info from "proton.json":
    #     {"X.Y": AppID, ... , "default": "X.Y"}
    # example:
    #     {"5.0": 1245040, "4.11": 1113280, "default": "5.0"}
    try:
        with open(File.proton_json) as f_in:
            AppId.proton = json.load(f_in)
    except (OSError, ValueError) as ex:
        sys.exit("Failed to load proton.json: {}".format(ex))

    # load Steam Runtime AppID info from "steamruntime.json":
    #     {"platform": AppID, ... }
    # example:
    #     {"Linux": 1391110}
    try:
        with open(File.steamruntime_json) as f_in:
            AppId.steamruntime = json.load(f_in)
    except (OSError, ValueError) as ex:
        sys.exit("Failed to load steamruntime.json: {}".format(ex))

    # parse options
    arg_parser = create_arg_parser()[0]
    arg_parser.parse_args(namespace=Args)
    process_actions_gamenames()

    # load configuration file
    cfg = ConfigFile(Args.configfile)

    # print version
    if Args.version:
        print(get_version_string())
        sys.exit()

    # check whether the executable of our inject program is present
    if not os.access(File.inject_exe, os.R_OK):
        sys.exit("""DLL inject program ("{}") is missing.

Try one of the following:
* Install truckersmp-cli via pip [RECOMMENDED]
  (e.g. "python3 -m pip install --user truckersmp-cli[optional]")
  and run it (e.g. "~/.local/bin/truckersmp-cli [ARGUMENTS...]")
* Download GitHub release file from "{}", unpack it, and run
  the "truckersmp-cli" script in the unpacked directory
* Build "truckersmp-cli.exe" with mingw-w64, put it into "{}",
  and run this script again

See {} for additional information.""".format(
            File.inject_exe, URL.project_releases, Dir.scriptdir, URL.project_doc_inst))

    # set up logging
    setup_logging()

    # self update
    if Args.self_update:
        perform_self_update()
        sys.exit()

    # fallback to old local folder
    if not Args.moddir:
        old_local_moddir = os.path.join(Dir.scriptdir, "truckersmp")
        if (os.path.isdir(old_local_moddir)
                and os.access(old_local_moddir, os.R_OK | os.W_OK | os.X_OK)):
            logging.debug("No moddir set and fallback found")
            Args.moddir = old_local_moddir
        else:
            logging.debug("No moddir set, setting to default")
            Args.moddir = Dir.default_moddir
    logging.info("Mod directory: %s", Args.moddir)

    # check for errors
    check_args_errors()

    # download/update ATS/ETS2 and Proton
    if Args.update:
        logging.debug("Updating game files")
        update_game()

    # update truckersmp when starting multiplayer
    if not Args.singleplayer:
        logging.debug("Updating mod files")
        update_mod()

    # start truckersmp with proton or wine
    if Args.start:
        if Args.proton:
            # check for Proton availability when starting with Proton
            if not os.access(os.path.join(Args.protondir, "proton"), os.R_OK):
                sys.exit("""Proton is not found in {}
Run with '--update' option to install Proton""".format(Args.protondir))
            # check for Steam Runtime availability and the permission of "var"
            # when starting with Proton + Steam Runtime
            run = os.path.join(Args.steamruntimedir, "run")
            var = os.path.join(Args.steamruntimedir, "var")
            if not Args.without_steam_runtime:
                if not os.access(run, os.R_OK | os.X_OK):
                    sys.exit("""Steam Runtime is not found in {}
Update the game or start with "--without-steam-runtime" option
to disable the Steam Runtime""".format(
                             Args.steamruntimedir))
                if (not os.access(Args.steamruntimedir, os.R_OK | os.W_OK | os.X_OK)
                        or (os.path.isdir(var)
                            and not os.access(var, os.R_OK | os.W_OK | os.X_OK))):
                    sys.exit("""The Steam Runtime directory ({}) and
the "var" subdirectory must be writable""".format(Args.steamruntimedir))

        if not check_libsdl2():
            sys.exit("SDL2 was not found on your system.")
        starter = StarterProton(cfg) if Args.proton else StarterWine(cfg)
        logging.debug("Starting game with %s", starter.runner_name)
        starter.run()

    sys.exit()


def setup_game_env(env, steamdir):
    """
    Set up environment variables for running the game with Proton.

    env: A dict of environment variables
    steamdir: Path to Steam installation
    """
    # enable Steam Overlay by default
    if not Args.disable_proton_overlay:
        overlayrenderer = os.path.join(steamdir, File.overlayrenderer_inner)
        if "LD_PRELOAD" in env:
            env["LD_PRELOAD"] += ":" + overlayrenderer
        else:
            env["LD_PRELOAD"] = overlayrenderer
    env["SteamGameId"] = env["SteamAppId"] = Args.steamid
    env["PROTON_USE_WINED3D"] = "1" if Args.use_wined3d else "0"
    env["PROTON_NO_D3D11"] = "1" if not Args.enable_d3d11 else "0"


def setup_logging():
    """
    Set up Python logging facility.

    This function must be called after parse_args().
    """
    formatter = logging.Formatter("** {levelname} **  {message}", style="{")
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    logger = logging.getLogger()
    if Args.verbose:
        logger.setLevel(logging.INFO if Args.verbose == 1 else logging.DEBUG)
    logger.addHandler(stderr_handler)
    if Args.logfile != "":
        file_handler = logging.FileHandler(Args.logfile, mode="w")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
