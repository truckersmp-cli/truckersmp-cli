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
#include <windows.h>


#define BUF_SIZE 1024


static void inject(char *cmd, char *dll);
static void die(const char *fmt, ...);
static int upprivileges();


int
main(int argc, char **argv)
{
	int i, len;
	char *exepath = "\\bin\\win_x64\\eurotrucks2.exe";
	char *dllpath = "\\core_ets2mp.dll";
	const char opts[] = "-nointro -64bit";
	char cmd[BUF_SIZE];
	char dll[BUF_SIZE];

	if (argc < 3)
		die("Usage: truckersmp-cli GAMEDIR MODDIR\n");

	for (i = 1; i < 3; i++) { /* '\' and '/' can be mixed in windows type pathes */
		len = strlen(argv[i]);
		if (argv[i][len - 1] == '\\' || argv[i][len - 1] == '/')
			argv[i][len - 1] = '\0';
	}

	snprintf(cmd, sizeof(cmd), "%s%s %s", argv[1], exepath, opts);
	snprintf(dll, sizeof(dll), "%s%s", argv[2], dllpath);

	SetEnvironmentVariable("SteamGameId", "227300");
	SetEnvironmentVariable("SteamAppID", "227300");

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
		die("CreateProcess(\"%s\") failed; error code = 0x%08X\n", cmd, GetLastError());

	// Allocate a page in memory for the arguments of LoadLibrary.
	page = VirtualAllocEx(pi.hProcess, NULL, MAX_PATH, MEM_COMMIT|MEM_RESERVE, PAGE_READWRITE);
	if (page == NULL)
		die("VirtualAllocEx failed; error code = 0x%08X\n", GetLastError());

	/* Inject the core dll into the process address space */
	len = strlen(dll) + 1;
	if (len > MAX_PATH)
		die("path length (%d) exceeds MAX_PATH (%d).\n", len, MAX_PATH);

	if (GetFileAttributes(dll) == INVALID_FILE_ATTRIBUTES)
		die("unable to locate library (%s).\n", dll);

	/* Write library path to the page used for LoadLibrary arguments. */
	if (!WriteProcessMemory(pi.hProcess, page, dll, len, NULL))
		die("WriteProcessMemory failed; error code = 0x%08X\n", GetLastError());

	/* Inject the library */
	hThread = CreateRemoteThread(pi.hProcess, NULL, 0, (LPTHREAD_START_ROUTINE) LoadLibraryA, page, 0, NULL);
	if (!hThread)
		die("CreateRemoteThread failed; error code = 0x%08X\n", GetLastError());

	if (WaitForSingleObject(hThread, INFINITE) == WAIT_FAILED)
		die("WaitForSingleObject failed; error code = 0x%08X\n", GetLastError());

	CloseHandle(hThread);

	if (ResumeThread(pi.hThread) == -1)
		die("ResumeThread failed; error code = 0x%08X\n", GetLastError());

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
