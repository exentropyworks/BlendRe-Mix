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
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 *
 * ***** END GPL LICENSE BLOCK *****
 */

/** \file remix_python.c
 *  \ingroup remix
 *
 * The "_bge_remix" Python module. bge_remix_bridge.dll is loaded the first
 * time a function here needs it, never at startup, so Blender pays nothing
 * when Remix is not used and keeps working when the DLL is missing.
 */

#include <Python.h>
#include <stdint.h>
#include <string.h>

#ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include "BLI_utildefines.h"

#include "BLI_listbase.h"

#include "DNA_ID.h"
#include "DNA_image_types.h"
#include "DNA_material_types.h"
#include "DNA_mesh_types.h"
#include "DNA_object_types.h"
#include "DNA_scene_types.h"

#include "BKE_global.h"
#include "BKE_main.h"

#include "BRMX_capture.h"
#include "BRMX_loader.h"
#include "BRMX_remaster.h"
#include "BRMX_remix.h"
#include "BRMX_session.h"
#include "BRMX_view.h"

/* ------------------------------------------------------------------------- */
/* Bridge DLL (loaded by the shared loader, BRMX_loader.h) */

#define B (BRMX_bridge())

static int bridge_ensure(void)
{
	return BRMX_bridge() != NULL;
}

/* ------------------------------------------------------------------------- */
/* Python */

static const char *status_name(brb_status s)
{
	switch (s) {
		case BRB_STATUS_NOT_LOADED: return "NOT_LOADED";
		case BRB_STATUS_NOT_INSTALLED: return "NOT_INSTALLED";
		case BRB_STATUS_INCOMPATIBLE_VERSION: return "INCOMPATIBLE_VERSION";
		case BRB_STATUS_LOAD_FAILED: return "LOAD_FAILED";
		case BRB_STATUS_STARTUP_FAILED: return "STARTUP_FAILED";
		case BRB_STATUS_READY: return "READY";
		case BRB_STATUS_RUNNING: return "RUNNING";
	}
	return "UNKNOWN";
}

static PyObject *status_tuple(void)
{
	if (!bridge_ensure()) {
		return Py_BuildValue("(ss)", "NO_BRIDGE", BRMX_bridge_error());
	}
	return Py_BuildValue("(ss)", status_name(B->get_status()), B->status_text());
}

PyDoc_STRVAR(brmx_bridge_info_doc,
".. function:: bridge_info()\n"
"\n"
"   Information about bge_remix_bridge.dll (loads it if needed).\n"
"\n"
"   :rtype: dict with loaded, error, path, interface, api_version, log_path\n");
static PyObject *brmx_bridge_info(PyObject *UNUSED_self)
{
	const int ok = bridge_ensure();
	PyObject *path = PyUnicode_FromWideChar(BRMX_bridge_path(), -1);
	PyObject *d = Py_BuildValue(
	        "{s:O,s:s,s:N,s:i,s:s,s:s}",
	        "loaded", ok ? Py_True : Py_False,
	        "error", ok ? "" : BRMX_bridge_error(),
	        "path", path,
	        "interface", ok ? B->abi_version() : 0,
	        "api_version", ok ? B->api_version() : "",
	        "log_path", ok ? B->log_path() : "");
	return d;
}

PyDoc_STRVAR(brmx_status_doc,
".. function:: status()\n"
"\n"
"   :return: (status, text), status one of NO_BRIDGE, NOT_LOADED, NOT_INSTALLED,\n"
"      INCOMPATIBLE_VERSION, LOAD_FAILED, STARTUP_FAILED, READY, RUNNING.\n"
"   :rtype: tuple\n");
static PyObject *brmx_status(PyObject *UNUSED_self)
{
	return status_tuple();
}

PyDoc_STRVAR(brmx_load_doc,
".. function:: load(runtime_dir)\n"
"\n"
"   Load the RTX Remix runtime from a folder that contains its d3d9.dll.\n"
"\n"
"   :return: (status, text)\n");
static PyObject *brmx_load(PyObject *UNUSED_self, PyObject *args)
{
	PyObject *dir_obj;
	wchar_t *dir;

	if (!PyArg_ParseTuple(args, "U:load", &dir_obj)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		return status_tuple();
	}
	dir = PyUnicode_AsWideCharString(dir_obj, NULL);
	if (dir == NULL) {
		return NULL;
	}
	B->load(dir);
	PyMem_Free(dir);
	return status_tuple();
}

PyDoc_STRVAR(brmx_startup_doc,
".. function:: startup(width=1280, height=720, visible=True)\n"
"\n"
"   Start Remix in a window of its own (needs status READY).\n"
"\n"
"   :return: (status, text)\n");
static PyObject *brmx_startup(PyObject *UNUSED_self, PyObject *args, PyObject *kw)
{
	static const char *kwlist[] = {"width", "height", "visible", NULL};
	int width = 1280, height = 720, visible = 1;

	if (!PyArg_ParseTupleAndKeywords(args, kw, "|iip:startup", (char **)kwlist, &width, &height, &visible)) {
		return NULL;
	}
	if (bridge_ensure()) {
		B->startup(width, height, visible);
	}
	return status_tuple();
}

PyDoc_STRVAR(brmx_set_config_doc,
".. function:: set_config(key, value)\n"
"\n"
"   Set one Remix option (rtx.conf key and value).\n"
"\n"
"   :return: Remix error code, 0 on success\n");
static PyObject *brmx_set_config(PyObject *UNUSED_self, PyObject *args)
{
	const char *key, *value;

	if (!PyArg_ParseTuple(args, "ss:set_config", &key, &value)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		return PyLong_FromLong(-1);
	}
	return PyLong_FromLong(B->set_config(key, value));
}

PyDoc_STRVAR(brmx_triangle_test_doc,
".. function:: triangle_test(seconds=5.0, screenshot='', capture=False)\n"
"\n"
"   Draw the P1 test scene for a while (needs status RUNNING).\n"
"\n"
"   :arg screenshot: BMP file to save the last frame to, or '' for none.\n"
"   :arg capture: press Remix's capture hotkey half-way through.\n"
"   :rtype: dict\n");
static PyObject *brmx_triangle_test(PyObject *UNUSED_self, PyObject *args, PyObject *kw)
{
	static const char *kwlist[] = {"seconds", "screenshot", "capture", NULL};
	double seconds = 5.0;
	PyObject *shot_obj = NULL;
	int capture = 0;
	wchar_t *shot = NULL;
	brb_triangle_result r;
	int rc;

	if (!PyArg_ParseTupleAndKeywords(args, kw, "|dUp:triangle_test", (char **)kwlist,
	                                 &seconds, &shot_obj, &capture))
	{
		return NULL;
	}
	memset(&r, 0, sizeof(r));
	if (!bridge_ensure()) {
		PyErr_SetString(PyExc_RuntimeError, BRMX_bridge_error());
		return NULL;
	}
	if (shot_obj) {
		shot = PyUnicode_AsWideCharString(shot_obj, NULL);
		if (shot == NULL) {
			return NULL;
		}
	}
	Py_BEGIN_ALLOW_THREADS
	rc = B->triangle_test(seconds, shot, capture, &r);
	Py_END_ALLOW_THREADS
	if (shot) {
		PyMem_Free(shot);
	}
	return Py_BuildValue(
	        "{s:O,s:i,s:d,s:d,s:d,s:d,s:i,s:O,s:O,s:i}",
	        "ok", rc == 0 ? Py_True : Py_False,
	        "frames", r.frames,
	        "seconds", r.seconds,
	        "frame_ms_mean", r.frame_ms_mean,
	        "frame_ms_median", r.frame_ms_median,
	        "frame_ms_p95", r.frame_ms_p95,
	        "present_errors", r.present_errors,
	        "screenshot_saved", r.screenshot_saved ? Py_True : Py_False,
	        "capture_requested", r.capture_requested ? Py_True : Py_False,
	        "last_error", r.last_error);
}

PyDoc_STRVAR(brmx_runtime_dir_doc,
".. function:: runtime_dir()\n"
"\n"
"   The runtime folder as the game engine finds it (environment variable,\n"
"   settings.json, default), so Python and C can be checked against each other.\n"
"\n"
"   :rtype: str\n");
static PyObject *brmx_runtime_dir(PyObject *UNUSED_self)
{
	wchar_t dir[MAX_PATH * 2];
	if (!BRMX_runtime_dir(dir, (int)(sizeof(dir) / sizeof(dir[0])))) {
		Py_RETURN_NONE;
	}
	return PyUnicode_FromWideChar(dir, -1);
}

