# truckersmp-cli

truckersmp-cli isn't far from the simplest TruckersMP launcher you could possibly conceive.
It downloads the mod, launches the game, and that's about it. Its aim is to provide linux
players with a launcher that's made to work with Wine. I developped this launcher in
frustration after having spent multiple days trying to make the official launcher work on
linux with Wine.

## Usage ##
### General ###
<pre>
<b>truckersmp-cli</b> [-huv] [-d <i>path</i>] GAMEDIR
    -d <i>path</i>     mod directory, defaults to <i>$XDG_CACHE_HOME/truckersmp-cli</i>
    -h          this help
    -u          update mod files only
    -v          verbose
    GAMEDIR     path to ETS2 od ATS game data, optional with -u
</pre>

By default `truckersmp-cli` stores the mod in `$XDG_CACHE_HOME/truckersmp-cli`.
This is overrided as a fallback to the old behavior if a folder named `truckersmp`
is found in the script directory.
You can specify your own directory by using `-d path`.

### Example ###
You will first have to lauch steam by itself, because for some reason steam refuses to
launch the mod without having been brough up first. Then you can just run the script

```
$ WINEPREFIX=<wine prefix> ./truckersmp-cli <path to your ETS2 install folder>
```

the `WINEPREFIX` is only mandatory if you are not using the standard `~/.wine/`

**WARNING !** Your WINEPREFIX must be 64bits, the mod is not 32bits-compatible.

## Install ##

Just clone this repository wherever you want your TruckersMP installation to be.

## Build ##

You can build this program on linux, in fact the executable provided has built on a linux
machine. Just install mingw64-w64 and then

```
$ make
```

## Credits ##

I was greatly inspired by mewrev's [Inject](https://github.com/mewrev/inject) tool
and TheUnknownNO's unofficial [TruckersMP-Launcher](https://github.com/TheUnknownNO/TruckersMP-Launcher).

Amit Malik's [article](http://securityxploded.com/dll-injection-and-hooking.php) on dll injection was also a great help.
