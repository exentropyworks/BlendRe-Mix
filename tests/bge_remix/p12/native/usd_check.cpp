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

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

#include "bge_remix_usd.h"

/* a capture as JSON (what the reader gave): for check_capture.py */
static std::string jstr(const char *s)
{
	std::string out = "\"";
	for (const char *c = s ? s : ""; *c; c++) {
		if (*c == '"' || *c == '\\')
			out += '\\';
		if (*c == '\n') {
			out += "\\n";
			continue;
		}
		out += *c;
	}
	return out + "\"";
}

static std::string jnum(double v)
{
	if (!std::isfinite(v))
		return "null";
	char buf[64];
	snprintf(buf, sizeof(buf), "%.9g", v);
	return buf;
}

static std::string jhex(uint64_t h)
{
	char buf[32];
	snprintf(buf, sizeof(buf), "\"%016llX\"", (unsigned long long)h);
	return buf;
}

static std::string jarr(const double *v, int n)
{
	std::string out = "[";
	for (int i = 0; i < n; i++)
		out += (i ? ", " : "") + jnum(v[i]);
	return out + "]";
}

static std::string jarrf(const float *v, int n)
{
	std::string out = "[";
	for (int i = 0; i < n; i++)
		out += (i ? ", " : "") + jnum(v[i]);
	return out + "]";
}

/* read a capture and write what came out; returns 0 when it was read */
static int dump_capture(const bru_capture_api *api, const char *plugins, const char *path, const char *json)
{
	char err[2048] = "";
	bru_capture *cap = api->open(plugins, path, err, int(sizeof(err)));
	FILE *f = fopen(json, "w");
	if (!f)
		return 1;
	if (!cap) {
		fprintf(f, "{\"error\": %s}\n", jstr(err).c_str());
		fclose(f);
		printf("capture %s: not read (%s)\n", path, err);
		return 2;
	}
	bru_capture_info info;
	api->info(cap, &info);
	std::string o = "{\"meters_per_unit\": " + jnum(info.meters_per_unit) + ", \"z_up\": " + std::to_string(info.z_up) +
	                ", \"game_name\": " + jstr(info.game_name) + ", \"report\": " + jstr(info.report);
	o += ",\n \"meshes\": [";
	for (int i = 0; i < info.mesh_count; i++) {
		bru_mesh m;
		api->mesh(cap, i, &m);
		o += std::string(i ? ",\n  " : "\n  ") + "{\"hash\": " + jhex(m.hash) + ", \"name\": " + jstr(m.name) +
		     ", \"vertices\": " + std::to_string(m.vertex_count) + ", \"faces\": " + std::to_string(m.face_count) +
		     ", \"corners\": " + std::to_string(m.corner_count) + ", \"normals\": " + (m.normals ? "1" : "0") +
		     ", \"uvs\": " + (m.uvs ? "1" : "0") + ", \"first_point\": " + jarrf(m.points, 3) +
		     (m.uvs ? ", \"first_uv\": " + jarrf(m.uvs, 2) : "") + "}";
	}
	o += "],\n \"instances\": [";
	for (int i = 0; i < info.instance_count; i++) {
		bru_instance in;
		api->instance(cap, i, &in);
		bru_mesh m;
		api->mesh(cap, in.mesh, &m);
		bru_material mt;
		const bool has_mat = in.material >= 0 && api->material(cap, in.material, &mt);
		o += std::string(i ? ",\n  " : "\n  ") + "{\"name\": " + jstr(in.name) + ", \"mesh\": " + jhex(m.hash) +
		     ", \"material\": " + (has_mat ? jhex(mt.hash) : std::string("null")) + ", \"matrix\": " +
		     jarr(in.matrix, 16) + "}";
	}
	o += "],\n \"materials\": [";
	for (int i = 0; i < info.material_count; i++) {
		bru_material mt;
		api->material(cap, i, &mt);
		o += std::string(i ? ",\n  " : "\n  ") + "{\"hash\": " + jhex(mt.hash) + ", \"mdl\": " + jstr(mt.mdl) +
		     ", \"sub_identifier\": " + jstr(mt.sub_identifier) + ", \"inputs\": {";
		for (int k = 0; k < mt.input_count; k++) {
			bru_input in;
			api->material_input(cap, i, k, &in);
			o += std::string(k ? ", " : "") + jstr(in.name) + ": {\"kind\": " + std::to_string(in.kind) +
			     ", \"v\": " + jarr(in.v, 4) + ", \"text\": " + jstr(in.text) + ", \"path\": " + jstr(in.path) +
			     ", \"exists\": " + std::to_string(in.exists) + "}";
		}
		o += "}}";
	}
	o += "],\n \"lights\": [";
	for (int i = 0; i < info.light_count; i++) {
		bru_light l;
		api->light(cap, i, &l);
		o += std::string(i ? ",\n  " : "\n  ") + "{\"hash\": " + jhex(l.hash) + ", \"kind\": " + std::to_string(l.kind) +
		     ", \"color\": " + jarrf(l.color, 3) + ", \"intensity\": " + jnum(l.intensity) + ", \"radius\": " +
		     jnum(l.radius) + ", \"shaped\": " + std::to_string(l.shaped) + ", \"cone_angle\": " + jnum(l.cone_angle) +
		     ", \"cone_softness\": " + jnum(l.cone_softness) + ", \"matrix\": " + jarr(l.matrix, 16) + "}";
	}
	o += "],\n \"camera\": ";
	bru_camera c;
	if (api->camera(cap, &c)) {
		o += "{\"matrix\": " + jarr(c.matrix, 16) + ", \"focal_length\": " + jnum(c.focal_length) +
		     ", \"horizontal_aperture\": " + jnum(c.horizontal_aperture) + ", \"near\": " + jnum(c.near_clip) +
		     ", \"far\": " + jnum(c.far_clip) + "}";
	}
	else {
		o += "null";
	}
	o += "}\n";
	fputs(o.c_str(), f);
	fclose(f);
	printf("capture %s: %d meshes, %d instances, %d materials, %d lights, camera %d\n%s", path, info.mesh_count,
	       info.instance_count, info.material_count, info.light_count, info.camera_found, info.report);
	api->close(cap);
	return 0;
}

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>