PyDoc_STRVAR(brmx_shutdown_doc,
".. function:: shutdown()\n"
"\n"
"   Shut Remix down and unload it (also happens when Blender quits).\n");
static PyObject *brmx_shutdown(PyObject *UNUSED_self)
{
	BRMX_exit();
	Py_RETURN_NONE;
}

/* ------------------------------------------------------------------------- */
/* P5: the RTX Remix render engine (release/scripts/startup/render_remix).
 * The engine passes its own pointers (as_pointer()); see BRMX_view.h. */

#define PTR(type, v) ((type *)(uintptr_t)(v))

PyDoc_STRVAR(brmx_view_update_doc,
".. function:: view_update(engine, data, scene, region, space, region_data)\n"
"\n"
"   RenderEngine.view_update: the scene changed (pointers from as_pointer()).\n");
static PyObject *brmx_view_update(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long engine, data, scene, region, space, rv3d;
	if (!PyArg_ParseTuple(args, "KKKKKK", &engine, &data, &scene, &region, &space, &rv3d)) {
		return NULL;
	}
	BRMX_view_update(PTR(struct RenderEngine, engine), PTR(struct Main, data), PTR(struct Scene, scene),
	                 PTR(struct ARegion, region), PTR(struct View3D, space), PTR(struct RegionView3D, rv3d));
	Py_RETURN_NONE;
}

PyDoc_STRVAR(brmx_view_draw_doc,
".. function:: view_draw(engine, data, scene, region, space, region_data)\n"
"\n"
"   RenderEngine.view_draw: draw the view. True when it should be drawn again soon.\n"
"\n"
"   :rtype: bool\n");
static PyObject *brmx_view_draw(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long engine, data, scene, region, space, rv3d;
	int again;
	if (!PyArg_ParseTuple(args, "KKKKKK", &engine, &data, &scene, &region, &space, &rv3d)) {
		return NULL;
	}
	again = BRMX_view_draw(PTR(struct RenderEngine, engine), PTR(struct Main, data), PTR(struct Scene, scene),
	                       PTR(struct ARegion, region), PTR(struct View3D, space), PTR(struct RegionView3D, rv3d));
	return PyBool_FromLong(again);
}

PyDoc_STRVAR(brmx_engine_free_doc,
".. function:: engine_free(engine)\n"
"\n"
"   The engine goes away: its 3D view and F12 data go too.\n");
static PyObject *brmx_engine_free(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long engine;
	if (!PyArg_ParseTuple(args, "K", &engine)) {
		return NULL;
	}
	BRMX_view_free(PTR(struct RenderEngine, engine));
	BRMX_render_free(PTR(struct RenderEngine, engine));
	Py_RETURN_NONE;
}

PyDoc_STRVAR(brmx_render_sync_doc,
".. function:: render_sync(engine, data, scene)\n"
"\n"
"   RenderEngine.update (F12): read the scene. Returns (ok, message).\n"
"\n"
"   :rtype: tuple\n");
static PyObject *brmx_render_sync(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long engine, data, scene;
	const char *message = "";
	int ok;
	if (!PyArg_ParseTuple(args, "KKK", &engine, &data, &scene)) {
		return NULL;
	}
	Py_BEGIN_ALLOW_THREADS
	ok = BRMX_render_sync(PTR(struct RenderEngine, engine), PTR(struct Main, data), PTR(struct Scene, scene),
	                      &message);
	Py_END_ALLOW_THREADS
	return Py_BuildValue("(Ns)", PyBool_FromLong(ok), message ? message : "");
}

PyDoc_STRVAR(brmx_render_frame_doc,
".. function:: render_frame(engine, scene)\n"
"\n"
"   RenderEngine.render (F12): render and fill the result. Returns (ok, message).\n"
"\n"
"   :rtype: tuple\n");
static PyObject *brmx_render_frame(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long engine, scene;
	const char *message = "";
	int ok;
	if (!PyArg_ParseTuple(args, "KK", &engine, &scene)) {
		return NULL;
	}
	Py_BEGIN_ALLOW_THREADS
	ok = BRMX_render_frame(PTR(struct RenderEngine, engine), PTR(struct Scene, scene), &message);
	Py_END_ALLOW_THREADS
	return Py_BuildValue("(Ns)", PyBool_FromLong(ok), message ? message : "");
}

PyDoc_STRVAR(brmx_view_stats_doc,
".. function:: view_stats()\n"
"\n"
"   Counters of the 3D view and F12, for the tests (JSON text).\n"
"\n"
"   :rtype: str\n");
static PyObject *brmx_view_stats(PyObject *UNUSED_self)
{
	return PyUnicode_FromString(BRMX_view_stats_json());
}

PyDoc_STRVAR(brmx_material_match_doc,
".. function:: material_match(pointer)\n"
"\n"
"   BGE-Remix P8.24: how the material (its as_pointer()) reaches RTX Remix,\n"
"   field by field (JSON text).\n"
"\n"
"   :rtype: str\n");
static PyObject *brmx_material_match(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long ptr = 0;
	if (!PyArg_ParseTuple(args, "K:material_match", &ptr) || !ptr) {
		if (!PyErr_Occurred()) {
			PyErr_SetString(PyExc_ValueError, "material_match: a material's as_pointer() is needed");
		}
		return NULL;
	}
	return PyUnicode_FromString(BRMX_material_match_json((struct Material *)(uintptr_t)ptr));
}

PyDoc_STRVAR(brmx_inspect_doc,
".. function:: inspect(object_pointer, scene_pointer)\n"
"\n"
"   BGE-Remix P9.7: what RTX Remix gets for the object (its as_pointer(); the\n"
"   scene's for its instance count, or 0): mesh, instances, each material's\n"
"   values, textures and their cache files, and its Match rows (JSON text).\n"
"\n"
"   :rtype: str\n");
static PyObject *brmx_inspect(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long ob = 0, scene = 0;
	if (!PyArg_ParseTuple(args, "K|K:inspect", &ob, &scene) || !ob) {
		if (!PyErr_Occurred()) {
			PyErr_SetString(PyExc_ValueError, "inspect: an object's as_pointer() is needed");
		}
		return NULL;
	}
	return PyUnicode_FromString(BRMX_object_inspect_json((struct Object *)(uintptr_t)ob,
	                                                     (struct Scene *)(uintptr_t)scene));
}

PyDoc_STRVAR(brmx_debug_option_doc,
".. function:: debug_option(key, value)\n"
"\n"
"   BGE-Remix P9.7: one of the Remix View's debug options (rtx.debugView.*,\n"
"   rtx.hashCollisionDetection.enable): sent now when Remix runs, and kept\n"
"   for a game started from Blender.\n");
static PyObject *brmx_debug_option(PyObject *UNUSED_self, PyObject *args)
{
	const char *key, *value;
	if (!PyArg_ParseTuple(args, "ss:debug_option", &key, &value)) {
		return NULL;
	}
	BRMX_debug_option_set(key, value);
	Py_RETURN_NONE;
}

PyDoc_STRVAR(brmx_bake_tile_doc,
".. function:: bake_tile(material_pointer, scene_pointer, size, slots)\n"
"\n"
"   BGE-Remix P10.2: a preset material's tile baked at size x size, always\n"
"   drawn (not from the cache). slots: bits 1 << slot (0 albedo, 1 roughness,\n"
"   2 emissive, 3 normal, 4 metallic, 5 height). Returns {slot: bytes} (RGBA,\n"
"   bottom row first). Needs Blender's OpenGL context (not the background).\n"
"\n"
"   :rtype: dict\n");
static PyObject *brmx_bake_tile(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long ma = 0, scene = 0;
	int size = 256;
	unsigned int slots = 1;
	unsigned char *px[BRMX_REMASTER_SLOTS];
	char error[256] = "";
	unsigned done;
	PyObject *r;
	int i;
	if (!PyArg_ParseTuple(args, "KK|iI:bake_tile", &ma, &scene, &size, &slots) || !ma || !scene) {
		if (!PyErr_Occurred()) {
			PyErr_SetString(PyExc_ValueError, "bake_tile: a material's and a scene's as_pointer() are needed");
		}
		return NULL;
	}
	if (size < 16 || size > 8192) {
		PyErr_SetString(PyExc_ValueError, "bake_tile: size 16..8192");
		return NULL;
	}
	done = BRMX_remaster_bake_tile(PTR(struct Scene, scene), PTR(struct Material, ma), size, slots, px, error,
	                               (int)sizeof(error));
	if (!done) {
		PyErr_SetString(PyExc_RuntimeError, error[0] ? error : "the tile could not be baked");
		return NULL;
	}
	r = PyDict_New();
	for (i = 0; i < BRMX_REMASTER_SLOTS; i++) {
		if (px[i]) {
			PyObject *key = PyLong_FromLong(i);
			PyObject *val = PyBytes_FromStringAndSize((const char *)px[i], (Py_ssize_t)size * size * 4);
			PyDict_SetItem(r, key, val);
			Py_DECREF(key);
			Py_DECREF(val);
			BRMX_remaster_free(px[i]);
		}
	}
	return r;
}

