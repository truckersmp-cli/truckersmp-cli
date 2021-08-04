"""
Utilities for truckersmp-cli main script.

Licensed under MIT.
"""

import ctypes
import glob
import hashlib
import http.client
import io
import logging
import os
import platform
import shutil
import subprocess as subproc
import sys
import tarfile
import time
import urllib.parse
import urllib.request
from getpass import getuser
from gettext import ngettext

from .variables import Args, Dir, File, URL

VDF_IS_AVAILABLE = False
try:
    import vdf
    VDF_IS_AVAILABLE = True
except ImportError:
    pass


def activate_native_d3dcompiler_47(prefix, wine):
    """
    Download/activate native 64-bit version of d3dcompiler_47.

    wine: A list used to run Wine executable
    """
    # check whether DLL is already downloaded
    need_download = True
    try:
        if check_hash(File.d3dcompiler_47, File.d3dcompiler_47_md5, hashlib.md5()):
            logging.debug("d3dcompiler_47.dll is present, MD5 is OK.")
            need_download = False
    except OSError:
        pass

    # download 64-bit d3dcompiler_47.dll from ImagingSIMS' repo
    # https://github.com/ImagingSIMS/ImagingSIMS
    if need_download:
        logging.debug("Downloading d3dcompiler_47.dll")
        os.makedirs(Dir.dllsdir, exist_ok=True)
        if not download_files(
                URL.github,
                [(URL.d3dcompilerpath, File.d3dcompiler_47, File.d3dcompiler_47_md5), ]):
            sys.exit("Failed to download d3dcompiler_47.dll")

    # copy into system32
    destdir = os.path.join(prefix, Dir.system32_inner)
    logging.debug("Copying d3dcompiler_47.dll into %s", destdir)
    shutil.copy(File.d3dcompiler_47, destdir)

    # add DLL override setting
    env = os.environ.copy()
    env.update(WINEDEBUG="-all", WINEPREFIX=prefix)
    if Args.proton:
        env.update(
            WINEESYNC="0" if is_envar_enabled(env, "PROTON_NO_ESYNC") else "1",
            WINEFSYNC="0" if is_envar_enabled(env, "PROTON_NO_FSYNC") else "1",
        )
    exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
    logging.debug("Adding DLL override setting for %s", exename)
    subproc.call(
        wine + [
            "reg", "add",
            "HKCU\\Software\\Wine\\AppDefaults\\{}\\DllOverrides".format(exename),
            "/v", "d3dcompiler_47", "/t", "REG_SZ", "/d", "native", "/f"],
        env=env)


def check_hash(path, digest, hashobj):
    """
    Compare given digest and calculated one.

    This returns True if the two digests match.
    Otherwise this returns False.

    path: Path to the input file
    digest: Expected hex digest string
    hashobj: hashlib object (e.g. hashlib.md5())
    """
    with open(path, "rb") as f_in:
        while True:
            buf = f_in.read(hashobj.block_size * 4096)
            if not buf:
                break
            hashobj.update(buf)
    return hashobj.hexdigest() == digest


def check_libsdl2():
    """
    Check whether SDL2 shared object file is present.

    If SDL2 is detected, this function returns True.
    Otherwise, this returns False.

    Currently the check is done only on Linux systems.
    """
    if platform.system() != "Linux":
        return True

    try:
        ctypes.cdll.LoadLibrary(File.sdl2_soname)
        return True
    except OSError:
        return False


