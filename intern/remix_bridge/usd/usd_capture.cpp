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

/** \file usd_capture.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12 round 2: reading an RTX Remix capture (bge_remix_usd.h).
 *
 * The layout is Remix 1.6's capture exporter's (dxvk-remix,
 * src/lssusd/game_exporter.cpp):
 *   /RootNode                      the default prim
 *   /RootNode/meshes/mesh_<H>      an Xform referencing meshes/mesh_<H>.usd;
 *                                  its child "mesh" the geometry (invisible:
 *                                  a prototype)
 *   /RootNode/Looks/mat_<H>        a Material referencing materials/mat_<H>.usd,
 *                                  its child Shader an AperturePBR MDL
 *   /RootNode/instances/inst_<H>_<n>  an Xform referencing (internally) its
 *                                  mesh, with its transform and material
 *   /RootNode/lights/light_<H>     UsdLux lights (spheres in their own files,
 *                                  distant ones in the stage)
 *   /RootNode/cameras/Camera       the camera
 * the root layer's customLayerData lightspeed_layer_type = "capture".
 * Everything is read through USD's composition, so a capture edited in the
 * Remix Toolkit (other attributes, other interpolations) reads the same.
 */

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

#include "pxr/pxr.h"
#include "pxr/base/gf/camera.h"
#include "pxr/base/gf/matrix4d.h"
#include "pxr/base/tf/errorMark.h"
#include "pxr/usd/sdf/layer.h"
#include "pxr/usd/sdf/layerUtils.h"
#include "pxr/usd/sdf/primSpec.h"
#include "pxr/usd/sdf/reference.h"
#include "pxr/usd/usd/primRange.h"
#include "pxr/usd/usd/stage.h"
#include "pxr/usd/usdGeom/camera.h"
#include "pxr/usd/usdGeom/mesh.h"
#include "pxr/usd/usdGeom/metrics.h"
#include "pxr/usd/usdGeom/primvarsAPI.h"
#include "pxr/usd/usdGeom/xformCache.h"
#include "pxr/usd/usdLux/cylinderLight.h"
#include "pxr/usd/usdLux/diskLight.h"
#include "pxr/usd/usdLux/distantLight.h"
#include "pxr/usd/usdLux/domeLight.h"
#include "pxr/usd/usdLux/lightAPI.h"
#include "pxr/usd/usdLux/rectLight.h"
#include "pxr/usd/usdLux/shapingAPI.h"
#include "pxr/usd/usdLux/sphereLight.h"
#include "pxr/usd/usdShade/material.h"
#include "pxr/usd/usdShade/materialBindingAPI.h"
#include "pxr/usd/usdShade/shader.h"

#include "bge_remix_usd.h"
#include "usd_core.h"

PXR_NAMESPACE_USING_DIRECTIVE

struct bru_capture {
	struct Mesh {
		uint64_t hash = 0;
		std::string name;
		SdfPath path;  /* the prototype, /RootNode/meshes/mesh_<H> */
		std::vector<float> points, normals, uvs, colors;
		std::vector<int> face_sizes, corners;
		bool double_sided = false;
	};
	struct Instance {
		uint64_t hash = 0;
		std::string name;
		int mesh = -1, material = -1;
		bool sky = false;
		double matrix[16];
	};
	struct Input {
		std::string name, text, path;
		int kind = BRU_VALUE_FLOAT;
		double v[4] = {0, 0, 0, 0};
		bool exists = false;
	};
	struct Material {
		uint64_t hash = 0;
		std::string name, mdl, sub_identifier;
		SdfPath path;
		std::vector<Input> inputs;
	};
	struct Light {
		bru_light d;
		std::string name;
	};

	UsdStageRefPtr stage;
	double meters_per_unit = 1.0;
	bool z_up = true;
	double time = 0.0;
	std::string game_name, exe_name, report;
	std::vector<Mesh> meshes;
	std::vector<Instance> instances;
	std::vector<Material> materials;
	std::vector<Light> lights;
	bool camera_found = false;
	bru_camera camera;
	std::map<SdfPath, int> mesh_index, material_index;

