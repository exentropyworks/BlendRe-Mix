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

/** \file remix_capture.cc
 *  \ingroup remix
 *
 * BGE-Remix P12 round 5: a capture scene checked against how it came in
 * (BRMX_capture.h). The notes' wording is the mod export's report, word for
 * word: the Remix View shows what the export will say.
 */

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <map>
#include <set>
#include <string>
#include <vector>

extern "C" {
#include "DNA_ID.h"
#include "DNA_image_types.h"
#include "DNA_lamp_types.h"
#include "DNA_material_types.h"
#include "DNA_mesh_types.h"
#include "DNA_meshdata_types.h"
#include "DNA_node_types.h"
#include "DNA_object_types.h"
#include "DNA_scene_types.h"
#include "DNA_texture_types.h"
#include "DNA_customdata_types.h"

#include "BLI_fileops.h"
#include "BLI_hash_md5.h"
#include "BLI_path_util.h"
#include "BLI_string.h"
#include "BLI_utildefines.h"

#include "BKE_customdata.h"
#include "BKE_idprop.h"
#include "BKE_image.h"
#include "BKE_main.h"
#include "BKE_material.h"
#include "BKE_material_physical.h"
#include "BKE_node.h"
}

#include "BRMX_capture.h"

namespace {

const char *HASH = "bge_remix_capture_hash";
const char *FP = "bge_remix_capture_fp";
const char *PLACE = "bge_remix_capture_place";
const char *PLACE_MESH = "bge_remix_capture_mesh";

/* ------------------------------------------------------------------------- */
/* ID properties */

IDProperty *idp(const ID *id, const char *name)
{
	if (!id || !id->properties) {
		return NULL;
	}
	return IDP_GetPropertyFromGroup(id->properties, name);
}

/* a string property ("" when there is none) */
std::string idp_str(const ID *id, const char *name)
{
	IDProperty *p = idp(id, name);
	return (p && p->type == IDP_STRING) ? std::string(IDP_String(p)) : std::string();
}

/* a number property (int, float or double), or def */
double idp_num(const ID *id, const char *name, double def)
{
	IDProperty *p = idp(id, name);
	if (!p) return def;
	switch (p->type) {
		case IDP_INT: return (double)IDP_Int(p);
		case IDP_FLOAT: return (double)IDP_Float(p);
		case IDP_DOUBLE: return IDP_Double(p);
	}
	return def;
}

/* a string inside a group property (a place's fingerprint parts) */
std::string idp_group_str(const ID *id, const char *group, const char *name)
{
	IDProperty *g = idp(id, group);
	if (!g || g->type != IDP_GROUP) return std::string();
	IDProperty *p = IDP_GetPropertyFromGroup(g, name);
	return (p && p->type == IDP_STRING) ? std::string(IDP_String(p)) : std::string();
}

/* the place kept at import (bge_remix_capture_matrix: ob->obmat's 16
 * numbers) against where it is now, within a tenth of a millimetre: the
 * scene's updates remake obmat from the place, turn and size a hair
 * differently */
const char *MATRIX = "bge_remix_capture_matrix";

bool moved(const Object *ob)
{
	IDProperty *p = idp(&ob->id, MATRIX);
	if (!p || p->type != IDP_ARRAY || p->len != 16 || !ELEM(p->subtype, IDP_FLOAT, IDP_DOUBLE)) {
		return false;
	}
	const float *m = &ob->obmat[0][0];
	for (int i = 0; i < 16; i++) {
		const double v = p->subtype == IDP_DOUBLE ? ((const double *)IDP_Array(p))[i] :
		                                           (double)((const float *)IDP_Array(p))[i];
		if (std::fabs(v - (double)m[i]) > 1e-4) {
			return true;
		}
	}
	return false;
}

const char *id_name(const ID *id)
{
	return id ? id->name + 2 : "";
}

std::string fmt(const char *f, ...)
{
	char buf[1024];
	va_list ap;
	va_start(ap, f);
	vsnprintf(buf, sizeof(buf), f, ap);
	va_end(ap);
	return std::string(buf);
}

/* ------------------------------------------------------------------------- */
/* fingerprints: md5 of the parts, each written out exactly (bytes), except
 * matrices, which the scene's updates may remake a hair differently: those
 * to a millionth */

struct Digest {
	std::string buf;
	void bytes(const void *p, size_t n)
	{
		buf.append((const char *)p, n);
		buf.push_back('|');
	}
	void i(long long v) { bytes(&v, sizeof(v)); }
	void f(float v) { bytes(&v, sizeof(v)); }
	void s(const char *t) { bytes(t ? t : "", t ? strlen(t) : 0); }
	void s(const std::string &t) { bytes(t.data(), t.size()); }
	void matrix(const float m[4][4])
	{
		for (int r = 0; r < 4; r++) {
			for (int c = 0; c < 4; c++) {
				long long q = std::llround((double)m[r][c] * 1e6);
				i(q == 0 ? 0 : q);
			}
		}
	}
	void hex(char r_fp[33]) const
	{
		unsigned char res[16];
		BLI_hash_md5_buffer(buf.data(), buf.size(), res);
		BLI_hash_md5_to_hexdigest(res, r_fp);
	}
};

void image_parts(Main *bmain, const Image *ima, Digest &d, bool dirty)
{
	d.s(id_name(&ima->id));
	d.i(ima->source);
	char path[FILE_MAX];
	BLI_strncpy(path, ima->name, sizeof(path));
	if (path[0]) {
		BLI_path_abs(path, bmain ? ID_BLEND_PATH(bmain, &ima->id) : "");
	}
	d.s(path);
	BLI_stat_t st;
	d.i(path[0] && BLI_stat(path, &st) == 0 ? (long long)st.st_mtime : 0);
	if (dirty) {
		d.i(BKE_image_is_dirty((Image *)ima) ? 1 : 0);
	}
}

}  // namespace

