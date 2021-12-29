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
        self._parser = configparser.ConfigParser()
        self._parser.read(configfile)
        # log file must be configured first
        self._logfile = self._configure_game_specific_setting(
            Args.logfile, "log-file", "", "Log file")

    def parse_settings(self):
        """Parse settings."""
        wants_rich_presence_cnt = 0
        sections = self._parser.sections()
        for sect in sections:
            # get data from valid thirdparty.* sections
            if (not sect.startswith("thirdparty.")
                    or "executable" not in self._parser[sect]):
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
                wait = int(self._parser[sect]["wait"])
            except (KeyError, ValueError):
                wait = 0  # invalid or missing
            self._thirdparty_wait = max(wait, self._thirdparty_wait)
            exe_path = self._parser[sect]["executable"]
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
                if self._parser[sect].getboolean("wants-rich-presence", fallback=False):
                    wants_rich_presence_cnt += 1
            except ValueError as ex:
                raise ValueError(
                    ConfigFile.format_error("wants-rich-presence", ex)) from ex

        self._handle_game_specific_settings(wants_rich_presence_cnt)

    def _configure_game_specific_setting(
            self, arg_value, config_name, default_value, log_name):
        """
        Configure a game specific setting.

        The return value will be one of:
         * The value from command line option (always used when specified)
         * The value from game specific setting in config file
           (used only when the command line option is not given)
         * The default value

        arg_value: The given value from command line option
        config_name: The string for the setting
        default_value: The default value for the setting or a dict of defaults
                       that contains the keys "ats" and "ets2"
        log_name: The configuration description for logging
        """
        if arg_value is not None:
            config_src = ConfigSource.OPTION
            ret = arg_value
        else:
            if Args.game in self._parser and config_name in self._parser[Args.game]:
                config_src = ConfigSource.FILE
                ret = self._parser[Args.game][config_name]
                if ((config_name.endswith("-directory") or config_name.endswith("-file"))
                        and not os.path.isabs(ret)):
                    # assume it's relative to our data directory
                    ret = os.path.join(Dir.truckersmp_cli_data, ret)
            else:
                config_src = ConfigSource.DEFAULT
                ret = default_value[Args.game.replace("mp", "")] \
                    if isinstance(default_value, dict) else default_value
        logging.info(
            "%s: %s (%s)", log_name, ret if ret != "" else "<empty>", config_src.value)

        return ret

    def _configure_game_specific_setting_boolean(
            self, arg_value, config_name, default_value, log_name):
        """
        Configure a game specific setting (boolean).

        The return value will be one of:
         * The value from command line option (always used when specified)
         * The value from game specific setting in config file
           (used only when the command line option is not given)
         * The default value

        arg_value: The given value from command line option
        config_name: The string for the setting
        default_value: The default value for the setting
        log_name: The configuration description for logging
        """
        if arg_value is not None:
            config_src = ConfigSource.OPTION
            ret = arg_value
        else:
            if Args.game in self._parser and config_name in self._parser[Args.game]:
                config_src = ConfigSource.FILE
                try:
                    ret = self._parser[Args.game].getboolean(config_name)
                except ValueError as ex:
                    raise ValueError(
                        ConfigFile.format_error(config_name, ex)) from ex
            else:
                config_src = ConfigSource.DEFAULT
                ret = default_value
        logging.info("%s: %s (%s)", log_name, ret, config_src.value)

        return ret

    def _configure_rich_presence(self, wants_rich_presence_cnt):
        """
        Determine whether to use wine-discord-ipc-bridge.

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
                        Args.game in self._parser and self._parser[Args.game].getboolean(
                            "without-rich-presence", fallback=False)
                        or ("mp" not in Args.game and wants_rich_presence_cnt == 0)
                    )):
                logging.debug("Disabling Rich Presence because the game is"
                              " singleplayer and no third-party programs want it")
                Args.without_wine_discord_ipc_bridge = True
        except ValueError as ex:
            raise ValueError(
                ConfigFile.format_error("without-rich-presence", ex)) from ex

    def _determine_rendering_backend(self):
        """Determine rendering backend."""
        config_src = ConfigSource.OPTION

        if Args.enable_d3d11:
            logging.warning("'--enable-d3d11' ('-d') option is deprecated,"
                            " use '--rendering-backend dx11 (-r dx11)' instead")
            Args.rendering_backend = "dx11"

        if Args.rendering_backend == "auto":
            rendering_backend = None
            try:
                if Args.game in self._parser:
                    rendering_backend = self._parser[Args.game].get("rendering-backend")
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

    def _handle_game_specific_settings(self, wants_rich_presence_cnt):
        """
        Handle game specific settings.

        wants_rich_presence_cnt: The number of third-party program sections
                                 that have "wants-rich-presence = [true]"
        """
        # game directory
        Args.gamedir = self._configure_game_specific_setting(
            Args.gamedir, "game-directory",
            Dir.default_gamedir, "Game directory",
        )

        # prefix directory
        Args.prefixdir = self._configure_game_specific_setting(
            Args.prefixdir, "prefix-directory",
            Dir.default_prefixdir, "Prefix directory",
        )

        # game options
        # note that game starters will prepend "-rdevice" to the given options
        Args.game_options = self._configure_game_specific_setting(
            Args.game_options, "game-options",
            "-nointro -64bit", "Game options",
        )

        # TruckersMP MOD directory
        Args.moddir = self._configure_game_specific_setting(
            Args.moddir, "truckersmp-directory",
            Dir.default_moddir, "TruckersMP MOD directory",
        )

        # whether to disable Steam Runtime
        Args.without_steam_runtime = self._configure_game_specific_setting_boolean(
            Args.without_steam_runtime, "without-steamruntime",
            False, "Whether to disable Steam Runtime (deprecated)",
        )
        Args.disable_steamruntime = self._configure_game_specific_setting_boolean(
            Args.disable_steamruntime, "disable-steamruntime",
            False, "Whether to disable Steam Runtime",
        )
        if Args.without_steam_runtime:
            logging.warning(
                "'--without-steam-runtime' option and "
                "'without-steamruntime' setting are deprecated, "
                "use '--disable-steamruntime' option or "
                "'disable-steamruntime' setting instead")
            Args.disable_steamruntime = True

        # whether to disable Steam Overlay
        Args.disable_proton_overlay = self._configure_game_specific_setting_boolean(
            Args.disable_proton_overlay, "disable-proton-overlay",
            False, "Whether to disable Steam Overlay",
        )

        # Proton/Steam Runtime directory
        if Args.proton:
            Args.protondir = self._configure_game_specific_setting(
                Args.protondir, "proton-directory",
                Dir.default_protondir, "Proton directory",
            )
            Args.steamruntimedir = self._configure_game_specific_setting(
                Args.steamruntimedir, "steamruntime-directory",
                Dir.default_steamruntimedir, "Steam Runtime directory",
            )

        # Discord Rich Presence
        self._configure_rich_presence(wants_rich_presence_cnt)

        # rendering backend
        self._determine_rendering_backend()

    @staticmethod
    def format_error(name, ex):
        """
        Get a formatted output string for ValueError.

        name: configuration name
        ex: A ValueError object
        """
        return f"  Name: {name}\n  Error: {ex}"

    @property
    def logfile(self):
        """Return the path to log file."""
        return self._logfile

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
