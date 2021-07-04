"""
Configuration file handler for truckersmp-cli main script.

Licensed under MIT.
"""

import configparser


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
            try:
                wait = int(parser[sect]["wait"])
            except (KeyError, ValueError):
                wait = 0  # invalid or missing
            self._thirdparty_wait = max(wait, self._thirdparty_wait)
            self._thirdparty_executables.append(parser[sect]["executable"])

    @property
    def thirdparty_executables(self):
        """Sections for third-party programs."""
        return self._thirdparty_executables

    @property
    def thirdparty_total_wait(self):
        """Total waiting time for third-party programs."""
        return self._thirdparty_wait