extern "C" {

void BRMX_capture_fp_mesh(const Mesh *me, char r_fp[33])
{
	Digest d;
	d.i(me->totvert);
	for (int v = 0; v < me->totvert; v++) d.bytes(me->mvert[v].co, sizeof(float[3]));
	d.i(me->totloop);
	for (int l = 0; l < me->totloop; l++) d.i(me->mloop[l].v);
	d.i(me->totpoly);
	for (int p = 0; p < me->totpoly; p++) {
		d.i(me->mpoly[p].loopstart);
		d.i(me->mpoly[p].totloop);
		d.i(me->mpoly[p].mat_nr);
	}
	d.i((me->flag & ME_TWOSIDED) ? 1 : 0);
	d.i(me->totcol);
	const int uvs = CustomData_number_of_layers(&me->ldata, CD_MLOOPUV);
	for (int n = 0; n < uvs; n++) {
		d.s(CustomData_get_layer_name(&me->ldata, CD_MLOOPUV, n));
		const MLoopUV *uv = (const MLoopUV *)CustomData_get_layer_n(&me->ldata, CD_MLOOPUV, n);
		for (int l = 0; uv && l < me->totloop; l++) d.bytes(uv[l].uv, sizeof(float[2]));
	}
	const int cols = CustomData_number_of_layers(&me->ldata, CD_MLOOPCOL);
	for (int n = 0; n < cols; n++) {
		d.s(CustomData_get_layer_name(&me->ldata, CD_MLOOPCOL, n));
		const MLoopCol *col = (const MLoopCol *)CustomData_get_layer_n(&me->ldata, CD_MLOOPCOL, n);
		for (int l = 0; col && l < me->totloop; l++) d.bytes(&col[l], sizeof(MLoopCol));
	}
	d.hex(r_fp);
}

void BRMX_capture_fp_image(Main *bmain, const Image *ima, char r_fp[33])
{
	Digest d;
	image_parts(bmain, ima, d, false);
	d.hex(r_fp);
}

void BRMX_capture_fp_material(Main *bmain, const Material *ma, char r_fp[33])
{
	Digest d;
	d.i(ma->use_nodes);
	d.i((ma->mode & MA_SHLESS) ? 1 : 0);
	d.i(ma->game.alpha_blend);
	d.f(ma->alpha);
	const bNodeTree *nt = ma->nodetree;
	if (nt) {
		std::vector<const bNode *> nodes;
		for (const bNode *n = (const bNode *)nt->nodes.first; n; n = n->next) nodes.push_back(n);
		std::sort(nodes.begin(), nodes.end(), [](const bNode *a, const bNode *b) { return strcmp(a->name, b->name) < 0; });
		for (const bNode *n : nodes) {
			d.s(n->idname);
			d.s(n->name);
			d.i((n->flag & NODE_MUTED) ? 1 : 0);
			d.i(n->custom1);
			d.i(n->custom2);
			d.f(n->custom3);
			d.f(n->custom4);
			for (const bNodeSocket *s = (const bNodeSocket *)n->inputs.first; s; s = s->next) {
				d.s(s->identifier);
				if (!s->default_value) continue;
				switch (s->type) {
					case SOCK_FLOAT: d.f(((const bNodeSocketValueFloat *)s->default_value)->value); break;
					case SOCK_INT: d.i(((const bNodeSocketValueInt *)s->default_value)->value); break;
					case SOCK_BOOLEAN: d.i(((const bNodeSocketValueBoolean *)s->default_value)->value); break;
					case SOCK_VECTOR:
						d.bytes(((const bNodeSocketValueVector *)s->default_value)->value, sizeof(float[3]));
						break;
					case SOCK_RGBA:
						d.bytes(((const bNodeSocketValueRGBA *)s->default_value)->value, sizeof(float[4]));
						break;
				}
			}
			if (n->type == SH_NODE_MAPPING && n->storage) {
				const TexMapping *tm = (const TexMapping *)n->storage;
				d.bytes(tm->loc, sizeof(float[3]));
				d.bytes(tm->rot, sizeof(float[3]));
				d.bytes(tm->size, sizeof(float[3]));
				d.i(tm->flag);
				d.i(tm->type);
			}
			if (n->type == SH_NODE_TEXTURE && n->id) {
				const Tex *tex = (const Tex *)n->id;
				d.s(id_name(&tex->id));
				d.i(tex->type);
				if (tex->type == TEX_IMAGE && tex->ima) {
					/* a picture painted on since (dirty) counts as changed */
					image_parts(bmain, tex->ima, d, true);
				}
			}
		}
		std::vector<std::string> links;
		for (const bNodeLink *l = (const bNodeLink *)nt->links.first; l; l = l->next) {
			links.push_back(fmt("%s/%s>%s/%s", l->fromnode ? l->fromnode->name : "",
			                    l->fromsock ? l->fromsock->identifier : "", l->tonode ? l->tonode->name : "",
			                    l->tosock ? l->tosock->identifier : ""));
		}
		std::sort(links.begin(), links.end());
		for (const std::string &l : links) d.s(l);
	}
	d.hex(r_fp);
}

void BRMX_capture_fp_lamp(const Object *ob, char r_fp[33])
{
	Digest d;
	const Lamp *la = (const Lamp *)ob->data;
	if (la) {
		d.i(la->type);
		d.f(la->energy);
		d.f(la->r);
		d.f(la->g);
		d.f(la->b);
		d.f(la->dist);
		d.f(la->area_size);
		d.f((float)idp_num(&la->id, "bge_physical", -1.0));
		d.f((float)idp_num(&la->id, "bge_sun_angle", -1.0));
		if (la->type == LA_SPOT) {
			d.f(la->spotsize);
			d.f(la->spotblend);
			d.i((la->mode & LA_HALO) ? 1 : 0);
			d.f(la->haint);
		}
		if (la->type == LA_AREA) {
			d.i(la->area_shape);
			d.f(la->area_sizey);
		}
	}
	d.hex(r_fp);
}

void BRMX_capture_fp_object(Object *ob, char r_matrix[33], char r_materials[33], char r_physics[33])
{
	Digest m;
	m.matrix(ob->obmat);
	m.hex(r_matrix);
	Digest s;
	for (short i = 0; i < ob->totcol; i++) {
		s.i(ob->matbits && ob->matbits[i] ? 1 : 0);
		Material *ma = give_current_material(ob, i + 1);
		const std::string h = ma ? idp_str(&ma->id, HASH) : std::string();
		s.s(ma ? (h.empty() ? std::string(id_name(&ma->id)) : h) : std::string());
	}
	s.hex(r_materials);
	Digest p;
	p.i(ob->body_type);
	p.hex(r_physics);
}

int BRMX_capture_scene(const Scene *scene)
{
	return scene && idp(&scene->id, "bge_remix_capture") != NULL;
}

}  /* extern "C" */