def check_steam_process(use_proton, wine=None, env=None):
    """
    Check whether Steam client is already running.

    If Steam is running, this function returns True.
    Otherwise this returns False.

    use_proton: True if Proton is used, False if Wine is used
    wine: Wine command (path or name)
         (can be None if use_proton is True)
    env: A dictionary that contains environment variables
         (can be None if use_proton is True)
    """
    if use_proton:
        try:
            subproc.check_call(
                ("pgrep", "-u", getuser(), "-x", "steam"), stdout=subproc.DEVNULL)
            return True
        except (OSError, subproc.CalledProcessError):
            return False
    else:
        steam_is_running = False
        argv = (wine, "winedbg", "--command", "info process")
        env_wine = env.copy()
        env_wine["WINEDLLOVERRIDES"] = "winex11.drv="
        if "WINEPREFIX" in env_wine:
            os.makedirs(env_wine["WINEPREFIX"], exist_ok=True)
        try:
            output = subproc.check_output(argv, env=env_wine, stderr=subproc.DEVNULL)
            for line in output.decode("utf-8").splitlines():
                line = line[:-1]  # strip last "'" for rindex()
                try:
                    exename = line[line.rindex("'") + 1:]
                except ValueError:
                    continue
                if exename.lower().endswith("steam.exe"):
                    steam_is_running = True
                    break
        except (OSError, subproc.CalledProcessError) as ex:
            sys.exit("Failed to get Wine process list: " + ex.output.decode("utf-8"))
        return steam_is_running


def download_files(host, files_to_download, progress_count=None):
    """Download files."""
    # pylint: disable=too-many-branches,too-many-locals,too-many-statements

    file_count = progress_count[0] if progress_count else 1
    num_of_files = progress_count[1] if progress_count else len(files_to_download)
    conn = http.client.HTTPSConnection(host)
    try:
        while len(files_to_download) > 0:
            path, dest, md5 = files_to_download[0]
            md5hash = hashlib.md5()
            bufsize = md5hash.block_size * 256
            name = os.path.basename(dest)
            destdir = os.path.dirname(dest)
            name_getting = "[{}/{}] Get: {}".format(file_count, num_of_files, name)
            if len(name) >= 67:
                name = name[:63] + "..."
            if len(name_getting) >= 49:
                name_getting = name_getting[:45] + "..."
            logging.debug(
                "Downloading file https://%s%s to %s", host, path, destdir)

            # make file hierarchy
            os.makedirs(destdir, exist_ok=True)

            # download file
            conn.request("GET", path, headers={"Connection": "keep-alive"})
            res = conn.getresponse()

            if (res.status == 301
                    or res.status == 302
                    or res.status == 303
                    or res.status == 307
                    or res.status == 308):
                # HTTP redirection
                newloc = urllib.parse.urlparse(res.getheader("Location"))
                newpath = newloc.path
                if len(newloc.query) > 0:
                    newpath += "?" + newloc.query
                if not download_files(
                        newloc.netloc,
                        [(newpath, dest, md5), ],
                        (file_count, num_of_files)):
                    return False
                # downloaded successfully from redirected URL
                del files_to_download[0]
                file_count += 1
                conn = http.client.HTTPSConnection(host)
                continue
            if res.status != 200:
                logging.error(
                    "Server %s responded with status code %s.", host, res.status)
                return False

            lastmod = res.getheader("Last-Modified")
            content_len = res.getheader("Content-Length")

            with open(dest, "wb") as f_out:
                downloaded = 0
                while True:
                    buf = res.read(bufsize)
                    if not buf:
                        break
                    downloaded += len(buf)
                    f_out.write(buf)
                    md5hash.update(buf)
                    if content_len:
                        int_content_len = int(content_len)
                        ten_percent_count = int(downloaded * 10 / int_content_len)
                        # downloaded / length [progressbar]
                        # e.g. 555.5K / 777.7K [=======>  ]
                        progress = "{} / {} [{}{}{}]".format(
                            get_short_size(downloaded),
                            get_short_size(int_content_len),
                            "=" * ten_percent_count,
                            ">" if ten_percent_count < 10 else "",
                            " " * max(9 - ten_percent_count, 0),
                        )
                    else:
                        progress = get_short_size(downloaded)
                    print("\r{:49}{:>30}".format(name_getting, progress), end="")

            if md5hash.hexdigest() != md5:
                print("\r{:67}{:>12}".format(name, "MD5 MISMATCH"))
                logging.error("MD5 mismatch for %s", dest)
                return False

            # wget-like timestamping for downloaded files
            if lastmod:
                timestamp = time.mktime(
                    time.strptime(lastmod, "%a, %d %b %Y %H:%M:%S GMT")) - time.timezone
                try:
                    os.utime(dest, (timestamp, timestamp))
                except OSError:
                    pass

            # downloaded successfully
            print("\r{:67}{:>12}".format(name, "[    OK    ]"))

            # skip already downloaded files
            # when trying to download from URL.dlurlalt
            del files_to_download[0]

            file_count += 1
    except (OSError, http.client.HTTPException) as ex:
        logging.error("Failed to download https://%s%s: %s", host, path, ex)
        return False
    finally:
        conn.close()

    return True


