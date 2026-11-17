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

/** \file usd_dll.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: bge_remix_usd.dll's C functions (bge_remix_usd.h) over
 * usd_core.cpp. No C++ object leaves this DLL; OpenUSD's own exceptions are
 * caught here.
 */

#include <cstring>
#include <exception>
#include <string>

#include "bge_remix_usd.h"  /* BGE_REMIX_USD_EXPORTS: CMakeLists.txt */
#include "usd_core.h"

static void copy_out(const std::string &text, char *r_out, int max_bytes)
{
	if (!r_out || max_bytes <= 0)
		return;
	size_t n = text.size() < size_t(max_bytes - 1) ? text.size() : size_t(max_bytes - 1);
	memcpy(r_out, text.data(), n);
	r_out[n] = '\0';
}

BRU_API int bru_abi_version(void)
{
	return BRU_ABI_VERSION;
}

BRU_API const char *bru_usd_version(void)
{
	return brb::usd::version();
}

BRU_API int bru_started(void)
{
	return brb::usd::started() ? 1 : 0;
}

BRU_API int bru_selftest(const char *plugin_dir, const char *folder, char *r_report, int max_bytes)
{
	std::string report;
	int failed;
	try {
		failed = brb::usd::selftest(plugin_dir ? plugin_dir : "", folder ? folder : ".", report);
	}
	catch (const std::exception &e) {
		report += std::string("FAIL  OpenUSD threw: ") + e.what() + "\n";
		failed = 1;
	}
	catch (...) {
		report += "FAIL  OpenUSD threw\n";
		failed = 1;
	}
	copy_out(report, r_report, max_bytes);
	return failed;
}
