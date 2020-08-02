"""
Main module for truckersmp-cli main script.

Licensed under MIT.
"""

import json
import locale
import logging
import os
import signal
import subprocess as subproc
import sys

from .args import check_args_errors, create_arg_parser
from .steamcmd import update_game
from .truckersmp import update_mod
from .utils import (
    activate_native_d3dcompiler_47, check_libsdl2,
    perform_self_update, wait_for_steam,
)
from .variables import AppId, Args, Dir, File

pkg_resources_is_available = False
try:
    import pkg_resources
    pkg_resources_is_available = True
except ImportError:
    pass


def main():
    """truckersmp-cli main function."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    locale.setlocale(locale.LC_MESSAGES, "")
    locale.setlocale(locale.LC_TIME, "C")

    # load Proton AppID info from "proton.json":
    #     {"X.Y": AppID, ... , "default": "X.Y"}
    # example:
    #     {"5.0": 1245040, "4.11": 1113280, "default": "5.0"}
    try:
        with open(File.proton_json) as f:
            AppId.proton = json.load(f)
    except Exception as e:
        sys.exit("Failed to load proton.json: {}".format(e))

    # parse options
    arg_parser = create_arg_parser()
    arg_parser.parse_args(namespace=Args)

    # print version
    if Args.version:
        version = ""
        try:
            # try to load "RELEASE" file for release assets or cloned git directory
            with open(os.path.join(os.path.dirname(Dir.scriptdir), "RELEASE")) as f:
                version += f.readline().rstrip()
        except Exception:
            pass
        if version:
            try:
                # try to get git commit hash, and append it if succeeded
                version += subproc.check_output(
                  ("git", "log", "-1", "--format= (%h)")).decode("utf-8").rstrip()
            except Exception:
                pass
        else:
            # try to get version from Python package
            try:
                if pkg_resources_is_available:
                    version += pkg_resources.get_distribution(__package__).version
            except pkg_resources.DistributionNotFound:
                pass
        print(version if version else "unknown")
        sys.exit()

    # initialize logging
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

    # self update
    if Args.self_update:
        perform_self_update()
        sys.exit()

    # fallback to old local folder
    if not Args.moddir:
        if os.path.isdir(os.path.join(Dir.scriptdir, "truckersmp")):
            logging.debug("No moddir set and fallback found")
            Args.moddir = os.path.join(Dir.scriptdir, "truckersmp")
        else:
            logging.debug("No moddir set, setting to default")
            Args.moddir = Dir.default_moddir
    logging.info("Mod directory: " + Args.moddir)

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
        if not check_libsdl2():
            sys.exit("SDL2 was not found on your system.")
        start_functions = (("Proton", start_with_proton), ("Wine", start_with_wine))
        i = 0 if Args.proton else 1
        compat_tool, start_game = start_functions[i]
        logging.debug("Starting game with {}".format(compat_tool))
        start_game()

    sys.exit()


def start_with_proton():
    """Start game with Proton."""
    steamdir = wait_for_steam(use_proton=True, loginvdf_paths=File.loginusers_paths)
    logging.info("Steam installation directory: " + steamdir)

    if not os.path.isdir(Args.prefixdir):
        logging.debug("Creating directory {}".format(Args.prefixdir))
    os.makedirs(Args.prefixdir, exist_ok=True)

    # activate native d3dcompiler_47
    wine = os.path.join(Args.protondir, "dist/bin/wine")
    if Args.activate_native_d3dcompiler_47:
        activate_native_d3dcompiler_47(os.path.join(Args.prefixdir, "pfx"), wine)

    env = os.environ.copy()
    env["SteamGameId"] = Args.steamid
    env["SteamAppId"] = Args.steamid
    env["STEAM_COMPAT_DATA_PATH"] = Args.prefixdir
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steamdir
    env["PROTON_USE_WINED3D"] = "1" if Args.use_wined3d else "0"
    env["PROTON_NO_D3D11"] = "1" if not Args.enable_d3d11 else "0"
    # enable Steam Overlay unless "--disable-proton-overlay" is specified
    if Args.disable_proton_overlay:
        ld_preload = ""
    else:
        overlayrenderer = os.path.join(steamdir, File.overlayrenderer_inner)
        if "LD_PRELOAD" in env:
            env["LD_PRELOAD"] += ":" + overlayrenderer
        else:
            env["LD_PRELOAD"] = overlayrenderer
        ld_preload = "LD_PRELOAD={}\n  ".format(env["LD_PRELOAD"])
    proton = os.path.join(Args.protondir, "proton")
    # check whether singleplayer or multiplayer
    argv = [sys.executable, proton, "run"]
    if Args.singleplayer:
        exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
        gamepath = os.path.join(Args.gamedir, "bin/win_x64", exename)
        argv += gamepath, "-nointro", "-64bit"
    else:
        argv += File.inject_exe, Args.gamedir, Args.moddir
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
    if Args.activate_native_d3dcompiler_47:
        activate_native_d3dcompiler_47(Args.prefixdir, wine)

    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEARCH"] = "win64"
    env["WINEPREFIX"] = Args.prefixdir

    wait_for_steam(
      use_proton=False,
      loginvdf_paths=(os.path.join(Args.wine_steam_dir, "config/loginusers.vdf"), ),
      wine=wine,
      env=env,
    )
    if "WINEDLLOVERRIDES" not in env:
        env["WINEDLLOVERRIDES"] = ""
    if not Args.enable_d3d11:
        env["WINEDLLOVERRIDES"] += ";d3d11=;dxgi="

    argv = [wine, ]
    if Args.singleplayer:
        exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
        gamepath = os.path.join(Args.gamedir, "bin/win_x64", exename)
        argv += gamepath, "-nointro", "-64bit"
    else:
        argv += File.inject_exe, Args.gamedir, Args.moddir
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