def find_discord_ipc_sockets():
    """
    Find Discord IPC sockets.

    This function returns a list of Discord IPC socket paths.
    When no sockets found, an empty list ([]) is returned.
    """
    # Discord creates sockets in $XDG_RUNTIME_DIR
    # "/tmp/" is used as fallback directory
    return glob.glob(
        os.path.join(os.getenv("XDG_RUNTIME_DIR", "/tmp"), "discord-ipc-*"))


def get_current_steam_user():
    """
    Get the current AccountName with saved login credentials.

    If successful this returns the AccountName of the user with saved credentials.
    Otherwise this returns None.

    This function depends on the package "vdf".
    """
    loginvdf_paths = File.loginusers_paths.copy()
    # try Wine Steam directory first when Wine is used
    if Args.wine:
        loginvdf_paths.insert(0, os.path.join(Args.wine_steam_dir, File.loginvdf_inner))
    for path in loginvdf_paths:
        try:
            with open(path) as f_in:
                login_vdf = vdf.parse(f_in)

            for info in login_vdf["users"].values():
                remember = "RememberPassword" in info and info["RememberPassword"] == "1"
                recent_uc = "MostRecent" in info and info["MostRecent"] == "1"
                recent_lc = "mostrecent" in info and info["mostrecent"] == "1"
                if remember and (recent_lc or recent_uc) and "AccountName" in info:
                    return info["AccountName"]
        except (KeyError, OSError, TypeError, ValueError):
            pass
    return None


def get_proton_version(protondir):
    """
    Get Proton version from "version" file.

    This function returns (major, minor) version pair.
    Examples:
      "xxxxxxxxxx proton-5.13-6" -> (5, 13)
      "xxxxxxxxxx 6.1-GE-2" -> (6, 1)
      "xxxxxxxxxx proton-tkg-6.8.r15.gf308782d" -> (6, 8)

    protondir: Proton top directory that has "version" file
    """
    with open(os.path.join(protondir, "version")) as f_version:
        ver = f_version.read(128)
    if "proton-tkg" in ver:
        # 11 = len("proton-tkg") + 1
        major, minor = ver[ver.index("proton-tkg") + 11:].split(".")[:2]
    else:
        ver = ver.replace("proton-", "")
        major, minor = ver[ver.index(" ") + 1:ver.index("-")].split(".")
    return int(major), int(minor)


def get_short_size(size_bytes):
    """
    Get a file size string in short format.

    This function returns:
        "B" size (e.g. 2) when size_bytes < 1KiB
        "KiB" size (e.g. 345.6K) when size_bytes >= 1KiB and size_bytes < 1MiB
        "MiB" size (e.g. 7.8M) when size_bytes >= 1MiB

    size_bytes: File size in bytes
    """
    if size_bytes < 1024:
        return str(size_bytes)
    if size_bytes < 1048576:
        return "{:.1f}K".format(size_bytes / 1024)
    return "{:.1f}M".format(size_bytes / 1048576)


