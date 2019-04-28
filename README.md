# truckersmp-cli

truckersmp-cli is an easy to use script to download TruckersMP and start the
game afterwards.

It can install and update the windows version of
American Truck Simulator (`-a`) or Euro Truck Simulator 2 (`-e`)
with steamcmd (`-u`) and handles starting (`-s`) the mod through Proton aka.
Steam Play (`-p`) or Wine (`-w`).

It needs a working Steam installation in `$XDG_DATA_HOME/Steam` for starting
through Proton or to update the game files. It will
stop all running Steam processes while updating to prevent Steam asking
for password and guard code at the next startup.
When using standard Wine you should start the windows version of Steam first.

## Usage
<pre>
    <b>truckersmp-cli</b> [-a|e] [-p|w] [-hsuv] [-g <i>path</i> -i <i>appid</i> -m <i>path</i> -n <i>name</i> -o <i>path</i> -x <i>path</i>]

    -a  Use American Truck Simulator.
        or
    -e  Use Euro Truck Simulator 2.
    
    -p  Start the game with Proton.
        or
    -w  Start the game with Wine

    -h  Display this help.
    -s  Start the game.
    -u  Update the game.
    -v  verbose

    -g <i>path</i>     Choose a different parent directory for the game files.
                  Default: <i>$XDG_DATA_HOME/truckersmp-cli/$GAME/data</i>
    -i <i>appid</i>    Choose a different appid for Proton
                  Needs an update for changes.
                  Proton 4.2:	      <i>1054830</i> (Default)
                  Proton 3.16 Beta: <i>996510</i>
                  Proton 3.16:      <i>961940</i>
                  Proton 3.7 Beta:  <i>930400</i>
                  Proton 3.7:       <i>858280</i>
                  See https://github.com/ValveSoftware/Proton/issues/162 if you
                  want to use a version lower than 3.16 Beta.
    -m <i>path</i>     Choose a different directory for the mod files.
                  Default: <i>$XDG_DATA_HOME/truckersmp-cli/TruckersMP</i>
                  Fallback: <i>./truckersmp</i>
    -n <i>name</i>     Steam account name to use.
                  This account should own the game and ideally is logged in with saved
                  credentials.
    -o <i>path</i>     Choose a different Proton directory.
                  Default: <i>$XDG_DATA_HOME/truckersmp-cli/Proton</i>
                  While updating any previous version in this folder gets changed
                  to the given (-i) or default Proton version.
    -x <i>path</i>     Choose a different parent directory for the prefix.
                  Default: <i>$XDG_DATA_HOME/truckersmp-cli/$GAME/prefix</i>
</pre>

## Examples
### Install Euro Truck Simulator 2
~~~
$ ./truckersmp-cli -eu -n steamuser
~~~

### Update Euro Truck Simulator 2 and start TruckersMP using Proton
~~~
$ ./truckersmp-cli -eusp -n steamuser
~~~

### Only start TruckersMP without updating Euro Truck Simulator 2 using Wine
Note:
* Make sure wine steam is running in the same `$WINEPREFIX`!
* Default prefix folder is `$XDG_DATA_HOME/truckersmp-cli/$GAME/prefix`.

~~~
$ ./truckersmp-cli -esw
~~~

### Using a different prefix location
Note:
* While the prefix for Wine will point directly to the prefix location,
Proton uses a subfolder `pfx` for the actual prefix and points to the parent folder.
* Your prefix must be 64bits, the mod is not 32bits-compatible.

~~~
$ ./truckersmp-cli -esp -x "/path/to/prefix"
$ ./truckersmp-cli -esw -x "/path/to/prefix/pfx"
~~~

## Warning
* Every time `steamcmd` is used the steam client thinks every proton game has an update with 0 Bytes.
    https://github.com/ValveSoftware/steam-for-linux/issues/5644
* If steam is running while `steamcmd` uses the same session credentials the steam client looses all
    connections and asks for the password and the guard code at the next startup.
    This script closes all steam processes before acting with `steamcmd` so **starting an update with a shortcut out of
    the steam client won't work** because steam waits for the script and the script waits for steam.

## Dependencies

### Required
* `python` in version 3
* `steam` either the native linux version in use with proton or the windows steam in use with wine
* `wget` to download the mod files

### Optional
* `inotify-tools` to detect if steam is started completely
* `steamcmd` for updating proton or the game files, will be fetched automatically by the script if not present in `$PATH`
* `wine` as a possible replacement to proton
* `git` to clone this repo and self update the script

## Install ##

Just clone this repository wherever you want.

## Build ##

You can build the executable on linux, in fact the executable provided has built on a linux
machine. Just install mingw64-w64 and then

```
$ make
```

## Credits ##

I was greatly inspired by mewrev's [Inject](https://github.com/mewrev/inject) tool
and TheUnknownNO's unofficial [TruckersMP-Launcher](https://github.com/TheUnknownNO/TruckersMP-Launcher).

Amit Malik's [article](http://securityxploded.com/dll-injection-and-hooking.php) on dll injection was also a great help.
    