/* ------------------------------------------------------------------------- */
/* the check */

struct BRMX_CaptureCheck {
	struct Note {
		std::string code, object, text;
	};
	struct Group {
		Object *place;
		std::string hash;
		std::vector<Object *> added;
	};
	std::vector<Note> notes;
	std::vector<std::pair<std::string, Mesh *>> meshes;     /* replaced, by hash */
	std::vector<Group> groups;                              /* added, by mesh hash */
	std::vector<Object *> lamps;                            /* replaced capture lamps */
	std::vector<Material *> materials;                      /* replaced capture materials */
	std::set<const Material *> capture_materials;           /* every capture material in use */
	std::map<const Object *, int> object_mod;
	std::map<const Object *, std::string> object_hash;
	std::map<const Object *, int> object_count;
};

namespace {

typedef BRMX_CaptureCheck Check;

void note(Check &c, const char *code, const Object *ob, const std::string &text)
{
	for (const Check::Note &n : c.notes) {
		if (n.text == text) return;
	}
	c.notes.push_back({code, ob ? id_name(&ob->id) : "", text});
}

std::vector<Object *> scene_objects(Scene *scene)
{
	std::vector<Object *> out;
	for (Base *b = (Base *)scene->base.first; b; b = b->next) {
		if (b->object) out.push_back(b->object);
	}
	return out;
}

void descendants(const std::vector<Object *> &all, Object *ob, std::vector<Object *> &out)
{
	for (Object *c : all) {
		if (c->parent == ob) {
			out.push_back(c);
			descendants(all, c, out);
		}
	}
}

bool is_place(const Object *ob)
{
	return idp(&ob->id, PLACE) != NULL;
}

const Object *place_of(const Object *ob)
{
	for (const Object *p = ob->parent; p; p = p->parent) {
		if (is_place(p)) return p;
	}
	return NULL;
}

/* Python's lower-case type names (ob.type.lower(), lamp.type.lower()) */
const char *object_type_name(const Object *ob)
{
	switch (ob->type) {
		case OB_MESH: return "mesh";
		case OB_CURVE: return "curve";
		case OB_SURF: return "surface";
		case OB_FONT: return "font";
		case OB_MBALL: return "meta";
		case OB_LAMP: return "lamp";
		case OB_CAMERA: return "camera";
		case OB_EMPTY: return "empty";
		case OB_LATTICE: return "lattice";
		case OB_ARMATURE: return "armature";
		case OB_SPEAKER: return "speaker";
	}
	return "object";
}

const char *lamp_type_name(const Lamp *la)
{
	switch (la ? la->type : -1) {
		case LA_LOCAL: return "point";
		case LA_SUN: return "sun";
		case LA_SPOT: return "spot";
		case LA_HEMI: return "hemi";
		case LA_AREA: return "area";
	}
	return "unknown";
}

bool mesh_like(const Object *ob)
{
	return ELEM(ob->type, OB_MESH, OB_CURVE, OB_SURF, OB_FONT, OB_MBALL);
}

void check_place(Check &c, Object *ob)
{
	const std::string old_materials = idp_group_str(&ob->id, FP, "materials");
	const std::string old_physics = idp_group_str(&ob->id, FP, "physics");
	char m[33], s[33], p[33];
	BRMX_capture_fp_object(ob, m, s, p);
	const char *name = id_name(&ob->id);
	(void)m;
	if (moved(ob)) {
		note(c, "RMX_MOD_MOVED", ob,
		     fmt("%s was moved: a mod cannot move what the game draws (the game places it)", name));
	}
	if (!old_materials.empty() && old_materials != s) {
		note(c, "RMX_MOD_MATERIAL", ob,
		     fmt("%s was given another material: a mod changes a material wherever it is used, not one place's; "
		         "change the material itself", name));
	}
	const Mesh *me = (const Mesh *)ob->data;
	if (idp_str(me ? &me->id : NULL, HASH) != idp_str(&ob->id, PLACE_MESH)) {
		note(c, "RMX_MOD_MESH", ob,
		     fmt("%s shows another mesh: a mod replaces a mesh wherever the game draws it; edit the mesh itself", name));
	}
	if (!old_physics.empty() && old_physics != p) {
		note(c, "RMX_MOD_PHYSICS", ob, fmt("%s: physics is not part of a mod (the game runs its own)", name));
	}
	if (ob->sensors.first || ob->controllers.first || ob->actuators.first || ob->prop.first) {
		note(c, "RMX_MOD_LOGIC", ob, fmt("%s: logic and game properties are not part of a mod", name));
	}
	if (ob->modifiers.first) {
		note(c, "RMX_MOD_MODIFIERS", ob,
		     fmt("%s: its modifiers are not in the mod (apply them to the mesh first)", name));
	}
}

bool material_changed(Main *bmain, const Material *ma)
{
	char fp[33];
	BRMX_capture_fp_material(bmain, ma, fp);
	return idp_str(&ma->id, FP) != fp;
}

}  // namespace

