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

/** \file bridge_usd_api.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: the brb_usd_* functions (bge_remix_bridge.h). OpenUSD is in
 * bge_remix_usd.dll beside the bridge (usd/bge_remix_usd.h), loaded here on
 * the first call that needs it; its plugin descriptions are the usd folder
 * beside it. Loading it loads tbb12.dll (oneTBB) from the same folder, or
 * uses the one already in the process (Remix's own, the same 2021.12).
 */

#include <cstdio>
#include <cstring>

#include "bridge_intern.h"
#include "usd/bge_remix_usd.h"

namespace brb {

/* the folder of the bridge DLL, with no slash at the end */
static std::wstring bridge_dir()
{
	HMODULE self = nullptr;
	if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                        reinterpret_cast<LPCWSTR>(&bridge_dir), &self)) {
		return std::wstring();
	}
	wchar_t path[MAX_PATH * 2];
	DWORD n = GetModuleFileNameW(self, path, DWORD(sizeof(path) / sizeof(path[0])));
	if (n == 0 || n >= sizeof(path) / sizeof(path[0]))
		return std::wstring();
	std::wstring dir(path, n);
	size_t slash = dir.find_last_of(L"\\/");
	if (slash != std::wstring::npos)
		dir.resize(slash);
	return dir;
}

namespace {

struct UsdDll {
	HMODULE dll = nullptr;
	bool tried = false;
	std::string error;
	int (*abi_version)(void) = nullptr;
	const char *(*usd_version)(void) = nullptr;
	int (*started)(void) = nullptr;
	int (*selftest)(const char *, const char *, char *, int) = nullptr;
	const bru_capture_api *(*capture_api)(void) = nullptr;
	int (*stage_dump)(const char *, const char *, const char *, char *, int) = nullptr;
	const bru_scene_api *(*scene_api)(void) = nullptr;
	int (*convert)(const char *, const char *, const char *, char *, int) = nullptr;
};
UsdDll g_usd;

template<typename T> bool find_fn(T &fn, const char *name)
{
	fn = reinterpret_cast<T>(GetProcAddress(g_usd.dll, name));
	if (!fn)
		g_usd.error = std::string("bge_remix_usd.dll lacks ") + name;
	return fn != nullptr;
}

/* load bge_remix_usd.dll (once; its error kept) */
bool usd_dll()
{
	if (g_usd.dll)
		return true;
	if (g_usd.tried)
		return false;
	g_usd.tried = true;
	const std::wstring path = bridge_dir() + L"\\bge_remix_usd.dll";
	if (!file_exists(path)) {
		g_usd.error = "no bge_remix_usd.dll beside the bridge (" + utf8(path) +
		              "): this build has no OpenUSD";
		log("OpenUSD: %s", g_usd.error.c_str());
		return false;
	}
	/* its own folder first for what it needs (tbb12.dll) */
	g_usd.dll = LoadLibraryExW(path.c_str(), nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
	if (!g_usd.dll) {
		const DWORD code = GetLastError();
		g_usd.error = "bge_remix_usd.dll did not load (Windows error " + std::to_string(code) +
		              (code == ERROR_MOD_NOT_FOUND ? ": tbb12.dll missing beside it?" : "") + ")";
		log("OpenUSD: %s", g_usd.error.c_str());
		return false;
	}
	if (!find_fn(g_usd.abi_version, "bru_abi_version") || !find_fn(g_usd.usd_version, "bru_usd_version") ||
	    !find_fn(g_usd.started, "bru_started") || !find_fn(g_usd.selftest, "bru_selftest") ||
	    !find_fn(g_usd.capture_api, "bru_capture_get_api") || !find_fn(g_usd.stage_dump, "bru_stage_dump") ||
	    !find_fn(g_usd.scene_api, "bru_scene_get_api") || !find_fn(g_usd.convert, "bru_stage_convert")) {
		FreeLibrary(g_usd.dll);
		g_usd.dll = nullptr;
		log("OpenUSD: %s", g_usd.error.c_str());
		return false;
	}
	if (g_usd.abi_version() != BRU_ABI_VERSION) {
		g_usd.error = "bge_remix_usd.dll is of another version (" + std::to_string(g_usd.abi_version()) +
		              ", the bridge needs " + std::to_string(BRU_ABI_VERSION) + ")";
		FreeLibrary(g_usd.dll);
		g_usd.dll = nullptr;
		log("OpenUSD: %s", g_usd.error.c_str());
		return false;
	}
	log("OpenUSD %s loaded (bge_remix_usd.dll)", g_usd.usd_version());
	return true;
}

}  // namespace

void log_usd_state()
{
	log("OpenUSD: bge_remix_usd.dll %s, tbb12.dll %s", g_usd.dll ? "loaded" : "not loaded",
	    GetModuleHandleW(L"tbb12.dll") ? "loaded" : "not loaded");
}

}  // namespace brb

