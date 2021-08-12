"""
Main module for truckersmp-cli main script.

Licensed under MIT.
"""

import json
import logging
import os
import signal
import subprocess as subproc
import sys

from .args import check_args_errors, create_arg_parser, process_actions_gamenames
from .configfile import ConfigFile
from .gamestarter import StarterProton, StarterWine
from .steamcmd import update_game
from .truckersmp import update_mod
from .utils import check_libsdl2, perform_self_update
from .variables import AppId, Args, Dir, File, URL

PKG_RESOURCES_IS_AVAILABLE = False
try:
    import pkg_resources
    PKG_RESOURCES_IS_AVAILABLE = True
except ImportError:
    pass


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

    # set up logging
    setup_logging()

    # load configuration file
    try:
        cfg = ConfigFile(Args.configfile)
    except ValueError as ex:
        sys.exit("Invalid configuration found in {}:\n{}".format(Args.configfile, ex))

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