	void note(const std::string &line)
	{
		report += line;
		report += "\n";
	}
};

namespace {

/* the hash in a name such as mesh_0123456789ABCDEF (0: not one) */
uint64_t name_hash(const std::string &name, const char *prefix)
{
	const size_t n = strlen(prefix);
	if (name.compare(0, n, prefix) != 0 || name.size() < n + 16)
		return 0;
	const std::string hex = name.substr(n, 16);
	for (char c : hex) {
		if (!isxdigit((unsigned char)c))
			return 0;
	}
	return strtoull(hex.c_str(), nullptr, 16);
}

void copy_matrix(const GfMatrix4d &m, double r[16])
{
	const double *d = m.GetArray();
	for (int i = 0; i < 16; i++)
		r[i] = d[i];
}

void fail(const std::string &text, char *r_error, int max_bytes)
{
	if (r_error && max_bytes > 0) {
		snprintf(r_error, size_t(max_bytes), "%s", text.c_str());
	}
}

std::string errors_since(const TfErrorMark &mark)
{
	std::string text;
	for (const TfError &e : mark) {
		if (!text.empty())
			text += "; ";
		text += e.GetCommentary();
	}
	return text;
}

/* a per-something primvar spread over the corners: vertex values through
 * the corners' vertices, face-varying ones as they are, uniform ones per
 * face, a constant one everywhere; indexed ones through their indices */
template<typename T>
bool spread(const VtArray<T> &values, const VtIntArray &indices, const TfToken &interp,
            const std::vector<int> &face_sizes, const std::vector<int> &corners, std::vector<T> &r_out)
{
	auto value = [&](size_t i, T &r) {
		if (!indices.empty()) {
			if (i >= indices.size())
				return false;
			i = size_t(indices[i]);
		}
		if (i >= values.size())
			return false;
		r = values[i];
		return true;
	};
	r_out.resize(corners.size());
	if (interp == UsdGeomTokens->vertex || interp == UsdGeomTokens->varying) {
		for (size_t c = 0; c < corners.size(); c++) {
			if (!value(size_t(corners[c]), r_out[c]))
				return false;
		}
	}
	else if (interp == UsdGeomTokens->faceVarying) {
		for (size_t c = 0; c < corners.size(); c++) {
			if (!value(c, r_out[c]))
				return false;
		}
	}
	else if (interp == UsdGeomTokens->uniform) {
		size_t c = 0;
		for (size_t f = 0; f < face_sizes.size(); f++) {
			T v;
			if (!value(f, v))
				return false;
			for (int k = 0; k < face_sizes[f]; k++)
				r_out[c++] = v;
		}
	}
	else if (interp == UsdGeomTokens->constant) {
		T v;
		if (!value(0, v))
			return false;
		for (auto &o : r_out)
			o = v;
	}
	else {
		return false;
	}
	return true;
}

bool read_mesh(bru_capture &cap, const UsdPrim &proto, bru_capture::Mesh &m)
{
	const UsdTimeCode t(cap.time);
	/* the geometry: the prototype's child "mesh", or the prototype itself */
	UsdGeomMesh mesh(proto.GetChild(TfToken("mesh")));
	if (!mesh)
		mesh = UsdGeomMesh(proto);
	if (!mesh) {
		cap.note("mesh " + m.name + ": no geometry (its file could not be read, or holds no mesh): left out");
		return false;
	}
	VtVec3fArray points;
	VtIntArray counts, indices;
	mesh.GetPointsAttr().Get(&points, t);
	mesh.GetFaceVertexCountsAttr().Get(&counts, t);
	mesh.GetFaceVertexIndicesAttr().Get(&indices, t);
	if (points.empty() || counts.empty() || indices.empty()) {
		cap.note("mesh " + m.name + ": no points or faces (its file could not be read): left out");
		return false;
	}
	size_t total = 0;
	for (int c : counts) {
		if (c < 3) {
			cap.note("mesh " + m.name + ": a face with fewer than 3 corners: left out");
			return false;
		}
		total += size_t(c);
	}
	if (total != indices.size()) {
		cap.note("mesh " + m.name + ": its faces and corners do not agree: left out");
		return false;
	}
	for (int i : indices) {
		if (i < 0 || size_t(i) >= points.size()) {
			cap.note("mesh " + m.name + ": a corner points past its vertices: left out");
			return false;
		}
	}
	m.points.resize(points.size() * 3);
	for (size_t i = 0; i < points.size(); i++)
		for (int a = 0; a < 3; a++)
			m.points[i * 3 + a] = points[i][a];
	m.face_sizes.assign(counts.begin(), counts.end());
	m.corners.assign(indices.begin(), indices.end());

	/* normals: primvars:normals first (it wins in USD), else normals */
	UsdGeomPrimvarsAPI pv(mesh.GetPrim());
	{
		VtVec3fArray values;
		VtIntArray idx;
		TfToken interp;
		UsdGeomPrimvar p = pv.GetPrimvar(TfToken("normals"));
		bool have = false;
		if (p && p.HasValue()) {
			have = p.Get(&values, t);
			p.GetIndices(&idx, t);
			interp = p.GetInterpolation();
		}
		else if (mesh.GetNormalsAttr().HasValue()) {
			have = mesh.GetNormalsAttr().Get(&values, t);
			interp = mesh.GetNormalsInterpolation();
		}
		if (have && !values.empty()) {
			std::vector<GfVec3f> out;
			if (spread(values, idx, interp, m.face_sizes, m.corners, out)) {
				m.normals.resize(out.size() * 3);
				for (size_t c = 0; c < out.size(); c++)
					for (int a = 0; a < 3; a++)
						m.normals[c * 3 + a] = out[c][a];
			}
			else {
				cap.note("mesh " + m.name + ": its normals do not fit its corners: left out (Blender's own used)");
			}
		}
	}
	/* UVs: primvars:st */
	{
		UsdGeomPrimvar p = pv.GetPrimvar(TfToken("st"));
		VtVec2fArray values;
		VtIntArray idx;
		if (p && p.Get(&values, t) && !values.empty()) {
			p.GetIndices(&idx, t);
			std::vector<GfVec2f> out;
			if (spread(values, idx, p.GetInterpolation(), m.face_sizes, m.corners, out)) {
				m.uvs.resize(out.size() * 2);
				for (size_t c = 0; c < out.size(); c++) {
					m.uvs[c * 2] = out[c][0];
					m.uvs[c * 2 + 1] = out[c][1];
				}
			}
			else {
				cap.note("mesh " + m.name + ": its UVs do not fit its corners: left out");
			}
		}
	}
	/* colours: displayColor and displayOpacity */
	{
		UsdGeomPrimvar pc = pv.GetPrimvar(UsdGeomTokens->primvarsDisplayColor);
		VtVec3fArray values;
		VtIntArray idx;
		if (pc && pc.Get(&values, t) && !values.empty()) {
			pc.GetIndices(&idx, t);
			std::vector<GfVec3f> out;
			if (spread(values, idx, pc.GetInterpolation(), m.face_sizes, m.corners, out)) {
				std::vector<float> alpha(out.size(), 1.0f);
				UsdGeomPrimvar po = pv.GetPrimvar(UsdGeomTokens->primvarsDisplayOpacity);
				VtFloatArray av;
				VtIntArray aidx;
				if (po && po.Get(&av, t) && !av.empty()) {
					po.GetIndices(&aidx, t);
					std::vector<float> aout;
					if (spread(av, aidx, po.GetInterpolation(), m.face_sizes, m.corners, aout))
						alpha = aout;
				}
				m.colors.resize(out.size() * 4);
				for (size_t c = 0; c < out.size(); c++) {
					for (int a = 0; a < 3; a++)
						m.colors[c * 4 + a] = out[c][a];
					m.colors[c * 4 + 3] = alpha[c];
				}
			}
		}
	}
	bool ds = false;
	mesh.GetDoubleSidedAttr().Get(&ds, t);
	m.double_sided = ds;
	/* left-handed faces turn the other way round in Blender */
	TfToken orient;
	mesh.GetOrientationAttr().Get(&orient, t);
	if (orient == UsdGeomTokens->leftHanded) {
		size_t c = 0;
		for (int n : m.face_sizes) {
			std::reverse(m.corners.begin() + long(c), m.corners.begin() + long(c + size_t(n)));
			auto rev3 = [&](std::vector<float> &v, int w) {
				if (v.empty())
					return;
				for (int a = 0; a < n / 2; a++)
					for (int k = 0; k < w; k++)
						std::swap(v[(c + size_t(a)) * size_t(w) + size_t(k)],
						          v[(c + size_t(n - 1 - a)) * size_t(w) + size_t(k)]);
			};
			rev3(m.normals, 3);
			rev3(m.uvs, 2);
			rev3(m.colors, 4);
			c += size_t(n);
		}
	}
	return true;
}

/* a value of a shader input */
bool read_value(const UsdAttribute &attr, double time, bru_capture::Input &in)
{
	VtValue v;
	if (!attr.Get(&v, UsdTimeCode(time)) || v.IsEmpty())
		return false;
	if (v.IsHolding<float>()) {
		in.kind = BRU_VALUE_FLOAT;
		in.v[0] = v.UncheckedGet<float>();
	}
	else if (v.IsHolding<double>()) {
		in.kind = BRU_VALUE_FLOAT;
		in.v[0] = v.UncheckedGet<double>();
	}
	else if (v.IsHolding<int>()) {
		in.kind = BRU_VALUE_INT;
		in.v[0] = v.UncheckedGet<int>();
	}
	else if (v.IsHolding<unsigned int>()) {
		in.kind = BRU_VALUE_INT;
		in.v[0] = v.UncheckedGet<unsigned int>();
	}
	else if (v.IsHolding<int64_t>()) {
		in.kind = BRU_VALUE_INT;
		in.v[0] = double(v.UncheckedGet<int64_t>());
	}
	else if (v.IsHolding<bool>()) {
		in.kind = BRU_VALUE_BOOL;
		in.v[0] = v.UncheckedGet<bool>() ? 1.0 : 0.0;
	}
	else if (v.IsHolding<GfVec2f>()) {
		in.kind = BRU_VALUE_VEC2;
		for (int a = 0; a < 2; a++)
			in.v[a] = v.UncheckedGet<GfVec2f>()[a];
	}
	else if (v.IsHolding<GfVec3f>()) {
		in.kind = BRU_VALUE_VEC3;
		for (int a = 0; a < 3; a++)
			in.v[a] = v.UncheckedGet<GfVec3f>()[a];
	}
	else if (v.IsHolding<GfVec3d>()) {
		in.kind = BRU_VALUE_VEC3;
		for (int a = 0; a < 3; a++)
			in.v[a] = v.UncheckedGet<GfVec3d>()[a];
	}
	else if (v.IsHolding<GfVec4f>()) {
		in.kind = BRU_VALUE_VEC4;
		for (int a = 0; a < 4; a++)
			in.v[a] = v.UncheckedGet<GfVec4f>()[a];
	}
	else if (v.IsHolding<TfToken>()) {
		in.kind = BRU_VALUE_TOKEN;
		in.text = v.UncheckedGet<TfToken>().GetString();
	}
	else if (v.IsHolding<std::string>()) {
		in.kind = BRU_VALUE_TOKEN;
		in.text = v.UncheckedGet<std::string>();
	}
	else if (v.IsHolding<SdfAssetPath>()) {
		const SdfAssetPath &a = v.UncheckedGet<SdfAssetPath>();
		in.kind = BRU_VALUE_ASSET;
		in.text = a.GetAssetPath();
		in.path = a.GetResolvedPath();
		if (in.path.empty() && !in.text.empty()) {
			/* not found: where it would be, from the layer that wrote it */
			for (const SdfPropertySpecHandle &spec : attr.GetPropertyStack(UsdTimeCode(time))) {
				if (spec && spec->HasDefaultValue()) {
					in.path = SdfComputeAssetPathRelativeToLayer(spec->GetLayer(), in.text);
					break;
				}
			}
		}
		std::error_code ec;
		in.exists = !in.path.empty() && std::filesystem::exists(std::filesystem::u8path(in.path), ec);
	}
	else {
		return false;
	}
	return true;
}

void read_material(bru_capture &cap, const UsdPrim &prim, bru_capture::Material &mat)
{
	UsdShadeMaterial m(prim);
	const TfToken mdl("mdl");
	UsdShadeShader shader = m ? m.ComputeSurfaceSource({mdl}) : UsdShadeShader();
	if (!shader) {
		for (const UsdPrim &child : prim.GetChildren()) {
			if (child.IsA<UsdShadeShader>()) {
				shader = UsdShadeShader(child);
				break;
			}
		}
	}
	if (!shader) {
		cap.note("material " + mat.name + ": no shader (its file could not be read): it comes in plain");
		return;
	}
	SdfAssetPath src;
	if (shader.GetSourceAsset(&src, mdl))
		mat.mdl = src.GetAssetPath();
	TfToken sub;
	if (shader.GetSourceAssetSubIdentifier(&sub, mdl))
		mat.sub_identifier = sub.GetString();
	if (mat.mdl.empty()) {
		TfToken id;
		shader.GetShaderId(&id);
		cap.note("material " + mat.name + ": its shader is not an MDL (" +
		         (id.IsEmpty() ? std::string("none") : id.GetString()) + "): its values are read as they are");
	}
	else if (mat.mdl.find("AperturePBR") == std::string::npos) {
		cap.note("material " + mat.name + ": its shader is " + mat.mdl + ", not AperturePBR: its values are read as they are");
	}
	for (const UsdAttribute &attr : shader.GetPrim().GetAttributes()) {
		const std::string full = attr.GetName().GetString();
		std::string name;
		if (full.compare(0, 7, "inputs:") == 0)
			name = full.substr(7);
		else if (full.find(':') == std::string::npos)
			name = full;  /* Remix's own: enable_opacity, filter_mode, wrap_mode_u, wrap_mode_v */
		else
			continue;
		bru_capture::Input in;
		in.name = name;
		if (!read_value(attr, cap.time, in))
			continue;
		if (in.kind == BRU_VALUE_ASSET && !in.text.empty() && !in.exists)
			cap.note("material " + mat.name + ": " + name + " " + in.text + " is missing (" + in.path + ")");
		mat.inputs.push_back(in);
	}
}

void read_light(bru_capture &cap, UsdGeomXformCache &xf, const UsdPrim &prim)
{
	bru_capture::Light l;
	memset(&l.d, 0, sizeof(l.d));
	l.name = prim.GetName().GetString();
	l.d.hash = name_hash(l.name, "light_");
	if (!l.d.hash)
		l.d.hash = name_hash(l.name, "sphereLight_");  /* Remix's older name */
	const UsdTimeCode t(cap.time);
	if (prim.IsA<UsdLuxDomeLight>()) {
		cap.note("light " + l.name + ": a dome (the sky): left out, the scene's world is the sky");
		return;
	}
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
		if (prim.HasAPI<UsdLuxLightAPI>())
			cap.note("light " + l.name + ": a " + prim.GetTypeName().GetString() + ": left out");
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
	copy_matrix(xf.GetLocalToWorldTransform(prim), l.d.matrix);
	cap.lights.push_back(l);
}

void read_camera(bru_capture &cap, UsdGeomXformCache &xf, const UsdPrim &root)
{
	UsdGeomCamera cam;
	const UsdPrim cams = root.GetChild(TfToken("cameras"));
	if (cams) {
		UsdGeomCamera named(cams.GetChild(TfToken("Camera")));
		if (named) {
			cam = named;
		}
		else {
			for (const UsdPrim &p : UsdPrimRange(cams)) {
				if (p.IsA<UsdGeomCamera>()) {
					cam = UsdGeomCamera(p);
					break;
				}
			}
		}
	}
	if (!cam)
		return;
	const UsdTimeCode t(cap.time);
	memset(&cap.camera, 0, sizeof(cap.camera));
	copy_matrix(xf.GetLocalToWorldTransform(cam.GetPrim()), cap.camera.matrix);
	cam.GetFocalLengthAttr().Get(&cap.camera.focal_length, t);
	cam.GetHorizontalApertureAttr().Get(&cap.camera.horizontal_aperture, t);
	cam.GetVerticalApertureAttr().Get(&cap.camera.vertical_aperture, t);
	GfVec2f clip(1.0f, 1000000.0f);
	cam.GetClippingRangeAttr().Get(&clip, t);
	cap.camera.near_clip = clip[0];
	cap.camera.far_clip = clip[1];
	TfToken proj;
	cam.GetProjectionAttr().Get(&proj, t);
	cap.camera.perspective = proj != UsdGeomTokens->orthographic;
	cap.camera_found = true;
}

/* the mesh an instance draws: the prim its (internal) reference names, or
 * from its name (inst_<mesh hash>_<n>) */
SdfPath instance_mesh(const UsdPrim &inst)
{
	for (const SdfPrimSpecHandle &spec : inst.GetPrimStack()) {
		if (!spec)
			continue;
		for (const SdfReference &ref : spec->GetReferenceList().GetAppliedItems()) {
			if (ref.GetAssetPath().empty() && !ref.GetPrimPath().IsEmpty())
				return ref.GetPrimPath();
		}
	}
	return SdfPath();
}

bru_capture *capture_open(const char *plugin_dir, const char *path, char *r_error, int max_bytes)
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
	SdfLayerRefPtr layer = SdfLayer::FindOrOpen(path);
	if (!layer) {
		std::string more = errors_since(mark);
		mark.Clear();
		fail(std::string("not a USD file OpenUSD can read: ") + path + (more.empty() ? "" : " (" + more + ")"),
		     r_error, max_bytes);
		return nullptr;
	}
	VtDictionary data = layer->GetCustomLayerData();
	auto text = [&](const char *key) {
		auto it = data.find(key);
		return (it != data.end() && it->second.IsHolding<std::string>()) ? it->second.UncheckedGet<std::string>()
		                                                                   : std::string();
	};
	if (text("lightspeed_layer_type") != "capture") {
		const std::string kind = text("lightspeed_layer_type");
		mark.Clear();
		fail(std::string("not an RTX Remix capture (") +
		         (kind.empty() ? std::string("no capture marks in the file") :
		                         "its Remix layer type is \"" + kind + "\", not \"capture\"") +
		         "): " + path,
		     r_error, max_bytes);
		return nullptr;
	}
	auto *cap = new bru_capture();
	cap->stage = UsdStage::Open(layer);
	if (!cap->stage) {
		std::string more = errors_since(mark);
		mark.Clear();
		delete cap;
		fail(std::string("the capture could not be opened: ") + path + (more.empty() ? "" : " (" + more + ")"),
		     r_error, max_bytes);
		return nullptr;
	}
	cap->game_name = text("lightspeed_game_name");
	cap->exe_name = text("lightspeed_exe_name");
	UsdStageRefPtr stage = cap->stage;
	cap->meters_per_unit = UsdGeomGetStageMetersPerUnit(stage);
	cap->z_up = UsdGeomGetStageUpAxis(stage) == UsdGeomTokens->z;
	cap->time = stage->HasAuthoredTimeCodeRange() ? stage->GetStartTimeCode() : 0.0;
	const UsdTimeCode t = stage->HasAuthoredTimeCodeRange() ? UsdTimeCode(cap->time) : UsdTimeCode::Default();
	if (!stage->HasAuthoredTimeCodeRange())
		cap->time = UsdTimeCode::Default().GetValue();

