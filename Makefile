CC=x86_64-w64-mingw32-gcc

all: truckersmp_cli/truckersmp-cli.exe _truckersmp-cli truckersmp-cli.bash

truckersmp_cli/truckersmp-cli.exe: truckersmp-cli.c
	$(CC) $< -o $@

_truckersmp-cli: gen_completions truckersmp_cli/args.py truckersmp_cli/variables.py truckersmp_cli/proton.json
	./gen_completions --zsh-completion $@

truckersmp-cli.bash: gen_completions truckersmp_cli/args.py truckersmp_cli/variables.py truckersmp_cli/proton.json
	./gen_completions --bash-completion $@

clean:
	rm -f truckersmp_cli/truckersmp-cli.exe _truckersmp-cli truckersmp-cli.bash

.PHONY: clean