PyDoc_STRVAR(brmx_precache_doc,
".. function:: precache(object_pointer, scene_pointer)\n"
"\n"
"   BGE-Remix P10.5: the object's materials made into Remix's images as the\n"
"   game makes them (bakes, the texture cache), the encodes started.\n"
"   Returns the textures asked for. Needs Blender's OpenGL context for bakes.\n"
"\n"
"   :rtype: int\n");
static PyObject *brmx_precache(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long ob = 0, scene = 0;
	char error[256] = "";
	int n;
	if (!PyArg_ParseTuple(args, "KK:precache", &ob, &scene) || !ob || !scene) {
		if (!PyErr_Occurred()) {
			PyErr_SetString(PyExc_ValueError, "precache: an object's and a scene's as_pointer() are needed");
		}
		return NULL;
	}
	n = BRMX_remaster_precache(PTR(struct Scene, scene), PTR(struct Object, ob), error, (int)sizeof(error));
	if (n < 0) {
		PyErr_SetString(PyExc_RuntimeError, error[0] ? error : "precache failed");
		return NULL;
	}
	return PyLong_FromLong(n);
}

PyDoc_STRVAR(brmx_precache_poll_doc,
".. function:: precache_poll()\n"
"\n"
"   BGE-Remix P10.5: the up-front encodes: {waiting, encoded, reused, failed,\n"
"   seconds, bakes}.\n"
"\n"
"   :rtype: dict\n");
static PyObject *brmx_precache_poll(PyObject *UNUSED_self)
{
	int waiting = 0, encoded = 0, reused = 0, failed = 0, bakes = 0;
	double seconds = 0.0;
	BRMX_remaster_poll(&waiting, &encoded, &reused, &failed, &seconds, &bakes);
	return Py_BuildValue("{s:i,s:i,s:i,s:i,s:d,s:i}", "waiting", waiting, "encoded", encoded, "reused", reused,
	                     "failed", failed, "seconds", seconds, "bakes", bakes);
}

PyDoc_STRVAR(brmx_precache_reset_doc,
".. function:: precache_reset()\n"
"\n"
"   BGE-Remix P10.5: the counts back to 0 (the next Apply).\n");
static PyObject *brmx_precache_reset(PyObject *UNUSED_self)
{
	BRMX_remaster_reset();
	Py_RETURN_NONE;
}

/* BGE-Remix P10.4: atlases (remix_atlas.cc, remix_atlas_pack.cc) */
struct Material;
struct Scene;
const char *BRMX_atlas_bake_json(struct Material *ma, struct Scene *scene);
const unsigned char *BRMX_atlas_preview(int *r_width, int *r_height);
int BRMX_atlas_pack(const int *sizes, int count, int page, int padding, int *r_places);

PyDoc_STRVAR(brmx_atlas_bake_doc,
".. function:: atlas_bake(material_pointer, scene_pointer)\n"
"\n"
"   BGE-Remix P10.4: bake the material's tile set or flipbook now and encode\n"
"   its files into the texture cache (OpenGL needed: not in the background).\n"
"   Use bge_remix.atlas rather than this.\n"
"\n"
"   :rtype: str (JSON)\n");
static PyObject *brmx_atlas_bake(PyObject *UNUSED_self, PyObject *args)
{
	unsigned long long ma = 0, scene = 0;
	if (!PyArg_ParseTuple(args, "KK:atlas_bake", &ma, &scene) || !ma || !scene) {
		if (!PyErr_Occurred()) {
			PyErr_SetString(PyExc_ValueError, "atlas_bake: a material's and a scene's as_pointer() are needed");
		}
		return NULL;
	}
	return PyUnicode_FromString(BRMX_atlas_bake_json((struct Material *)(uintptr_t)ma,
	                                                 (struct Scene *)(uintptr_t)scene));
}

PyDoc_STRVAR(brmx_atlas_preview_doc,
".. function:: atlas_preview()\n"
"\n"
"   BGE-Remix P10.4: the last atlas_bake's albedo atlas, smaller (at most 1024\n"
"   a side): (width, height, RGBA bytes, rows from the bottom), or None.\n");
static PyObject *brmx_atlas_preview(PyObject *UNUSED_self, PyObject *UNUSED_args)
{
	int w = 0, h = 0;
	const unsigned char *px = BRMX_atlas_preview(&w, &h);
	if (!px || w <= 0 || h <= 0) {
		Py_RETURN_NONE;
	}
	return Py_BuildValue("(iiy#)", w, h, (const char *)px, (Py_ssize_t)w * h * 4);
}

PyDoc_STRVAR(brmx_atlas_pack_doc,
".. function:: atlas_pack(sizes, page, padding)\n"
"\n"
"   BGE-Remix P10.4: rectangles (a list of (width, height)) packed onto\n"
"   pages of page x page pixels, padding apart, with xatlas: a list of\n"
"   (page, x, y) (bottom-left corners), or None when one does not fit.\n");
static PyObject *brmx_atlas_pack(PyObject *UNUSED_self, PyObject *args)
{
	PyObject *list = NULL, *seq = NULL, *out = NULL;
	int page = 0, padding = 0;
	Py_ssize_t n, i;
	int *sizes, *places;
	if (!PyArg_ParseTuple(args, "Oii:atlas_pack", &list, &page, &padding)) {
		return NULL;
	}
	seq = PySequence_Fast(list, "atlas_pack: a list of (width, height) is needed");
	if (!seq) {
		return NULL;
	}
	n = PySequence_Fast_GET_SIZE(seq);
	sizes = (int *)malloc(sizeof(int) * 2 * (size_t)(n + 1));
	places = (int *)malloc(sizeof(int) * 3 * (size_t)(n + 1));
	for (i = 0; i < n; i++) {
		PyObject *item = PySequence_Fast_GET_ITEM(seq, i);
		int w = 0, h = 0;
		if (!PyArg_ParseTuple(item, "ii", &w, &h)) {
			free(sizes);
			free(places);
			Py_DECREF(seq);
			return NULL;
		}
		sizes[i * 2] = w;
		sizes[i * 2 + 1] = h;
	}
	Py_DECREF(seq);
	if (n > 0 && BRMX_atlas_pack(sizes, (int)n, page, padding, places) > 0) {
		out = PyList_New(n);
		for (i = 0; i < n; i++) {
			PyList_SET_ITEM(out, i, Py_BuildValue("(iii)", places[i * 3], places[i * 3 + 1], places[i * 3 + 2]));
		}
	}
	free(sizes);
	free(places);
	if (!out) {
		Py_RETURN_NONE;
	}
	return out;
}

PyDoc_STRVAR(brmx_settings_doc,
".. function:: settings()\n"
"\n"
"   BGE-Remix P10.12: the RTX Remix settings the RTX Remix actuator lists\n"
"   (the Render tab's curated ones and the quality ones), as (key, kind,\n"
"   default) with kind 'BOOL', 'INT' or 'FLOAT'.\n");
static PyObject *brmx_settings(PyObject *UNUSED_self)
{
	PyObject *list = PyList_New(0);
	const char *key, *def;
	char kind;
	int i;
	for (i = 0; BRMX_setting_get(i, &key, &kind, &def); i++) {
		PyObject *item = Py_BuildValue("(sss)", key, kind == 'b' ? "BOOL" : (kind == 'i' ? "INT" : "FLOAT"), def);
		if (item) {
			PyList_Append(list, item);
			Py_DECREF(item);
		}
	}
	return list;
}

