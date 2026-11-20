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
 *             p12_usd_check.exe <bge_remix_bridge.dll> --dump <stage> <dump.json>
 *             (P12 round 3) any stage, a mod, written out as JSON through
 *             the bridge (brb_usd_stage_dump), for check_mod.py.
 *   Elsewhere: p12_usd_check <folder> [<plugin folder>]
 *             the same self-test, usd_core.cpp linked in (the native checks
 *             of the USD code itself); p12_usd_check --dump <plugin folder>
 *             <stage> <dump.json> the stage dump.
 *   P12 round 6: --scene <file> <scene.json> a scene as the import reads it
 *             (brb_usd_scene_api); --convert <src> <dst> a layer written in
 *             another format (brb_usd_convert); elsewhere each with the
 *             plugin folder first.
 * Exit code: the number of failed checks. */

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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

/* P12 round 6: a scene as the import reads it, as JSON (check_scene.py);
 * returns 0 when it was read */
static int dump_scene(const bru_scene_api *api, const char *plugins, const char *path, const char *json)
{
	char err[2048] = "";
	bru_scene *sc = api->open(plugins, path, err, int(sizeof(err)));
	FILE *f = fopen(json, "w");
	if (!f)
		return 1;
	if (!sc) {
		fprintf(f, "{\"error\": %s}\n", jstr(err).c_str());
		fclose(f);
		printf("scene %s: not read (%s)\n", path, err);
		return 2;
	}
	bru_scene_info info;
	api->info(sc, &info);
	std::string o = "{\"meters_per_unit\": " + jnum(info.meters_per_unit) + ", \"z_up\": " + std::to_string(info.z_up) +
	                ", \"default_prim\": " + jstr(info.default_prim) + ", \"creator\": " + jstr(info.creator) + ", \"usd_errors\": " +
	                std::to_string(info.usd_errors) + ", \"report\": " + jstr(info.report);
	o += ",\n \"nodes\": [";
	for (int i = 0; i < info.node_count; i++) {
		bru_node n;
		api->node(sc, i, &n);
		std::string subs = "[";
		for (int k = 0; k < n.subset_count; k++)
			subs += (k ? ", " : "") + std::to_string(n.subset_materials[k]);
		subs += "]";
		o += std::string(i ? ",\n  " : "\n  ") + "{\"name\": " + jstr(n.name) + ", \"path\": " + jstr(n.path) +
		     ", \"parent\": " + std::to_string(n.parent) + ", \"kind\": " + std::to_string(n.kind) +
		     ", \"index\": " + std::to_string(n.index) + ", \"visible\": " + std::to_string(n.visible) +
		     ", \"material\": " + std::to_string(n.material) + ", \"subset_materials\": " + subs +
		     ", \"matrix\": " + jarr(n.matrix, 16) + "}";
	}
	o += "],\n \"meshes\": [";
	for (int i = 0; i < info.mesh_count; i++) {
		bru_scene_mesh m;
		api->mesh(sc, i, &m);
		std::string subs = "[";
		for (int k = 0; k < m.subset_count; k++) {
			bru_subset s;
			api->subset(sc, i, k, &s);
			std::string faces = "[";
			for (int j = 0; j < s.face_count; j++)
				faces += (j ? ", " : "") + std::to_string(s.faces[j]);
			subs += std::string(k ? ", " : "") + "{\"name\": " + jstr(s.name) + ", \"faces\": " + faces + "]}";
		}
		subs += "]";
		o += std::string(i ? ",\n  " : "\n  ") + "{\"name\": " + jstr(m.name) + ", \"vertices\": " +
		     std::to_string(m.vertex_count) + ", \"faces\": " + std::to_string(m.face_count) + ", \"corners\": " +
		     std::to_string(m.corner_count) + ", \"points\": " + jarrf(m.points, m.vertex_count * 3) +
		     ", \"normals\": " + (m.normals ? jarrf(m.normals, m.corner_count * 3) : std::string("null")) +
		     ", \"uvs\": " + (m.uvs ? jarrf(m.uvs, m.corner_count * 2) : std::string("null")) +
		     ", \"uv_name\": " + jstr(m.uv_name) +
		     ", \"colors\": " + (m.colors ? jarrf(m.colors, m.corner_count * 4) : std::string("null")) +
		     ", \"double_sided\": " + std::to_string(m.double_sided) + ", \"subsets\": " + subs + "}";
	}
	o += "],\n \"materials\": [";
	for (int i = 0; i < info.material_count; i++) {
		bru_scene_material mt;
		api->material(sc, i, &mt);
		o += std::string(i ? ",\n  " : "\n  ") + "{\"name\": " + jstr(mt.name) + ", \"path\": " + jstr(mt.path) +
		     ", \"preview\": " + std::to_string(mt.preview) + ", \"aperture\": " + std::to_string(mt.aperture) +
		     ", \"mdl\": " + jstr(mt.mdl) + ", \"sub_identifier\": " + jstr(mt.sub_identifier) +
		     ", \"other\": " + jstr(mt.other);
		for (int which = 0; which < 2; which++) {
			const int count = which ? mt.aperture_input_count : mt.preview_input_count;
			o += which ? ", \"aperture_inputs\": {" : ", \"preview_inputs\": {";
			for (int k = 0; k < count; k++) {
				bru_shader_input in;
				api->material_input(sc, i, which, k, &in);
				o += std::string(k ? ", " : "") + jstr(in.name) + ": {\"kind\": " + std::to_string(in.kind) +
				     ", \"v\": " + jarr(in.v, 4) + ", \"text\": " + jstr(in.text) + ", \"path\": " +
				     jstr(in.path) + ", \"exists\": " + std::to_string(in.exists) + ", \"output\": " +
				     jstr(in.output) + ", \"color_space\": " + jstr(in.color_space) + "}";
			}
			o += "}";
		}
		o += "}";
	}
	o += "],\n \"lights\": [";
	for (int i = 0;; i++) {
		bru_light l;
		if (!api->light(sc, i, &l))
			break;
		o += std::string(i ? ",\n  " : "\n  ") + "{\"name\": " + jstr(l.name) + ", \"kind\": " +
		     std::to_string(l.kind) + ", \"color\": " + jarrf(l.color, 3) + ", \"intensity\": " + jnum(l.intensity) +
		     ", \"exposure\": " + jnum(l.exposure) + ", \"radius\": " + jnum(l.radius) + ", \"angle\": " +
		     jnum(l.angle) + ", \"width\": " + jnum(l.width) + ", \"height\": " + jnum(l.height) +
		     ", \"shaped\": " + std::to_string(l.shaped) + ", \"cone_angle\": " + jnum(l.cone_angle) +
		     ", \"cone_softness\": " + jnum(l.cone_softness) + "}";
	}
	o += "],\n \"cameras\": [";
	for (int i = 0;; i++) {
		bru_camera c;
		if (!api->camera(sc, i, &c))
			break;
		o += std::string(i ? ",\n  " : "\n  ") + "{\"focal_length\": " + jnum(c.focal_length) +
		     ", \"horizontal_aperture\": " + jnum(c.horizontal_aperture) + ", \"vertical_aperture\": " +
		     jnum(c.vertical_aperture) + ", \"near\": " + jnum(c.near_clip) + ", \"far\": " + jnum(c.far_clip) +
		     ", \"perspective\": " + std::to_string(c.perspective) + "}";
	}
	o += "],\n \"physics\": ";
	o += api->physics(sc);  /* round 7: JSON already */
	o += "}\n";
	fputs(o.c_str(), f);
	fclose(f);
	printf("scene %s: %d nodes, %d meshes, %d materials\n%s", path, info.node_count, info.mesh_count,
	       info.material_count, info.report);
	api->close(sc);
	return 0;
}

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>

