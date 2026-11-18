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

/** \file BRMX_capture.h
 *  \ingroup remix
 *
 * BGE-Remix P12 round 5: a scene imported from an RTX Remix capture
 * (bge_remix_capture.py), checked against how it came in. One set of checks
 * for the Remix View's Remix layer (BL_GameViewLayers.cpp) and File >
 * Export > RTX Remix Mod (bge_remix_mod.py, through _bge_remix.capture_check):
 *
 *  - the fingerprints the import keeps on each mesh, material, lamp, image
 *    and place (ID property bge_remix_capture_fp), made here and compared
 *    here;
 *  - what the mod carries: the meshes it replaces, the objects it adds
 *    under a mesh, the lamps and materials it replaces;
 *  - what a mod cannot carry, as notes (the export's report, the view's
 *    warnings), one wording for both.
 *
 * The marks the import leaves: bge_remix_capture_hash (objects, meshes,
 * materials, lamps), bge_remix_capture_place (each place: its capture
 * name), bge_remix_capture_mesh (a place's capture mesh hash),
 * bge_remix_capture_matrix (a place's or lamp's obmat as it came in: 16
 * numbers, compared within a tenth of a millimetre); on the
 * scene bge_remix_capture and bge_remix_capture_places (the places, as a
 * group's keys).
 */

#ifndef __BRMX_CAPTURE_H__
#define __BRMX_CAPTURE_H__

#ifdef __cplusplus
extern "C" {
#endif

struct Image;
struct Main;
struct Material;
struct Mesh;
struct Object;
struct Scene;

/* what the mod does with an object, a material or a lamp */
enum {
	BRMX_MOD_NONE = 0,      /* not from the capture and not in the mod */
	BRMX_MOD_OWN,           /* from the capture, unchanged: the game's own */
	BRMX_MOD_REPLACED,      /* the mod replaces it (a place: its mesh) */
	BRMX_MOD_ADDS,          /* a place: the mod adds objects to its mesh */
	BRMX_MOD_ADDED,         /* under an imported mesh object: the mod adds it */
	BRMX_MOD_LEFT_OUT,      /* under an imported mesh object, but left out (see the notes) */
};

/* fingerprints: 32 hex digits and a 0 */
void BRMX_capture_fp_mesh(const struct Mesh *me, char r_fp[33]);
void BRMX_capture_fp_material(struct Main *bmain, const struct Material *ma, char r_fp[33]);
/* a lamp's settings (where it is: bge_remix_capture_matrix, as a place's) */
void BRMX_capture_fp_lamp(const struct Object *ob, char r_fp[33]);
void BRMX_capture_fp_image(struct Main *bmain, const struct Image *ima, char r_fp[33]);
/* a place's parts: where it is, its materials, its physics */
void BRMX_capture_fp_object(struct Object *ob, char r_matrix[33], char r_materials[33], char r_physics[33]);

/* the scene came from a capture (bge_remix_capture) */
int BRMX_capture_scene(const struct Scene *scene);

typedef struct BRMX_CaptureCheck BRMX_CaptureCheck;

/* the scene checked against how it came in; NULL for a scene not from a
 * capture */
BRMX_CaptureCheck *BRMX_capture_check(struct Main *bmain, struct Scene *scene);
void BRMX_capture_check_free(BRMX_CaptureCheck *check);

/* what the mod does with ob (r_count: a place's added objects; r_hash: its
 * capture hash, or for an added object the mesh it is added to) */
int BRMX_capture_object_mod(const BRMX_CaptureCheck *check, const struct Object *ob, int *r_count,
                            const char **r_hash);
int BRMX_capture_material_mod(const BRMX_CaptureCheck *check, const struct Material *ma);

/* the notes: what a mod cannot carry (r_code: RMX_MOD_*; r_object: the
 * object it is about, "" for none) */
int BRMX_capture_note_count(const BRMX_CaptureCheck *check);
const char *BRMX_capture_note(const BRMX_CaptureCheck *check, int index, const char **r_code,
                              const char **r_object);

/* what goes into the mod */
int BRMX_capture_mesh_count(const BRMX_CaptureCheck *check);
struct Mesh *BRMX_capture_mesh(const BRMX_CaptureCheck *check, int index, const char **r_hash);
int BRMX_capture_group_count(const BRMX_CaptureCheck *check);
struct Object *BRMX_capture_group(const BRMX_CaptureCheck *check, int index, const char **r_hash, int *r_count);
struct Object *BRMX_capture_group_object(const BRMX_CaptureCheck *check, int index, int object);
int BRMX_capture_lamp_count(const BRMX_CaptureCheck *check);
struct Object *BRMX_capture_lamp(const BRMX_CaptureCheck *check, int index);
int BRMX_capture_material_count(const BRMX_CaptureCheck *check);
struct Material *BRMX_capture_material(const BRMX_CaptureCheck *check, int index);

#ifdef __cplusplus
}
#endif

#endif /* __BRMX_CAPTURE_H__ */
