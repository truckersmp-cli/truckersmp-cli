"""
Game starter for truckersmp-cli main script.

Licensed under MIT.
"""

import logging
import os
import shutil
import subprocess as subproc
import sys
import tempfile
import time

from .utils import (
    activate_native_d3dcompiler_47, find_discord_ipc_sockets,
    get_proton_version, get_steam_library_dirs, is_d3dcompiler_setup_skippable,
    log_info_formatted_envars_and_args, print_child_output,
    set_wine_desktop_registry, setup_wine_discord_ipc_bridge, wait_for_steam,
)
from .variables import Args, Dir, File


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
            not Args.disable_steamruntime
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

    def _determine_shared_paths(self, steamdir):
        """
        Determine and return paths that are shared with Steam Runtime or Flatpak.

        steamdir: Path to Steam installation
        """
        # pylint: disable=consider-using-with

        if not self._use_steam_runtime and not Args.flatpak_steam:
            return []

        # share directories with Steam Runtime container
        shared_paths = [
            Args.gamedir, Args.protondir, Args.prefixdir, Dir.truckersmp_cli_data]
        if Args.singleplayer:
            if not Args.flatpak_steam:
                # workshop mods may be loaded from other steam libraries
                # despite they are also present in our gamedir library
                shared_paths += get_steam_library_dirs(steamdir)
        else:
            shared_paths.append(Args.moddir)
        if Dir.scriptdir.startswith("/usr/"):
            logging.info("System-wide installation detected: %s", Dir.scriptdir)
            # when truckersmp-cli is installed system-wide,
            # the Steam Runtime helper (singleplayer/multiplayer) and
            # the inject program (multiplayer) need to be
            # temporarily copied because /usr cannot be shared
            self._steamruntime_usr_tempdir = tempfile.TemporaryDirectory(
                prefix="truckersmp-cli-container-sharing-workaround-")
            logging.debug(
                "Copying Steam Runtime helper to %s",
                self._steamruntime_usr_tempdir.name)
            shutil.copy(
                File.steamruntime_helper, self._steamruntime_usr_tempdir.name)
            logging.debug(
                "Copying Flatpak helper to %s", self._steamruntime_usr_tempdir.name)
            shutil.copy(
                File.flatpak_helper, self._steamruntime_usr_tempdir.name)
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
        Initialize command line arguments (for Wine, Proton, Steam Runtime, and Flatpak).

        args: A dict for arguments
        steamdir: Path to Steam installation
        """
        shared_paths = self._determine_shared_paths(steamdir)
        if self._use_steam_runtime:
            python = "python3"
            args["steamrt"].append(os.path.join(Args.steamruntimedir, "run"))
            for shared_path in shared_paths:
                args["steamrt"] += "--filesystem", shared_path
            args["steamrt"].append("--")
        else:
            python = sys.executable
        if Args.flatpak_steam:
            args["flatpak"] += "flatpak", "run", "--command=python3"
            for shared_path in shared_paths:
                args["flatpak"].append(f"--filesystem={shared_path}")
            args["flatpak"].append("com.valvesoftware.Steam")
            args["flatpak"].append(
                File.flatpak_helper if self._steamruntime_usr_tempdir is None
                else os.path.join(
                    self._steamruntime_usr_tempdir.name,
                    os.path.basename(File.flatpak_helper)))
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
        if (not Args.without_wine_discord_ipc_bridge
                # don't start wine-discord-ipc-bridge when no Discord sockets found
                and len(self._discord_sockets) > 0):
            args += "--early-executable", setup_wine_discord_ipc_bridge(), \
                "--early-wait-before-start", "5"
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
        for opt in f"-rdevice {Args.rendering_backend} {Args.game_options}".split(" "):
            if opt != "":
                proton_args.append(opt)

    @staticmethod
    def determine_env_print(env):
        """
        Determine environment variable names to print.

        env: A dict of environment variables
        """
        env_print = ["SteamAppId", "SteamGameId"]
        if "LD_PRELOAD" in env:
            env_print.append("LD_PRELOAD")
        env_print += [
            "PROTON_USE_WINED3D",
            "STEAM_COMPAT_CLIENT_INSTALL_PATH",
            "STEAM_COMPAT_DATA_PATH",
        ]
        return env_print

    @staticmethod
    def shutdown_flatpak_steam():
        """Shut down Flatpak version of Steam."""
        if not Args.flatpak_steam:
            return

        ps_output = subproc.check_output(("flatpak", "ps", "--columns=application"))
        if b"com.valvesoftware.Steam" in ps_output:
            # we need to shut down the running Flatpak version of Steam
            # and restart from flatpak_helper.py
            logging.info("Shutting down already running Steam")
            subproc.call(("flatpak", "kill", "com.valvesoftware.Steam"))

    def run(self):
        """Start the specified game with Proton."""
        args = dict(wine=[], proton=[], steamrt=[], flatpak=[])
        prefix = os.path.join(Args.prefixdir, "pfx")
        env = os.environ.copy()
        steamdir = Dir.flatpak_steamdir if Args.flatpak_steam else \
            wait_for_steam(
                use_proton=True, loginvdf_paths=File.loginusers_paths)
        logging.info("Steam installation directory: %s", steamdir)

        logging.debug("Creating directory %s if it doesn't exist", Args.prefixdir)
        os.makedirs(Args.prefixdir, exist_ok=True)

        env.update(
            STEAM_COMPAT_DATA_PATH=Args.prefixdir,
            STEAM_COMPAT_CLIENT_INSTALL_PATH=steamdir,
        )

        self._init_args(args, steamdir)

        do_d3dcompiler_setup = (Args.activate_native_d3dcompiler_47
                                or (not Args.singleplayer
                                    and Args.rendering_backend == "dx11"
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
                sys.exit(f"Failed to run wineboot: {ex}")
            except subproc.CalledProcessError as ex:
                sys.exit(f"wineboot failed:\n{ex.output.decode('utf-8')}")

        # activate native d3dcompiler_47
        if do_d3dcompiler_setup:
            activate_native_d3dcompiler_47(prefix, args["wine"])

        # enable Wine desktop if requested
        if Args.wine_desktop:
            set_wine_desktop_registry(prefix, args["wine"], True)

        StarterProton.setup_game_env(env, steamdir)
        self._setup_proton_args(args["proton"])
        StarterProton.shutdown_flatpak_steam()

        log_info_formatted_envars_and_args(
            runner="Steam Runtime helper",
            env_print=StarterProton.determine_env_print(env),
            env=env,
            args=args["proton"])
        helper_args = args["flatpak"] + self._setup_helper_args(args["steamrt"]) \
            + ["--", ] + args["proton"]
        logging.debug("Helper arguments: %s", helper_args)
        try:
            with subproc.Popen(
                    helper_args,
                    env=env, stdout=subproc.PIPE, stderr=subproc.STDOUT) as proc:
                if Args.verbose:
                    print_child_output(proc)
                proc.wait()
        except subproc.CalledProcessError as ex:
            logging.error(
                "Steam Runtime helper exited abnormally:\n%s", ex.output.decode("utf-8"))

        # disable Wine desktop if enabled
        if Args.wine_desktop:
            set_wine_desktop_registry(prefix, args["wine"], False)

        self._cleanup()

    @staticmethod
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
        env.update(
            SteamAppId=Args.steamid,
            SteamGameId=Args.steamid,
            PROTON_USE_WINED3D="1" if Args.use_wined3d else "0",
        )

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
        env.update(WINEDEBUG="-all", WINEARCH="win64", WINEPREFIX=Args.prefixdir)
        wine_command = os.getenv("WINE", "wine")
        wine_args = [wine_command, ]

        if (Args.activate_native_d3dcompiler_47
                or (not Args.singleplayer
                    and Args.rendering_backend == "dx11"
                    and not is_d3dcompiler_setup_skippable())):
            activate_native_d3dcompiler_47(Args.prefixdir, wine_args)

        wait_for_steam(
            use_proton=False,
            loginvdf_paths=(os.path.join(Args.wine_steam_dir, File.loginvdf_inner), ),
            wine=wine_command,
            env=env,
        )

        executables = self._cfg.thirdparty_executables.copy()
        if not Args.without_wine_discord_ipc_bridge:
            discord_bridge = setup_wine_discord_ipc_bridge()
            # start wine-discord-ipc-bridge before other third-party programs
            # and wait
            self._thirdparty_processes.append(
                subproc.Popen(
                    [wine_command, ] + [discord_bridge, ],
                    env=env, stderr=subproc.STDOUT))
            time.sleep(5)

        for path in executables:
            self._thirdparty_processes.append(
                subproc.Popen(
                    [wine_command, ] + [path, ], env=env, stderr=subproc.STDOUT))

        time.sleep(self._cfg.thirdparty_wait)

        if "WINEDLLOVERRIDES" not in env:
            env["WINEDLLOVERRIDES"] = ""

        wine_args = StarterWine.setup_wine_args(wine_args)

        for opt in f"-rdevice {Args.rendering_backend} {Args.game_options}".split(" "):
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

    @staticmethod
    def setup_wine_args(args):
        """
        Set up command line for running the game with Wine.

        args: A list of command line for Wine
        """
        if Args.wine_desktop:
            args += "explorer", f"/desktop=TruckersMP,{Args.wine_desktop}"
        if Args.singleplayer:
            exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
            gamepath = os.path.join(Args.gamedir, "bin/win_x64", exename)
            args.append(gamepath)
        else:
            args += File.inject_exe, Args.gamedir, Args.moddir
        return args
