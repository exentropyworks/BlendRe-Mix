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

/** \file usd_dump.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12 round 3: any USD stage written out as JSON (bru_stage_dump):
 * what OpenUSD composes from it, prim by prim. Used to read back what we
 * export (an RTX Remix mod) and by the tests. Arrays are given by their
 * length, their first values and, for points, their bounds.
 */

#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

#include "pxr/pxr.h"
#include "pxr/base/gf/matrix4d.h"
#include "pxr/base/gf/vec2d.h"
#include "pxr/base/gf/vec2f.h"
#include "pxr/base/gf/vec3d.h"
#include "pxr/base/gf/vec3f.h"
#include "pxr/base/gf/vec4f.h"
#include "pxr/base/tf/errorMark.h"
#include "pxr/usd/sdf/assetPath.h"
#include "pxr/usd/sdf/primSpec.h"
#include "pxr/usd/sdf/reference.h"
#include "pxr/usd/usd/primRange.h"
#include "pxr/usd/usd/stage.h"
#include "pxr/usd/usdGeom/metrics.h"
#include "pxr/usd/usdGeom/xformCache.h"
#include "pxr/usd/usdGeom/xformable.h"

#include "bge_remix_usd.h"
#include "usd_core.h"

PXR_NAMESPACE_USING_DIRECTIVE

