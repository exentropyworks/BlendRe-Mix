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

/** \file usd_scene.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12 round 6: any tool's USD scene, read for File > Import >
 * Universal Scene Description (bge_remix_usd.h bru_scene_api), and a layer
 * written again in another format (bru_stage_convert: the export's .usdc).
 *
 * The stage is walked as OpenUSD composes it, instance proxies included, so
 * an instanced reference gives one node for each instance and one mesh for
 * them all (its prototype's). Materials are read through OpenUSD's own
 * surface lookup: the universal surface for a UsdPreviewSurface, the mdl
 * one for Remix's AperturePBR; a preview surface's inputs wired to a
 * UsdUVTexture come as that texture's file.
 */

#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

#include "pxr/pxr.h"
#include "pxr/base/gf/matrix4d.h"
#include "pxr/base/tf/errorMark.h"
#include "pxr/usd/sdf/layer.h"
#include "pxr/usd/usd/primRange.h"
#include "pxr/usd/usd/stage.h"
#include "pxr/usd/usdGeom/camera.h"
#include "pxr/usd/usdGeom/gprim.h"
#include "pxr/usd/usdGeom/imageable.h"
#include "pxr/usd/usdGeom/mesh.h"
#include "pxr/usd/usdGeom/metrics.h"
#include "pxr/usd/usdGeom/pointInstancer.h"
#include "pxr/usd/usdGeom/scope.h"
#include "pxr/usd/usdGeom/subset.h"
#include "pxr/usd/usdGeom/xformCache.h"
#include "pxr/usd/usdGeom/xformable.h"
#include "pxr/usd/usdLux/boundableLightBase.h"
#include "pxr/usd/usdLux/cylinderLight.h"
#include "pxr/usd/usdLux/diskLight.h"
#include "pxr/usd/usdLux/distantLight.h"
#include "pxr/usd/usdLux/domeLight.h"
#include "pxr/usd/usdLux/lightAPI.h"
#include "pxr/usd/usdLux/nonboundableLightBase.h"
#include "pxr/usd/usdLux/rectLight.h"
#include "pxr/usd/usdLux/shapingAPI.h"
#include "pxr/usd/usdLux/sphereLight.h"
#include "pxr/usd/usdPhysics/collisionAPI.h"
#include "pxr/usd/usdShade/material.h"
#include "pxr/usd/usdShade/materialBindingAPI.h"
#include "pxr/usd/usdShade/shader.h"
#include "pxr/usd/usdShade/utils.h"

#include "bge_remix_usd.h"
#include "usd_core.h"
#include "usd_read.h"

#ifdef _MSC_VER
#  include <windows.h>  /* __try: GetExceptionCode */
#endif

PXR_NAMESPACE_USING_DIRECTIVE
using brb::usd::copy_matrix;
using brb::usd::errors_since;
using brb::usd::read_value;

struct bru_scene {
	struct Node {
		std::string name, prim_name, path;
		int parent = -1, kind = BRU_NODE_XFORM, index = -1, material = -1;
		bool visible = true;
		std::vector<int> subset_materials;
		double matrix[16];
	};
	struct Subset {
		std::string name;
		std::vector<int> faces;
	};
	struct Mesh : brb::usd::MeshData {
		std::vector<Subset> subsets;
	};
	struct Input : brb::usd::Value {
		std::string output, color_space;
	};
	struct Material {
		std::string name, path, mdl, sub_identifier, other;
		bool preview = false, aperture = false;
		std::vector<Input> preview_inputs, aperture_inputs;
	};
	struct Light {
		bru_light d;
		std::string name;
	};

	UsdStageRefPtr stage;
	double meters_per_unit = 1.0;
	bool z_up = false;
	double time = 0.0;
	std::string default_prim, creator, report, physics;
	int usd_errors = 0;
	std::vector<Node> nodes;
	std::vector<Mesh> meshes;
	std::vector<Material> materials;
	std::vector<Light> lights;
	std::vector<bru_camera> cameras;
	std::map<SdfPath, int> mesh_index, material_index;