/* ------------------------------------------------------------------------- */
/* BGE-Remix P12: OpenUSD, RTX Remix captures */

PyDoc_STRVAR(brmx_usd_selftest_doc,
".. function:: usd_selftest(folder)\n"
"\n"
"   BGE-Remix P12: load and check the bridge's OpenUSD (bge_remix_usd.dll):\n"
"   a stage written into the folder and read back.\n"
"\n"
"   :return: (failed checks, report, OpenUSD version)\n");
static PyObject *brmx_usd_selftest(PyObject *UNUSED_self, PyObject *args)
{
	PyObject *dir_obj;
	wchar_t *dir;
	static char report[32768];
	int failed;

	if (!PyArg_ParseTuple(args, "U:usd_selftest", &dir_obj)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		return Py_BuildValue("(iss)", 1, BRMX_bridge_error(), "");
	}
	dir = PyUnicode_AsWideCharString(dir_obj, NULL);
	if (dir == NULL) {
		return NULL;
	}
	report[0] = '\0';
	failed = B->usd_selftest(dir, report, (int)sizeof(report));
	PyMem_Free(dir);
	return Py_BuildValue("(iss)", failed, report, B->usd_version());
}

static PyObject *hex_hash(uint64_t h)
{
	char buf[32];
	_snprintf(buf, sizeof(buf), "%016llX", (unsigned long long)h);
	return PyUnicode_FromString(buf);
}

static PyObject *bytes_or_none(const void *data, size_t size)
{
	if (data == NULL) {
		Py_RETURN_NONE;
	}
	return PyBytes_FromStringAndSize((const char *)data, (Py_ssize_t)size);
}

static PyObject *matrix_tuple(const double m[16])
{
	PyObject *t = PyTuple_New(16);
	int i;
	for (i = 0; i < 16; i++) {
		PyTuple_SET_ITEM(t, i, PyFloat_FromDouble(m[i]));
	}
	return t;
}

/* d[key] = value, the value's reference taken */
static void dict_set(PyObject *d, const char *key, PyObject *value)
{
	if (value) {
		PyDict_SetItemString(d, key, value);
		Py_DECREF(value);
	}
}

static PyObject *input_value(const bru_input *in)
{
	switch (in->kind) {
		case BRU_VALUE_FLOAT: return PyFloat_FromDouble(in->v[0]);
		case BRU_VALUE_INT: return PyLong_FromLongLong((long long)in->v[0]);
		case BRU_VALUE_BOOL: return PyBool_FromLong(in->v[0] != 0.0);
		case BRU_VALUE_VEC2: return Py_BuildValue("(dd)", in->v[0], in->v[1]);
		case BRU_VALUE_VEC3: return Py_BuildValue("(ddd)", in->v[0], in->v[1], in->v[2]);
		case BRU_VALUE_VEC4: return Py_BuildValue("(dddd)", in->v[0], in->v[1], in->v[2], in->v[3]);
		case BRU_VALUE_ASSET:
			return Py_BuildValue("{s:s,s:s,s:O}", "asset", in->text, "path", in->path,
			                     "exists", in->exists ? Py_True : Py_False);
		case BRU_VALUE_TOKEN: return PyUnicode_FromString(in->text);
	}
	Py_RETURN_NONE;
}

static const char *light_kind(int kind)
{
	switch (kind) {
		case BRU_LIGHT_SPHERE: return "SPHERE";
		case BRU_LIGHT_DISTANT: return "DISTANT";
		case BRU_LIGHT_RECT: return "RECT";
		case BRU_LIGHT_DISK: return "DISK";
		case BRU_LIGHT_CYLINDER: return "CYLINDER";
	}
	return "UNKNOWN";
}

PyDoc_STRVAR(brmx_capture_read_doc,
".. function:: capture_read(path)\n"
"\n"
"   BGE-Remix P12: read an RTX Remix capture (its .usd or .usda stage) with\n"
"   the bridge's OpenUSD, everything as the capture has it (its units and up\n"
"   axis; USD's matrices, row vectors, as 16 numbers).\n"
"\n"
"   :return: dict with meters_per_unit, z_up, game_name, exe_name, report\n"
"      (a list of lines), meshes (hash, name, points, face_sizes, corners,\n"
"      normals, uvs, colors: bytes of float32/int32 or None; double_sided),\n"
"      instances (hash, name, mesh, material: indices, -1 none; sky, matrix),\n"
"      materials (hash, name, mdl, sub_identifier, inputs: name to value; an\n"
"      asset is a dict with asset, path, exists), lights (hash, name, kind,\n"
"      color, intensity, exposure, radius, angle, width, height, length,\n"
"      shaped, cone_angle, cone_softness, focus, matrix), camera (matrix,\n"
"      focal_length, horizontal_aperture, vertical_aperture, near, far,\n"
"      perspective) or None.\n"
"   :raises RuntimeError: when it cannot be read, or is no capture.\n");
static PyObject *brmx_capture_read(PyObject *UNUSED_self, PyObject *args)
{
	const char *path;
	char err[2048] = "";
	const bru_capture_api *api;
	bru_capture *cap;
	bru_capture_info info;
	PyObject *out, *list, *lines;
	const char *line, *end;
	int i, k;

	if (!PyArg_ParseTuple(args, "s:capture_read", &path)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		PyErr_SetString(PyExc_RuntimeError, BRMX_bridge_error());
		return NULL;
	}
	api = B->usd_capture_api(err, (int)sizeof(err));
	if (api == NULL) {
		PyErr_SetString(PyExc_RuntimeError, err);
		return NULL;
	}
	Py_BEGIN_ALLOW_THREADS
	cap = api->open(B->usd_plugin_dir(), path, err, (int)sizeof(err));
	Py_END_ALLOW_THREADS
	if (cap == NULL) {
		PyErr_SetString(PyExc_RuntimeError, err);
		return NULL;
	}
	api->info(cap, &info);
	out = PyDict_New();
	dict_set(out, "meters_per_unit", PyFloat_FromDouble(info.meters_per_unit));
	dict_set(out, "z_up", PyBool_FromLong(info.z_up));
	dict_set(out, "game_name", PyUnicode_FromString(info.game_name));
	dict_set(out, "exe_name", PyUnicode_FromString(info.exe_name));
	lines = PyList_New(0);
	for (line = info.report; *line; line = *end ? end + 1 : end) {
		PyObject *l;
		end = strchr(line, '\n');
		if (end == NULL) {
			end = line + strlen(line);
		}
		if (end > line) {
			l = PyUnicode_DecodeUTF8(line, end - line, "replace");
			if (l) {
				PyList_Append(lines, l);
				Py_DECREF(l);
			}
		}
	}
	dict_set(out, "report", lines);

	list = PyList_New(0);
	for (i = 0; i < info.mesh_count; i++) {
		bru_mesh m;
		PyObject *d;
		if (!api->mesh(cap, i, &m)) {
			continue;
		}
		d = PyDict_New();
		dict_set(d, "hash", hex_hash(m.hash));
		dict_set(d, "name", PyUnicode_FromString(m.name));
		dict_set(d, "points", bytes_or_none(m.points, sizeof(float) * 3 * (size_t)m.vertex_count));
		dict_set(d, "face_sizes", bytes_or_none(m.face_sizes, sizeof(int) * (size_t)m.face_count));
		dict_set(d, "corners", bytes_or_none(m.corners, sizeof(int) * (size_t)m.corner_count));
		dict_set(d, "normals", bytes_or_none(m.normals, sizeof(float) * 3 * (size_t)m.corner_count));
		dict_set(d, "uvs", bytes_or_none(m.uvs, sizeof(float) * 2 * (size_t)m.corner_count));
		dict_set(d, "colors", bytes_or_none(m.colors, sizeof(float) * 4 * (size_t)m.corner_count));
		dict_set(d, "double_sided", PyBool_FromLong(m.double_sided));
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "meshes", list);

	list = PyList_New(0);
	for (i = 0; i < info.instance_count; i++) {
		bru_instance in;
		if (!api->instance(cap, i, &in)) {
			continue;
		}
		{
			PyObject *d = PyDict_New();
			dict_set(d, "hash", hex_hash(in.hash));
			dict_set(d, "name", PyUnicode_FromString(in.name));
			dict_set(d, "mesh", PyLong_FromLong(in.mesh));
			dict_set(d, "material", PyLong_FromLong(in.material));
			dict_set(d, "sky", PyBool_FromLong(in.sky));
			dict_set(d, "matrix", matrix_tuple(in.matrix));
			PyList_Append(list, d);
			Py_DECREF(d);
		}
	}
	dict_set(out, "instances", list);

	list = PyList_New(0);
	for (i = 0; i < info.material_count; i++) {
		bru_material mt;
		PyObject *d, *inputs;
		if (!api->material(cap, i, &mt)) {
			continue;
		}
		d = PyDict_New();
		dict_set(d, "hash", hex_hash(mt.hash));
		dict_set(d, "name", PyUnicode_FromString(mt.name));
		dict_set(d, "mdl", PyUnicode_FromString(mt.mdl));
		dict_set(d, "sub_identifier", PyUnicode_FromString(mt.sub_identifier));
		inputs = PyDict_New();
		for (k = 0; k < mt.input_count; k++) {
			bru_input in;
			if (api->material_input(cap, i, k, &in)) {
				dict_set(inputs, in.name, input_value(&in));
			}
		}
		dict_set(d, "inputs", inputs);
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "materials", list);

	list = PyList_New(0);
	for (i = 0; i < info.light_count; i++) {
		bru_light l;
		PyObject *d;
		if (!api->light(cap, i, &l)) {
			continue;
		}
		d = PyDict_New();
		dict_set(d, "hash", hex_hash(l.hash));
		dict_set(d, "name", PyUnicode_FromString(l.name));
		dict_set(d, "kind", PyUnicode_FromString(light_kind(l.kind)));
		dict_set(d, "color", Py_BuildValue("(fff)", l.color[0], l.color[1], l.color[2]));
		dict_set(d, "intensity", PyFloat_FromDouble(l.intensity));
		dict_set(d, "exposure", PyFloat_FromDouble(l.exposure));
		dict_set(d, "radius", PyFloat_FromDouble(l.radius));
		dict_set(d, "angle", PyFloat_FromDouble(l.angle));
		dict_set(d, "width", PyFloat_FromDouble(l.width));
		dict_set(d, "height", PyFloat_FromDouble(l.height));
		dict_set(d, "length", PyFloat_FromDouble(l.length));
		dict_set(d, "shaped", PyBool_FromLong(l.shaped));
		dict_set(d, "cone_angle", PyFloat_FromDouble(l.cone_angle));
		dict_set(d, "cone_softness", PyFloat_FromDouble(l.cone_softness));
		dict_set(d, "focus", PyFloat_FromDouble(l.focus));
		dict_set(d, "matrix", matrix_tuple(l.matrix));
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "lights", list);

	{
		bru_camera c;
		if (api->camera(cap, &c)) {
			PyObject *d = PyDict_New();
			dict_set(d, "matrix", matrix_tuple(c.matrix));
			dict_set(d, "focal_length", PyFloat_FromDouble(c.focal_length));
			dict_set(d, "horizontal_aperture", PyFloat_FromDouble(c.horizontal_aperture));
			dict_set(d, "vertical_aperture", PyFloat_FromDouble(c.vertical_aperture));
			dict_set(d, "near", PyFloat_FromDouble(c.near_clip));
			dict_set(d, "far", PyFloat_FromDouble(c.far_clip));
			dict_set(d, "perspective", PyBool_FromLong(c.perspective));
			dict_set(out, "camera", d);
		}
		else {
			Py_INCREF(Py_None);
			dict_set(out, "camera", Py_None);
		}
	}
	api->close(cap);
	return out;
}

