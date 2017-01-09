CC=x86_64-w64-mingw32-gcc

all: truckersmp-cli.exe

truckersmp-cli.exe: truckersmp-cli.c
	$(CC) $< -o $@

clean:
	rm -f truckersmp-cli.exe

.PHONY: clean