	UsdPrim root = stage->GetPrimAtPath(SdfPath("/RootNode"));
	if (!root) {
		mark.Clear();
		delete cap;
		fail(std::string("the capture has no /RootNode: ") + path, r_error, max_bytes);
		return nullptr;
	}
	UsdGeomXformCache xf(t);

	/* materials */
	if (UsdPrim looks = root.GetChild(TfToken("Looks"))) {
		for (const UsdPrim &p : looks.GetChildren()) {
			if (!p.IsA<UsdShadeMaterial>())
				continue;
			bru_capture::Material m;
			m.name = p.GetName().GetString();
			m.hash = name_hash(m.name, "mat_");
			m.path = p.GetPath();
			read_material(*cap, p, m);
			cap->material_index[m.path] = int(cap->materials.size());
			cap->materials.push_back(std::move(m));
		}
	}
	/* meshes (the prototypes) */
	if (UsdPrim meshes = root.GetChild(TfToken("meshes"))) {
		for (const UsdPrim &p : meshes.GetChildren()) {
			bru_capture::Mesh m;
			m.name = p.GetName().GetString();
			m.hash = name_hash(m.name, "mesh_");
			m.path = p.GetPath();
			if (!read_mesh(*cap, p, m))
				continue;
			cap->mesh_index[m.path] = int(cap->meshes.size());
			cap->meshes.push_back(std::move(m));
		}
	}
	/* instances */
	if (UsdPrim insts = root.GetChild(TfToken("instances"))) {
		for (const UsdPrim &p : insts.GetChildren()) {
			bru_capture::Instance in;
			in.name = p.GetName().GetString();
			in.sky = in.name.compare(0, 4, "sky_") == 0;
			in.hash = name_hash(in.name, in.sky ? "sky_" : "inst_");
			SdfPath mesh = instance_mesh(p);
			if (mesh.IsEmpty() && in.hash) {
				char buf[64];
				snprintf(buf, sizeof(buf), "/RootNode/meshes/mesh_%016llX", (unsigned long long)in.hash);
				mesh = SdfPath(buf);
			}
			auto mi = cap->mesh_index.find(mesh);
			if (mi == cap->mesh_index.end()) {
				cap->note("instance " + in.name + ": its mesh " +
				          (mesh.IsEmpty() ? std::string("(none named)") : mesh.GetName()) +
				          " was not read: left out");
				continue;
			}
			in.mesh = mi->second;
			/* the place of the geometry: the instance's own "mesh" child (as
			 * referenced from the prototype), or the instance */
			UsdPrim geo = p.GetChild(TfToken("mesh"));
			if (!geo)
				geo = p;
			copy_matrix(xf.GetLocalToWorldTransform(geo), in.matrix);
			UsdShadeMaterial bound = UsdShadeMaterialBindingAPI(geo).ComputeBoundMaterial();
			if (!bound)
				bound = UsdShadeMaterialBindingAPI(p).ComputeBoundMaterial();
			if (bound) {
				auto mt = cap->material_index.find(bound.GetPath());
				if (mt != cap->material_index.end())
					in.material = mt->second;
				else
					cap->note("instance " + in.name + ": its material " + bound.GetPath().GetString() +
					          " is not one of the capture's: it comes in without");
			}
			cap->instances.push_back(in);
		}
	}
	/* lights and the camera */
	if (UsdPrim lights = root.GetChild(TfToken("lights"))) {
		for (const UsdPrim &p : lights.GetChildren())
			read_light(*cap, xf, p);
	}
	read_camera(*cap, xf, root);
	if (!cap->camera_found)
		cap->note("no camera in the capture");

