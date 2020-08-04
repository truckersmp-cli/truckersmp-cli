"""
Utilities for truckersmp-cli main script.

Licensed under MIT.
"""

import ctypes
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

vdf_is_available = False
try:
    import vdf
    vdf_is_available = True
except ImportError:
    pass


def activate_native_d3dcompiler_47(prefix, wine):
    """Download/activate native 64-bit version of d3dcompiler_47."""
    # check whether DLL is already downloaded
    md5hash = hashlib.md5()
    need_download = True
    try:
        with open(File.d3dcompiler_47, "rb") as f:
            while True:
                buf = f.read(md5hash.block_size * 4096)
                if not buf:
                    break
                md5hash.update(buf)
        if md5hash.hexdigest() == File.d3dcompiler_47_md5:
            logging.debug("d3dcompiler_47.dll is present, MD5 is OK.")
            need_download = False
    except Exception:
        pass

    # download 64-bit d3dcompiler_47.dll from ImagingSIMS' repo
    # https://github.com/ImagingSIMS/ImagingSIMS
    if need_download:
        logging.debug("Downloading d3dcompiler_47.dll")
        os.makedirs(Dir.dllsdir, exist_ok=True)
        if not download_files(
          URL.raw_github,
          [(URL.d3dcompilerpath, File.d3dcompiler_47, File.d3dcompiler_47_md5), ]):
            sys.exit("Failed to download d3dcompiler_47.dll")

    # copy into system32
    destdir = os.path.join(prefix, "drive_c/windows/system32")
    logging.debug("Copying d3dcompiler_47.dll into {}".format(destdir))
    shutil.copy(File.d3dcompiler_47, destdir)

    # add DLL override setting
    env = os.environ.copy()
    env["WINEDEBUG"] = "-all"
    env["WINEPREFIX"] = prefix
    exename = "eurotrucks2.exe" if Args.ets2 else "amtrucks.exe"
    logging.debug("Adding DLL override setting for {}".format(exename))
    subproc.call(
      [wine, "reg", "add",
       "HKCU\\Software\\Wine\\AppDefaults\\{}\\DllOverrides".format(exename),
       "/v", "d3dcompiler_47", "/t", "REG_SZ", "/d", "native"],
      env=env)


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
        except Exception:
            return False
    else:
        steam_is_running = False
        argv = (wine, "winedbg", "--command", "info process")
        env_wine = env.copy()
        env_wine["WINEDLLOVERRIDES"] = "winex11.drv="
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
        except subproc.CalledProcessError as e:
            sys.exit("Failed to get Wine process list: " + e.output.decode("utf-8"))
        return steam_is_running


def download_files(host, files_to_download, progress_count=None):
    """Download files."""
    file_count = progress_count[0] if progress_count else 1
    num_of_files = progress_count[1] if progress_count else len(files_to_download)
    conn = http.client.HTTPSConnection(host)
    try:
        while len(files_to_download) > 0:
            path, dest, md5 = files_to_download[0]
            md5hash = hashlib.md5()
            bufsize = md5hash.block_size * 256
            name = os.path.basename(path)
            destdir = os.path.dirname(dest)
            name_getting = "[{}/{}] Get: {}".format(file_count, num_of_files, name)
            logging.debug(
              "Downloading file https://{}{} to {}".format(host, path, destdir))

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
                u = urllib.parse.urlparse(res.getheader("Location"))
                if not download_files(
                  u.netloc, [(u.path, dest, md5), ], (file_count, num_of_files)):
                    return False
                # downloaded successfully from redirected URL
                del files_to_download[0]
                file_count += 1
                conn = http.client.HTTPSConnection(host)
                continue
            elif res.status != 200:
                logging.error(
                  "Server {} responded with status code {}.".format(host, res.status))
                return False

            lastmod = res.getheader("Last-Modified")
            content_len = res.getheader("Content-Length")

            with open(dest, "wb") as f:
                downloaded = 0
                while True:
                    buf = res.read(bufsize)
                    if not buf:
                        break
                    downloaded += len(buf)
                    f.write(buf)
                    md5hash.update(buf)
                    if content_len:
                        progress = "{:,} / {:,}".format(downloaded, int(content_len))
                    else:
                        progress = "{:,}".format(downloaded)
                    print("\r{:40}{:>40}".format(name_getting, progress), end="")

            if md5hash.hexdigest() != md5:
                print("\r{:40}{:>40}".format(name, "MD5 MISMATCH"))
                logging.error("MD5 mismatch for {}".format(dest))
                return False

            # wget-like timestamping for downloaded files
            if lastmod:
                timestamp = time.mktime(
                  time.strptime(lastmod, "%a, %d %b %Y %H:%M:%S GMT")) - time.timezone
                try:
                    os.utime(dest, (timestamp, timestamp))
                except Exception:
                    pass

            # downloaded successfully
            print("\r{:40}{:>40}".format(name, "OK"))

            # skip already downloaded files
            # when trying to download from URL.dlurlalt
            del files_to_download[0]

            file_count += 1
    except Exception as e:
        logging.error("Failed to download https://{}{}: {}".format(host, path, e))
        return False
    finally:
        conn.close()

    return True


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
            with open(path) as f:
                login_vdf = vdf.parse(f)

            for info in login_vdf["users"].values():
                remember = "RememberPassword" in info and info["RememberPassword"] == "1"
                recent_uc = "MostRecent" in info and info["MostRecent"] == "1"
                recent_lc = "mostrecent" in info and info["mostrecent"] == "1"
                if remember and (recent_lc or recent_uc) and "AccountName" in info:
                    return info["AccountName"]
        except Exception:
            pass
    return None


