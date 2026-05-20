"""
Diagnostics command for truckersmp-cli.

Licensed under MIT.
"""

import json
import os
import platform
import subprocess as subproc
from getpass import getuser

from .utils import check_libsdl2, get_proton_version
from .variables import Args, Dir, File


def _make_check(check_id, ok, label, detail="", category="general"):
    """Create one diagnostic check result."""
    return {
        "id": check_id,
        "ok": ok,
        "status": "ok" if ok else "fail",
        "category": category,
        "label": label,
        "detail": detail,
    }


def _check_path(check_id, label, path, mode=os.R_OK, category="general"):
    """Check whether a path exists and is accessible."""
    return _make_check(check_id, os.access(path, mode), label, path, category)


def _steam_install_candidates():
    """Return known native, Flatpak, Snap, and custom Steam candidates."""
    home = os.path.expanduser("~")
    candidates = []

    if Args.native_steam_dir != "auto":
        candidates.append(("custom", os.path.expanduser(Args.native_steam_dir)))

    candidates.extend((
        ("native", os.path.join(Dir.XDG_DATA_HOME, "Steam")),
        ("native", os.path.expanduser("~/.steam")),
        ("native", os.path.expanduser("~/.steam/debian-installation")),
        ("flatpak", os.path.join(
            home, ".var/app/com.valvesoftware.Steam/.local/share/Steam")),
        ("snap", os.path.join(home, "snap/steam/common/.local/share/Steam")),
        ("snap", os.path.join(home, "snap/steam/common/.steam/steam")),
    ))

    # Preserve order but remove duplicates.
    seen = set()
    unique = []
    for install_type, path in candidates:
        norm_path = os.path.normpath(path)
        if norm_path in seen:
            continue
        seen.add(norm_path)
        unique.append((install_type, norm_path))
    return unique


def _steam_has_config_files(path):
    """Return True if a Steam directory has recognizable config files."""
    return (
        os.path.isfile(os.path.join(path, File.loginvdf_inner))
        or os.path.isfile(os.path.join(path, File.steamlibvdf_inner))
        or os.path.isfile(os.path.join(path, File.steamlibvdf_inner_legacy))
    )


def _detect_steam_installation():
    """Detect the most likely Steam installation directory and package/source."""
    for install_type, path in _steam_install_candidates():
        if os.path.isdir(path) and _steam_has_config_files(path):
            return install_type, path

    for install_type, path in _steam_install_candidates():
        if os.path.isdir(path):
            return install_type, path

    return "unknown", "No known Steam directory found"


def _is_steam_running():
    """Check whether the Steam process appears to be running."""
    if platform.system() != "Linux":
        return False, "Steam process check is only supported on Linux"

    try:
        subproc.check_call(
            ("pgrep", "-u", getuser(), "-x", "steam"),
            stdout=subproc.DEVNULL,
            stderr=subproc.DEVNULL,
        )
        return True, "steam process found"
    except FileNotFoundError:
        return False, "pgrep command not found"
    except subproc.CalledProcessError:
        return False, "steam process not found"


def _find_steam_library_checks():
    """Find Steam libraryfolders.vdf files in known locations."""
    checks = []
    for _install_type, steamdir in _steam_install_candidates():
        for inner_path in (File.steamlibvdf_inner, File.steamlibvdf_inner_legacy):
            path = os.path.join(steamdir, inner_path)
            if os.path.isfile(path):
                checks.append(_make_check(
                    "steam_libraryfolders",
                    True,
                    "libraryfolders.vdf found",
                    path,
                    "steam",
                ))

    if not checks:
        checks.append(_make_check(
            "steam_libraryfolders",
            False,
            "libraryfolders.vdf found",
            "No known path found",
            "steam",
        ))

    return checks


def _build_steam_checks():
    """Build Steam-related diagnostic checks."""
    install_type, steamdir = _detect_steam_installation()
    steam_running, steam_running_detail = _is_steam_running()

    checks = [
        _make_check(
            "steam_install_source",
            install_type != "unknown",
            "Steam package/source",
            install_type,
            "steam",
        ),
        _make_check(
            "steam_directory",
            install_type != "unknown",
            "Steam directory detected",
            steamdir,
            "steam",
        ),
        _make_check(
            "steam_running",
            steam_running,
            "Steam process running",
            steam_running_detail,
            "steam",
        ),
    ]
    checks.extend(_find_steam_library_checks())
    return checks, install_type, steamdir


