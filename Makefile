CC=x86_64-w64-mingw32-gcc

all: truckersmp-cli.exe _truckersmp-cli truckersmp-cli.bash

truckersmp-cli.exe: truckersmp-cli.c
	$(CC) $< -o $@

_truckersmp-cli:
	if command -v genzshcomp > /dev/null; then \
		./truckersmp-cli --help | genzshcomp -f zsh > _truckersmp-cli; \
	fi

truckersmp-cli.bash:
	if command -v genzshcomp > /dev/null; then \
		./truckersmp-cli --help | genzshcomp -f bash > truckersmp-cli.bash; \
	fi

clean:
	rm -f truckersmp-cli.exe _truckersmp-cli truckersmp-cli.bash

.PHONY: clean