static const char *g_step = "starting";

typedef const char *(*version_fn)(void);
typedef int (*started_fn)(void);
typedef int (*selftest_fn)(const wchar_t *, char *, int);
typedef const bru_capture_api *(*capture_api_fn)(char *, int);
typedef const char *(*plugin_dir_fn)(void);
typedef int (*dds_fn)(const wchar_t *, const wchar_t *, char *, int);
typedef int (*stage_dump_fn)(const char *, const char *, char *, int);
typedef const bru_scene_api *(*scene_api_fn)(char *, int);
typedef int (*convert_fn)(const char *, const char *, char *, int);

static std::wstring wide(const char *s)
{
	int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
	std::wstring w(n > 0 ? size_t(n - 1) : 0, L'\0');
	if (n > 0)
		MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
	return w;
}

/* a crash says where (the module and offset), even when the output is a
 * pipe: stdout is unbuffered (P12 round 2: a crash left no output at all) */
static LONG WINAPI on_crash(EXCEPTION_POINTERS *e)
{
	void *at = e->ExceptionRecord->ExceptionAddress;
	HMODULE mod = nullptr;
	char name[MAX_PATH] = "?";
	if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                       (LPCSTR)at, &mod)) {
		GetModuleFileNameA(mod, name, MAX_PATH);
	}
	printf("FAIL  crashed: exception 0x%08lX at %s+0x%llX (step: %s)\n", e->ExceptionRecord->ExceptionCode, name,
	       (unsigned long long)((const char *)at - (const char *)mod), g_step);
	fflush(stdout);
	return EXCEPTION_EXECUTE_HANDLER;
}