	/* OpenUSD's own complaints (a mesh file cut short, a missing file) */
	for (const TfError &e : mark)
		cap->note("OpenUSD: " + e.GetCommentary());
	mark.Clear();
	return cap;
}

void capture_close(bru_capture *cap)
{
	delete cap;
}

void capture_info(const bru_capture *cap, bru_capture_info *r)
{
	memset(r, 0, sizeof(*r));
	r->meters_per_unit = cap->meters_per_unit;
	r->z_up = cap->z_up ? 1 : 0;
	r->time = cap->time;
	r->mesh_count = int(cap->meshes.size());
	r->instance_count = int(cap->instances.size());
	r->material_count = int(cap->materials.size());
	r->light_count = int(cap->lights.size());
	r->camera_found = cap->camera_found ? 1 : 0;
	r->game_name = cap->game_name.c_str();
	r->exe_name = cap->exe_name.c_str();
	r->report = cap->report.c_str();
}

int capture_mesh(const bru_capture *cap, int i, bru_mesh *r)
{
	if (i < 0 || size_t(i) >= cap->meshes.size())
		return 0;
	const bru_capture::Mesh &m = cap->meshes[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->hash = m.hash;
	r->name = m.name.c_str();
	r->vertex_count = int(m.points.size() / 3);
	r->face_count = int(m.face_sizes.size());
	r->corner_count = int(m.corners.size());
	r->points = m.points.data();
	r->face_sizes = m.face_sizes.data();
	r->corners = m.corners.data();
	r->normals = m.normals.empty() ? nullptr : m.normals.data();
	r->uvs = m.uvs.empty() ? nullptr : m.uvs.data();
	r->colors = m.colors.empty() ? nullptr : m.colors.data();
	r->double_sided = m.double_sided ? 1 : 0;
	return 1;
}

int capture_instance(const bru_capture *cap, int i, bru_instance *r)
{
	if (i < 0 || size_t(i) >= cap->instances.size())
		return 0;
	const bru_capture::Instance &in = cap->instances[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->hash = in.hash;
	r->name = in.name.c_str();
	r->mesh = in.mesh;
	r->material = in.material;
	r->sky = in.sky ? 1 : 0;
	memcpy(r->matrix, in.matrix, sizeof(r->matrix));
	return 1;
}

int capture_material(const bru_capture *cap, int i, bru_material *r)
{
	if (i < 0 || size_t(i) >= cap->materials.size())
		return 0;
	const bru_capture::Material &m = cap->materials[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->hash = m.hash;
	r->name = m.name.c_str();
	r->mdl = m.mdl.c_str();
	r->sub_identifier = m.sub_identifier.c_str();
	r->input_count = int(m.inputs.size());
	return 1;
}

int capture_material_input(const bru_capture *cap, int mat, int i, bru_input *r)
{
	if (mat < 0 || size_t(mat) >= cap->materials.size())
		return 0;
	const bru_capture::Material &m = cap->materials[size_t(mat)];
	if (i < 0 || size_t(i) >= m.inputs.size())
		return 0;
	const bru_capture::Input &in = m.inputs[size_t(i)];
	memset(r, 0, sizeof(*r));
	r->name = in.name.c_str();
	r->kind = in.kind;
	memcpy(r->v, in.v, sizeof(r->v));
	r->text = in.text.c_str();
	r->path = in.path.c_str();
	r->exists = in.exists ? 1 : 0;
	return 1;
}

int capture_light(const bru_capture *cap, int i, bru_light *r)
{
	if (i < 0 || size_t(i) >= cap->lights.size())
		return 0;
	*r = cap->lights[size_t(i)].d;
	r->name = cap->lights[size_t(i)].name.c_str();
	return 1;
}

int capture_camera(const bru_capture *cap, bru_camera *r)
{
	if (!cap->camera_found)
		return 0;
	*r = cap->camera;
	return 1;
}

/* every call caught: OpenUSD's exceptions do not leave the DLL */
bru_capture *api_open(const char *plugin_dir, const char *path, char *r_error, int max_bytes)
{
	try {
		return capture_open(plugin_dir, path, r_error, max_bytes);
	}
	catch (const std::exception &e) {
		fail(std::string("reading the capture failed: ") + e.what(), r_error, max_bytes);
	}
	catch (...) {
		fail("reading the capture failed", r_error, max_bytes);
	}
	return nullptr;
}

const bru_capture_api kApi = {
    BRU_ABI_VERSION, api_open,         capture_close,          capture_info,   capture_mesh,
    capture_instance, capture_material, capture_material_input, capture_light, capture_camera,
};

}  // namespace

BRU_API const bru_capture_api *bru_capture_get_api(void)
{
	return &kApi;
}