def get_steam_library_dirs(steamdir):
    """
    Get Steam library directories.

    steamdir: A Steam installation path
    """
    # pylint: disable=consider-using-with
    #
    # the 1st Steam library directory is the Steam installation
    steam_libraries = [steamdir, ]
    # additional directories are stored in libraryfolders.vdf
    #
    # old format example:
    #     "LibraryFolders"
    #     {
    #         "TimeNextStatsReport"  "xxxx"
    #         "ContentStatsID"       "xxxx"
    #         "1"                    "/path/to/steam/library1"
    #         "2"                    "/path/to/steam/library2"
    #     }  -> [steamdir, "/path/to/steam/library1", "/path/to/steam/library2"]
    #
    # new format example:
    #    "libraryfolders"
    #    {
    #        "contentstatsid"        "xxx"
    #        "1"
    #        {
    #            "path"        "/path/to/steam/library1"
    #            ...
    #            "apps"
    #            {
    #                "AppId1"        "xxx"
    #                "AppId2"        "xxx"
    #                ...
    #            }
    #        }
    #        "2"
    #        {
    #            "path"        "/path/to/steam/library2"
    #            ...
    #        }
    #    }  -> [steamdir, "/path/to/steam/library1", "/path/to/steam/library2"]
    try:
        try:
            f_vdf = open(os.path.join(steamdir, File.steamlibvdf_inner))
        except OSError:
            f_vdf = open(os.path.join(steamdir, File.steamlibvdf_inner_legacy))
        with f_vdf:
            for line in f_vdf:
                # skip lines that don't have 4 quotes
                if line.count('"') != 4:
                    continue
                # if the 1st quoted stuff is a (natural) number,
                # the 2nd quoted string is a path to Steam library
                try:
                    elements = line.split('"')
                    int(elements[1])
                except (IndexError, ValueError):
                    # in the new format (introduced in summer 2021),
                    # Steam library directory is the value of "path"
                    if elements[1] != "path":
                        continue
                # exclude AppId items in the new format
                if os.path.sep not in elements[3]:
                    continue
                # as of May 2021, Steam can't add a Steam library directory
                # that contains '"' and we can safely use the split element
                steam_libraries.append(elements[3])
    except OSError:
        pass
    return steam_libraries


def is_d3dcompiler_setup_skippable():
    """
    Check whether native d3dcompiler setup can be skipped.

    It can be skipped when:
      * Wine is used and the native DLL is present
      * Proton is used, the native DLL is present, and
        Proton prefix version <= Proton version
                                 ("CURRENT_PREFIX_VERSION" in "proton" script)

    This function returns True if it can be skipped, otherwise False.

    Proton prefix version examples:
      * 6.3-2 (major=6, minor=3)
      * 6.10-GE-1 (major=6, minor=10)
    """
    # first check whether the native DLL is present
    have_native_dll = False
    wine_prefix = Args.prefixdir
    if Args.proton:
        wine_prefix = os.path.join(wine_prefix, "pfx")
    installed_dll_path = os.path.join(wine_prefix, File.d3dcompiler_47_inner)
    try:
        if check_hash(installed_dll_path, File.d3dcompiler_47_md5, hashlib.md5()):
            have_native_dll = True
    except OSError:
        pass
    if not have_native_dll:
        logging.debug("Native d3dcompiler_47.dll is not found")
        return False

    logging.debug("Native d3dcompiler_47.dll is found")
    # if Wine is used, nothing else to check
    if Args.wine:
        return True

    # if Proton is used, get prefix version from the prefix directory
    ver_pfx = dict(major=0, minor=0)
    try:
        with open(os.path.join(Args.prefixdir, "version")) as f_prefix_ver:
            ver = f_prefix_ver.readline().replace("-GE-", "-")
            major, minor = ver[:ver.index("-")].split(".")
            ver_pfx["major"], ver_pfx["minor"] = int(major), int(minor)
    except (OSError, ValueError):
        pass
    if ver_pfx["major"] == 0 or ver_pfx["minor"] == 0:
        # failed to get prefix version, unable to compare
        logging.debug("Failed to get Proton prefix version from version file")
        return False

    # get CURRENT_PREFIX_VERSION from "proton" script
    ver_proton = dict(major=0, minor=0)
    try:
        with open(os.path.join(Args.protondir, "proton")) as f_proton:
            for line in f_proton:
                if line.startswith('CURRENT_PREFIX_VERSION="'):
                    ver = line[line.index('"') + 1:-1]
                    major, minor = ver[:ver.index("-")].split(".")
                    ver_proton["major"], ver_proton["minor"] = int(major), int(minor)
    except (OSError, ValueError):
        pass
    if ver_proton["major"] == 0 or ver_proton["minor"] == 0:
        # failed to get CURRENT_PREFIX_VERSION, unable to compare
        logging.debug("Failed to get CURRENT_PREFIX_VERSION from proton script")
        return False

    logging.debug(
        "Proton:(%d, %d), Prefix:(%d, %d)",
        ver_proton["major"], ver_proton["minor"], ver_pfx["major"], ver_pfx["minor"])
    return (ver_proton["major"] > ver_pfx["major"]
            or (ver_proton["major"] == ver_pfx["major"]
                and ver_proton["minor"] >= ver_pfx["minor"]))


