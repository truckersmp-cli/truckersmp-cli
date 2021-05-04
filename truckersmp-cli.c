/* See LICENSE file for copyright and license details.
 * Inspired by mewrev "inject" tool
 * https://github.com/mewrev/inject
 *
 * This barebone truckersMP launcher only provides the most basic launching
 * capability: it perform the dll injection needed to start the mod and
 * nothing else.
 *
 * Author : lhark
 */

#include <stdio.h>
#include <string.h>
#include <windows.h>
#include <unistd.h>


#define BUF_SIZE 1024
#define STEAMID_ETS2 "227300"
#define STEAMID_ATS "270880"


static void inject(char *cmd, char *dll);
static void die(const char *fmt, ...);
static void dieonerror(const char* function, const char* cmd);
static int upprivileges();


int
main(int argc, char **argv)
{
	int i, len;
	char opts[BUF_SIZE] = {0};
	char cmd[BUF_SIZE];
	char dll[BUF_SIZE];
	char *exepath, *dllpath, *steamid;

	if (argc < 3)
		die("Usage: truckersmp-cli GAMEDIR MODDIR GAME_OPTIONS...\n");

	for (i = 1; i < 3; i++) { /* '\' and '/' can be mixed in windows type pathes */
		len = strlen(argv[i]);
		if (argv[i][len - 1] == '\\' || argv[i][len - 1] == '/')
			argv[i][len - 1] = '\0';
	}

	snprintf(cmd, sizeof(cmd), "%s%s", argv[1], "\\bin\\win_x64\\eurotrucks2.exe");
	if (access (cmd, F_OK) != -1) {
		exepath = "\\bin\\win_x64\\eurotrucks2.exe";
		dllpath = "\\core_ets2mp.dll";
		steamid = STEAMID_ETS2;
	} else {
		snprintf(cmd, sizeof(cmd), "%s%s", argv[1], "\\bin\\win_x64\\amtrucks.exe");
		if (access (cmd, F_OK) != -1) {
			exepath = "\\bin\\win_x64\\amtrucks.exe";
			dllpath = "\\core_atsmp.dll";
			steamid = STEAMID_ATS;
		} else {
			die ("Unable to find ETS2 or ATS in this GAMEDIR.");
		}
	}

	if (argc == 3) {
		/* if game options are not given, use default options for compatibility */
		strcpy(opts, " -nointro -64bit");
	} else {
		/* build game options string */
		len = strlen(argv[1]) + strlen(exepath) + 1;  /* game exe path + "\0" */
		for (i = 3; i < argc; i++) {
			/* check whether a space and the option can be added to the buffer */
			len += 1 + strlen(argv[i]);  /* 1 = strlen(" ") */
			if (len <= BUF_SIZE) {
				strcat(opts, " ");
				strcat(opts, argv[i]);
			} else {
				die("Game options are too long.");
			}
		}
	}

	snprintf(cmd, sizeof(cmd), "%s%s%s", argv[1], exepath, opts);
	snprintf(dll, sizeof(dll), "%s%s", argv[2], dllpath);

	SetEnvironmentVariable("SteamGameId", steamid);
	SetEnvironmentVariable("SteamAppID", steamid);

	upprivileges();
	inject(cmd, dll);
	return 0;
}

static void
inject(char *cmd, char *dll)
{
	int len;
	void *page;
	HANDLE hThread;
	STARTUPINFO si = {0};
	PROCESS_INFORMATION pi = {0};

	si.cb = sizeof(STARTUPINFO);
	if (!CreateProcess(NULL, cmd, NULL, NULL, FALSE, CREATE_SUSPENDED, NULL, NULL, &si, &pi))
		dieonerror("CreateProcess()", cmd);

	// Allocate a page in memory for the arguments of LoadLibrary.
	page = VirtualAllocEx(pi.hProcess, NULL, MAX_PATH, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE);
	if (page == NULL)
		dieonerror("VirtualAllocEx()", "[]");

	/* Inject the core dll into the process address space */
	len = strlen(dll) + 1;
	if (len > MAX_PATH)
		die("path length (%d) exceeds MAX_PATH (%d).\n", len, MAX_PATH);

	if (GetFileAttributes(dll) == INVALID_FILE_ATTRIBUTES)
		die("unable to locate library (%s).\n", dll);

	/* Write library path to the page used for LoadLibrary arguments. */
	if (!WriteProcessMemory(pi.hProcess, page, dll, len, NULL))
		dieonerror("WriteProcessMemory", "[]");

	/* Inject the library */
	hThread = CreateRemoteThread(pi.hProcess, NULL, 0, (LPTHREAD_START_ROUTINE) LoadLibraryA, page, 0, NULL);
	if (!hThread)
		dieonerror("CreateRemoteThread", "[]");

	if (WaitForSingleObject(hThread, INFINITE) == WAIT_FAILED)
		dieonerror("WaitForSingleObject", "[]");

	CloseHandle(hThread);

	if (ResumeThread(pi.hThread) == -1)
		dieonerror("ResumeThread", "[]");

	CloseHandle(pi.hProcess);
	VirtualFreeEx(pi.hProcess, page, MAX_PATH, MEM_RELEASE);
}

static int
upprivileges()
{
	HANDLE Token;
	TOKEN_PRIVILEGES tp;
	if (OpenProcessToken(GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &Token)) {
		LookupPrivilegeValue(NULL, SE_DEBUG_NAME, &tp.Privileges[0].Luid);
		tp.PrivilegeCount = 1;
		tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
		AdjustTokenPrivileges(Token, 0, &tp, sizeof(tp), NULL, NULL);
	}
}


static void
die(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);

	if (fmt[0] && fmt[strlen(fmt)-1] == ':') {
		fputc(' ', stderr);
		perror(NULL);
	} else {
		fputc('\n', stderr);
	}

	exit(1);
}


static void
dieonerror(const char* function, const char* cmd)
{
	LPVOID buf;
	DWORD err = GetLastError();

	FormatMessage(
		FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
		NULL, err, MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
		(LPTSTR) &buf, 0, NULL );

	fprintf(stderr, "%s with argument \"%s\" failed with error %d: %s\n", function, cmd, err, buf);

	LocalFree(buf);
	ExitProcess(err);
}
