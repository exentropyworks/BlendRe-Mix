/*
 * ***** BEGIN GPL LICENSE BLOCK *****
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation; either version 2
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * ***** END GPL LICENSE BLOCK *****
 */

/* BGE-Remix P12: the bridge's OpenUSD, checked without Remix or Blender.
 *   Windows:  p12_usd_check.exe <bge_remix_bridge.dll> <folder>
 *             loads the built bridge DLL: loading it must not load OpenUSD
 *             (bge_remix_usd.dll) nor tbb12.dll; then brb_usd_selftest
 *             loads them.
 *   Elsewhere: p12_usd_check <folder> [<plugin folder>]
 *             the same self-test, usd_core.cpp linked in (the native checks
 *             of the USD code itself).
 * Exit code: the number of failed checks. */

#include <cstdio>
#include <cstdlib>
#include <string>

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>

typedef const char *(*version_fn)(void);
typedef int (*started_fn)(void);
typedef int (*selftest_fn)(const wchar_t *, char *, int);

static std::wstring wide(const char *s)
{
	int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
	std::wstring w(n > 0 ? size_t(n - 1) : 0, L'\0');
	if (n > 0)
		MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
	return w;
}

int main(int argc, char **argv)
{
	if (argc < 3) {
		fprintf(stderr, "usage: p12_usd_check <bge_remix_bridge.dll> <folder>\n");
		return 1;
	}
	int failed = 0;
	wchar_t full[MAX_PATH * 2];
	GetFullPathNameW(wide(argv[1]).c_str(), MAX_PATH * 2, full, nullptr);
	HMODULE dll = LoadLibraryExW(full, nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
	if (!dll) {
		printf("FAIL  the bridge did not load (error %lu)\n", GetLastError());
		return 1;
	}
	version_fn version = (version_fn)GetProcAddress(dll, "brb_usd_version");
	started_fn started = (started_fn)GetProcAddress(dll, "brb_usd_started");
	selftest_fn selftest = (selftest_fn)GetProcAddress(dll, "brb_usd_selftest");
	if (!version || !started || !selftest) {
		printf("FAIL  the bridge lacks brb_usd_version, brb_usd_started or brb_usd_selftest\n");
		return 1;
	}
	printf("bridge OpenUSD %s\n", version());
	bool idle = started() == 0;
	printf("%s  loading the bridge does not start OpenUSD\n", idle ? "ok   " : "FAIL ");
	failed += idle ? 0 : 1;
	bool no_dll = GetModuleHandleW(L"bge_remix_usd.dll") == nullptr;
	printf("%s  loading the bridge does not load bge_remix_usd.dll\n", no_dll ? "ok   " : "FAIL ");
	failed += no_dll ? 0 : 1;
	bool no_tbb = GetModuleHandleW(L"tbb12.dll") == nullptr;
	printf("%s  loading the bridge does not load tbb12.dll\n", no_tbb ? "ok   " : "FAIL ");
	failed += no_tbb ? 0 : 1;

	static char report[16384];
	int n = selftest(wide(argv[2]).c_str(), report, int(sizeof(report)));
	printf("%s", report);
	failed += n;
	bool now = started() == 1 && GetModuleHandleW(L"bge_remix_usd.dll") && GetModuleHandleW(L"tbb12.dll");
	printf("%s  the self-test loaded bge_remix_usd.dll and tbb12.dll and started OpenUSD\n", now ? "ok   " : "FAIL ");
	failed += now ? 0 : 1;
	printf("%d failed\n", failed);
	return failed;
}

#else

#include "usd_core.h"

int main(int argc, char **argv)
{
	if (argc < 2) {
		fprintf(stderr, "usage: p12_usd_check <folder> [plugin folder]\n");
		return 1;
	}
	int failed = 0;
	bool idle = !brb::usd::started();
	printf("%s  OpenUSD not started before the first call\n", idle ? "ok   " : "FAIL ");
	failed += idle ? 0 : 1;
	std::string report;
	failed += brb::usd::selftest(argc > 2 ? argv[2] : "", argv[1], report);
	printf("%s", report.c_str());
	printf("%d failed\n", failed);
	return failed;
}

#endif
