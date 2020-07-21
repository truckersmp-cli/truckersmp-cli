"""
Module for truckersmp-cli main script.

Licensed under MIT.
"""

from truckersmp_cli import utils
from truckersmp_cli import downloads
from truckersmp_cli import variables

import argparse
import json
import locale
import logging
import os
import signal
import subprocess as subproc
import sys

pkg_resources_is_available = False
try:
    import pkg_resources
    pkg_resources_is_available = True
except ImportError:
    pass


def start_with_proton():
    """Start game with Proton."""
    steamdir = utils.wait_for_steam(use_proton=True,
                                    loginvdf_paths=variables.File.loginusers_paths)
    logging.info("Steam installation directory: " + steamdir)

    if not os.path.isdir(args.prefixdir):
        logging.debug("Creating directory {}".format(args.prefixdir))
    os.makedirs(args.prefixdir, exist_ok=True)

    # activate native d3dcompiler_47
    wine = os.path.join(args.protondir, "dist/bin/wine")
    if args.activate_native_d3dcompiler_47:
        utils.activate_native_d3dcompiler_47(os.path.join(args.prefixdir, "pfx"),
                                             wine, args.ets2)

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
        overlayrenderer = os.path.join(steamdir, variables.File.overlayrenderer_inner)
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
        argv += variables.File.inject_exe, args.gamedir, args.moddir
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
        utils.activate_native_d3dcompiler_47(args.prefixdir, wine, args.ets2)

    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEARCH"] = "win64"
    env["WINEPREFIX"] = args.prefixdir

    utils.wait_for_steam(
      use_proton=False,
      loginvdf_paths=(os.path.join(args.wine_steam_dir, "config/loginusers.vdf"), ),
      wine=wine,
      wine_steam_dir=args.wine_steam_dir,
      env=env,
    )
    if "WINEDLLOVERRIDES" not in env:
        env["WINEDLLOVERRIDES"] = ""
    if not args.enable_d3d11:
        env["WINEDLLOVERRIDES"] += ";d3d11=;dxgi="

    argv = [wine, ]
    if args.singleplayer:
        exename = "eurotrucks2.exe" if args.ets2 else "amtrucks.exe"
        gamepath = os.path.join(args.gamedir, "bin/win_x64", exename)
        argv += gamepath, "-nointro", "-64bit"
    else:
        argv += variables.File.inject_exe, args.gamedir, args.moddir
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


def create_arg_parser():
    """Create ArgumentParser for this program."""
    desc = """
A simple launcher for TruckersMP to play ATS or ETS2 in multiplayer.

truckersmp-cli allows to download TruckersMP and handles starting TruckersMP
through Wine while supporting the Windows versions of
American Truck Simulator and Euro Truck Simulator 2.

The Windows version of Steam should already be able to run in the same
Wine prefix. The Windows versions of ATS and ETS2 can be installed and updated
via SteamCMD while all running Steam processes will be stopped
to prevent Steam from loosing connection. Your Steam password
and guard code are required by SteamCMD once for this to work.

On Linux it's possible to start TruckersMP through Proton.
A working native Steam installation is needed for this.
SteamCMD can use your saved credentials for convenience.
"""
    epilog = "Proton AppID list:\n"
    for k, v in variables.AppId.proton.items():
        default_mark = ""
        if k == variables.AppId.proton["default"]:
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
      "-b", "--beta", metavar="VERSION", type=str,
      help="""set game version to VERSION,
              useful for downgrading (e.g. "temporary_1_35")""")
    ap.add_argument(
      "-d", "--enable-d3d11",
      help="use Direct3D 11 instead of OpenGL",
      action="store_true")
    ap.add_argument(
      "-e", "--ets2",
      help="""use Euro Truck Simulator 2
              [Default if neither ATS or ETS2 are specified] """,
      action="store_true")
    ap.add_argument(
      "-g", "--gamedir", metavar="DIR", type=str,
      help="""choose a different directory for the game files
              [Default: $XDG_DATA_HOME/truckersmp-cli/(Game name)/data]""")
    ap.add_argument(
      "-i", "--proton-appid", metavar="APPID", type=int,
      default=variables.AppId.proton[variables.AppId.proton["default"]],
      help="""choose a different AppID for Proton (Needs an update for changes)
              [Default:{}] """.format(variables.AppId.proton[
                                        variables.AppId.proton["default"]]))
    ap.add_argument(
      "-l", "--logfile", metavar="LOG", type=str,
      default="",
      help="""write log into LOG, "-vv" option is recommended
              [Default: Empty string (only stderr)]
              Note: Messages from Steam/SteamCMD won't be written,
              only from this script (Game logs are written into
              "My Documents/{ETS2,ATS}MP/logs/client_*.log")""")
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
      default=variables.Dir.default_protondir,
      help="""choose a different Proton directory
              [Default: $XDG_DATA_HOME/truckersmp-cli/Proton]
              While updating any previous version in this folder gets changed
              to the given (-i) or default Proton version""")
    ap.add_argument(
      "-p", "--proton",
      help="""start the game with Proton
              [Default on Linux if neither Proton or Wine are specified] """,
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
      "-w", "--wine",
      help="""start the game with Wine
              [Default on other systems if neither Proton or Wine are specified]""",
      action="store_true")
    ap.add_argument(
      "-x", "--prefixdir", metavar="DIR", type=str,
      help="""choose a different directory for the prefix
              [Default: $XDG_DATA_HOME/truckersmp-cli/(Game name)/prefix]""")
    ap.add_argument(
      "--activate-native-d3dcompiler-47",
      help="""activate native 64-bit d3dcompiler_47.dll when starting
              (Needed for D3D11 renderer)""",
      action="store_true")
    ap.add_argument(
      "--disable-proton-overlay",
      help="disable Steam Overlay when using Proton",
      action="store_true")
    ap.add_argument(
      "--self-update",
      help="""update files to the latest release and quit
              Note: Python package users should use pip instead""",
      action="store_true")
    ap.add_argument(
      "--singleplayer",
      help="""start singleplayer game, useful for save editing,
              using/testing DXVK in singleplayer, etc.""",
      action="store_true")
    ap.add_argument(
      "--use-wined3d",
      help="use OpenGL-based D3D11 instead of DXVK when using Proton",
      action="store_true")
    ap.add_argument(
      "--wine-steam-dir", metavar="DIR", type=str,
      help="""choose a directory for Windows version of Steam
              [Default: "C:\\Program Files (x86)\\Steam" in the prefix]""")
    ap.add_argument(
      "--version",
      help="""print version information and quit""",
      action="store_true")

    return ap


