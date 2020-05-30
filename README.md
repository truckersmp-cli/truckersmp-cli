# truckersmp-cli

truckersmp-cli is an easy to use script to download TruckersMP and start
the game afterwards.

It can install and update the windows version of
American Truck Simulator (`-a`, `--ats`) or Euro Truck Simulator 2 (`-e`, `--ets2`)
with steamcmd (`-u`, `--update`) and handles starting (`-s`, `--start`) the mod
through Proton aka. Steam Play (`-p`, `--proton`) or Wine (`-w`, `--wine`).

It needs a working Steam installation for starting through Proton or to update
the game files. It will stop all running Steam processes while updating to
prevent Steam asking for password and guard code at the next startup.
When using standard Wine you should start the windows version of Steam first.

## Usage

<pre>
<b>truckersmp-cli</b> [-a|e] [-p|w] [-hsuvc] [-g <i>path</i> -i <i>appid</i> -m <i>path</i> -n <i>name</i> -o <i>path</i> -x <i>path</i> -l <i>path</i>]
</pre>

### Options

Short option|Long option|Description
---|---|---
`-a`|`--ats`|Use American Truck Simulator
`-e`|`--ets2`|Use Euro Truck Simulator 2 [Default if neither ATS or ETS2 are specified]
`-p`|`--proton`|Start the game with Proton [Default on Linux if neither Proton or Wine are specified]
`-w`|`--wine`|Start the game with Wine [Default on other systems if neither Proton or Wine are specified]
`-h`|`--help`|Show help
`-s`|`--start`|Start the game [Default if neither start or update are specified]
`-u`|`--update`|Update the game [Default if neither start or update are specified]
`-v`|`--verbose`|Verbose output (none:error, once:info, twice or more:debug)
`-g DIR`|`--gamedir DIR`|Choose a different directory for the game files [Default: `$XDG_DATA_HOME/truckersmp-cli/(Game name)/data`]
`-i APPID`|`--proton-appid APPID`|Choose a different AppId for Proton (Needs an update for changes)
`-m DIR`|`--moddir DIR`|Choose a different directory for the mod files [Default: `$XDG_DATA_HOME/truckersmp-cli/TruckersMP`, Fallback: `./truckersmp`]
`-n NAME`|`--account NAME`|Steam account name to use
`-o DIR`|`--protondir DIR`|Choose a different Proton directory [Default: $XDG_DATA_HOME/truckersmp-cli/Proton]
`-l LOG`|`--logfile LOG`|Write log into LOG, `-vv` option is recommended [Default: Empty string (only stderr)] Note: Messages from Steam/steamcmd won't be written, only from this script (Game logs are written into `My Documents/{ETS2,ATS}MP/logs/client_*.log`)
`-x DIR`|`--prefixdir DIR`|Choose a different directory for the prefix [Default: `$XDG_DATA_HOME/truckersmp-cli/(Game name)/prefix`]
`-c`|`--activate-native-d3dcompiler-47`|Activate native 64-bit `d3dcompiler_47.dll` when starting (Needed for D3D11 renderer)
(Not available)|`--use-wined3d`|Use OpenGL-based D3D11 instead of DXVK when using Proton
(Not available)|`--enable-d3d11`|Use Direct3D 11 instead of OpenGL
(Not available)|`--disable-proton-overlay`|Disable Steam Overlay when using Proton
(Not available)|`--beta VERSION`|Set game version to VERSION, useful for downgrading (e.g. `temporary_1_35`)
(Not available)|`--singleplayer`|Start singleplayer game, useful for save editing, using/testing DXVK in singleplayer, etc.)

### Proton versions and AppIds

