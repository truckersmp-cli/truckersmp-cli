# pylint: disable=too-few-public-methods

"""
Variables for truckersmp-cli main script.

Licensed under MIT.
"""

import os


class AppId:
    """Steam AppIDs."""

    game = {
        "ats":          270880,        # https://steamdb.info/app/270880/
        "ets2":         227300,        # https://steamdb.info/app/227300/
    }
    proton = {}


class Args:
    """Arguments from command line."""


class Dir:
    """Directories."""

    XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    default_gamedir = {
        "ats": os.path.join(
            XDG_DATA_HOME, "truckersmp-cli/American Truck Simulator/data"),
        "ets2": os.path.join(
            XDG_DATA_HOME, "truckersmp-cli/Euro Truck Simulator 2/data"),
    }
    default_prefixdir = {
        "ats": os.path.join(
            XDG_DATA_HOME, "truckersmp-cli/American Truck Simulator/prefix"),
        "ets2": os.path.join(
            XDG_DATA_HOME, "truckersmp-cli/Euro Truck Simulator 2/prefix"),
    }
    default_moddir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/TruckersMP")
    default_protondir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/Proton")
    steamcmddir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/steamcmd")
    steamcmdpfx = os.path.join(steamcmddir, "pfx")
    dllsdir = os.path.join(XDG_DATA_HOME, "truckersmp-cli/dlls")
    scriptdir = os.path.dirname(os.path.realpath(__file__))


class File:
    """Files."""

    loginvdf_inner = "config/loginusers.vdf"
    # known paths for [steam installation directory]/config/loginusers.vdf
    loginusers_paths = [
        # Official (Valve) version
        os.path.join(Dir.XDG_DATA_HOME, "Steam", loginvdf_inner),
        # Debian-based systems, old path
        os.path.join(os.path.expanduser("~/.steam"), loginvdf_inner),
        # Debian-based systems, new path
        os.path.join(os.path.expanduser("~/.steam/debian-installation"), loginvdf_inner),
    ]
    proton_json = os.path.join(Dir.scriptdir, "proton.json")
    inject_exe = os.path.join(Dir.scriptdir, "truckersmp-cli.exe")
    overlayrenderer_inner = "ubuntu12_64/gameoverlayrenderer.so"
    d3dcompiler_47 = os.path.join(Dir.dllsdir, "d3dcompiler_47.dll")
    d3dcompiler_47_md5 = "b2cc65e1930e75f563078c6a20221b37"
    sdl2_soname = "libSDL2-2.0.so.0"


class URL:
    """URLs."""

    project = "https://github.com/lhark/truckersmp-cli"
    dlurl = "download.ets2mp.com"
    dlurlalt = "failover.truckersmp.com"
    listurl = "https://update.ets2mp.com/files.json"
    steamcmdlnx = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    steamcmdwin = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
    raw_github = "raw.githubusercontent.com"
    d3dcompilerpath = "/ImagingSIMS/ImagingSIMS/master/Redist/x64/d3dcompiler_47.dll"
    truckersmp_api = "https://api.truckersmp.com/v2/version"
    truckersmp_stats = "https://stats.truckersmp.com"
    truckersmp_downgrade_help = "https://truckersmp.com/kb/26"
    issueurl = project + "/issues"
    release = project + "/raw/master/RELEASE"
    rel_tarxz_tmpl = project + "/releases/download/{0}/truckersmp-cli-{0}.tar.xz"