PyDoc_STRVAR(brmx_dds_to_png_doc,
".. function:: dds_to_png(dds, png)\n"
"\n"
"   BGE-Remix P12: a DDS texture (any format: block-compressed or not; its\n"
"   first mip level) written as a PNG, with the bridge's DirectXTex.\n"
"\n"
"   :return: (ok, error)\n");
static PyObject *brmx_dds_to_png(PyObject *UNUSED_self, PyObject *args)
{
	PyObject *dds_obj, *png_obj;
	wchar_t *dds, *png;
	char err[1024] = "";
	int ok;

	if (!PyArg_ParseTuple(args, "UU:dds_to_png", &dds_obj, &png_obj)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		return Py_BuildValue("(Os)", Py_False, BRMX_bridge_error());
	}
	dds = PyUnicode_AsWideCharString(dds_obj, NULL);
	png = dds ? PyUnicode_AsWideCharString(png_obj, NULL) : NULL;
	if (dds == NULL || png == NULL) {
		if (dds) {
			PyMem_Free(dds);
		}
		return NULL;
	}
	Py_BEGIN_ALLOW_THREADS
	ok = B->dds_to_png(dds, png, err, (int)sizeof(err));
	Py_END_ALLOW_THREADS
	PyMem_Free(dds);
	PyMem_Free(png);
	return Py_BuildValue("(Os)", ok ? Py_True : Py_False, err);
}

PyDoc_STRVAR(brmx_usd_dump_doc,
".. function:: usd_dump(path, json_path)\n"
"\n"
"   BGE-Remix P12: the USD stage at path as the bridge's OpenUSD composes it,\n"
"   written as JSON to json_path (every prim, its attributes and their values;\n"
"   arrays as their count and first values).\n"
"\n"
"   :return: (ok, error)\n");
static PyObject *brmx_usd_dump(PyObject *UNUSED_self, PyObject *args)
{
	const char *path, *json;
	char err[1024] = "";
	int ok;

	if (!PyArg_ParseTuple(args, "ss:usd_dump", &path, &json)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		return Py_BuildValue("(Os)", Py_False, BRMX_bridge_error());
	}
	Py_BEGIN_ALLOW_THREADS
	ok = B->usd_stage_dump(path, json, err, (int)sizeof(err));
	Py_END_ALLOW_THREADS
	return Py_BuildValue("(Os)", ok ? Py_True : Py_False, err);
}

/* BGE-Remix P12 round 6: any tool's scene (File > Import > Universal Scene
 * Description) */

static PyObject *shader_input(const bru_shader_input *in)
{
	return Py_BuildValue("{s:i,s:(dddd),s:s,s:s,s:O,s:s,s:s}", "kind", in->kind, "v", in->v[0], in->v[1], in->v[2],
	                     in->v[3], "text", in->text, "path", in->path, "exists", in->exists ? Py_True : Py_False,
	                     "output", in->output, "color_space", in->color_space);
}