namespace {

const size_t kFirst = 8;

std::string jstr(const std::string &s)
{
	std::string out = "\"";
	for (char c : s) {
		switch (c) {
			case '"': out += "\\\""; break;
			case '\\': out += "\\\\"; break;
			case '\n': out += "\\n"; break;
			case '\r': out += "\\r"; break;
			case '\t': out += "\\t"; break;
			default:
				if ((unsigned char)c < 0x20) {
					char buf[8];
					snprintf(buf, sizeof(buf), "\\u%04x", c);
					out += buf;
				}
				else {
					out += c;
				}
		}
	}
	return out + "\"";
}

std::string jnum(double v)
{
	if (!std::isfinite(v))
		return "null";
	char buf[40];
	snprintf(buf, sizeof(buf), "%.9g", v);
	return buf;
}

template<typename V> std::string jvec(const V &v, int n)
{
	std::string out = "[";
	for (int i = 0; i < n; i++)
		out += (i ? ", " : "") + jnum(double(v[i]));
	return out + "]";
}

std::string jmatrix(const GfMatrix4d &m)
{
	std::string out = "[";
	const double *d = m.GetArray();
	for (int i = 0; i < 16; i++)
		out += (i ? ", " : "") + jnum(d[i]);
	return out + "]";
}

template<typename T, typename F> std::string jarray(const VtArray<T> &a, F one)
{
	std::string out = "{\"count\": " + std::to_string(a.size()) + ", \"first\": [";
	for (size_t i = 0; i < a.size() && i < kFirst; i++)
		out += (i ? ", " : "") + one(a[i]);
	return out + "]}";
}

std::string jbounds3(const VtArray<GfVec3f> &a)
{
	if (a.empty())
		return "null";
	GfVec3f lo = a[0], hi = a[0];
	for (const GfVec3f &p : a) {
		for (int k = 0; k < 3; k++) {
			lo[k] = std::min(lo[k], p[k]);
			hi[k] = std::max(hi[k], p[k]);
		}
	}
	return "[" + jvec(lo, 3) + ", " + jvec(hi, 3) + "]";
}

/* a value as JSON (null for a kind not written out) */
std::string jvalue(const VtValue &v)
{
	if (v.IsHolding<float>()) return jnum(v.UncheckedGet<float>());
	if (v.IsHolding<double>()) return jnum(v.UncheckedGet<double>());
	if (v.IsHolding<int>()) return std::to_string(v.UncheckedGet<int>());
	if (v.IsHolding<unsigned int>()) return std::to_string(v.UncheckedGet<unsigned int>());
	if (v.IsHolding<unsigned char>()) return std::to_string(int(v.UncheckedGet<unsigned char>()));
	if (v.IsHolding<int64_t>()) return std::to_string(v.UncheckedGet<int64_t>());
	if (v.IsHolding<bool>()) return v.UncheckedGet<bool>() ? "true" : "false";
	if (v.IsHolding<std::string>()) return jstr(v.UncheckedGet<std::string>());
	if (v.IsHolding<TfToken>()) return jstr(v.UncheckedGet<TfToken>().GetString());
	if (v.IsHolding<SdfAssetPath>()) {
		const SdfAssetPath &a = v.UncheckedGet<SdfAssetPath>();
		return "{\"asset\": " + jstr(a.GetAssetPath()) + ", \"resolved\": " + jstr(a.GetResolvedPath()) + "}";
	}
	if (v.IsHolding<GfVec2f>()) return jvec(v.UncheckedGet<GfVec2f>(), 2);
	if (v.IsHolding<GfVec2d>()) return jvec(v.UncheckedGet<GfVec2d>(), 2);
	if (v.IsHolding<GfVec3f>()) return jvec(v.UncheckedGet<GfVec3f>(), 3);
	if (v.IsHolding<GfVec3d>()) return jvec(v.UncheckedGet<GfVec3d>(), 3);
	if (v.IsHolding<GfVec4f>()) return jvec(v.UncheckedGet<GfVec4f>(), 4);
	if (v.IsHolding<GfMatrix4d>()) return jmatrix(v.UncheckedGet<GfMatrix4d>());
	if (v.IsHolding<VtArray<GfVec3f>>()) {
		const VtArray<GfVec3f> &a = v.UncheckedGet<VtArray<GfVec3f>>();
		std::string s = jarray(a, [](const GfVec3f &x) { return jvec(x, 3); });
		s.pop_back();
		return s + ", \"bounds\": " + jbounds3(a) + "}";
	}
	if (v.IsHolding<VtArray<GfVec2f>>())
		return jarray(v.UncheckedGet<VtArray<GfVec2f>>(), [](const GfVec2f &x) { return jvec(x, 2); });
	if (v.IsHolding<VtArray<int>>())
		return jarray(v.UncheckedGet<VtArray<int>>(), [](int x) { return std::to_string(x); });
	if (v.IsHolding<VtArray<float>>())
		return jarray(v.UncheckedGet<VtArray<float>>(), [](float x) { return jnum(x); });
	if (v.IsHolding<VtArray<TfToken>>())
		return jarray(v.UncheckedGet<VtArray<TfToken>>(), [](const TfToken &x) { return jstr(x.GetString()); });
	return "null";
}

std::string jdict(const VtDictionary &d)
{
	std::string out = "{";
	bool first = true;
	for (const auto &kv : d) {
		const std::string v = kv.second.IsHolding<VtDictionary>() ? jdict(kv.second.UncheckedGet<VtDictionary>()) :
		                                                            jvalue(kv.second);
		out += (first ? "" : ", ") + jstr(kv.first) + ": " + v;
		first = false;
	}
	return out + "}";
}

bool dump(const char *plugin_dir, const char *path, const char *json, std::string &r_error)
{
	if (!brb::usd::start(plugin_dir ? plugin_dir : "", r_error))
		return false;
	std::error_code ec;
	if (!path || !std::filesystem::exists(std::filesystem::u8path(path), ec)) {
		r_error = std::string("no such file: ") + (path ? path : "");
		return false;
	}
	TfErrorMark mark;
	UsdStageRefPtr stage = UsdStage::Open(path);
	std::string errors = "[";
	bool first_error = true;
	for (const TfError &e : mark) {
		errors += (first_error ? "" : ", ") + jstr(e.GetCommentary());
		first_error = false;
	}
	errors += "]";
	mark.Clear();
	if (!stage) {
		r_error = std::string("OpenUSD could not open ") + path;
		return false;
	}
	std::string o = "{\"ok\": true, \"meters_per_unit\": " + jnum(UsdGeomGetStageMetersPerUnit(stage)) +
	                ", \"up_axis\": " + jstr(UsdGeomGetStageUpAxis(stage).GetString()) +
	                ", \"default_prim\": " + jstr(stage->GetDefaultPrim() ? stage->GetDefaultPrim().GetName().GetString() :
	                                                                         std::string()) +
	                ", \"custom_layer_data\": " + jdict(stage->GetRootLayer()->GetCustomLayerData()) +
	                ", \"errors\": " + errors + ",\n \"prims\": [";
	UsdGeomXformCache xf;
	bool first = true;
	for (const UsdPrim &prim : stage->TraverseAll()) {
		std::string p = "{\"path\": " + jstr(prim.GetPath().GetString()) + ", \"type\": " +
		                jstr(prim.GetTypeName().GetString()) + ", \"active\": " + (prim.IsActive() ? "true" : "false") +
		                ", \"defined\": " + (prim.IsDefined() ? "true" : "false");
		/* the references and API schemas as written */
		std::string refs = "[";
		bool rfirst = true;
		bool explicit_refs = false;
		for (const SdfPrimSpecHandle &spec : prim.GetPrimStack()) {
			if (!spec || !spec->HasReferences())
				continue;
			if (spec->GetReferenceList().IsExplicit())
				explicit_refs = true;
			for (const SdfReference &r : spec->GetReferenceList().GetAppliedItems()) {
				refs += (rfirst ? "" : ", ") + jstr(r.GetAssetPath() + "<" + r.GetPrimPath().GetString() + ">");
				rfirst = false;
			}
		}
		p += ", \"references\": " + refs + "], \"explicit_references\": " + (explicit_refs ? "true" : "false");
		std::string schemas = "[";
		bool sfirst = true;
		for (const TfToken &t : prim.GetAppliedSchemas()) {
			schemas += (sfirst ? "" : ", ") + jstr(t.GetString());
			sfirst = false;
		}
		p += ", \"api\": " + schemas + "]";
		if (prim.IsA<UsdGeomXformable>())
			p += ", \"local_to_world\": " + jmatrix(xf.GetLocalToWorldTransform(prim));
		p += ", \"attrs\": {";
		bool afirst = true;
		for (const UsdAttribute &a : prim.GetAuthoredAttributes()) {
			VtValue v;
			a.Get(&v);
			p += (afirst ? "" : ", ") + jstr(a.GetName().GetString()) + ": {\"type\": " +
			     jstr(a.GetTypeName().GetAsToken().GetString()) + ", \"value\": " + jvalue(v) + "}";
			afirst = false;
		}
		p += "}, \"rels\": {";
		bool lfirst = true;
		for (const UsdRelationship &r : prim.GetAuthoredRelationships()) {
			SdfPathVector targets;
			r.GetTargets(&targets);
			std::string t = "[";
			for (size_t i = 0; i < targets.size(); i++)
				t += (i ? ", " : "") + jstr(targets[i].GetString());
			p += (lfirst ? "" : ", ") + jstr(r.GetName().GetString()) + ": " + t + "]";
			lfirst = false;
		}
		p += "}}";
		o += (first ? "\n  " : ",\n  ") + p;
		first = false;
	}
	o += "]}\n";
	FILE *f = nullptr;
#ifdef _WIN32
	{
		std::filesystem::path out = std::filesystem::u8path(json);
		f = _wfopen(out.c_str(), L"wb");
	}
#else
	f = fopen(json, "wb");
#endif
	if (!f) {
		r_error = std::string("could not write ") + json;
		return false;
	}
	fwrite(o.data(), 1, o.size(), f);
	fclose(f);
	return true;
}

}  // namespace

BRU_API int bru_stage_dump(const char *plugin_dir, const char *path, const char *json, char *r_error, int max_bytes)
{
	std::string err;
	bool ok = false;
	try {
		ok = dump(plugin_dir, path, json, err);
	}
	catch (const std::exception &e) {
		err = std::string("reading the stage failed: ") + e.what();
	}
	catch (...) {
		err = "reading the stage failed";
	}
	if (r_error && max_bytes > 0)
		snprintf(r_error, size_t(max_bytes), "%s", err.c_str());
	return ok ? 1 : 0;
}