def is_dos_style_abspath(path):
    """
    Check whether the given path is a DOS/Windows style absolute path.

    path: A path string
    """
    if len(path) < 3:
        return False
    drv = path[0]  # drive letter
    # A:65, B:66, ... Z:90, a:97, b:98, ... z:122
    if ord(drv) < 65 or (ord(drv) > 90 and ord(drv) < 97) or ord(drv) > 122:
        return False
    return path[1:3] == ":\\"


def is_envar_enabled(envars, name):
    """
    Check whether the specified environment variable is enabled.

    This returns True if the specified environment variable is
    already defined and set to nonempty and nonzero value.
    Otherwise this returns False.

    envars: A dict of environment variables
    name: The name of environment variable to check
    """
    if name not in envars:
        return False
    value = envars[name]
    return len(value) > 0 and value != "0"


def log_info_formatted_envars_and_args(runner, env_print, env, args):
    """
    Print formatted envars and command line with logging level "info".

    runner: "Steam Runtime helper" or "Wine"
    env_print: Environment variable names to print
    env: A dict of environment variables
    args: Command line
    """
    env_str = ""
    cmd_str = ""
    name_value_pairs = []
    for name in env_print:
        name_value_pairs.append("{}={}".format(name, env[name]))
    env_str += "\n  ".join(name_value_pairs) + "\n  "
    cmd_str += "\n    ".join(args)
    logging.info("Running %s:\n  %s%s", runner, env_str, cmd_str)