PyDoc_STRVAR(brmx_usd_read_doc,
".. function:: usd_read(path)\n"
"\n"
"   BGE-Remix P12 round 6: read any tool's USD scene with the bridge's\n"
"   OpenUSD, as it composes it (references, instancing), in the file's own\n"
"   units and up axis (USD's matrices: rows, 16 numbers, local to world).\n"
"\n"
"   :return: dict with meters_per_unit, z_up, default_prim, creator, report\n"
"      (text, a line each), usd_errors, nodes (name, path, parent, kind: 0\n"
"      transform, 1 mesh, 2 light, 3 camera; index, visible, material,\n"
"      subset_materials, matrix), meshes (name, vertices, faces, corners,\n"
"      points, face_sizes, corners_data, normals, uvs, colors: bytes of\n"
"      float32/int32 or None; uv_name, double_sided, subsets: name, faces),\n"
"      materials (name, path, preview, aperture, mdl, sub_identifier, other,\n"
"      preview_inputs, aperture_inputs: name to kind, v, text, path, exists,\n"
"      output, color_space), lights (as capture_read's), cameras, physics\n"
"      (round 7: the physics as JSON text, bge_remix_usd.h).\n"
"   :raises RuntimeError: when it cannot be read.\n");
static PyObject *brmx_usd_read(PyObject *UNUSED_self, PyObject *args)
{
	const char *path;
	char err[2048] = "";
	const bru_scene_api *api;
	bru_scene *sc;
	bru_scene_info info;
	PyObject *out, *list;
	int i, k;

	if (!PyArg_ParseTuple(args, "s:usd_read", &path)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		PyErr_SetString(PyExc_RuntimeError, BRMX_bridge_error());
		return NULL;
	}
	api = B->usd_scene_api(err, (int)sizeof(err));
	if (api == NULL) {
		PyErr_SetString(PyExc_RuntimeError, err);
		return NULL;
	}
	Py_BEGIN_ALLOW_THREADS
	sc = api->open(B->usd_plugin_dir(), path, err, (int)sizeof(err));
	Py_END_ALLOW_THREADS
	if (sc == NULL) {
		PyErr_SetString(PyExc_RuntimeError, err);
		return NULL;
	}
	api->info(sc, &info);
	out = PyDict_New();
	dict_set(out, "meters_per_unit", PyFloat_FromDouble(info.meters_per_unit));
	dict_set(out, "z_up", PyBool_FromLong(info.z_up));
	dict_set(out, "default_prim", PyUnicode_FromString(info.default_prim));
	dict_set(out, "creator", PyUnicode_FromString(info.creator));
	dict_set(out, "report", PyUnicode_DecodeUTF8(info.report, (Py_ssize_t)strlen(info.report), "replace"));
	dict_set(out, "usd_errors", PyLong_FromLong(info.usd_errors));

	list = PyList_New(0);
	for (i = 0; i < info.node_count; i++) {
		bru_node n;
		PyObject *d, *subs;
		if (!api->node(sc, i, &n)) {
			continue;
		}
		d = PyDict_New();
		dict_set(d, "name", PyUnicode_FromString(n.name));
		dict_set(d, "prim_name", PyUnicode_FromString(n.prim_name));
		dict_set(d, "path", PyUnicode_FromString(n.path));
		dict_set(d, "parent", PyLong_FromLong(n.parent));
		dict_set(d, "kind", PyLong_FromLong(n.kind));
		dict_set(d, "index", PyLong_FromLong(n.index));
		dict_set(d, "visible", PyBool_FromLong(n.visible));
		dict_set(d, "material", PyLong_FromLong(n.material));
		subs = PyList_New(0);
		for (k = 0; k < n.subset_count; k++) {
			PyObject *v = PyLong_FromLong(n.subset_materials[k]);
			PyList_Append(subs, v);
			Py_DECREF(v);
		}
		dict_set(d, "subset_materials", subs);
		dict_set(d, "matrix", matrix_tuple(n.matrix));
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "nodes", list);

	list = PyList_New(0);
	for (i = 0; i < info.mesh_count; i++) {
		bru_scene_mesh m;
		PyObject *d, *subs;
		if (!api->mesh(sc, i, &m)) {
			continue;
		}
		d = PyDict_New();
		dict_set(d, "name", PyUnicode_FromString(m.name));
		dict_set(d, "vertices", PyLong_FromLong(m.vertex_count));
		dict_set(d, "faces", PyLong_FromLong(m.face_count));
		dict_set(d, "corners", PyLong_FromLong(m.corner_count));
		dict_set(d, "points", bytes_or_none(m.points, sizeof(float) * 3 * (size_t)m.vertex_count));
		dict_set(d, "face_sizes", bytes_or_none(m.face_sizes, sizeof(int) * (size_t)m.face_count));
		dict_set(d, "corners_data", bytes_or_none(m.corners, sizeof(int) * (size_t)m.corner_count));
		dict_set(d, "normals", bytes_or_none(m.normals, sizeof(float) * 3 * (size_t)m.corner_count));
		dict_set(d, "uvs", bytes_or_none(m.uvs, sizeof(float) * 2 * (size_t)m.corner_count));
		dict_set(d, "uv_name", PyUnicode_FromString(m.uv_name));
		dict_set(d, "colors", bytes_or_none(m.colors, sizeof(float) * 4 * (size_t)m.corner_count));
		dict_set(d, "double_sided", PyBool_FromLong(m.double_sided));
		subs = PyList_New(0);
		for (k = 0; k < m.subset_count; k++) {
			bru_subset s;
			if (api->subset(sc, i, k, &s)) {
				PyObject *faces = PyList_New(s.face_count), *sd;
				int j;
				for (j = 0; j < s.face_count; j++) {
					PyList_SET_ITEM(faces, j, PyLong_FromLong(s.faces[j]));
				}
				sd = PyDict_New();
				dict_set(sd, "name", PyUnicode_FromString(s.name));
				dict_set(sd, "faces", faces);
				PyList_Append(subs, sd);
				Py_DECREF(sd);
			}
		}
		dict_set(d, "subsets", subs);
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "meshes", list);

	list = PyList_New(0);
	for (i = 0; i < info.material_count; i++) {
		bru_scene_material mt;
		PyObject *d;
		int which;
		if (!api->material(sc, i, &mt)) {
			continue;
		}
		d = PyDict_New();
		dict_set(d, "name", PyUnicode_FromString(mt.name));
		dict_set(d, "path", PyUnicode_FromString(mt.path));
		dict_set(d, "preview", PyBool_FromLong(mt.preview));
		dict_set(d, "aperture", PyBool_FromLong(mt.aperture));
		dict_set(d, "mdl", PyUnicode_FromString(mt.mdl));
		dict_set(d, "sub_identifier", PyUnicode_FromString(mt.sub_identifier));
		dict_set(d, "other", PyUnicode_FromString(mt.other));
		for (which = 0; which < 2; which++) {
			const int count = which ? mt.aperture_input_count : mt.preview_input_count;
			PyObject *inputs = PyDict_New();
			for (k = 0; k < count; k++) {
				bru_shader_input in;
				if (api->material_input(sc, i, which, k, &in)) {
					dict_set(inputs, in.name, shader_input(&in));
				}
			}
			dict_set(d, which ? "aperture_inputs" : "preview_inputs", inputs);
		}
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "materials", list);

	list = PyList_New(0);
	for (i = 0;; i++) {
		bru_light l;
		PyObject *d;
		if (!api->light(sc, i, &l)) {
			break;
		}
		d = PyDict_New();
		dict_set(d, "hash", hex_hash(l.hash));
		dict_set(d, "name", PyUnicode_FromString(l.name));
		dict_set(d, "kind", PyUnicode_FromString(light_kind(l.kind)));
		dict_set(d, "color", Py_BuildValue("(fff)", l.color[0], l.color[1], l.color[2]));
		dict_set(d, "intensity", PyFloat_FromDouble(l.intensity));
		dict_set(d, "exposure", PyFloat_FromDouble(l.exposure));
		dict_set(d, "radius", PyFloat_FromDouble(l.radius));
		dict_set(d, "angle", PyFloat_FromDouble(l.angle));
		dict_set(d, "width", PyFloat_FromDouble(l.width));
		dict_set(d, "height", PyFloat_FromDouble(l.height));
		dict_set(d, "length", PyFloat_FromDouble(l.length));
		dict_set(d, "shaped", PyBool_FromLong(l.shaped));
		dict_set(d, "cone_angle", PyFloat_FromDouble(l.cone_angle));
		dict_set(d, "cone_softness", PyFloat_FromDouble(l.cone_softness));
		dict_set(d, "focus", PyFloat_FromDouble(l.focus));
		dict_set(d, "matrix", matrix_tuple(l.matrix));
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "lights", list);

	list = PyList_New(0);
	for (i = 0;; i++) {
		bru_camera c;
		PyObject *d;
		if (!api->camera(sc, i, &c)) {
			break;
		}
		d = PyDict_New();
		dict_set(d, "matrix", matrix_tuple(c.matrix));
		dict_set(d, "focal_length", PyFloat_FromDouble(c.focal_length));
		dict_set(d, "horizontal_aperture", PyFloat_FromDouble(c.horizontal_aperture));
		dict_set(d, "vertical_aperture", PyFloat_FromDouble(c.vertical_aperture));
		dict_set(d, "near", PyFloat_FromDouble(c.near_clip));
		dict_set(d, "far", PyFloat_FromDouble(c.far_clip));
		dict_set(d, "perspective", PyBool_FromLong(c.perspective));
		PyList_Append(list, d);
		Py_DECREF(d);
	}
	dict_set(out, "cameras", list);
	/* round 7: the physics, as JSON (bge_remix_usd.py parses it) */
	{
		const char *phys = api->physics(sc);
		dict_set(out, "physics", PyUnicode_DecodeUTF8(phys, (Py_ssize_t)strlen(phys), "replace"));
	}
	api->close(sc);
	return out;
}

