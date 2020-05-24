CC=x86_64-w64-mingw32-gcc

all: truckersmp-cli.exe autocompletion

truckersmp-cli.exe: truckersmp-cli.c
	$(CC) $< -o $@

autocompletion:
	# genzshcomp <(./truckersmp-cli --help) > _truckermp-cli
	if which genzshcomp &> /dev/null; then \
		./truckersmp-cli --help > helptext; \
		genzshcomp helptext > _truckersmp-cli; \
		rm -f helptext; \
	fi

clean:
	rm -f truckersmp-cli.exe _truckersmp-cli

.PHONY: clean