def perform_self_update():
    """
    Update files to latest release. Do nothing for Python package.

    This function checks the latest GitHub release first.
    If local version is not up-to-date, this function retrieves the latest
    GitHub release asset (.tar.xz) and replaces existing files with extracted files.
    """
    # get latest release
    logging.info("Retrieving RELEASE from master")
    try:
        with urllib.request.urlopen(URL.release) as f_in:
            release = f_in.readline().rstrip().decode("ascii")
    except OSError as ex:
        sys.exit("Failed to retrieve RELEASE file: {}".format(ex))

    # we don't update when Python package is used
    try:
        with open(os.path.join(os.path.dirname(Dir.scriptdir), "RELEASE")) as f_in:
            # do nothing if the installed version is latest
            if release == f_in.readline().rstrip():
                logging.info("Already up-to-date.")
                return
    except OSError:
        sys.exit("'RELEASE' file doesn't exist. Self update aborted.")

    # retrieve the release asset
    archive_url = URL.rel_tarxz_tmpl.format(release)
    logging.info("Retrieving release asset %s", archive_url)
    try:
        with urllib.request.urlopen(archive_url) as f_in:
            asset_archive = f_in.read()
    except OSError as ex:
        sys.exit("Failed to retrieve release asset file: {}".format(ex))

    # unpack the archive
    logging.info("Unpacking archive %s", archive_url)
    topdir = os.path.dirname(Dir.scriptdir)
    try:
        with tarfile.open(fileobj=io.BytesIO(asset_archive), mode="r:xz") as f_in:
            f_in.extractall(topdir)
    except (OSError, tarfile.TarError) as ex:
        sys.exit("Failed to unpack release asset file: {}".format(ex))

    # update files
    archive_dir = os.path.join(topdir, "truckersmp-cli-" + release)
    for root, _dirs, files in os.walk(archive_dir, topdown=False):
        inner_root = root[len(archive_dir):]
        destdir = topdir + inner_root
        logging.debug("Creating directory %s", destdir)
        os.makedirs(destdir, exist_ok=True)
        for fname in files:
            srcpath = os.path.join(root, fname)
            dstpath = os.path.join(destdir, fname)
            logging.info("Copying %s as %s", srcpath, dstpath)
            os.replace(srcpath, dstpath)
        os.rmdir(root)

    # done
    logging.info("Self update complete")


def print_child_output(proc):
    """
    Print child process output.

    proc: A subprocess.Popen object
    """
    for line in proc.stdout:
        try:
            print(line.decode("utf-8"), end="", flush=True)
        except UnicodeDecodeError:
            print(
                "!! NON UNICODE OUTPUT !!", repr(line), sep="  ", end="", flush=True)


def setup_wine_discord_ipc_bridge():
    """
    Check and download wine-discord-ipc-bridge.

    This checks whether winediscordipcbridge.exe is already downloaded
    and download it only when it is not present.
    When ready, this function returns the path to wine-discord-ipc-bridge.
    """
    # check whether the file is already downloaded
    need_download = True
    try:
        if check_hash(File.ipcbridge, File.ipcbridge_md5, hashlib.md5()):
            logging.debug("winediscordipcbridge.exe is present, MD5 is OK.")
            need_download = False
    except OSError:
        pass

    if need_download:
        # download winediscordipcbridge.exe from official repo
        # https://github.com/0e4ef622/wine-discord-ipc-bridge
        logging.debug("Downloading winediscordipcbridge.exe")
        os.makedirs(Dir.ipcbrdir, exist_ok=True)
        if not download_files(
                URL.github, [(URL.ipcbrpath, File.ipcbridge, File.ipcbridge_md5), ]):
            sys.exit("Failed to download winediscordipcbridge.exe")

    return File.ipcbridge


def set_wine_desktop_registry(prefix, wine, enable):
    """
    Set Wine desktop registry.

    If the 3rd argument (enable) is True, this function enables Wine desktop
    for the given Wine prefix.
    Otherwise, this function disables Wine desktop.

    prefix: Path to Wine prefix to configure
    wine: A list used to run Wine executable
    enable: Whether to enable Wine desktop
    """
    env = os.environ.copy()
    env.update(WINEDEBUG="-all", WINEPREFIX=prefix)
    if Args.proton:
        env.update(
            WINEESYNC="0" if is_envar_enabled(env, "PROTON_NO_ESYNC") else "1",
            WINEFSYNC="0" if is_envar_enabled(env, "PROTON_NO_FSYNC") else "1",
        )
    regkey_explorer = "HKCU\\Software\\Wine\\Explorer"
    regkey_desktops = "HKCU\\Software\\Wine\\Explorer\\Desktops"
    if enable:
        logging.info("Enabling Wine desktop (%s)", Args.wine_desktop)
        subproc.call(
            wine + [
                "reg", "add", regkey_explorer,
                "/v", "Desktop", "/t", "REG_SZ", "/d", "Default", "/f"],
            env=env)
        subproc.call(
            wine + [
                "reg", "add", regkey_desktops,
                "/v", "Default", "/t", "REG_SZ", "/d", Args.wine_desktop, "/f"],
            env=env)
    else:
        logging.info("Disabling Wine desktop")
        subproc.call(
            wine + [
                "reg", "delete", regkey_explorer, "/v", "Desktop", "/f"], env=env)
        subproc.call(
            wine + [
                "reg", "delete", regkey_desktops, "/v", "Default", "/f"], env=env)