PyDoc_STRVAR(brmx_usd_convert_doc,
".. function:: usd_convert(src, dst)\n"
"\n"
"   BGE-Remix P12 round 6: the USD layer at src written again at dst, in the\n"
"   format dst's extension names (.usdc binary, .usd binary, .usda text).\n"
"\n"
"   :return: (ok, error)\n");
static PyObject *brmx_usd_convert(PyObject *UNUSED_self, PyObject *args)
{
	const char *src, *dst;
	char err[1024] = "";
	int ok;

	if (!PyArg_ParseTuple(args, "ss:usd_convert", &src, &dst)) {
		return NULL;
	}
	if (!bridge_ensure()) {
		return Py_BuildValue("(Os)", Py_False, BRMX_bridge_error());
	}
	Py_BEGIN_ALLOW_THREADS
	ok = B->usd_convert(src, dst, err, (int)sizeof(err));
	Py_END_ALLOW_THREADS
	return Py_BuildValue("(Os)", ok ? Py_True : Py_False, err);
}

PyDoc_STRVAR(brmx_dds_write_doc,
".. function:: dds_write(path, width, height, rgba, kind, top_first)\n"
"\n"
"   BGE-Remix P12: write a DDS texture with the bridge's encoder (what\n"
"   Remix reads: BC7 for colour, BC5 octahedral for normal maps, BC4 for one\n"
"   channel), with a full mip chain. rgba: width * height * 4 bytes, rows\n"
"   from the bottom (as Blender keeps images), sRGB for colour. kind: 'COLOR',\n"
"   'NORMAL' or 'SCALAR' (its red channel). top_first: the file's rows from\n"
"   the picture's top (USD's coordinates, an RTX Remix mod).\n"
"\n"
"   :return: (ok, error)\n");
static PyObject *brmx_dds_write(PyObject *UNUSED_self, PyObject *args)
{
	PyObject *path_obj;
	const char *kind;
	Py_buffer px;
	int width, height, top_first;
	wchar_t *path;
	brb_texture_desc desc;
	brb_texture_result res;
	int r;

	if (!PyArg_ParseTuple(args, "Uiiy*sp:dds_write", &path_obj, &width, &height, &px, &kind, &top_first)) {
		return NULL;
	}
	if (width <= 0 || height <= 0 || px.len < (Py_ssize_t)width * height * 4) {
		PyBuffer_Release(&px);
		PyErr_SetString(PyExc_ValueError, "dds_write: the pixels do not fill width * height * 4 bytes");
		return NULL;
	}
	if (!bridge_ensure()) {
		PyBuffer_Release(&px);
		return Py_BuildValue("(Os)", Py_False, BRMX_bridge_error());
	}
	path = PyUnicode_AsWideCharString(path_obj, NULL);
	if (path == NULL) {
		PyBuffer_Release(&px);
		return NULL;
	}
	memset(&desc, 0, sizeof(desc));
	memset(&res, 0, sizeof(res));
	desc.path = path;
	desc.kind = STREQ(kind, "NORMAL") ? BRB_TEXTURE_NORMAL : STREQ(kind, "SCALAR") ? BRB_TEXTURE_SCALAR :
	                                                                                  BRB_TEXTURE_COLOR;
	desc.width = width;
	desc.height = height;
	desc.rgba8 = (const unsigned char *)px.buf;
	desc.channel = 0;
	desc.flags = top_first ? BRB_TEXTURE_TOP_FIRST : 0;
	Py_BEGIN_ALLOW_THREADS
	r = B->texture_write(&desc, &res);
	Py_END_ALLOW_THREADS
	PyMem_Free(path);
	PyBuffer_Release(&px);
	return Py_BuildValue("(Os)", r == 0 ? Py_True : Py_False, r == 0 ? "" : res.error);
}

/* BGE-Remix P12 round 5: the capture checks (BRMX_capture.h) */

static ID *find_id(ListBase *lb, const char *name)
{
	return (ID *)BLI_findstring(lb, name, offsetof(ID, name) + 2);
}

PyDoc_STRVAR(brmx_capture_fp_doc,
".. function:: capture_fp(kind, name)\n"
"\n"
"   BGE-Remix P12: the fingerprint of a datablock as a capture import keeps\n"
"   it (bge_remix_capture_fp). kind: 'MESH', 'MATERIAL', 'IMAGE' (by the\n"
"   datablock's name), 'LAMP' (a lamp object: its lamp's settings),\n"
"   'OBJECT' (a place: a dict of its parts matrix, materials, physics) or\n"
"   'MATRIX' (a place or lamp: where it is, a list of 16 numbers).\n"
"\n"
"   :return: the fingerprint, or None when there is no such datablock\n");
static PyObject *brmx_capture_fp(PyObject *UNUSED_self, PyObject *args)
{
	const char *kind, *name;
	char fp[33], fp2[33], fp3[33];
	Main *bmain = G.main;
	if (!PyArg_ParseTuple(args, "ss:capture_fp", &kind, &name)) {
		return NULL;
	}
	if (STREQ(kind, "MESH")) {
		Mesh *me = (Mesh *)find_id(&bmain->mesh, name);
		if (!me) Py_RETURN_NONE;
		BRMX_capture_fp_mesh(me, fp);
	}
	else if (STREQ(kind, "MATERIAL")) {
		Material *ma = (Material *)find_id(&bmain->mat, name);
		if (!ma) Py_RETURN_NONE;
		BRMX_capture_fp_material(bmain, ma, fp);
	}
	else if (STREQ(kind, "IMAGE")) {
		Image *ima = (Image *)find_id(&bmain->image, name);
		if (!ima) Py_RETURN_NONE;
		BRMX_capture_fp_image(bmain, ima, fp);
	}
	else if (STREQ(kind, "LAMP")) {
		Object *ob = (Object *)find_id(&bmain->object, name);
		if (!ob || ob->type != OB_LAMP) Py_RETURN_NONE;
		BRMX_capture_fp_lamp(ob, fp);
	}
	else if (STREQ(kind, "MATRIX")) {
		/* where a place or lamp is: obmat's 16 numbers, as kept at import */
		Object *ob = (Object *)find_id(&bmain->object, name);
		if (!ob) Py_RETURN_NONE;
		PyObject *l = PyList_New(16);
		for (int i = 0; i < 16; i++) {
			PyList_SET_ITEM(l, i, PyFloat_FromDouble((double)(&ob->obmat[0][0])[i]));
		}
		return l;
	}
	else if (STREQ(kind, "OBJECT")) {
		Object *ob = (Object *)find_id(&bmain->object, name);
		if (!ob) Py_RETURN_NONE;
		BRMX_capture_fp_object(ob, fp, fp2, fp3);
		return Py_BuildValue("{s:s,s:s,s:s}", "matrix", fp, "materials", fp2, "physics", fp3);
	}
	else {
		PyErr_Format(PyExc_ValueError, "capture_fp: no kind %s", kind);
		return NULL;
	}
	return PyUnicode_FromString(fp);
}

static void dict_take(PyObject *d, const char *key, PyObject *value)
{
	PyDict_SetItemString(d, key, value);
	Py_DECREF(value);
}

static PyObject *id_list(int count, ID *(*get)(const BRMX_CaptureCheck *, int), const BRMX_CaptureCheck *c)
{
	PyObject *l = PyList_New(0);
	for (int i = 0; i < count; i++) {
		ID *id = get(c, i);
		PyObject *n = PyUnicode_FromString(id ? id->name + 2 : "");
		PyList_Append(l, n);
		Py_DECREF(n);
	}
	return l;
}

static ID *get_lamp(const BRMX_CaptureCheck *c, int i)
{
	return (ID *)BRMX_capture_lamp(c, i);
}

static ID *get_material(const BRMX_CaptureCheck *c, int i)
{
	return (ID *)BRMX_capture_material(c, i);
}