	void note(const std::string &line)
	{
		report += line;
		report += "\n";
	}
};

namespace {

void fail(const std::string &text, char *r_error, int max_bytes)
{
	if (r_error && max_bytes > 0)
		snprintf(r_error, size_t(max_bytes), "%s", text.c_str());
}

/* the prim an instance proxy stands for (shared by every instance) */
SdfPath source_path(const UsdPrim &prim)
{
	return prim.IsInstanceProxy() ? prim.GetPrimInPrototype().GetPath() : prim.GetPath();
}

std::string shown_name(const UsdPrim &prim)
{
	const std::string dn = prim.GetDisplayName();
	return dn.empty() ? prim.GetName().GetString() : dn;
}

std::string type_name(const UsdPrim &prim)
{
	const std::string t = prim.GetTypeName().GetString();
	return t.empty() ? std::string("prim") : t;
}

/* -- materials ------------------------------------------------------------- */

TfToken shader_id(const UsdShadeShader &sh)
{
	TfToken id;
	sh.GetShaderId(&id);
	return id;
}

/* a UsdPreviewSurface input: its value, or the file of the UsdUVTexture it
 * is wired to */
bool read_preview_input(bru_scene &sc, const std::string &mat_name, const UsdShadeInput &input, bru_scene::Input &in)
{
	in.name = input.GetBaseName().GetString();
	const UsdShadeAttributeVector srcs = input.GetValueProducingAttributes();
	if (srcs.empty())
		return false;
	const UsdAttribute &attr = srcs[0];
	if (UsdShadeUtils::GetBaseNameAndType(attr.GetName()).second != UsdShadeAttributeType::Output)
		return read_value(attr, sc.time, in);
	UsdShadeShader tex(attr.GetPrim());
	const TfToken id = tex ? shader_id(tex) : TfToken();
	if (id != TfToken("UsdUVTexture")) {
		sc.note("material " + mat_name + ": its " + in.name + " comes from a " +
		        (id.IsEmpty() ? type_name(attr.GetPrim()) : id.GetString()) + ": left at its value");
		return false;
	}
	UsdShadeInput file = tex.GetInput(TfToken("file"));
	const UsdShadeAttributeVector fsrcs = file ? file.GetValueProducingAttributes() : UsdShadeAttributeVector();
	if (fsrcs.empty() || !read_value(fsrcs[0], sc.time, in) || in.kind != BRU_VALUE_ASSET) {
		sc.note("material " + mat_name + ": its " + in.name + " texture names no file: left out");
		return false;
	}
	in.output = UsdShadeUtils::GetBaseNameAndType(attr.GetName()).first.GetString();
	if (UsdShadeInput cs = tex.GetInput(TfToken("sourceColorSpace"))) {
		TfToken v;
		if (cs.Get(&v, UsdTimeCode(sc.time)))
			in.color_space = v.GetString();
	}
	if (!in.text.empty() && !in.exists)
		sc.note("material " + mat_name + ": its " + in.name + " picture " + in.text + " is missing (" + in.path + ")");
	return true;
}

void read_aperture_inputs(bru_scene &sc, const std::string &mat_name, const UsdShadeShader &sh,
                          std::vector<bru_scene::Input> &out)
{
	for (const UsdAttribute &attr : sh.GetPrim().GetAttributes()) {
		const std::string full = attr.GetName().GetString();
		std::string name;
		if (full.compare(0, 7, "inputs:") == 0)
			name = full.substr(7);
		else if (full.find(':') == std::string::npos)
			name = full;  /* Remix's own: enable_opacity, filter_mode, wrap_mode_u, wrap_mode_v */
		else
			continue;
		bru_scene::Input in;
		in.name = name;
		if (!read_value(attr, sc.time, in))
			continue;
		if (in.kind == BRU_VALUE_ASSET && !in.text.empty() && !in.exists)
			sc.note("material " + mat_name + ": " + name + " " + in.text + " is missing (" + in.path + ")");
		out.push_back(in);
	}
}

int material_of(bru_scene &sc, const UsdShadeMaterial &bound)
{
	if (!bound)
		return -1;
	const SdfPath key = source_path(bound.GetPrim());
	auto it = sc.material_index.find(key);
	if (it != sc.material_index.end())
		return it->second;
	bru_scene::Material m;
	m.name = shown_name(bound.GetPrim());
	m.path = bound.GetPath().GetString();
	const TfToken mdl("mdl");
	/* the universal surface: what any tool reads */
	UsdShadeShader surf = bound.ComputeSurfaceSource();
	if (surf) {
		const TfToken id = shader_id(surf);
		if (id == TfToken("UsdPreviewSurface")) {
			m.preview = true;
			for (const UsdShadeInput &input : surf.GetInputs()) {
				bru_scene::Input in;
				if (read_preview_input(sc, m.name, input, in))
					m.preview_inputs.push_back(in);
			}
		}
		else {
			SdfAssetPath src;
			m.other = !id.IsEmpty() ? id.GetString() :
			          (surf.GetSourceAsset(&src) ? src.GetAssetPath() : type_name(surf.GetPrim()));
		}
	}
	/* Remix's: the mdl surface (OpenUSD falls back on the universal one
	 * when there is none: only an MDL counts) */
	UsdShadeShader ms = bound.ComputeSurfaceSource({mdl});
	SdfAssetPath src;
	if (ms && ms.GetSourceAsset(&src, mdl)) {
		TfToken sub;
		ms.GetSourceAssetSubIdentifier(&sub, mdl);
		if (src.GetAssetPath().find("AperturePBR") != std::string::npos ||
		    sub.GetString().find("AperturePBR") == 0) {
			m.aperture = true;
			m.mdl = src.GetAssetPath();
			m.sub_identifier = sub.GetString();
			read_aperture_inputs(sc, m.name, ms, m.aperture_inputs);
		}
		else if (!m.preview && m.other.empty()) {
			m.other = src.GetAssetPath();
		}
	}
	if (!m.preview && !m.aperture) {
		sc.note("material " + m.name + ": " +
		        (m.other.empty() ? std::string("no surface shader") :
		                           "its shader " + m.other + " is neither a UsdPreviewSurface nor AperturePBR") +
		        ": it comes in plain");
	}
	const int index = int(sc.materials.size());
	sc.material_index[key] = index;
	sc.materials.push_back(std::move(m));
	return index;
}

/* -- nodes ----------------------------------------------------------------- */

int add_node(bru_scene &sc, UsdGeomXformCache &xf, const UsdPrim &prim, int parent, int kind)
{
	bru_scene::Node n;
	n.name = shown_name(prim);
	n.prim_name = prim.GetName().GetString();
	n.path = prim.GetPath().GetString();
	n.parent = parent;
	n.kind = kind;
	UsdGeomImageable im(prim);
	n.visible = !im || im.ComputeVisibility(UsdTimeCode(sc.time)) != UsdGeomTokens->invisible;
	copy_matrix(xf.GetLocalToWorldTransform(prim), n.matrix);
	sc.nodes.push_back(std::move(n));
	return int(sc.nodes.size()) - 1;
}

bool read_mesh(bru_scene &sc, const UsdPrim &prim, bru_scene::Mesh &m)
{
	m.name = prim.IsInstanceProxy() ? prim.GetPrimInPrototype().GetName().GetString() : prim.GetName().GetString();
	const std::string where = prim.GetPath().GetString();
	if (!brb::usd::read_mesh_data(UsdGeomMesh(prim), sc.time, m,
	                              [&](const std::string &line) { sc.note(line + " (" + where + ")"); }, true))
		return false;
	const int faces = int(m.face_sizes.size());
	for (const UsdGeomSubset &s : UsdShadeMaterialBindingAPI(prim).GetMaterialBindSubsets()) {
		bru_scene::Subset sub;
		sub.name = s.GetPrim().GetName().GetString();
		TfToken type;
		s.GetElementTypeAttr().Get(&type);
		if (!type.IsEmpty() && type != UsdGeomTokens->face)
			continue;
		VtIntArray idx;
		s.GetIndicesAttr().Get(&idx, UsdTimeCode(sc.time));
		bool ok = true;
		for (int f : idx) {
			if (f < 0 || f >= faces) {
				ok = false;
				break;
			}
			sub.faces.push_back(f);
		}
		if (!ok) {
			sc.note("mesh " + m.name + ": its subset " + sub.name + " names faces it does not have: left out");
			continue;
		}
		m.subsets.push_back(std::move(sub));
	}
	return true;
}

void mesh_node(bru_scene &sc, UsdGeomXformCache &xf, const UsdPrim &prim, int parent)
{
	const SdfPath key = source_path(prim);
	int index;
	auto it = sc.mesh_index.find(key);
	if (it != sc.mesh_index.end()) {
		index = it->second;
	}
	else {
		bru_scene::Mesh m;
		if (!read_mesh(sc, prim, m))
			return;
		index = int(sc.meshes.size());
		sc.mesh_index[key] = index;
		sc.meshes.push_back(std::move(m));
	}
	const int n = add_node(sc, xf, prim, parent, BRU_NODE_MESH);
	sc.nodes[size_t(n)].index = index;
	UsdShadeMaterialBindingAPI api(prim);
	sc.nodes[size_t(n)].material = material_of(sc, api.ComputeBoundMaterial());
	/* each subset's material here (an instance may bind its own) */
	const bru_scene::Mesh &me = sc.meshes[size_t(index)];
	std::map<std::string, UsdGeomSubset> by_name;
	for (const UsdGeomSubset &s : api.GetMaterialBindSubsets())
		by_name[s.GetPrim().GetName().GetString()] = s;
	for (const bru_scene::Subset &s : me.subsets) {
		auto f = by_name.find(s.name);
		int mat = -1;
		if (f != by_name.end())
			mat = material_of(sc, UsdShadeMaterialBindingAPI(f->second.GetPrim()).ComputeBoundMaterial());
		sc.nodes[size_t(n)].subset_materials.push_back(mat);
	}
}

void light_node(bru_scene &sc, UsdGeomXformCache &xf, const UsdPrim &prim, int parent)
{
	bru_scene::Light l;
	memset(&l.d, 0, sizeof(l.d));
	l.name = shown_name(prim);
	const UsdTimeCode t(sc.time);
	if (prim.IsA<UsdLuxSphereLight>()) {
		l.d.kind = BRU_LIGHT_SPHERE;
		UsdLuxSphereLight(prim).GetRadiusAttr().Get(&l.d.radius, t);
	}
	else if (prim.IsA<UsdLuxDistantLight>()) {
		l.d.kind = BRU_LIGHT_DISTANT;
		UsdLuxDistantLight(prim).GetAngleAttr().Get(&l.d.angle, t);
	}
	else if (prim.IsA<UsdLuxRectLight>()) {
		l.d.kind = BRU_LIGHT_RECT;
		UsdLuxRectLight(prim).GetWidthAttr().Get(&l.d.width, t);
		UsdLuxRectLight(prim).GetHeightAttr().Get(&l.d.height, t);
	}
	else if (prim.IsA<UsdLuxDiskLight>()) {
		l.d.kind = BRU_LIGHT_DISK;
		UsdLuxDiskLight(prim).GetRadiusAttr().Get(&l.d.radius, t);
	}
	else if (prim.IsA<UsdLuxCylinderLight>()) {
		l.d.kind = BRU_LIGHT_CYLINDER;
		UsdLuxCylinderLight(prim).GetRadiusAttr().Get(&l.d.radius, t);
		UsdLuxCylinderLight(prim).GetLengthAttr().Get(&l.d.length, t);
	}
	else {
		sc.note(prim.GetPath().GetString() + ": a " + type_name(prim) +
		        (prim.IsA<UsdLuxDomeLight>() ? " (the sky): not imported, the scene's world is the sky" :
		                                       ": not imported (no lamp like it)"));
		return;
	}
	UsdLuxLightAPI light(prim);
	GfVec3f color(1.0f);
	light.GetColorAttr().Get(&color, t);
	for (int a = 0; a < 3; a++)
		l.d.color[a] = color[a];
	l.d.intensity = 1.0f;
	light.GetIntensityAttr().Get(&l.d.intensity, t);
	light.GetExposureAttr().Get(&l.d.exposure, t);
	l.d.cone_angle = 180.0f;
	if (prim.HasAPI<UsdLuxShapingAPI>()) {
		UsdLuxShapingAPI s(prim);
		l.d.shaped = 1;
		s.GetShapingConeAngleAttr().Get(&l.d.cone_angle, t);
		s.GetShapingConeSoftnessAttr().Get(&l.d.cone_softness, t);
		s.GetShapingFocusAttr().Get(&l.d.focus, t);
	}
	const int n = add_node(sc, xf, prim, parent, BRU_NODE_LIGHT);
	copy_matrix(xf.GetLocalToWorldTransform(prim), l.d.matrix);
	sc.nodes[size_t(n)].index = int(sc.lights.size());
	sc.lights.push_back(l);
}

int camera_node(bru_scene &sc, UsdGeomXformCache &xf, const UsdPrim &prim, int parent)
{
	UsdGeomCamera cam(prim);
	const UsdTimeCode t(sc.time);
	bru_camera c;
	memset(&c, 0, sizeof(c));
	copy_matrix(xf.GetLocalToWorldTransform(prim), c.matrix);
	c.focal_length = 50.0f;
	c.horizontal_aperture = 20.955f;
	c.vertical_aperture = 15.2908f;
	cam.GetFocalLengthAttr().Get(&c.focal_length, t);
	cam.GetHorizontalApertureAttr().Get(&c.horizontal_aperture, t);
	cam.GetVerticalApertureAttr().Get(&c.vertical_aperture, t);
	GfVec2f clip(1.0f, 1000000.0f);
	cam.GetClippingRangeAttr().Get(&clip, t);
	c.near_clip = clip[0];
	c.far_clip = clip[1];
	TfToken proj;
	cam.GetProjectionAttr().Get(&proj, t);
	c.perspective = proj != UsdGeomTokens->orthographic;
	const int n = add_node(sc, xf, prim, parent, BRU_NODE_CAMERA);
	sc.nodes[size_t(n)].index = int(sc.cameras.size());
	sc.cameras.push_back(c);
	return n;
}

void walk(bru_scene &sc, UsdGeomXformCache &xf, const UsdPrim &prim, int parent)
{
	for (const UsdPrim &c : prim.GetFilteredChildren(UsdTraverseInstanceProxies(UsdPrimDefaultPredicate))) {
		if (c.IsA<UsdShadeMaterial>() || c.IsA<UsdShadeShader>() || c.IsA<UsdShadeNodeGraph>())
			continue;  /* read through the bindings */
		if (c.IsA<UsdGeomMesh>()) {
			mesh_node(sc, xf, c, parent);
			continue;
		}
		if (c.IsA<UsdLuxBoundableLightBase>() || c.IsA<UsdLuxNonboundableLightBase>() || c.HasAPI<UsdLuxLightAPI>()) {
			light_node(sc, xf, c, parent);
			continue;
		}
		if (c.IsA<UsdGeomCamera>()) {
			camera_node(sc, xf, c, parent);
			continue;
		}
		if (c.IsA<UsdGeomPointInstancer>()) {
			sc.note(c.GetPath().GetString() + ": a point instancer: not imported (its prototypes and their copies "
			        "are left out)");
			continue;
		}
		if (c.IsA<UsdGeomGprim>() && c.HasAPI<UsdPhysicsCollisionAPI>())
			continue; /* a collision shape (Cube, Sphere, Capsule...): read with the physics (round 7) */
		if (c.IsA<UsdGeomGprim>()) {
			sc.note(c.GetPath().GetString() + ": a " + type_name(c) + ": not imported (only meshes are)");
			continue;
		}
		if (c.IsA<UsdGeomXformable>()) {
			walk(sc, xf, c, add_node(sc, xf, c, parent, BRU_NODE_XFORM));
			continue;
		}
		if (c.IsA<UsdGeomScope>() || c.GetTypeName().IsEmpty()) {
			walk(sc, xf, c, parent);  /* a group: what is under it hangs from parent */
			continue;
		}
		/* other typed prims (physics, render settings, subsets...): not a node */
	}
}

/* -- the API --------------------------------------------------------------- */

bru_scene *scene_open(const char *plugin_dir, const char *path, char *r_error, int max_bytes)
{
	std::string err;
	if (!brb::usd::start(plugin_dir ? plugin_dir : "", err)) {
		fail(err, r_error, max_bytes);
		return nullptr;
	}
	if (!path || !path[0]) {
		fail("no file given", r_error, max_bytes);
		return nullptr;
	}
	std::error_code ec;
	if (!std::filesystem::exists(std::filesystem::u8path(path), ec)) {
		fail(std::string("no such file: ") + path, r_error, max_bytes);
		return nullptr;
	}
	TfErrorMark mark;
	/* a file read before (and since written again) is read anew */
	SdfLayerRefPtr layer = SdfLayer::Find(path);
	if (layer)
		layer->Reload(true);
	else
		layer = SdfLayer::FindOrOpen(path);
	if (!layer) {
		std::string more = errors_since(mark);
		mark.Clear();
		fail(std::string("not a USD file OpenUSD can read: ") + path + (more.empty() ? "" : " (" + more + ")"),
		     r_error, max_bytes);
		return nullptr;
	}
	auto *sc = new bru_scene();
	sc->stage = UsdStage::Open(layer, UsdStage::LoadAll);
	if (!sc->stage) {
		std::string more = errors_since(mark);
		mark.Clear();
		delete sc;
		fail(std::string("the file could not be opened: ") + path + (more.empty() ? "" : " (" + more + ")"),
		     r_error, max_bytes);
		return nullptr;
	}
	UsdStageRefPtr stage = sc->stage;
	{
		const VtDictionary data = layer->GetCustomLayerData();
		auto it = data.find("creator");
		if (it != data.end() && it->second.IsHolding<std::string>())
			sc->creator = it->second.UncheckedGet<std::string>();
	}
	sc->meters_per_unit = UsdGeomGetStageMetersPerUnit(stage);
	sc->z_up = UsdGeomGetStageUpAxis(stage) == UsdGeomTokens->z;
	const bool timed = stage->HasAuthoredTimeCodeRange();
	sc->time = timed ? stage->GetStartTimeCode() : UsdTimeCode::Default().GetValue();
	if (UsdPrim dp = stage->GetDefaultPrim())
		sc->default_prim = dp.GetName().GetString();
	UsdGeomXformCache xf(timed ? UsdTimeCode(sc->time) : UsdTimeCode::Default());
	walk(*sc, xf, stage->GetPseudoRoot(), -1);
	{
		std::string notes;
		sc->physics = brb::usd::physics_json(stage, sc->time, notes);
		if (!notes.empty())
			sc->report += notes;
	}

	/* OpenUSD's own complaints */
	for (const TfError &e : mark) {
		sc->note("OpenUSD: " + e.GetCommentary());
		sc->usd_errors++;
	}
	mark.Clear();
	return sc;
}

void scene_close(bru_scene *sc)
{
	delete sc;
}

void scene_info(const bru_scene *sc, bru_scene_info *r)
{
	memset(r, 0, sizeof(*r));
	r->meters_per_unit = sc->meters_per_unit;
	r->z_up = sc->z_up ? 1 : 0;
	r->time = sc->time;
	r->node_count = int(sc->nodes.size());
	r->mesh_count = int(sc->meshes.size());
	r->material_count = int(sc->materials.size());
	r->default_prim = sc->default_prim.c_str();
	r->creator = sc->creator.c_str();
	r->report = sc->report.c_str();
	r->usd_errors = sc->usd_errors;
}

int scene_node(const bru_scene *sc, int i, bru_node *r)
{
	if (i < 0 || size_t(i) >= sc->nodes.size())
		return 0;
	const bru_scene::Node &n = sc->nodes[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->name = n.name.c_str();
	r->prim_name = n.prim_name.c_str();
	r->path = n.path.c_str();
	r->parent = n.parent;
	r->kind = n.kind;
	r->index = n.index;
	r->visible = n.visible ? 1 : 0;
	r->material = n.material;
	r->subset_count = int(n.subset_materials.size());
	r->subset_materials = n.subset_materials.empty() ? nullptr : n.subset_materials.data();
	memcpy(r->matrix, n.matrix, sizeof(r->matrix));
	return 1;
}

int scene_mesh(const bru_scene *sc, int i, bru_scene_mesh *r)
{
	if (i < 0 || size_t(i) >= sc->meshes.size())
		return 0;
	const bru_scene::Mesh &m = sc->meshes[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->name = m.name.c_str();
	r->vertex_count = int(m.points.size() / 3);
	r->face_count = int(m.face_sizes.size());
	r->corner_count = int(m.corners.size());
	r->points = m.points.data();
	r->face_sizes = m.face_sizes.data();
	r->corners = m.corners.data();
	r->normals = m.normals.empty() ? nullptr : m.normals.data();
	r->uvs = m.uvs.empty() ? nullptr : m.uvs.data();
	r->uv_name = m.uv_name.c_str();
	r->colors = m.colors.empty() ? nullptr : m.colors.data();
	r->double_sided = m.double_sided ? 1 : 0;
	r->subset_count = int(m.subsets.size());
	return 1;
}

int scene_subset(const bru_scene *sc, int mesh, int i, bru_subset *r)
{
	if (mesh < 0 || size_t(mesh) >= sc->meshes.size())
		return 0;
	const bru_scene::Mesh &m = sc->meshes[size_t(mesh)];
	if (i < 0 || size_t(i) >= m.subsets.size())
		return 0;
	const bru_scene::Subset &s = m.subsets[size_t(i)];
	r->name = s.name.c_str();
	r->face_count = int(s.faces.size());
	r->faces = s.faces.empty() ? nullptr : s.faces.data();
	return 1;
}

int scene_material(const bru_scene *sc, int i, bru_scene_material *r)
{
	if (i < 0 || size_t(i) >= sc->materials.size())
		return 0;
	const bru_scene::Material &m = sc->materials[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->name = m.name.c_str();
	r->path = m.path.c_str();
	r->preview = m.preview ? 1 : 0;
	r->aperture = m.aperture ? 1 : 0;
	r->mdl = m.mdl.c_str();
	r->sub_identifier = m.sub_identifier.c_str();
	r->other = m.other.c_str();
	r->preview_input_count = int(m.preview_inputs.size());
	r->aperture_input_count = int(m.aperture_inputs.size());
	return 1;
}

int scene_material_input(const bru_scene *sc, int mat, int which, int i, bru_shader_input *r)
{
	if (mat < 0 || size_t(mat) >= sc->materials.size())
		return 0;
	const bru_scene::Material &m = sc->materials[size_t(mat)];
	const std::vector<bru_scene::Input> &list = which ? m.aperture_inputs : m.preview_inputs;
	if (i < 0 || size_t(i) >= list.size())
		return 0;
	const bru_scene::Input &in = list[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->name = in.name.c_str();
	r->kind = in.kind;
	memcpy(r->v, in.v, sizeof(r->v));
	r->text = in.text.c_str();
	r->path = in.path.c_str();
	r->exists = in.exists ? 1 : 0;
	r->output = in.output.c_str();
	r->color_space = in.color_space.c_str();
	return 1;
}

int scene_light(const bru_scene *sc, int i, bru_light *r)
{
	if (i < 0 || size_t(i) >= sc->lights.size())
		return 0;
	*r = sc->lights[size_t(i)].d;
	r->name = sc->lights[size_t(i)].name.c_str();
	return 1;
}

const char *scene_physics(const bru_scene *sc)
{
	return sc->physics.c_str();
}

int scene_camera(const bru_scene *sc, int i, bru_camera *r)
{
	if (i < 0 || size_t(i) >= sc->cameras.size())
		return 0;
	*r = sc->cameras[size_t(i)];
	return 1;
}

#ifdef _MSC_VER
/* a crash while reading (a damaged file) is a failure, not Blender's end */
bru_scene *open_guarded(const char *plugin_dir, const char *path, char *r_error, int max_bytes, unsigned long *r_code)
{
	__try {
		return scene_open(plugin_dir, path, r_error, max_bytes);
	}
	__except (EXCEPTION_EXECUTE_HANDLER) {
		*r_code = GetExceptionCode();
		return nullptr;
	}
}
#endif

bru_scene *api_open(const char *plugin_dir, const char *path, char *r_error, int max_bytes)
{
	try {
#ifdef _MSC_VER
		unsigned long code = 0;
		bru_scene *sc = open_guarded(plugin_dir, path, r_error, max_bytes, &code);
		if (code) {
			char buf[96];
			snprintf(buf, sizeof(buf), "reading the file crashed (exception 0x%08lX)", code);
			fail(buf, r_error, max_bytes);
		}
		return sc;
#else
		return scene_open(plugin_dir, path, r_error, max_bytes);
#endif
	}
	catch (const std::exception &e) {
		fail(std::string("reading the file failed: ") + e.what(), r_error, max_bytes);
	}
	catch (...) {
		fail("reading the file failed", r_error, max_bytes);
	}
	return nullptr;
}

const bru_scene_api kSceneApi = {
    BRU_ABI_VERSION, api_open,      scene_close,          scene_info,  scene_node,   scene_mesh,
    scene_subset,    scene_material, scene_material_input, scene_light, scene_camera, scene_physics,
};

int convert(const char *plugin_dir, const char *src, const char *dst, char *r_error, int max_bytes)
{
	std::string err;
	if (!brb::usd::start(plugin_dir ? plugin_dir : "", err)) {
		fail(err, r_error, max_bytes);
		return 0;
	}
	if (!src || !src[0] || !dst || !dst[0]) {
		fail("no file given", r_error, max_bytes);
		return 0;
	}
	TfErrorMark mark;
	SdfLayerRefPtr layer = SdfLayer::Find(src);
	if (layer)
		layer->Reload(true);
	else
		layer = SdfLayer::FindOrOpen(src);
	if (!layer) {
		std::string more = errors_since(mark);
		mark.Clear();
		fail(std::string("not a USD file OpenUSD can read: ") + src + (more.empty() ? "" : " (" + more + ")"),
		     r_error, max_bytes);
		return 0;
	}
	if (!layer->Export(dst)) {
		std::string more = errors_since(mark);
		mark.Clear();
		fail(std::string("could not be written: ") + dst + (more.empty() ? "" : " (" + more + ")"), r_error,
		     max_bytes);
		return 0;
	}
	mark.Clear();
	/* the written file is read anew by the next open */
	if (SdfLayerHandle out = SdfLayer::Find(dst))
		out->Reload(true);
	return 1;
}

}  // namespace

BRU_API const bru_scene_api *bru_scene_get_api(void)
{
	return &kSceneApi;
}

BRU_API int bru_stage_convert(const char *plugin_dir, const char *src, const char *dst, char *r_error, int max_bytes)
{
	try {
		return convert(plugin_dir, src, dst, r_error, max_bytes);
	}
	catch (const std::exception &e) {
		fail(std::string("converting failed: ") + e.what(), r_error, max_bytes);
	}
	catch (...) {
		fail("converting failed", r_error, max_bytes);
	}
	return 0;
}
