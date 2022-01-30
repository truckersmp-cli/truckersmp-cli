#!/usr/bin/env python3

"""
Helper script for Flatpak.

This script starts Flatpak version of Steam and steamruntime_helper.py.
"""

import os
import subprocess as subproc
import sys
import time
from gettext import ngettext


def wait_for_flatpak_steam(timeout=99):
    """Wait for Flatpak version of Steam to be running."""
    loginvdf = os.path.expanduser("~/.local/share/Steam/config/loginusers.vdf")
    try:
        stat = os.stat(loginvdf)
        loginvdf_timestamp = stat.st_mtime
    except OSError:
        loginvdf_timestamp = 0

    waittime = timeout
    while waittime > 0:
        # "\r" can't be used here because this helper is subprocess
        print(ngettext(
            "Waiting {} second for steam to start up.",
            "Waiting {} seconds for steam to start up.",
            waittime).format(waittime), flush=True)
        time.sleep(1)
        waittime -= 1
        try:
            stat = os.stat(loginvdf)
            if stat.st_mtime > loginvdf_timestamp:
                break
        except OSError:
            pass


def main():
    """Start Flatpak version of Steam and steamruntime_helper.py."""
    # pylint: disable=consider-using-with

    args = sys.argv[1:]
    verbose = "-v" in args or "-vv" in args

    subproc.Popen(("steam", ), stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
    wait_for_flatpak_steam()

    try:
        with subproc.Popen(
                args,
                stdout=subproc.PIPE if verbose else subproc.DEVNULL,
                stderr=subproc.STDOUT) as proc:
            if verbose:
                print("Helper output:", flush=True)
            if proc.stdout is not None:
                for line in proc.stdout:
                    try:
                        print(line.decode("utf-8"), end="", flush=True)
                    except UnicodeDecodeError:
                        print(
                            "!! NON UNICODE OUTPUT !!", repr(line),
                            sep="  ", end="", flush=True)
            proc.wait()
    except subproc.CalledProcessError as ex:
        print("Helper output:\n" + ex.output.decode("utf-8"), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