extern "C" {

BRMX_CaptureCheck *BRMX_capture_check(Main *bmain, Scene *scene)
{
	if (!BRMX_capture_scene(scene)) {
		return NULL;
	}
	Check *c = new Check();
	const std::vector<Object *> all = scene_objects(scene);
	/* the places: the first of each name (a copy is noted) */
	std::map<std::string, Object *> places;
	for (Object *ob : all) {
		if (!is_place(ob)) continue;
		const std::string key = idp_str(&ob->id, PLACE);
		auto it = places.find(key);
		if (it != places.end()) {
			note(*c, "RMX_MOD_COPY", ob,
			     fmt("%s is a copy of %s: a mod cannot add places the game draws, left out", id_name(&ob->id),
			         id_name(&it->second->id)));
			continue;
		}
		places[key] = ob;
	}
	IDProperty *came = idp(&scene->id, "bge_remix_capture_places");
	if (came && came->type == IDP_GROUP) {
		std::vector<std::string> keys;
		for (IDProperty *p = (IDProperty *)came->data.group.first; p; p = p->next) keys.push_back(p->name);
		std::sort(keys.begin(), keys.end());
		for (const std::string &key : keys) {
			if (places.find(key) == places.end()) {
				note(*c, "RMX_MOD_DELETED", NULL,
				     fmt("%s was deleted: a mod cannot remove what the game draws", key.c_str()));
			}
		}
	}
	std::set<const Material *> in_use;
	std::map<std::string, size_t> group_of;
	for (auto &kv : places) {
		Object *ob = kv.second;
		if (ob->type == OB_LAMP) {
			char fp[33];
			BRMX_capture_fp_lamp(ob, fp);
			const bool changed = idp_str(&ob->id, FP) != fp || moved(ob);
			if (changed) c->lamps.push_back(ob);
			c->object_mod[ob] = changed ? BRMX_MOD_REPLACED : BRMX_MOD_OWN;
			c->object_hash[ob] = idp_str(&ob->id, HASH);
			std::vector<Object *> under;
			descendants(all, ob, under);
			for (Object *u : under) {
				note(*c, "RMX_MOD_UNDER_LAMP", u,
				     fmt("%s hangs under the lamp %s: only objects under an imported mesh object go into a mod, left "
				         "out", id_name(&u->id), id_name(&ob->id)));
				c->object_mod[u] = BRMX_MOD_LEFT_OUT;
			}
			continue;
		}
		if (ob->type != OB_MESH) continue;
		check_place(*c, ob);
		Mesh *me = (Mesh *)ob->data;
		const std::string h = idp_str(me ? &me->id : NULL, HASH);
		const std::string mh = idp_str(&ob->id, PLACE_MESH);
		c->object_hash[ob] = mh;
		c->object_mod[ob] = BRMX_MOD_OWN;
		if (!h.empty() && h == mh) {
			char fp[33];
			BRMX_capture_fp_mesh(me, fp);
			if (idp_str(&me->id, FP) != fp) {
				auto it = std::find_if(c->meshes.begin(), c->meshes.end(),
				                       [&](const std::pair<std::string, Mesh *> &x) { return x.first == h; });
				if (it == c->meshes.end()) {
					c->meshes.push_back(std::make_pair(h, me));
				}
				else if (it->second != me) {
					note(*c, "RMX_MOD_TWO_MESHES", ob,
					     fmt("%s and %s both carry the capture mesh %s: only %s goes in", id_name(&it->second->id),
					         id_name(&me->id), h.c_str(), id_name(&it->second->id)));
				}
			}
		}
		for (short i = 1; i <= ob->totcol; i++) {
			Material *ma = give_current_material(ob, i);
			if (ma && !idp_str(&ma->id, HASH).empty()) in_use.insert(ma);
		}
		std::vector<Object *> under, added;
		descendants(all, ob, under);
		for (Object *u : under) {
			if (!is_place(u)) added.push_back(u);
		}
		if (!added.empty()) {
			auto it = group_of.find(mh);
			if (it != group_of.end()) {
				const Object *first = c->groups[it->second].place;
				note(*c, "RMX_MOD_CHILDREN_TWICE", ob,
				     fmt("the objects under %s are left out: those under %s already go in, and Remix adds them "
				         "wherever the game draws mesh %s, %s included", id_name(&ob->id), id_name(&first->id),
				         mh.c_str(), id_name(&ob->id)));
				for (Object *a : added) {
					c->object_mod[a] = BRMX_MOD_LEFT_OUT;
					c->object_hash[a] = mh;
				}
			}
			else {
				group_of[mh] = c->groups.size();
				c->groups.push_back({ob, mh, added});
			}
		}
	}
	/* new objects not under an imported one */
	for (Object *ob : all) {
		if (is_place(ob) || ob->type == OB_CAMERA || place_of(ob) != NULL) continue;
		note(*c, "RMX_MOD_NOT_PARENTED", ob,
		     fmt("%s is not parented to an imported object: a mod only adds to what the game draws, left out",
		         id_name(&ob->id)));
	}
	/* the added objects: what each is, and its materials */
	for (Check::Group &g : c->groups) {
		int count = 0;
		for (Object *a : g.added) {
			c->object_hash[a] = g.hash;
			const char *name = id_name(&a->id);
			int mod = BRMX_MOD_ADDED;
			if (a->type == OB_LAMP) {
				const Lamp *la = (const Lamp *)a->data;
				if (la && la->type == LA_SUN) {
					note(*c, "RMX_MOD_SUN", a,
					     fmt("%s: a sun cannot hang under a mesh in a mod (Remix ignores it), left out", name));
					mod = BRMX_MOD_LEFT_OUT;
				}
				else if (!la || !ELEM(la->type, LA_LOCAL, LA_SPOT, LA_AREA)) {
					note(*c, "RMX_MOD_LAMP_KIND", a,
					     fmt("%s: a %s lamp has no Remix light like it, left out", name, lamp_type_name(la)));
					mod = BRMX_MOD_LEFT_OUT;
				}
			}
			else if (mesh_like(a)) {
				for (short i = 1; i <= a->totcol; i++) {
					Material *ma = give_current_material(a, i);
					if (!ma) continue;
					if (!idp_str(&ma->id, HASH).empty()) {
						in_use.insert(ma);
					}
					if (!BKE_material_is_remix(ma)) {
						note(*c, "RMX_MOD_NOT_REMIX_MATERIAL", a,
						     fmt("material %s is not an RTX Remix material (Material tab > RTX Remix): left out",
						         id_name(&ma->id)));
					}
				}
			}
			else if (a->type == OB_EMPTY) {
				mod = BRMX_MOD_NONE;
			}
			else {
				note(*c, "RMX_MOD_OBJECT_KIND", a,
				     fmt("%s: a %s cannot go into a mod, left out", name, object_type_name(a)));
				mod = BRMX_MOD_LEFT_OUT;
			}
			c->object_mod[a] = mod;
			if (mod == BRMX_MOD_ADDED) count++;
		}
		c->object_count[g.place] = count;
		if (c->object_mod[g.place] == BRMX_MOD_OWN) c->object_mod[g.place] = BRMX_MOD_ADDS;
	}
	for (auto &kv : c->meshes) {
		for (auto &om : c->object_mod) {
			const Object *ob = om.first;
			if (ob->type == OB_MESH && is_place(ob) && ob->data == kv.second &&
			    c->object_hash[ob] == kv.first) {
				om.second = BRMX_MOD_REPLACED;
			}
		}
	}
	/* the capture materials in use, the changed ones replaced */
	std::vector<Material *> sorted(in_use.size());
	std::transform(in_use.begin(), in_use.end(), sorted.begin(), [](const Material *m) { return (Material *)m; });
	std::sort(sorted.begin(), sorted.end(),
	          [](const Material *a, const Material *b) { return strcmp(a->id.name, b->id.name) < 0; });
	for (Material *ma : sorted) {
		c->capture_materials.insert(ma);
		if (material_changed(bmain, ma)) c->materials.push_back(ma);
	}
	return c;
}

void BRMX_capture_check_free(BRMX_CaptureCheck *check)
{
	delete check;
}

int BRMX_capture_object_mod(const BRMX_CaptureCheck *c, const Object *ob, int *r_count, const char **r_hash)
{
	if (r_count) *r_count = 0;
	if (r_hash) *r_hash = "";
	if (!c || !ob) return BRMX_MOD_NONE;
	auto h = c->object_hash.find(ob);
	if (h != c->object_hash.end() && r_hash) *r_hash = h->second.c_str();
	auto n = c->object_count.find(ob);
	if (n != c->object_count.end() && r_count) *r_count = n->second;
	auto it = c->object_mod.find(ob);
	return it == c->object_mod.end() ? BRMX_MOD_NONE : it->second;
}

int BRMX_capture_material_mod(const BRMX_CaptureCheck *c, const Material *ma)
{
	if (!c || !ma || idp_str(&ma->id, HASH).empty()) return BRMX_MOD_NONE;
	for (const Material *m : c->materials) {
		if (m == ma) return BRMX_MOD_REPLACED;
	}
	return BRMX_MOD_OWN;
}

int BRMX_capture_note_count(const BRMX_CaptureCheck *c)
{
	return c ? (int)c->notes.size() : 0;
}

const char *BRMX_capture_note(const BRMX_CaptureCheck *c, int i, const char **r_code, const char **r_object)
{
	if (!c || i < 0 || i >= (int)c->notes.size()) return NULL;
	if (r_code) *r_code = c->notes[i].code.c_str();
	if (r_object) *r_object = c->notes[i].object.c_str();
	return c->notes[i].text.c_str();
}

int BRMX_capture_mesh_count(const BRMX_CaptureCheck *c)
{
	return c ? (int)c->meshes.size() : 0;
}

Mesh *BRMX_capture_mesh(const BRMX_CaptureCheck *c, int i, const char **r_hash)
{
	if (!c || i < 0 || i >= (int)c->meshes.size()) return NULL;
	if (r_hash) *r_hash = c->meshes[i].first.c_str();
	return c->meshes[i].second;
}

int BRMX_capture_group_count(const BRMX_CaptureCheck *c)
{
	return c ? (int)c->groups.size() : 0;
}

Object *BRMX_capture_group(const BRMX_CaptureCheck *c, int i, const char **r_hash, int *r_count)
{
	if (!c || i < 0 || i >= (int)c->groups.size()) return NULL;
	if (r_hash) *r_hash = c->groups[i].hash.c_str();
	if (r_count) *r_count = (int)c->groups[i].added.size();
	return c->groups[i].place;
}

Object *BRMX_capture_group_object(const BRMX_CaptureCheck *c, int i, int j)
{
	if (!c || i < 0 || i >= (int)c->groups.size()) return NULL;
	const std::vector<Object *> &a = c->groups[i].added;
	return (j >= 0 && j < (int)a.size()) ? a[j] : NULL;
}

int BRMX_capture_lamp_count(const BRMX_CaptureCheck *c)
{
	return c ? (int)c->lamps.size() : 0;
}

Object *BRMX_capture_lamp(const BRMX_CaptureCheck *c, int i)
{
	return (c && i >= 0 && i < (int)c->lamps.size()) ? c->lamps[i] : NULL;
}

int BRMX_capture_material_count(const BRMX_CaptureCheck *c)
{
	return c ? (int)c->materials.size() : 0;
}

Material *BRMX_capture_material(const BRMX_CaptureCheck *c, int i)
{
	return (c && i >= 0 && i < (int)c->materials.size()) ? c->materials[i] : NULL;
}

}  /* extern "C" */