def wait_for_steam(use_proton, loginvdf_paths, wine=None, env=None):
    """
    Wait for Steam to be running.

    If use_proton is True and the value of "--native-steam-dir" option is
    "auto" (default), this function also detects
    the Steam installation directory for Proton and returns it.

    On user login the timestamp in
    [steam installation directory]/config/loginusers.vdf gets updated.
    We can detect the timestamp update with comparing timestamps.

    use_proton: True if Proton is used, False if Wine is used
    loginvdf_paths: loginusers.vdf paths
    wine: Wine command (path or name)
         (can be None if use_proton is True)
    env: A dictionary that contains environment variables
         (can be None if use_proton is True)
    """
    # pylint: disable=consider-using-with,too-many-branches,too-many-statements

    steamdir = None
    loginvdfs_checked = []
    loginusers_timestamps = []
    if use_proton and Args.native_steam_dir != "auto":
        # only check the specified vdf path
        loginvdfs_checked.append(os.path.join(Args.native_steam_dir, File.loginvdf_inner))
    else:
        # check all known vdf paths
        loginvdfs_checked += loginvdf_paths
    for path in loginvdfs_checked:
        try:
            stat = os.stat(path)
            loginusers_timestamps.append(stat.st_mtime)
        except OSError:
            loginusers_timestamps.append(0)
    if not check_steam_process(use_proton=use_proton, wine=wine, env=env):
        logging.debug("Starting Steam...")
        if use_proton:
            subproc.Popen(
                ("nohup", "steam"), stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
        else:
            subproc.Popen(
                ("nohup",
                 wine, os.path.join(Args.wine_steam_dir, "steam.exe"), "-no-cef-sandbox"),
                env=env, stdout=subproc.DEVNULL, stderr=subproc.STDOUT)
        waittime = 99
        while waittime > 0:
            print(ngettext(
                "\rWaiting {} second for steam to start up. ",
                "\rWaiting {} seconds for steam to start up. ",
                waittime).format(waittime), end="")
            time.sleep(1)
            waittime -= 1
            for i, path in enumerate(loginvdfs_checked):
                try:
                    stat = os.stat(path)
                    if stat.st_mtime > loginusers_timestamps[i]:
                        print("\r{}".format(" " * 70))  # clear "Waiting..." line
                        logging.debug(
                            "Steam should now be up and running and the user logged in.")
                        steamdir = os.path.dirname(os.path.dirname(loginvdfs_checked[i]))
                        break
                except OSError:
                    pass
            else:
                continue
            break
        else:
            # waited 99 seconds without detecting timestamp change
            print("\r{}".format(" " * 70))
            logging.debug("Steam should be up now.")
            if use_proton:
                if Args.native_steam_dir == "auto":
                    # could not detect steam installation directory
                    # fallback to $XDG_DATA_HOME/Steam
                    steamdir = os.path.join(Dir.XDG_DATA_HOME, "Steam")
                else:
                    # use specified path
                    steamdir = Args.native_steam_dir
    else:
        # Steam is running
        logging.debug("Steam is running")
        if use_proton:
            if Args.native_steam_dir == "auto":
                # detect most recently updated "loginusers.vdf" file
                max_mtime = max(loginusers_timestamps)
                for i, path in enumerate(loginvdfs_checked):
                    if loginusers_timestamps[i] == max_mtime:
                        steamdir = os.path.dirname(os.path.dirname(loginvdfs_checked[i]))
                        break
            else:
                steamdir = Args.native_steam_dir
    return steamdir
