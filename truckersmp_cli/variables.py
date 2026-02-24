# pylint: disable=too-few-public-methods

"""
Variables for truckersmp-cli main script.

Licensed under MIT.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional


class AppId:
    """Steam AppIDs."""

    game: Dict[str, int] = {
        "ats": 270880,  # https://steamdb.info/app/270880/
        "ets2": 227300,  # https://steamdb.info/app/227300/
    }
    proton: Dict[str, int] = {}
    steamruntime: Dict[str, int] = {}


class Args:
    """Arguments from command line."""

    proton: bool = False
    wine: bool = False
    ets2: bool = False
    ats: bool = False
    singleplayer: bool = False
    start: bool = False
    update: bool = False
    downgrade: bool = False
    kill_procs: bool = False
    beta: Optional[str] = None
    game: str = ""
    action: str = ""
    wine_steam_dir: Optional[str] = None
    prefixdir: str = ""
    gamedir: Optional[str] = None
    moddir: Optional[str] = None
    protondir: Optional[str] = None
    steamruntimedir: Optional[str] = None
    logfile: Optional[str] = None
    configfile: str = ""
    account: Optional[str] = None
    proton_appid: str = ""
    wine_desktop: Optional[str] = None
    native_steam_dir: str = "auto"
    self_update: bool = False
    skip_update_proton: bool = False
    disable_steamruntime: Optional[bool] = None
    flatpak_steam: Optional[bool] = None
    rendering_backend: str = "auto"
    use_wined3d: bool = False
    without_wine_discord_ipc_bridge: bool = False
    activate_native_d3dcompiler_47: bool = False
    check_windows_steam: bool = False
    disable_proton_overlay: Optional[bool] = None
    download_throttle: int = -1
    version: bool = False
    steamid: str = ""
    without_steam_runtime: Optional[bool] = None
    game_options: Optional[str] = None


class Dir:
    """Directories."""

    XDG_CONFIG_HOME = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    XDG_DATA_HOME = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    truckersmp_cli_data = Path(XDG_DATA_HOME) / "truckersmp-cli"
    default_gamedir: Dict[str, str] = {
        "ats": str(truckersmp_cli_data / "American Truck Simulator" / "data"),
        "ets2": str(truckersmp_cli_data / "Euro Truck Simulator 2" / "data"),
    }
    default_prefixdir: Dict[str, str] = {
        "ats": str(truckersmp_cli_data / "American Truck Simulator" / "prefix"),
        "ets2": str(truckersmp_cli_data / "Euro Truck Simulator 2" / "prefix"),
    }
    flatpak_steamdir = Path("~/.local/share/Steam").expanduser()
    default_moddir = str(truckersmp_cli_data / "TruckersMP")
    default_protondir = str(truckersmp_cli_data / "Proton")
    default_steamruntimedir = str(truckersmp_cli_data / "SteamRuntime")
    steamcmddir = str(truckersmp_cli_data / "steamcmd")
    steamcmdpfx = str(Path(steamcmddir) / "pfx")
    dllsdir = str(truckersmp_cli_data / "dlls")
    ipcbrdir = str(truckersmp_cli_data / "wine-discord-ipc-bridge")
    scriptdir = os.path.dirname(os.path.realpath(__file__))
    system32_inner = "dosdevices/c:/windows/system32"


class File:
    """Files."""

    loginvdf_inner = "config/loginusers.vdf"
    steamlibvdf_inner = "steamapps/libraryfolders.vdf"
    steamlibvdf_inner_legacy = "SteamApps/libraryfolders.vdf"
    # known paths for [steam installation directory]/config/loginusers.vdf
    loginusers_paths: List[str] = [
        # Official (Valve) version
        str(Path(Dir.XDG_DATA_HOME) / "Steam" / loginvdf_inner),
        # Debian-based systems, old path
        str(Path("~/.steam").expanduser() / loginvdf_inner),
        # Debian-based systems, new path
        str(Path("~/.steam/debian-installation").expanduser() / loginvdf_inner),
    ]
    default_configfile = str(
        Path(Dir.XDG_CONFIG_HOME) / "truckersmp-cli" / "truckersmp-cli.conf"
    )
    proton_json = os.path.join(Dir.scriptdir, "proton.json")
    steamruntime_json = os.path.join(Dir.scriptdir, "steamruntime.json")
    inject_exe = os.path.join(Dir.scriptdir, "truckersmp-cli.exe")
    overlayrenderer_inner = "ubuntu12_64/gameoverlayrenderer.so"
    d3dcompiler_47 = os.path.join(Dir.dllsdir, "d3dcompiler_47.dll")
    d3dcompiler_47_inner = os.path.join(Dir.system32_inner, "d3dcompiler_47.dll")
    d3dcompiler_47_sha256 = "b2cc65e1930e75f563078c6a20221b37"
    ipcbridge = os.path.join(Dir.ipcbrdir, "winediscordipcbridge.exe")
    ipcbridge_sha256 = "a433fb2ec994b664b662e798095f9059"
    sdl2_soname = "libSDL2-2.0.so.0"
    flatpak_helper = os.path.join(Dir.scriptdir, "flatpak_helper.py")
    steamruntime_helper = os.path.join(Dir.scriptdir, "steamruntime_helper.py")


class URL:
    """URLs."""

    project = "https://github.com/truckersmp-cli/truckersmp-cli"
    project_doc_inst = project + "#install"
    project_releases = project + "/releases"
    dlurl = "download.ets2mp.com"
    dlurlalt = "failover.truckersmp.com"
    listurl = "https://update.ets2mp.com/files.json"
    steamcmdlnx = (
        "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
    )
    steamcmdwin = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
    github = "github.com"
    d3dcompilerpath = (
        "/ImagingSIMS/ImagingSIMS/raw/"
        + "162e4b02445c1fb621ce81c2bdf82a7870a3fd2a/Redist/x64/d3dcompiler_47.dll"
    )
    ipcbrpath = (
        "/0e4ef622/wine-discord-ipc-bridge/releases/download/"
        + "v0.0.2/winediscordipcbridge.exe"
    )
    truckersmp_api = "https://api.truckersmp.com/v2/version"
    truckersmp_status = "https://truckersmp.com/status"
    issueurl = project + "/issues"
    release = project + "/raw/master/RELEASE"
    rel_tarxz_tmpl = project + "/releases/download/{0}/truckersmp-cli-{0}.tar.xz"