using namespace brb;

BRB_API const char *brb_usd_version(void)
{
	/* the version built with, without loading anything */
	return "25.11";
}

BRB_API int brb_usd_started(void)
{
	return (g_usd.dll && g_usd.started()) ? 1 : 0;
}

BRB_API const char *brb_usd_plugin_dir(void)
{
	static std::string dir;
	dir = utf8(bridge_dir() + L"\\usd");
	return dir.c_str();
}

BRB_API const bru_capture_api *brb_usd_capture_api(char *r_error, int max_bytes)
{
	const bru_capture_api *api = nullptr;
	std::string err;
	if (!usd_dll()) {
		err = g_usd.error;
	}
	else {
		api = g_usd.capture_api();
		if (!api || api->abi != BRU_ABI_VERSION) {
			err = "bge_remix_usd.dll's capture reader is of another version";
			api = nullptr;
		}
	}
	if (r_error && max_bytes > 0)
		snprintf(r_error, size_t(max_bytes), "%s", err.c_str());
	return api;
}

BRB_API int brb_usd_stage_dump(const char *path, const char *json_path, char *r_error, int max_bytes)
{
	if (!usd_dll()) {
		if (r_error && max_bytes > 0)
			snprintf(r_error, size_t(max_bytes), "%s", g_usd.error.c_str());
		return 0;
	}
	return g_usd.stage_dump(brb_usd_plugin_dir(), path, json_path, r_error, max_bytes);
}

BRB_API const bru_scene_api *brb_usd_scene_api(char *r_error, int max_bytes)
{
	const bru_scene_api *api = nullptr;
	std::string err;
	if (!usd_dll()) {
		err = g_usd.error;
	}
	else {
		api = g_usd.scene_api();
		if (!api || api->abi != BRU_ABI_VERSION) {
			err = "bge_remix_usd.dll's scene reader is of another version";
			api = nullptr;
		}
	}
	if (r_error && max_bytes > 0)
		snprintf(r_error, size_t(max_bytes), "%s", err.c_str());
	return api;
}

BRB_API int brb_usd_convert(const char *src, const char *dst, char *r_error, int max_bytes)
{
	if (!usd_dll()) {
		if (r_error && max_bytes > 0)
			snprintf(r_error, size_t(max_bytes), "%s", g_usd.error.c_str());
		return 0;
	}
	return g_usd.convert(brb_usd_plugin_dir(), src, dst, r_error, max_bytes);
}

BRB_API int brb_usd_selftest(const wchar_t *folder, char *r_report, int max_bytes)
{
	std::string report;
	int failed;
	if (!usd_dll()) {
		report = "FAIL  " + g_usd.error + "\n";
		failed = 1;
	}
	else {
		static char buf[32768];
		const std::string plugins = utf8(bridge_dir() + L"\\usd");
		failed = g_usd.selftest(plugins.c_str(), utf8(folder ? folder : L".").c_str(), buf, int(sizeof(buf)));
		report = buf;
	}
	log("OpenUSD self-test: %d failed\n%s", failed, report.c_str());
	if (r_report && max_bytes > 0) {
		size_t n = report.size() < size_t(max_bytes - 1) ? report.size() : size_t(max_bytes - 1);
		memcpy(r_report, report.data(), n);
		r_report[n] = '\0';
	}
	return failed;
}
