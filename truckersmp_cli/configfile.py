"""
Configuration file handler for truckersmp-cli main script.

Licensed under MIT.
"""

import configparser
import os

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
        parser = configparser.ConfigParser()
        parser.read(configfile)
        for sect in parser.sections():
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

    @property
    def thirdparty_executables(self):
        """Return third-party program paths."""
        return self._thirdparty_executables

    @property
    def thirdparty_wait(self):
        """Return waiting time for third-party programs."""
        return self._thirdparty_wait