def perform_self_update():
    """
    Update files to latest release. Do nothing for Python package.

    This function checks the latest GitHub release first.
    If local version is not up-to-date, this function retrieves the latest
    GitHub release asset (.tar.xz) and replaces existing files with extracted files.
    """
    # we don't update when Python package is used
    try:
        with open(os.path.join(os.path.dirname(Dir.scriptdir), "RELEASE")) as f:
            current_release = f.readline().rstrip()
    except Exception:
        sys.exit("'RELEASE' file doesn't exist. Self update aborted.")

    # get latest release
    logging.info("Retrieving RELEASE from master")
    try:
        with urllib.request.urlopen(URL.release) as f:
            release = f.readline().rstrip().decode("ascii")
    except Exception as e:
        sys.exit("Failed to retrieve RELEASE file: {}".format(e))

    # do nothing if the installed version is latest
    if release == current_release:
        logging.info("Already up-to-date.")
        return

    # retrieve the release asset
    archive_url = URL.rel_tarxz_tmpl.format(release)
    logging.info("Retrieving release asset {}".format(archive_url))
    try:
        with urllib.request.urlopen(archive_url) as f:
            asset_archive = f.read()
    except Exception as e:
        sys.exit("Failed to retrieve release asset file: {}".format(e))

    # unpack the archive
    logging.info("Unpacking archive {}".format(archive_url))
    topdir = os.path.dirname(Dir.scriptdir)
    try:
        with tarfile.open(fileobj=io.BytesIO(asset_archive), mode="r:xz") as f:
            f.extractall(topdir)
    except Exception as e:
        sys.exit("Failed to unpack release asset file: {}".format(e))

    # update files
    archive_dir = os.path.join(topdir, "truckersmp-cli-" + release)
    for root, _dirs, files in os.walk(archive_dir, topdown=False):
        inner_root = root[len(archive_dir):]
        destdir = topdir + inner_root
        logging.debug("Creating directory {}".format(destdir))
        os.makedirs(destdir, exist_ok=True)
        for f in files:
            srcpath = os.path.join(root, f)
            dstpath = os.path.join(destdir, f)
            logging.info("Copying {} as {}".format(srcpath, dstpath))
            os.replace(srcpath, dstpath)
        os.rmdir(root)

    # done
    logging.info("Self update complete")


def wait_for_steam(use_proton, loginvdf_paths, wine=None, env=None):
    """
    Wait for Steam to be running.

    If use_proton is True, this function also detects
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
    steamdir = None
    loginusers_timestamps = []
    for path in loginvdf_paths:
        try:
            st = os.stat(path)
            loginusers_timestamps.append(st.st_mtime)
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
            for i, path in enumerate(loginvdf_paths):
                try:
                    st = os.stat(path)
                    if st.st_mtime > loginusers_timestamps[i]:
                        print("\r{}".format(" " * 70))  # clear "Waiting..." line
                        logging.debug(
                          "Steam should now be up and running and the user logged in.")
                        steamdir = os.path.dirname(
                          os.path.dirname(loginvdf_paths[i]))
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
                # could not detect steam installation directory
                # fallback to $XDG_DATA_HOME/Steam
                steamdir = os.path.join(Dir.XDG_DATA_HOME, "Steam")
    else:
        # Steam is running
        logging.debug("Steam is running")
        if use_proton:
            # detect most recently updated "loginusers.vdf" file
            max_mtime = max(loginusers_timestamps)
            for i, path in enumerate(loginvdf_paths):
                if loginusers_timestamps[i] == max_mtime:
                    steamdir = os.path.dirname(os.path.dirname(loginvdf_paths[i]))
                    break
    return steamdir