Version|AppId
---|---
5.0 (Default)|[1245040](https://steamdb.info/app/1245040/)
4.11|[1113280](https://steamdb.info/app/1113280/)

## Rendering backends

### OpenGL

* Stable and faster than wined3d. But slower than DXVK.
* Useful if you're not using Vulkan-capable GPU.
* Used by default.

### Direct3D 11 (DXVK or wined3d)

* Faster than OpenGL when DXVK is used.
    * DXVK requires Vulkan support.
    * DXVK 1.4.6 or newer is needed because older versions have rendering issue. If you're using Proton, use 4.11-10 or newer.
* **Windows native 64-bit `d3dcompiler_47.dll` is needed.** This is not needed for singleplayer.
    * Without native DLL, TruckersMP login screen will not be shown.
    * When `-c`(`--activate-native-d3dcompiler-47`) is specified with `-s`(`--start`), `truckersmp-cli` downloads/activates the DLL.
    * Once the DLL is activated, no need to specify `-c` option again.
* Proton uses DXVK by default.
    * When using Proton, wined3d can be used by specifying `--use-wined3d`, but it's not recommended because this is slower than OpenGL.
* Used only when `--enable-d3d11` is specified.

## Default directories

### Game data

Game|Path
---|---
ETS2|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/`
ATS|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/`

### Wineprefix

Game|Path
---|---
ETS2|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/`
ATS|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/`

### Game logs

Game|Proton|Wine
---|---|---
ETS2|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/drive_c/users/steamuser/My Documents/ETS2MP/logs/`|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/drive_c/users/(os_login_name)/My Documents/ETS2MP/logs/`
ATS|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/drive_c/users/steamuser/My Documents/ATSMP/logs/`|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/drive_c/users/(os_login_name)/My Documents/ATSMP/logs/`

### Singleplayer mods and ProMods

Game|Proton|Wine
---|---|---
ETS2|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/drive_c/users/steamuser/My Documents/Euro Truck Simulator 2/mod/`|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/drive_c/users/(os_login_name)/My Documents/Euro Truck Simulator 2/mod/`
ATS|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/drive_c/users/steamuser/My Documents/American Truck Simulator/mod/`|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/drive_c/users/(os_login_name)/My Documents/American Truck Simulator/mod/`

### Season (weather) mods for ETS2MP/ATSMP

Game|Proton|Wine
---|---|---
ETS2|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/drive_c/users/steamuser/My Documents/ETS2MP/mod/`|`$XDG_DATA_HOME/truckersmp-cli/Euro Truck Simulator 2/prefix/pfx/drive_c/users/(os_login_name)/My Documents/ETS2MP/mod/`
ATS|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/drive_c/users/steamuser/My Documents/ATSMP/mod/`|`$XDG_DATA_HOME/truckersmp-cli/American Truck Simulator/prefix/pfx/drive_c/users/(os_login_name)/My Documents/ATSMP/mod/`

See [TruckersMP Knowledge Base](https://truckersmp.com/knowledge-base).

## Examples

### Install Euro Truck Simulator 2

```
$ ./truckersmp-cli -eu -n your_steam_account
```

### Update Euro Truck Simulator 2 and start TruckersMP using Proton

```
$ ./truckersmp-cli -eusp -n your_steam_account
```

### Only start TruckersMP without updating Euro Truck Simulator 2 using Wine

Note: Make sure Wine Steam is running in the same `$WINEPREFIX`!

```
$ ./truckersmp-cli -esw
```

### Using a different prefix location

Note:
* While the prefix for Wine will point directly to the prefix location,
Proton uses a subfolder `pfx` for the actual prefix and points to the parent folder.
* Your prefix must be 64bits, the mod is not 32bits-compatible.

```
$ ./truckersmp-cli -esp -x "/path/to/prefix"
$ ./truckersmp-cli -esw -x "/path/to/prefix/pfx"
```

## Warning

* Every time `steamcmd` is used the Steam client thinks every Proton game has an update with 0 Bytes.
    https://github.com/ValveSoftware/steam-for-linux/issues/5644
* If Steam is running while `steamcmd` uses the same session credentials the Steam client looses all
    connections and asks for the password and the guard code at the next startup.
    This script closes all Steam processes before acting with `steamcmd` so **starting an update with a shortcut out of
    the Steam client won't work** because Steam waits for the script and the script waits for Steam.

## Runtime dependencies

### Required

* `python3` 3.3 (released in September 2012) or later
* `steam` either the native Linux version in use with Proton or the Windows Steam in use with Wine
* x86_64 version of SDL2 library
    * `libsdl2-2.0-0` on Debian-based systems
    * `media-libs/libsdl2` on Gentoo Linux
    * `sdl2` on Arch Linux
    * `SDL2` on RPM-based systems

### Optional

* `wine` as a possible replacement to Proton
* `git` to clone this repo and self update the script
* [`vdf`][python-vdf] to automatically detect the steam account with saved credentials

## Buildtime dependencies

### Optional

* [`genzshcomp`][python-genzshcomp] to generate bash/zsh completions

## Install

Just clone this repository wherever you want.

## Build

You can build the executable on Linux, in fact the executable provided has built on a Linux
machine. Just install mingw-w64 and then

```
$ make
```

## Credits

I was greatly inspired by mewrev's [Inject](https://github.com/mewrev/inject) tool
and TheUnknownNO's unofficial [TruckersMP-Launcher](https://github.com/TheUnknownNO/TruckersMP-Launcher).

Amit Malik's [article](http://securityxploded.com/dll-injection-and-hooking.php) on dll injection was also a great help.

[python-genzshcomp]: https://github.com/hhatto/genzshcomp
[python-vdf]: https://github.com/ValvePython/vdf
