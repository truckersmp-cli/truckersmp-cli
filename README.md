# truckersmp-cli

truckersmp-cli isn't far from the simplest TruckersMP launcher you could possibly conceive.
It downloads the mod, launches the game, and that's about it. Its aim is to provide linux
players with a launcher that's made to work with Wine. I developped this launcher in
frustration after having spent multiple days trying to make the official launcher work on
linux with Wine.

## Usage ##

You will first have to lauch steam by itself, because for some reason steam refuses to
launch the mod without having been brough up first. Then you can just run the script

```
$ WINEPREFIX=<wine prefix> ./truckersmp-cli <path to your ETS2 install folder>
```

the `WINEPREFIX` is only mandatory if you are not using the standard `~/.wine/`

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