PyDoc_STRVAR(brmx_capture_check_doc,
".. function:: capture_check(scene)\n"
"\n"
"   BGE-Remix P12: a scene imported from an RTX Remix capture checked against\n"
"   how it came in, as the Remix View shows it and the mod export writes it.\n"
"\n"
"   :return: None for a scene not from a capture, else a dict: notes (a list\n"
"      of (code, object name, text): what a mod cannot carry), meshes (the\n"
"      replaced: a list of (hash, mesh name)), groups (the added: a list of\n"
"      (mesh hash, place object name, [object names])), lamps and materials\n"
"      (the replaced, by name), objects (object name: (mod, hash, count);\n"
"      mod: 'NONE', 'OWN', 'REPLACED', 'ADDS', 'ADDED', 'LEFT_OUT')\n");
static PyObject *brmx_capture_check(PyObject *UNUSED_self, PyObject *args)
{
	static const char *mods[] = {"NONE", "OWN", "REPLACED", "ADDS", "ADDED", "LEFT_OUT"};
	const char *scene_name;
	Main *bmain = G.main;
	if (!PyArg_ParseTuple(args, "s:capture_check", &scene_name)) {
		return NULL;
	}
	Scene *scene = (Scene *)find_id(&bmain->scene, scene_name);
	if (!scene) {
		PyErr_Format(PyExc_ValueError, "capture_check: no scene %s", scene_name);
		return NULL;
	}
	BRMX_CaptureCheck *c = BRMX_capture_check(bmain, scene);
	if (!c) {
		Py_RETURN_NONE;
	}
	PyObject *d = PyDict_New();
	PyObject *notes = PyList_New(0);
	for (int i = 0; i < BRMX_capture_note_count(c); i++) {
		const char *code = "", *object = "";
		const char *text = BRMX_capture_note(c, i, &code, &object);
		PyObject *t = Py_BuildValue("(sss)", code, object, text);
		PyList_Append(notes, t);
		Py_DECREF(t);
	}
	dict_take(d, "notes", notes);
	PyObject *meshes = PyList_New(0);
	for (int i = 0; i < BRMX_capture_mesh_count(c); i++) {
		const char *hash = "";
		Mesh *me = BRMX_capture_mesh(c, i, &hash);
		PyObject *t = Py_BuildValue("(ss)", hash, me ? me->id.name + 2 : "");
		PyList_Append(meshes, t);
		Py_DECREF(t);
	}
	dict_take(d, "meshes", meshes);
	PyObject *groups = PyList_New(0);
	for (int i = 0; i < BRMX_capture_group_count(c); i++) {
		const char *hash = "";
		int count = 0;
		Object *place = BRMX_capture_group(c, i, &hash, &count);
		PyObject *names = PyList_New(0);
		for (int j = 0; j < count; j++) {
			Object *ob = BRMX_capture_group_object(c, i, j);
			PyObject *n = PyUnicode_FromString(ob ? ob->id.name + 2 : "");
			PyList_Append(names, n);
			Py_DECREF(n);
		}
		PyObject *t = Py_BuildValue("(ssN)", hash, place ? place->id.name + 2 : "", names);
		PyList_Append(groups, t);
		Py_DECREF(t);
	}
	dict_take(d, "groups", groups);
	dict_take(d, "lamps", id_list(BRMX_capture_lamp_count(c), get_lamp, c));
	dict_take(d, "materials", id_list(BRMX_capture_material_count(c), get_material, c));
	PyObject *objects = PyDict_New();
	for (Base *b = (Base *)scene->base.first; b; b = b->next) {
		int count = 0;
		const char *hash = "";
		const int mod = BRMX_capture_object_mod(c, b->object, &count, &hash);
		PyObject *t = Py_BuildValue("(ssi)", mods[mod], hash, count);
		PyDict_SetItemString(objects, b->object->id.name + 2, t);
		Py_DECREF(t);
	}
	dict_take(d, "objects", objects);
	BRMX_capture_check_free(c);
	return d;
}

static PyMethodDef brmx_methods[] = {
	{"bridge_info", (PyCFunction)brmx_bridge_info, METH_NOARGS, brmx_bridge_info_doc},
	{"status", (PyCFunction)brmx_status, METH_NOARGS, brmx_status_doc},
	{"load", (PyCFunction)brmx_load, METH_VARARGS, brmx_load_doc},
	{"startup", (PyCFunction)brmx_startup, METH_VARARGS | METH_KEYWORDS, brmx_startup_doc},
	{"set_config", (PyCFunction)brmx_set_config, METH_VARARGS, brmx_set_config_doc},
	{"triangle_test", (PyCFunction)brmx_triangle_test, METH_VARARGS | METH_KEYWORDS, brmx_triangle_test_doc},
	{"runtime_dir", (PyCFunction)brmx_runtime_dir, METH_NOARGS, brmx_runtime_dir_doc},
	{"shutdown", (PyCFunction)brmx_shutdown, METH_NOARGS, brmx_shutdown_doc},
	{"view_update", (PyCFunction)brmx_view_update, METH_VARARGS, brmx_view_update_doc},
	{"view_draw", (PyCFunction)brmx_view_draw, METH_VARARGS, brmx_view_draw_doc},
	{"engine_free", (PyCFunction)brmx_engine_free, METH_VARARGS, brmx_engine_free_doc},
	{"render_sync", (PyCFunction)brmx_render_sync, METH_VARARGS, brmx_render_sync_doc},
	{"render_frame", (PyCFunction)brmx_render_frame, METH_VARARGS, brmx_render_frame_doc},
	{"view_stats", (PyCFunction)brmx_view_stats, METH_NOARGS, brmx_view_stats_doc},
	{"material_match", (PyCFunction)brmx_material_match, METH_VARARGS, brmx_material_match_doc},
	{"inspect", (PyCFunction)brmx_inspect, METH_VARARGS, brmx_inspect_doc},
	{"debug_option", (PyCFunction)brmx_debug_option, METH_VARARGS, brmx_debug_option_doc},
	/* BGE-Remix P10.2, P10.5: the texture remaster */
	{"bake_tile", (PyCFunction)brmx_bake_tile, METH_VARARGS, brmx_bake_tile_doc},
	{"precache", (PyCFunction)brmx_precache, METH_VARARGS, brmx_precache_doc},
	{"precache_poll", (PyCFunction)brmx_precache_poll, METH_NOARGS, brmx_precache_poll_doc},
	{"precache_reset", (PyCFunction)brmx_precache_reset, METH_NOARGS, brmx_precache_reset_doc},
	{"atlas_bake", (PyCFunction)brmx_atlas_bake, METH_VARARGS, brmx_atlas_bake_doc},
	{"atlas_preview", (PyCFunction)brmx_atlas_preview, METH_NOARGS, brmx_atlas_preview_doc},
	{"atlas_pack", (PyCFunction)brmx_atlas_pack, METH_VARARGS, brmx_atlas_pack_doc},
	{"settings", (PyCFunction)brmx_settings, METH_NOARGS, brmx_settings_doc},  /* BGE-Remix P10.12 */
	/* BGE-Remix P12: OpenUSD, RTX Remix captures */
	{"usd_selftest", (PyCFunction)brmx_usd_selftest, METH_VARARGS, brmx_usd_selftest_doc},
	{"capture_read", (PyCFunction)brmx_capture_read, METH_VARARGS, brmx_capture_read_doc},
	{"dds_to_png", (PyCFunction)brmx_dds_to_png, METH_VARARGS, brmx_dds_to_png_doc},
	{"usd_dump", (PyCFunction)brmx_usd_dump, METH_VARARGS, brmx_usd_dump_doc},
	{"usd_read", (PyCFunction)brmx_usd_read, METH_VARARGS, brmx_usd_read_doc},  /* round 6 */
	{"usd_convert", (PyCFunction)brmx_usd_convert, METH_VARARGS, brmx_usd_convert_doc},
	{"dds_write", (PyCFunction)brmx_dds_write, METH_VARARGS, brmx_dds_write_doc},
	/* BGE-Remix P12 round 5 */
	{"capture_fp", (PyCFunction)brmx_capture_fp, METH_VARARGS, brmx_capture_fp_doc},
	{"capture_check", (PyCFunction)brmx_capture_check, METH_VARARGS, brmx_capture_check_doc},
	{NULL, NULL, 0, NULL}
};

PyDoc_STRVAR(brmx_module_doc,
"BGE-Remix: access to the NVIDIA RTX Remix runtime through bge_remix_bridge.dll.\n"
"Use the bge_remix package rather than this module directly.");

static struct PyModuleDef brmx_module = {
	PyModuleDef_HEAD_INIT,
	"_bge_remix",
	brmx_module_doc,
	-1,
	brmx_methods,
	NULL, NULL, NULL, NULL
};

static void brmx_atexit(void)
{
	BRMX_exit();
}

PyObject *BRMX_initPython(void)
{
	PyObject *mod = PyModule_Create(&brmx_module);
	if (mod) {
		PyModule_AddIntConstant(mod, "INTERFACE", BRB_ABI_VERSION);
		/* Shut Remix down before Blender's process ends. */
		Py_AtExit(brmx_atexit);
	}
	return mod;
}