typedef const char *(*version_fn)(void);
typedef int (*started_fn)(void);
typedef int (*selftest_fn)(const wchar_t *, char *, int);
typedef const bru_capture_api *(*capture_api_fn)(char *, int);
typedef const char *(*plugin_dir_fn)(void);
typedef int (*dds_fn)(const wchar_t *, const wchar_t *, char *, int);

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
		fprintf(stderr, "usage: p12_usd_check <bge_remix_bridge.dll> <folder> [<capture> <dump.json> [<dds>...]]\n");
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

	/* P12 round 2: a capture read through the bridge, its DDS textures
	 * decoded (beside them, as .png) */
	if (argc >= 5) {
		capture_api_fn capture_api = (capture_api_fn)GetProcAddress(dll, "brb_usd_capture_api");
		plugin_dir_fn plugin_dir = (plugin_dir_fn)GetProcAddress(dll, "brb_usd_plugin_dir");
		dds_fn dds = (dds_fn)GetProcAddress(dll, "brb_dds_to_png");
		char err[1024] = "";
		const bru_capture_api *api = capture_api ? capture_api(err, int(sizeof(err))) : nullptr;
		if (!api || !plugin_dir || !dds) {
			printf("FAIL  the bridge's capture reader (%s)\n", err);
			failed++;
		}
		else {
			int r = dump_capture(api, plugin_dir(), argv[3], argv[4]);
			printf("%s  the capture read through the bridge\n", r == 0 ? "ok   " : "FAIL ");
			failed += r == 0 ? 0 : 1;
			for (int i = 5; i < argc; i++) {
				std::wstring in = wide(argv[i]);
				std::wstring out = in.substr(0, in.size() - 4) + L".png";
				int ok = dds(in.c_str(), out.c_str(), err, int(sizeof(err)));
				printf("%s  %s decoded%s%s\n", ok ? "ok   " : "FAIL ", argv[i], ok ? "" : ": ", ok ? "" : err);
				failed += ok ? 0 : 1;
			}
		}
	}
	printf("%d failed\n", failed);
	return failed;
}

#else

#include "usd_core.h"

int main(int argc, char **argv)
{
	if (argc < 2) {
		fprintf(stderr, "usage: p12_usd_check <folder> [<plugin folder> [<capture> <dump.json>]]\n");
		return 1;
	}
	int failed = 0;
	bool idle = !brb::usd::started();
	printf("%s  OpenUSD not started before the first call\n", idle ? "ok   " : "FAIL ");
	failed += idle ? 0 : 1;
	std::string report;
	failed += brb::usd::selftest(argc > 2 ? argv[2] : "", argv[1], report);
	printf("%s", report.c_str());
	if (argc >= 5) {
		int r = dump_capture(bru_capture_get_api(), argv[2], argv[3], argv[4]);
		printf("%s  the capture read\n", r == 0 ? "ok   " : "FAIL ");
		failed += r == 0 ? 0 : 1;
	}
	printf("%d failed\n", failed);
	return failed;
}

#endif
