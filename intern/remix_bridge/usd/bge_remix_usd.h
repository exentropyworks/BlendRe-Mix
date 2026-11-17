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

/** \file bge_remix_usd.h
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: the plain C interface of bge_remix_usd.dll, the bridge's
 * OpenUSD (25.11, built in whole). Only the bridge loads it, on the first
 * import, export or check (LoadLibrary + GetProcAddress of these), so
 * OpenUSD and its threading library (tbb12.dll) are in a game's process only
 * when it uses them. Only C passes between the two DLLs: each has its own
 * static C runtime. Strings and paths are UTF-8.
 */

#ifndef __BGE_REMIX_USD_H__
#define __BGE_REMIX_USD_H__

#ifdef __cplusplus
extern "C" {
#endif

#if !defined(_WIN32)
#  define BRU_API __attribute__((visibility("default")))  /* the native checks */
#elif defined(BGE_REMIX_USD_EXPORTS)
#  define BRU_API __declspec(dllexport)
#else
#  define BRU_API __declspec(dllimport)
#endif

/* Bumped whenever a function below changes; the bridge refuses a
 * bge_remix_usd.dll with another value. 1: P12 round 1. */
#define BRU_ABI_VERSION 1

BRU_API int bru_abi_version(void);

/* "25.11" */
BRU_API const char *bru_usd_version(void);

/* 1 once OpenUSD was started in this process, else 0 */
BRU_API int bru_started(void);

/* the self-test of usd_core.h, with OpenUSD's plugin descriptions in
 * plugin_dir; the report cut to max_bytes. Returns the failed checks. */
BRU_API int bru_selftest(const char *plugin_dir, const char *folder, char *r_report, int max_bytes);

#ifdef __cplusplus
}
#endif

#endif /* __BGE_REMIX_USD_H__ */
