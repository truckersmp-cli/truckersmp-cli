"""
Arguments handler for truckersmp-cli main script.

Licensed under MIT.
"""

import argparse
import logging
import os
import platform
import sys

from .utils import get_current_steam_user
from .variables import AppId, Dir, File

vdf_is_available = False
try:
    import vdf
    vdf_is_available = True
except ImportError:
    pass


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
      default=AppId.proton[AppId.proton["default"]],
      help="""choose a different AppID for Proton (Needs an update for changes)
              [Default:{}] """.format(AppId.proton[AppId.proton["default"]]))
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
      default=Dir.default_protondir,
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
