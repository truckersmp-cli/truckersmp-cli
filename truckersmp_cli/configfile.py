"""
Configuration file handler for truckersmp-cli main script.

Licensed under MIT.
"""

import configparser
import logging
import os
from enum import Enum

from .utils import is_dos_style_abspath
from .variables import Args, Dir


class ConfigFile:
    """Configuration file."""

    def __init__(self, configfile):
        """
        Initialize ConfigFile object.

        configfile: Path to configuration file
        """
        self._thirdparty_wait = 0
        self._thirdparty_executables = []
        wants_rich_presence_cnt = 0
        parser = configparser.ConfigParser()
        parser.read(configfile)
        sections = parser.sections()
        for sect in sections:
            # get data from valid thirdparty.* sections
            if not sect.startswith("thirdparty.") or "executable" not in parser[sect]:
                continue
            # only use configurations for the specified game
            #   [thirdparty.prog1]        -> all games
            #   [thirdparty.ets2mp.prog1] -> ETS2MP
            #   [thirdparty.ets2.prog1]   -> ETS2
            #   [thirdparty.atsmp.prog1]  -> ATSMP
            #   [thirdparty.ats.prog1]    -> ATS
            if (sect.count(".") == 2
                    and not sect.startswith("thirdparty." + Args.game + ".")):
                continue
            try:
                wait = int(parser[sect]["wait"])
            except (KeyError, ValueError):
                wait = 0  # invalid or missing
            self._thirdparty_wait = max(wait, self._thirdparty_wait)
            exe_path = parser[sect]["executable"]
            if os.path.isabs(exe_path):
                # absolute path: use the given path
                self._thirdparty_executables.append(exe_path)
            else:
                if is_dos_style_abspath(exe_path):
                    # DOS/Windows style absolute path: use the given path
                    self._thirdparty_executables.append(exe_path)
                else:
                    # relative path: assume it's relative to our data directory
                    self._thirdparty_executables.append(
                        os.path.join(Dir.truckersmp_cli_data, exe_path))
            # does it want Rich Presence?
            try:
                if parser[sect].getboolean("wants-rich-presence", fallback=False):
                    wants_rich_presence_cnt += 1
            except ValueError as ex:
                raise ValueError(
                    ConfigFile.format_error("wants-rich-presence", ex)) from ex

        ConfigFile.handle_game_specific_settings(parser, wants_rich_presence_cnt)

    @staticmethod
    def configure_game_and_prefix_directories(parser):
        """
        Determine game and prefix directories.

        parser: A ConfigParser object
        """
        config_src = dict(game=ConfigSource.OPTION, prefix=ConfigSource.OPTION)

        game = Args.game.replace("mp", "")  # {ats,ets2} for default_{game,prefix}dir

        if Args.gamedir is None:
            config_name = "game-directory"
            if Args.game in parser and config_name in parser[Args.game]:
                config_src["game"] = ConfigSource.FILE
                path = parser[Args.game][config_name]
                if not os.path.isabs(path):
                    # assume it's relative to our data directory
                    path = os.path.join(Dir.truckersmp_cli_data, path)
                Args.gamedir = path
            else:
                config_src["game"] = ConfigSource.DEFAULT
                Args.gamedir = Dir.default_gamedir[game]
        logging.info(
            "Game directory: %s (%s)", Args.gamedir, config_src["game"].value)

        if Args.prefixdir is None:
            config_name = "prefix-directory"
            if Args.game in parser and config_name in parser[Args.game]:
                config_src["prefix"] = ConfigSource.FILE
                path = parser[Args.game][config_name]
                if not os.path.isabs(path):
                    path = os.path.join(Dir.truckersmp_cli_data, path)
                Args.prefixdir = path
            else:
                config_src["prefix"] = ConfigSource.DEFAULT
                Args.prefixdir = Dir.default_prefixdir[game]
        logging.info(
            "Prefix directory: %s (%s)", Args.prefixdir, config_src["prefix"].value)

    @staticmethod
    def configure_game_options(parser):
        """
        Determine custom game options.

        If no options are specified, "-nointro -64bit" will be used.
        Note that game starters will prepend "-rdevice" to the given options.

        parser: A ConfigParser object
        """
        config_src = ConfigSource.OPTION

        if Args.game_options is None:
            config_name = "game-options"
            if Args.game in parser and config_name in parser[Args.game]:
                config_src = ConfigSource.FILE
                Args.game_options = parser[Args.game][config_name]
            else:
                config_src = ConfigSource.DEFAULT
                Args.game_options = "-nointro -64bit"
        logging.info(
            "Game options: %s (%s)", Args.game_options, config_src.value)

    @staticmethod
    def configure_rich_presence(parser, wants_rich_presence_cnt):
        """
        Determine whether to use wine-discord-ipc-bridge.

        parser: A ConfigParser object
        wants_rich_presence_cnt: The number of third-party program sections
                                 that have "wants-rich-presence = [true]"
        """
        # Rich Presense is enabled when
        # 1. "without-rich-presence = yes" is not specified
        # AND
        # 2. start multiplayer game or at least one
        #    thirdparty section has "wants-rich-presence = yes"
        try:
            if (not Args.without_wine_discord_ipc_bridge
                    and (
                        Args.game in parser and parser[Args.game].getboolean(
                            "without-rich-presence", fallback=False)
                        or ("mp" not in Args.game and wants_rich_presence_cnt == 0)
                    )):
                logging.debug("Disabling Rich Presence because the game is"
                              " singleplayer and no third-party programs want it")
                Args.without_wine_discord_ipc_bridge = True
        except ValueError as ex:
            raise ValueError(
                ConfigFile.format_error("without-rich-presence", ex)) from ex

    @staticmethod
    def determine_disable_steamruntime(parser):
        """
        Determine whether to disable Steam Runtime.

        parser: A ConfigParser object
        """
        config_src = ConfigSource.OPTION

        if not Args.without_steam_runtime:
            config_name = "without-steamruntime"
            if Args.game in parser and config_name in parser[Args.game]:
                try:
                    if parser[Args.game].getboolean(config_name, fallback=False):
                        config_src = ConfigSource.FILE
                        Args.without_steam_runtime = True
                except ValueError as ex:
                    raise ValueError(
                        ConfigFile.format_error(config_name, ex)) from ex
            else:
                config_src = ConfigSource.DEFAULT
                Args.without_steam_runtime = False
        logging.info(
            "Whether to disable Steam Runtime: %s (%s)",
            Args.without_steam_runtime, config_src.value)

    @staticmethod
    def determine_rendering_backend(parser):
        """
        Determine rendering backend.

        parser: A ConfigParser object
        """
        config_src = ConfigSource.OPTION

        if Args.enable_d3d11:
            logging.warning("'--enable-d3d11' ('-d') option is deprecated,"
                            " use '--rendering-backend dx11 (-r dx11)' instead")
            Args.rendering_backend = "dx11"

        if Args.rendering_backend == "auto":
            rendering_backend = None
            try:
                if Args.game in parser:
                    rendering_backend = parser[Args.game].get("rendering-backend")
                # use OpenGL when "rendering-backend" is not specified
                # in the game specific section
                if rendering_backend is None:
                    Args.rendering_backend = "gl"
                    config_src = ConfigSource.DEFAULT
                else:
                    if rendering_backend not in ("dx11", "gl"):
                        raise ValueError(
                            f'Invalid value "{rendering_backend}" '
                            '(Valid values are "dx11" or "gl")')
                    Args.rendering_backend = rendering_backend
                    config_src = ConfigSource.FILE
            except ValueError as ex:
                raise ValueError(
                    ConfigFile.format_error("rendering-backend", ex)) from ex
        logging.info(
            "Rendering backend: %s (%s)", Args.rendering_backend, config_src.value)

    @staticmethod
    def determine_truckersmp_directory(parser):
        """
        Determine TruckersMP MOD directory.

        parser: A ConfigParser object
        """
        config_src = ConfigSource.OPTION

        if Args.moddir is None:
            config_name = "truckersmp-directory"
            if Args.game in parser and config_name in parser[Args.game]:
                config_src = ConfigSource.FILE
                Args.moddir = parser[Args.game][config_name]
            else:
                config_src = ConfigSource.DEFAULT
                Args.moddir = Dir.default_moddir
        logging.info(
            "TruckersMP MOD directory: %s (%s)", Args.moddir, config_src.value)

    @staticmethod
    def format_error(name, ex):
        """
        Get a formatted output string for ValueError.

        name: configuration name
        ex: A ValueError object
        """
        return f"  Name: {name}\n  Error: {ex}"

    @staticmethod
    def handle_game_specific_settings(parser, wants_rich_presence_cnt):
        """
        Handle game specific settings.

        parser: A ConfigParser object
        wants_rich_presence_cnt: The number of third-party program sections
                                 that have "wants-rich-presence = [true]"
        """
        # game/prefix directories
        ConfigFile.configure_game_and_prefix_directories(parser)

        # game options
        ConfigFile.configure_game_options(parser)

        # Discord Rich Presence
        ConfigFile.configure_rich_presence(parser, wants_rich_presence_cnt)

        # whether to disable Steam Runtime
        ConfigFile.determine_disable_steamruntime(parser)

        # rendering backend
        ConfigFile.determine_rendering_backend(parser)

        # TruckersMP MOD directory
        ConfigFile.determine_truckersmp_directory(parser)

    @property
    def thirdparty_executables(self):
        """Return third-party program paths."""
        return self._thirdparty_executables

    @property
    def thirdparty_wait(self):
        """Return waiting time for third-party programs."""
        return self._thirdparty_wait


class ConfigSource(Enum):
    """Source of the configuration."""

    DEFAULT = "Default"
    OPTION = "Command line option"
    FILE = "Configuration file"
