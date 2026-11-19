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

/** \file usd_read.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: the readers' shared parts (usd_read.h).
 */

#include <algorithm>
#include <filesystem>

#include "pxr/usd/sdf/layerUtils.h"
#include "pxr/usd/sdf/propertySpec.h"
#include "pxr/usd/usdGeom/primvarsAPI.h"

#include "bge_remix_usd.h"
#include "usd_read.h"

PXR_NAMESPACE_USING_DIRECTIVE

namespace brb {
namespace usd {

namespace {

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

}  // namespace

bool read_mesh_data(const UsdGeomMesh &mesh, double time, MeshData &m,
                    const std::function<void(const std::string &)> &note, bool any_uv)
{
	const UsdTimeCode t(time);
	VtVec3fArray points;
	VtIntArray counts, indices;
	mesh.GetPointsAttr().Get(&points, t);
	mesh.GetFaceVertexCountsAttr().Get(&counts, t);
	mesh.GetFaceVertexIndicesAttr().Get(&indices, t);
	if (points.empty() || counts.empty() || indices.empty()) {
		note("mesh " + m.name + ": no points or faces (its file could not be read): left out");
		return false;
	}
	size_t total = 0;
	for (int c : counts) {
		if (c < 3) {
			note("mesh " + m.name + ": a face with fewer than 3 corners: left out");
			return false;
		}
		total += size_t(c);
	}
	if (total != indices.size()) {
		note("mesh " + m.name + ": its faces and corners do not agree: left out");
		return false;
	}
	for (int i : indices) {
		if (i < 0 || size_t(i) >= points.size()) {
			note("mesh " + m.name + ": a corner points past its vertices: left out");
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
				note("mesh " + m.name + ": its normals do not fit its corners: left out (Blender's own used)");
			}
		}
	}
	/* UVs: primvars:st (or another tool's first texture coordinates) */
	{
		UsdGeomPrimvar p = pv.GetPrimvar(TfToken("st"));
		if (any_uv && !(p && p.HasValue())) {
			for (const UsdGeomPrimvar &q : pv.GetPrimvarsWithValues()) {
				const SdfValueTypeName type = q.GetTypeName();
				if (type == SdfValueTypeNames->TexCoord2fArray ||
				    (type == SdfValueTypeNames->Float2Array && q.GetPrimvarName().GetString().find("st") == 0)) {
					p = q;
					break;
				}
			}
		}
		VtVec2fArray values;
		VtIntArray idx;
		if (p && p.Get(&values, t) && !values.empty()) {
			m.uv_name = p.GetPrimvarName().GetString();
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
				note("mesh " + m.name + ": its UVs do not fit its corners: left out");
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
bool read_value(const UsdAttribute &attr, double time, Value &in)
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

void copy_matrix(const GfMatrix4d &m, double r[16])
{
	const double *d = m.GetArray();
	for (int i = 0; i < 16; i++)
		r[i] = d[i];
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

}  // namespace usd
}  // namespace brb