int main(int argc, char **argv)
{
	setvbuf(stdout, nullptr, _IONBF, 0);
	SetUnhandledExceptionFilter(on_crash);
	if (argc < 3) {
		fprintf(stderr, "usage: p12_usd_check <bge_remix_bridge.dll> <folder> [<capture> <dump.json> [<dds>...]]\n");
		return 1;
	}
	g_step = "loading the bridge";
	int failed = 0;
	wchar_t full[MAX_PATH * 2];
	GetFullPathNameW(wide(argv[1]).c_str(), MAX_PATH * 2, full, nullptr);
	HMODULE dll = LoadLibraryExW(full, nullptr, LOAD_WITH_ALTERED_SEARCH_PATH);
	if (!dll) {
		printf("FAIL  the bridge did not load (error %lu)\n", GetLastError());
		return 1;
	}
	/* P12 round 3: a stage (a mod) written out as JSON, nothing else */
	if (argc >= 5 && strcmp(argv[2], "--dump") == 0) {
		stage_dump_fn stage_dump = (stage_dump_fn)GetProcAddress(dll, "brb_usd_stage_dump");
		if (!stage_dump) {
			printf("FAIL  the bridge lacks brb_usd_stage_dump\n");
			return 1;
		}
		char err[1024] = "";
		g_step = "the stage dump";
		int ok = stage_dump(argv[3], argv[4], err, int(sizeof(err)));
		printf("%s  %s read through the bridge%s%s\n", ok ? "ok   " : "FAIL ", argv[3], ok ? "" : ": ", err);
		return ok ? 0 : 1;
	}
	/* P12 round 6: a scene as the import reads it; a layer converted */
	if (argc >= 5 && strcmp(argv[2], "--scene") == 0) {
		scene_api_fn scene_api = (scene_api_fn)GetProcAddress(dll, "brb_usd_scene_api");
		plugin_dir_fn plugin_dir = (plugin_dir_fn)GetProcAddress(dll, "brb_usd_plugin_dir");
		char err[1024] = "";
		const bru_scene_api *api = (scene_api && plugin_dir) ? scene_api(err, int(sizeof(err))) : nullptr;
		if (!api) {
			printf("FAIL  the bridge's scene reader (%s)\n", err);
			return 1;
		}
		g_step = "reading the scene";
		int r = dump_scene(api, plugin_dir(), argv[3], argv[4]);
		printf("%s  %s read through the bridge\n", r == 0 ? "ok   " : "FAIL ", argv[3]);
		return r == 0 ? 0 : 1;
	}
	if (argc >= 5 && strcmp(argv[2], "--convert") == 0) {
		convert_fn conv = (convert_fn)GetProcAddress(dll, "brb_usd_convert");
		if (!conv) {
			printf("FAIL  the bridge lacks brb_usd_convert\n");
			return 1;
		}
		char err[1024] = "";
		g_step = "converting";
		int ok = conv(argv[3], argv[4], err, int(sizeof(err)));
		printf("%s  %s written as %s%s%s\n", ok ? "ok   " : "FAIL ", argv[3], argv[4], ok ? "" : ": ", err);
		return ok ? 0 : 1;
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
	g_step = "the self-test";
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
		g_step = "the capture reader";
		const bru_capture_api *api = capture_api ? capture_api(err, int(sizeof(err))) : nullptr;
		if (!api || !plugin_dir || !dds) {
			printf("FAIL  the bridge's capture reader (%s)\n", err);
			failed++;
		}
		else {
			g_step = "reading the capture";
			int r = dump_capture(api, plugin_dir(), argv[3], argv[4]);
			printf("%s  the capture read through the bridge\n", r == 0 ? "ok   " : "FAIL ");
			failed += r == 0 ? 0 : 1;
			for (int i = 5; i < argc; i++) {
				std::wstring in = wide(argv[i]);
				std::wstring out = in.substr(0, in.size() - 4) + L".png";
				g_step = "decoding a DDS texture";
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
		fprintf(stderr, "usage: p12_usd_check <folder> [<plugin folder> [<capture> <dump.json>]]\n"
		                "       p12_usd_check --dump <plugin folder> <stage> <dump.json>\n"
		                "       p12_usd_check --scene <plugin folder> <file> <scene.json>\n"
		                "       p12_usd_check --convert <plugin folder> <src> <dst>\n");
		return 1;
	}
	if (argc >= 5 && strcmp(argv[1], "--dump") == 0) {
		char err[1024] = "";
		int ok = bru_stage_dump(argv[2], argv[3], argv[4], err, int(sizeof(err)));
		printf("%s  %s read%s%s\n", ok ? "ok   " : "FAIL ", argv[3], ok ? "" : ": ", err);
		return ok ? 0 : 1;
	}
	if (argc >= 5 && strcmp(argv[1], "--scene") == 0) {
		int r = dump_scene(bru_scene_get_api(), argv[2], argv[3], argv[4]);
		printf("%s  %s read\n", r == 0 ? "ok   " : "FAIL ", argv[3]);
		return r == 0 ? 0 : 1;
	}
	if (argc >= 5 && strcmp(argv[1], "--convert") == 0) {
		char err[1024] = "";
		int ok = bru_stage_convert(argv[2], argv[3], argv[4], err, int(sizeof(err)));
		printf("%s  %s written as %s%s%s\n", ok ? "ok   " : "FAIL ", argv[3], argv[4], ok ? "" : ": ", err);
		return ok ? 0 : 1;
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
