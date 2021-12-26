"""
Log handler for truckersmp-cli main script.

Licensed under MIT.
"""

import logging

from .variables import Args


# pylint: disable=too-few-public-methods
class Logger:
    """
    Stdout/file Logger.

    Logger objects must be created after parse_args().
    """

    def __init__(self):
        """Initialize Logger object."""
        self._formatter = logging.Formatter("** {levelname} **  {message}", style="{")
        self._logger = logging.getLogger()
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(self._formatter)
        if Args.verbose:
            self._logger.setLevel(logging.INFO if Args.verbose == 1 else logging.DEBUG)
        self._logger.addHandler(stderr_handler)

    def add_file_handler(self, logfilepath):
        """
        Add a log file to handler.

        logfilepath: Path to a log file.
        """
        if logfilepath is None or logfilepath == "":
            return
        file_handler = logging.FileHandler(logfilepath, mode="w")
        file_handler.setFormatter(self._formatter)
        self._logger.addHandler(file_handler)