def _build_proton_checks():
    """Build Proton and Steam Runtime diagnostic checks."""
    checks = []
    if not Args.proton:
        return checks

    proton_executable = os.path.join(Args.protondir, "proton")
    checks.extend((
        _make_check(
            "proton_appid",
            True,
            "Selected Proton AppID/version",
            Args.proton_appid,
            "proton",
        ),
        _check_path(
            "proton_directory",
            "Proton directory exists",
            Args.protondir,
            os.R_OK | os.X_OK,
            "proton",
        ),
        _check_path(
            "proton_executable",
            "Proton executable exists",
            proton_executable,
            os.R_OK,
            "proton",
        ),
    ))

    try:
        major, minor = get_proton_version(Args.protondir)
        checks.append(_make_check(
            "proton_version",
            True,
            "Proton version file readable",
            f"{major}.{minor}",
            "proton",
        ))
    except (OSError, ValueError) as ex:
        checks.append(_make_check(
            "proton_version",
            False,
            "Proton version file readable",
            str(ex),
            "proton",
        ))

    steamruntime_run = os.path.join(Args.steamruntimedir, "run")
    if Args.disable_steamruntime:
        checks.append(_make_check(
            "steam_runtime_enabled",
            True,
            "Steam Runtime enabled",
            "disabled by configuration",
            "proton",
        ))
    else:
        checks.extend((
            _check_path(
                "steam_runtime_directory",
                "Steam Runtime directory exists",
                Args.steamruntimedir,
                os.R_OK | os.X_OK,
                "proton",
            ),
            _check_path(
                "steam_runtime_run",
                "Steam Runtime run executable exists",
                steamruntime_run,
                os.R_OK | os.X_OK,
                "proton",
            ),
        ))

    return checks


def _build_report(version_string):
    """Build diagnostics report data."""
    checks = [
        _make_check(
            "selected_runner",
            True,
            "Selected runner",
            "Proton" if Args.proton else "Wine",
        ),
        _check_path(
            "data_directory",
            "Data directory exists",
            Dir.truckersmp_cli_data,
            os.R_OK | os.W_OK | os.X_OK,
        ),
        _check_path(
            "inject_program",
            "Inject program exists",
            File.inject_exe,
            os.R_OK,
        ),
        _make_check(
            "sdl2",
            check_libsdl2(),
            "SDL2 library found",
            File.sdl2_soname,
        ),
    ]

    steam_checks, steam_install_type, steam_directory = _build_steam_checks()
    checks.extend(steam_checks)
    checks.extend(_build_proton_checks())

    ok = all(check["ok"] for check in checks)

    return {
        "ok": ok,
        "status": "ok" if ok else "issues_found",
        "version": version_string,
        "config_file": Args.configfile,
        "data_directory": Dir.truckersmp_cli_data,
        "runner": "proton" if Args.proton else "wine",
        "steam": {
            "source": steam_install_type,
            "directory": steam_directory,
            "configured_steam_directory": Args.native_steam_dir,
        },
        "proton": {
            "appid": Args.proton_appid if Args.proton else None,
            "directory": Args.protondir if Args.proton else None,
            "steam_runtime_directory": Args.steamruntimedir if Args.proton else None,
            "steam_runtime_disabled": Args.disable_steamruntime if Args.proton else None,
        },
        "checks": checks,
    }


def _print_check_group(report, category, title):
    """Print one group of diagnostic checks."""
    group = [check for check in report["checks"] if check["category"] == category]
    if not group:
        return

    print()
    print(title)
    for check in group:
        print(f"[{check['status'].upper()}] {check['label']}: {check['detail']}")


def _print_text_report(report):
    """Print diagnostics report in human-readable text format."""
    print("truckersmp-cli doctor")
    print()
    print(f"Version: {report['version']}")
    print(f"Config file: {report['config_file']}")
    print(f"Data directory: {report['data_directory']}")

    _print_check_group(report, "general", "General:")
    _print_check_group(report, "steam", "Steam:")
    _print_check_group(report, "proton", "Proton:")

    print()
    if report["ok"]:
        print("Doctor result: OK")
    else:
        print("Doctor result: issues found")


def run_doctor(version_string):
    """Run basic diagnostics for the local truckersmp-cli setup."""
    report = _build_report(version_string)

    if Args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text_report(report)

    return 0 if report["ok"] else 1
