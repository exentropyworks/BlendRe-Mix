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
 * stage written out as JSON: bru_stage_dump). 4: P12 round 6 (any tool's
 * scene read: bru_scene_get_api; text to binary: bru_stage_convert). 5: P12
 * round 7 (the scene's physics: bru_scene_api physics). 6: P12 round 8 (its
 * skeletons: bru_scene_api skeletons, skinned_points; BRU_NODE_SKELETON). */
#define BRU_ABI_VERSION 6

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

/* ------------------------------------------------------------------------- */
/* P12 round 6: any tool's USD scene (usd_scene.cpp), for File > Import >
 * Universal Scene Description.
 *
 * The stage as OpenUSD composes it (references, payloads, instancing), as a
 * tree of nodes: transforms (Xform and other transformable prims), meshes,
 * lights and cameras. Scopes and untyped prims are only groups: what is
 * under them hangs from the nearest node above. Instances are expanded:
 * each instance's meshes are nodes of their own sharing one mesh (that of
 * the prototype). Everything is in the stage's own units and up axis;
 * matrices are local to world (USD's rows: the translation in matrix[12..14]).
 * Whatever is not read (curves, points, point instancers, volumes, other
 * shaders) is named in the report. Pointers stay valid until close. */

typedef struct bru_scene bru_scene;

enum {
	BRU_NODE_XFORM = 0,
	BRU_NODE_MESH = 1,
	BRU_NODE_LIGHT = 2,
	BRU_NODE_CAMERA = 3,
	BRU_NODE_SKELETON = 4,  /* round 8: a UsdSkel Skeleton (see skeletons) */
};

typedef struct bru_scene_info {
	double meters_per_unit;
	int z_up;
	double time;
	int node_count, mesh_count, material_count;
	const char *default_prim;   /* "" if none */
	const char *creator;        /* the root layer's customLayerData creator ("" if none) */
	const char *report;         /* what was left out, one line each ("" if nothing) */
	int usd_errors;             /* OpenUSD's own complaints while reading (in the report too) */
} bru_scene_info;

typedef struct bru_node {
	const char *name;           /* the prim's displayName, else its name */
	const char *prim_name;
	const char *path;           /* where it is in the stage (an instance's: its proxy path) */
	int parent;                 /* the node it hangs from, -1: none (nodes come parents first) */
	int kind;                   /* BRU_NODE_* */
	int index;                  /* a mesh: its mesh; a light: its light; a camera: its camera */
	int visible;
	int material;               /* a mesh: the material bound to all of it, -1: none */
	int subset_count;           /* a mesh: its mesh's subsets */
	const int *subset_materials;/* the material bound to each subset here, -1: none */
	double matrix[16];          /* local to world */
} bru_node;

typedef struct bru_scene_mesh {
	const char *name;           /* the prim's (the prototype's, for an instance) */
	int vertex_count, face_count, corner_count;
	const float *points;
	const int *face_sizes;
	const int *corners;
	const float *normals;       /* corner_count * 3, or NULL */
	const float *uvs;           /* corner_count * 2, or NULL */
	const char *uv_name;        /* the UVs' primvar (st, or the first texCoord2f one) */
	const float *colors;        /* corner_count * 4, or NULL */
	int double_sided;
	int subset_count;           /* GeomSubsets of the materialBind family */
} bru_scene_mesh;

typedef struct bru_subset {
	const char *name;
	int face_count;
	const int *faces;
} bru_subset;

typedef struct bru_scene_material {
	const char *name;           /* displayName, else the prim's name */
	const char *path;
	int preview;                /* OpenUSD finds a UsdPreviewSurface as its surface */
	int aperture;               /* OpenUSD finds an AperturePBR MDL as its mdl surface */
	const char *mdl;            /* the MDL's sourceAsset, its sub-identifier */
	const char *sub_identifier;
	const char *other;          /* another shader found as its surface (its id), "" if none */
	int preview_input_count, aperture_input_count;
} bru_scene_material;

/* a shader's input; a UsdPreviewSurface input wired to a UsdUVTexture comes
 * as that texture's file (kind BRU_VALUE_ASSET) and the output read */
typedef struct bru_shader_input {
	const char *name;           /* without "inputs:" */
	int kind;                   /* BRU_VALUE_* */
	double v[4];
	const char *text;           /* a token, or an asset as written */
	const char *path;           /* an asset: its absolute path (resolved, or where it would be) */
	int exists;
	const char *output;         /* a texture: rgb, r, g, b, a ("" for a value) */
	const char *color_space;    /* a texture's sourceColorSpace ("" if not given) */
} bru_shader_input;

typedef struct bru_scene_api {
	int abi;                    /* BRU_ABI_VERSION */
	bru_scene *(*open)(const char *plugin_dir, const char *path, char *r_error, int max_bytes);
	void (*close)(bru_scene *sc);
	void (*info)(const bru_scene *sc, bru_scene_info *r_info);
	int (*node)(const bru_scene *sc, int index, bru_node *r_node);
	int (*mesh)(const bru_scene *sc, int index, bru_scene_mesh *r_mesh);
	int (*subset)(const bru_scene *sc, int mesh, int index, bru_subset *r_subset);
	int (*material)(const bru_scene *sc, int index, bru_scene_material *r_material);
	/* which: 0 the preview surface's inputs, 1 AperturePBR's */
	int (*material_input)(const bru_scene *sc, int material, int which, int index, bru_shader_input *r_input);
	int (*light)(const bru_scene *sc, int index, bru_light *r_light);
	int (*camera)(const bru_scene *sc, int index, bru_camera *r_camera);
	/* P12 round 7: the stage's physics as JSON, read with OpenUSD's own
	 * physics reader (usd_physics.cpp): scenes, bodies (with their MassAPI),
	 * shapes, physics materials, joints (with their authored frames and the
	 * world matrices of the prims they name), articulations, collision
	 * groups, and every prim's bgeRemix:* attributes ("custom"); in the
	 * stage's own units, angles in degrees. Collision shapes that are not
	 * meshes (a Cube, a Capsule...) are read only here, not as nodes. */
	const char *(*physics)(const bru_scene *sc);
	/* P12 round 8: the stage's skeletons as JSON, read with OpenUSD's own
	 * skeleton reader (usd_skel.cpp): skeletons (joints in order, parents,
	 * bind and rest transforms in the skeleton's space, the animation bound,
	 * the skeleton's local to world), skinned meshes (joint influences,
	 * geometry bind transform, skinning method, blend shapes), every
	 * SkelAnimation (joints, time samples), the stage's frame range and
	 * rate. Each matrix as USD's 16 numbers (rows). */
	const char *(*skeletons)(const bru_scene *sc);
	/* OpenUSD's own skinning of the mesh at mesh_path at time, in the world:
	 * x y z for each point into r_points (at most max_points); their number,
	 * or -1 when that mesh is not skinned */
	int (*skinned_points)(const bru_scene *sc, const char *mesh_path, double time, float *r_points, int max_points);
} bru_scene_api;

BRU_API const bru_scene_api *bru_scene_get_api(void);

/* P12 round 6: the layer at src written again at dst, in the format dst's
 * extension names (.usdc binary; .usd OpenUSD's default, binary; .usda
 * text). Returns 1, or 0 with the reason. */
BRU_API int bru_stage_convert(const char *plugin_dir, const char *src, const char *dst, char *r_error,
                              int max_bytes);

#ifdef __cplusplus
}
#endif

#endif /* __BGE_REMIX_USD_H__ */
