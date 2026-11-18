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

#include <stdint.h>

/* Bumped whenever a function below changes; the bridge refuses a
 * bge_remix_usd.dll with another value. 1: P12 round 1. 2: P12 round 2
 * (reading RTX Remix captures: bru_capture_get_api). 3: P12 round 3 (any
 * stage written out as JSON: bru_stage_dump). */
#define BRU_ABI_VERSION 3

BRU_API int bru_abi_version(void);

/* "25.11" */
BRU_API const char *bru_usd_version(void);

/* 1 once OpenUSD was started in this process, else 0 */
BRU_API int bru_started(void);

/* the self-test of usd_core.h, with OpenUSD's plugin descriptions in
 * plugin_dir; the report cut to max_bytes. Returns the failed checks. */
BRU_API int bru_selftest(const char *plugin_dir, const char *folder, char *r_report, int max_bytes);

/* ------------------------------------------------------------------------- */
/* P12 round 2: reading an RTX Remix capture (usd_capture.cpp)
 *
 * Everything is as the capture has it: its own units (meters_per_unit) and
 * up axis, USD's matrices (row vectors: the translation in the last row,
 * matrix[12..14]). The caller converts. Pointers stay valid until close. */

typedef struct bru_capture bru_capture;

enum {
	BRU_LIGHT_SPHERE = 0,
	BRU_LIGHT_DISTANT = 1,
	BRU_LIGHT_RECT = 2,
	BRU_LIGHT_DISK = 3,
	BRU_LIGHT_CYLINDER = 4,
};

enum {
	BRU_VALUE_FLOAT = 0,
	BRU_VALUE_INT = 1,
	BRU_VALUE_BOOL = 2,
	BRU_VALUE_VEC2 = 3,
	BRU_VALUE_VEC3 = 4,
	BRU_VALUE_VEC4 = 5,
	BRU_VALUE_ASSET = 6,
	BRU_VALUE_TOKEN = 7,
};

typedef struct bru_capture_info {
	double meters_per_unit;     /* the stage's metersPerUnit (Remix's rtx.sceneScale) */
	int z_up;                   /* 1: Z up, 0: Y up */
	double time;                /* the time read (the stage's start, or its default) */
	int mesh_count, instance_count, material_count, light_count;
	int camera_found;
	const char *game_name;      /* lightspeed_game_name ("" if none) */
	const char *exe_name;       /* lightspeed_exe_name */
	const char *report;         /* what was left out or missing, one line each ("" if nothing) */
} bru_capture_info;

/* a mesh: its vertices, and its faces as corners; normals, UVs and colours
 * per corner (whatever the capture's interpolation) */
typedef struct bru_mesh {
	uint64_t hash;              /* from its name, mesh_<16 hex digits> (0: another name) */
	const char *name;           /* the prim's name */
	int vertex_count, face_count, corner_count;
	const float *points;        /* vertex_count * 3 */
	const int *face_sizes;      /* face_count */
	const int *corners;         /* corner_count: vertex indices */
	const float *normals;       /* corner_count * 3, or NULL */
	const float *uvs;           /* corner_count * 2 (primvars:st), or NULL */
	const float *colors;        /* corner_count * 4 (displayColor, displayOpacity), or NULL */
	int double_sided;
} bru_mesh;

/* a place a mesh was drawn */
typedef struct bru_instance {
	uint64_t hash;              /* from its name, inst_<hash>_<n> (the mesh's hash) */
	const char *name;
	int mesh;                   /* index of its mesh */
	int material;               /* index of its material, -1: none */
	int sky;                    /* a sky_ instance */
	double matrix[16];          /* the mesh's object to world */
} bru_instance;

typedef struct bru_material {
	uint64_t hash;              /* from its name, mat_<16 hex digits> */
	const char *name;
	const char *mdl;            /* info:mdl:sourceAsset as written, e.g. ./AperturePBR_Opacity.mdl */
	const char *sub_identifier; /* e.g. AperturePBR_Opacity */
	int input_count;
} bru_material;

/* a material's input (inputs:<name>, or one of Remix's own attributes written
 * without the namespace, such as enable_opacity) */
typedef struct bru_input {
	const char *name;           /* without "inputs:" */
	int kind;                   /* BRU_VALUE_* */
	double v[4];                /* numbers, booleans (0, 1) */
	const char *text;           /* a token, or an asset as written */
	const char *path;           /* an asset: its absolute path (resolved, or where it would be) */
	int exists;                 /* an asset: the file is there */
} bru_input;

typedef struct bru_light {
	uint64_t hash;              /* from its name, light_<16 hex digits> */
	const char *name;
	int kind;                   /* BRU_LIGHT_* */
	float color[3];
	float intensity, exposure;
	float radius, angle;        /* sphere, disk, cylinder: radius; distant: angle (degrees) */
	float width, height, length;
	int shaped;                 /* UsdLuxShapingAPI */
	float cone_angle, cone_softness, focus;
	double matrix[16];          /* light to world; lights shine along their -Z */
} bru_light;

typedef struct bru_camera {
	double matrix[16];          /* camera to world; it looks along its -Z */
	float focal_length, horizontal_aperture, vertical_aperture;  /* millimetres (USD's tenths of a unit) */
	float near_clip, far_clip;
	int perspective;
} bru_camera;

typedef struct bru_capture_api {
	int abi;                    /* BRU_ABI_VERSION */
	/* NULL, with the reason in r_error, when it cannot be read or is no capture */
	bru_capture *(*open)(const char *plugin_dir, const char *path, char *r_error, int max_bytes);
	void (*close)(bru_capture *cap);
	void (*info)(const bru_capture *cap, bru_capture_info *r_info);
	int (*mesh)(const bru_capture *cap, int index, bru_mesh *r_mesh);
	int (*instance)(const bru_capture *cap, int index, bru_instance *r_instance);
	int (*material)(const bru_capture *cap, int index, bru_material *r_material);
	int (*material_input)(const bru_capture *cap, int material, int index, bru_input *r_input);
	int (*light)(const bru_capture *cap, int index, bru_light *r_light);
	int (*camera)(const bru_capture *cap, bru_camera *r_camera);
} bru_capture_api;

/* the capture reader's functions (the getters return 1, or 0 for an index
 * out of range) */
BRU_API const bru_capture_api *bru_capture_get_api(void);

/* P12 round 3 (usd_dump.cpp): the stage at path (UTF-8) as OpenUSD composes
 * it, written as JSON to json_path: its metres per unit, up axis, default
 * prim, customLayerData, OpenUSD's complaints, and every prim (path, type,
 * active, references, API schemas, local to world, authored attributes
 * with their values, arrays as their count, first values and, for points,
 * bounds; relationships' targets). Returns 1, or 0 with the reason. */
BRU_API int bru_stage_dump(const char *plugin_dir, const char *path, const char *json_path, char *r_error,
                           int max_bytes);

#ifdef __cplusplus
}
#endif

#endif /* __BGE_REMIX_USD_H__ */
