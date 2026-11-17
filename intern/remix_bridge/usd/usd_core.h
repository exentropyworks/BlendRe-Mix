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

/** \file usd_core.h
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: the bridge's OpenUSD code (OpenUSD 25.11 built in as a
 * static library, namespace pxrBgeRemix_v0_25_11), inside bge_remix_usd.dll
 * (usd_dll.cpp gives it its plain C interface). Plain C++ with no Windows or
 * Remix headers, so the native checks build it on any system.
 */

#ifndef __USD_CORE_H__
#define __USD_CORE_H__

#include <string>

namespace brb {
namespace usd {

/* "25.11": the OpenUSD the bridge was built with (starts nothing) */
const char *version();

/* Whether OpenUSD was started (its plugins found) in this process */
bool started();

/* Start OpenUSD: find its plugins (plugin_dir, UTF-8: the usd folder beside
 * the DLL; or BGE_REMIX_USD_PLUGINPATH). False, with the reason in r_error,
 * when they or the file formats it needs are missing (checked before OpenUSD
 * is asked: it stops the whole program when it finds none). Safe to call
 * again. */
bool start(const std::string &plugin_dir, std::string &r_error);

/* Write a small stage into the folder (UTF-8): a box mesh with UVs, an RTX
 * Remix (AperturePBR) material bound to it, a rigid body with mass and a
 * collision shape; as text (.usda) and binary (.usdc). Read each back and
 * check every value, and let OpenUSD's own UsdPhysics reader find the body
 * and its shape. Returns the number of failed checks (0: all passed); the
 * report lists every check. */
int selftest(const std::string &plugin_dir, const std::string &folder, std::string &r_report);

}  // namespace usd
}  // namespace brb

#endif /* __USD_CORE_H__ */