def main():
    """truckersmp-cli main function."""
    global args

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    locale.setlocale(locale.LC_MESSAGES, "")
    locale.setlocale(locale.LC_TIME, "C")

    # load Proton AppID info from "proton.json":
    #     {"X.Y": AppID, ... , "default": "X.Y"}
    # example:
    #     {"5.0": 1245040, "4.11": 1113280, "default": "5.0"}
    try:
        with open(variables.File.proton_json) as f:
            variables.AppId.proton = json.load(f)
    except Exception as e:
        sys.exit("Failed to load proton.json: {}".format(e))

    # parse options
    arg_parser = create_arg_parser()
    args = arg_parser.parse_args()

    # print version
    if args.version:
        version = ""
        try:
            # try to load "RELEASE" file for release assets or cloned git directory
            with open(os.path.join(os.path.dirname(variables.Dir.scriptdir),
                                   "RELEASE")) as f:
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
    if args.verbose:
        logger.setLevel(logging.INFO if args.verbose == 1 else logging.DEBUG)
    logger.addHandler(stderr_handler)
    if args.logfile != "":
        file_handler = logging.FileHandler(args.logfile, mode="w")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # self update
    if args.self_update:
        downloads.perform_self_update()
        sys.exit()

    # fallback to old local folder
    if not args.moddir:
        if os.path.isdir(os.path.join(variables.Dir.scriptdir, "truckersmp")):
            logging.debug("No moddir set and fallback found")
            args.moddir = os.path.join(variables.Dir.scriptdir, "truckersmp")
        else:
            logging.debug("No moddir set, setting to default")
            args.moddir = variables.Dir.default_moddir
    logging.info("Mod directory: " + args.moddir)

    # check for errors
    utils.check_args_errors(args)

    # download/update ATS/ETS2 and Proton
    if args.update:
        logging.debug("Updating game files")
        downloads.update_game(args)

    # update truckersmp when starting multiplayer
    if not args.singleplayer:
        logging.debug("Updating mod files")
        downloads.update_mod(args.moddir)

    # start truckersmp with proton or wine
    if args.start:
        if not utils.check_libsdl2():
            sys.exit("SDL2 was not found on your system.")
        start_functions = (("Proton", start_with_proton), ("Wine", start_with_wine))
        i = 0 if args.proton else 1
        compat_tool, start_game = start_functions[i]
        logging.debug("Starting game with {}".format(compat_tool))
        start_game()

    sys.exit()
