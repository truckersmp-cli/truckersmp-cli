#!/usr/bin/env python3

"""
Helper script for Steam Runtime.

This script starts truckersmp-cli inject program
and optionally 3rd party programs.
"""

import argparse
import os
import subprocess as subproc
import sys
import time


def start_thirdparty_programs(executables, proton_run):
    """
    Start third-party programs.

    This function starts specified third-party programs in the given list
    and returns a list of subprocess.Popen objects.

    executables: A list of executables
                 from "--early-executable" or "--executable",
                 or None when it's omitted
    proton_run: ["python3" command, Path to "proton" command, "run"]
    """
    # pylint: disable=consider-using-with
    if executables is None:  # nothing to do in this function
        return []
    thirdparty_processes = []
    env = os.environ.copy()
    if "LD_PRELOAD" in env:
        del env["LD_PRELOAD"]
    for path in executables:  # assume that "executables" is iterable
        thirdparty_processes.append(
            subproc.Popen(proton_run + [path, ], env=env, stderr=subproc.STDOUT))
    return thirdparty_processes


def main():
    """Start truckersmp-cli.exe and optionally 3rd party programs."""
    # pylint: disable=consider-using-with

    # options and arguments
    desc = "Helper script for Steam Runtime."
    arg_parser = argparse.ArgumentParser(description=desc)
    arg_parser.add_argument(
        "-v", "--verbose", action="count",
        help="verbose output (none:error, once:info, twice or more:debug)")
    arg_parser.add_argument(
        "--early-executable", action="append", metavar="FILE",
        help="""3rd party executable to start early in Steam Runtime container
                (can be specified multiple times for multiple files)""")
    arg_parser.add_argument(
        "--early-wait-before-start", metavar="SECS", type=int,
        default=0,
        help="""wait SECS seconds before starting 3rd party executables
                specified by --executable [Default: 0]""")
    arg_parser.add_argument(
        "--executable", action="append", metavar="FILE",
        help="""3rd party executable to start in Steam Runtime container
                (can be specified multiple times for multiple files)""")
    arg_parser.add_argument(
        "--wait-before-start", metavar="SECS", type=int,
        default=0,
        help="wait SECS seconds before starting the game [Default: 0]")
    arg_parser.add_argument(
        "game_arguments", nargs="+",
        help="argv for starting game (ATS/ETS2 executable or truckersmp-cli.exe)")
    args = arg_parser.parse_args()

    if args.verbose is not None and args.verbose > 1:
        print("Executables (early):", args.early_executable)
        print("Executables:", args.executable)
        print("Game Arguments:", args.game_arguments)
        print("Waiting time (early):", args.early_wait_before_start)
        print("Waiting time:", args.wait_before_start)

    early_thirdparty_processes = start_thirdparty_programs(
        args.early_executable, args.game_arguments[0:3])

    time.sleep(args.early_wait_before_start)

    thirdparty_processes = start_thirdparty_programs(
        args.executable, args.game_arguments[0:3])

    time.sleep(args.wait_before_start)

    env = os.environ.copy()
    try:
        with subproc.Popen(
                args.game_arguments,
                env=env,
                stdout=subproc.PIPE if args.verbose else subproc.DEVNULL,
                stderr=subproc.STDOUT) as proc:
            if args.verbose:
                print("Proton output:")
            if proc.stdout is not None:
                for line in proc.stdout:
                    try:
                        print(line.decode("utf-8"), end="", flush=True)
                    except UnicodeDecodeError:
                        print(
                            "!! NON UNICODE OUTPUT !!", repr(line),
                            sep="  ", end="", flush=True)
    except subproc.CalledProcessError as ex:
        print("Proton output:\n" + ex.output.decode("utf-8"), file=sys.stderr)

    for proc in thirdparty_processes + early_thirdparty_processes:
        # make sure 3rd party programs is exited
        if proc.poll() is None:
            proc.kill()
        proc.wait()


if __name__ == "__main__":
    main()
