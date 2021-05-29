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


def main():
    """Start truckersmp-cli.exe and optionally 3rd party programs."""
    # options and arguments
    desc = "Helper script for Steam Runtime."
    arg_parser = argparse.ArgumentParser(description=desc)
    arg_parser.add_argument(
        "-v", "--verbose", action="count",
        help="verbose output (none:error, once:info, twice or more:debug)")
    arg_parser.add_argument(
        "--executable", action="append", metavar="FILE",
        help="""3rd party executable to start in Steam Runtime container
                (can be specified multiple times for multiple files)""")
    arg_parser.add_argument(
        "game_arguments", nargs="+",
        help="argv for starting game (ATS/ETS2 executable or truckersmp-cli.exe)")
    args = arg_parser.parse_args()

    if args.verbose is not None and args.verbose > 1:
        print("Executables:", args.executable)
        print("Game Arguments:", args.game_arguments)

    env = os.environ.copy()

    third_party_processes = []
    if args.executable is not None:
        env_3rdparty = env.copy()
        if "LD_PRELOAD" in env_3rdparty:
            del env_3rdparty["LD_PRELOAD"]
        for path in args.executable:
            third_party_processes.append(
                subproc.Popen(
                    # ["python3", "/path/to/proton", "run"] + ["/path/to/program.exe"]
                    args.game_arguments[0:3] + [path, ],
                    env=env_3rdparty, stderr=subproc.STDOUT))

    try:
        with subproc.Popen(
                args.game_arguments,
                env=env, stdout=subproc.PIPE, stderr=subproc.STDOUT) as proc:
            if args.verbose:
                print("Proton output:")
                for line in proc.stdout:
                    try:
                        print(line.decode("utf-8"), end="", flush=True)
                    except UnicodeDecodeError:
                        print(
                            "!! NON UNICODE OUTPUT !!", repr(line),
                            sep="  ", end="", flush=True)
    except subproc.CalledProcessError as ex:
        print("Proton output:\n" + ex.output.decode("utf-8"), file=sys.stderr)

    for proc in third_party_processes:
        # make sure 3rd party programs is exited
        if proc.poll() is None:
            proc.kill()
        proc.wait()


if __name__ == "__main__":
    main()
