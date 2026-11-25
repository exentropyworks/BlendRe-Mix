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

/** \file usd_skel.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12 round 8: a stage's skeletons (UsdSkel) as JSON, for File >
 * Import > Universal Scene Description (bge_remix_usd.h bru_scene_api
 * skeletons), read with OpenUSD's own skeleton reader (UsdSkelCache,
 * UsdSkelSkeletonQuery, UsdSkelSkinningQuery): every skeleton (its joints
 * in order, their parents, bind and rest transforms in the skeleton's
 * space, the animation bound to it), every skinned mesh (its joint
 * influences, geometry bind transform, skinning method, blend shapes),
 * every SkelAnimation (its joints and time samples), the stage's frame
 * range and rate. And OpenUSD's own skinning of a mesh at a time, in the
 * world (Skel::skinned_points), the reference the tests hold Blender's
 * deformed meshes to.
 */

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "pxr/pxr.h"
#include "pxr/base/gf/matrix4d.h"
#include "pxr/usd/usd/primRange.h"
#include "pxr/usd/usd/stage.h"
#include "pxr/usd/usdGeom/mesh.h"
#include "pxr/usd/usdGeom/xformCache.h"
#include "pxr/usd/usdSkel/animation.h"
#include "pxr/usd/usdSkel/binding.h"
#include "pxr/usd/usdSkel/bindingAPI.h"
#include "pxr/usd/usdSkel/cache.h"
#include "pxr/usd/usdSkel/root.h"
#include "pxr/usd/usdSkel/skeleton.h"
#include "pxr/usd/usdSkel/skeletonQuery.h"
#include "pxr/usd/usdSkel/skinningQuery.h"
#include "pxr/usd/usdSkel/topology.h"

#include "usd_read.h"

PXR_NAMESPACE_USING_DIRECTIVE

namespace brb {
namespace usd {

struct Skel::Impl {
	UsdStageRefPtr stage;
	UsdSkelCache cache;
	/* a skinned mesh's path: its skeleton and skinning queries */
	std::map<SdfPath, std::pair<UsdSkelSkeletonQuery, UsdSkelSkinningQuery>> skinned;
};

namespace {

std::string js(const std::string &s)
{
	std::string o = "\"";
	for (char c : s) {
		if (c == '"' || c == '\\')
			o += '\\';
		if (c == '\n') {
			o += "\\n";
			continue;
		}
		o += c;
	}
	return o + "\"";
}

std::string jn(double v)
{
	if (!std::isfinite(v))
		return "null";
	char buf[64];
	snprintf(buf, sizeof(buf), "%.9g", v);
	return buf;
}

std::string jtokens(const VtTokenArray &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++)
		o += (i ? ", " : "") + js(v[i].GetString());
	return o + "]";
}

std::string jmatrices(const VtMatrix4dArray &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++) {
		const double *d = v[i].GetArray();
		for (int k = 0; k < 16; k++)
			o += ((i || k) ? ", " : "") + jn(d[k]);
	}
	return o + "]";
}

std::string jm(const GfMatrix4d &m)
{
	VtMatrix4dArray a(1, m);
	return jmatrices(a);
}

template<typename T> std::string jflat(const VtArray<T> &v, int width)
{
	std::string o = "[";
	bool first = true;
	for (const T &x : v) {
		for (int k = 0; k < width; k++) {
			o += (first ? "" : ", ") + jn(double(x[k]));
			first = false;
		}
	}
	return o + "]";
}

std::string jints(const VtIntArray &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++)
		o += (i ? ", " : "") + std::to_string(v[i]);
	return o + "]";
}

std::string jfloats(const VtFloatArray &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++)
		o += (i ? ", " : "") + jn(v[i]);
	return o + "]";
}

std::string list(const std::vector<std::string> &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++)
		o += std::string(i ? ",\n  " : "\n  ") + v[i];
	return o + "]";
}

/* a SkelAnimation's joints and samples, w x y z for the rotations */
std::string animation_json(const UsdSkelAnimation &anim)
{
	VtTokenArray joints;
	anim.GetJointsAttr().Get(&joints);
	std::vector<double> times;
	anim.GetTranslationsAttr().GetTimeSamples(&times);
	std::vector<double> more;
	anim.GetRotationsAttr().GetTimeSamples(&more);
	times.insert(times.end(), more.begin(), more.end());
	anim.GetScalesAttr().GetTimeSamples(&more);
	times.insert(times.end(), more.begin(), more.end());
	std::sort(times.begin(), times.end());
	times.erase(std::unique(times.begin(), times.end()), times.end());
	bool timed = !times.empty();
	if (!timed)
		times.push_back(UsdTimeCode::Default().GetValue());
	std::string ts = "[", tr = "[", ro = "[", sc = "[";
	for (size_t i = 0; i < times.size(); i++) {
		const UsdTimeCode t = timed ? UsdTimeCode(times[i]) : UsdTimeCode::Default();
		VtVec3fArray tv;
		VtQuatfArray rv;
		VtVec3hArray sv;
		anim.GetTranslationsAttr().Get(&tv, t);
		anim.GetRotationsAttr().Get(&rv, t);
		anim.GetScalesAttr().Get(&sv, t);
		std::string r = "[";
		for (size_t k = 0; k < rv.size(); k++) {
			const GfVec3f &im = rv[k].GetImaginary();
			r += (k ? ", " : "") + jn(rv[k].GetReal()) + ", " + jn(im[0]) + ", " + jn(im[1]) + ", " + jn(im[2]);
		}
		r += "]";
		std::string s = "[";
		for (size_t k = 0; k < sv.size(); k++)
			s += (k ? ", " : "") + jn(double(sv[k][0])) + ", " + jn(double(sv[k][1])) + ", " + jn(double(sv[k][2]));
		s += "]";
		ts += (i ? ", " : "") + (timed ? jn(times[i]) : std::string("null"));
		tr += std::string(i ? ", " : "") + jflat(tv, 3);
		ro += std::string(i ? ", " : "") + r;
		sc += std::string(i ? ", " : "") + s;
	}
	VtTokenArray shapes;
	anim.GetBlendShapesAttr().Get(&shapes);
	return "{\"path\": " + js(anim.GetPath().GetString()) + ", \"joints\": " + jtokens(joints) + ", \"times\": " + ts +
	       "], \"translations\": " + tr + "], \"rotations\": " + ro + "], \"scales\": " + sc +
	       "], \"blend_shapes\": " + jtokens(shapes) + "}";
}

}  // namespace

Skel::Skel() : impl(new Impl()) {}
Skel::~Skel() = default;

std::string Skel::read(const UsdStageRefPtr &stage, double time, std::string &r_notes)
{
	impl->stage = stage;
	const UsdTimeCode t(time);
	UsdGeomXformCache xf(t);
	std::vector<std::string> skels, skins, anims;
	const auto pred = UsdTraverseInstanceProxies(UsdPrimDefaultPredicate);
	std::map<SdfPath, bool> seen_skel;
	for (const UsdPrim &p : UsdPrimRange(stage->GetPseudoRoot(), pred)) {
		if (p.IsA<UsdSkelAnimation>()) {
			anims.push_back(animation_json(UsdSkelAnimation(p)));
			continue;
		}
		if (!p.IsA<UsdSkelRoot>())
			continue;
		UsdSkelRoot root(p);
		impl->cache.Populate(root, pred);
		std::vector<UsdSkelBinding> bindings;
		impl->cache.ComputeSkelBindings(root, &bindings, pred);
		/* skeletons under the root with nothing bound to them too */
		for (const UsdPrim &q : UsdPrimRange(p, pred)) {
			if (q.IsA<UsdSkelSkeleton>()) {
				bool bound = false;
				for (const UsdSkelBinding &b : bindings)
					bound = bound || b.GetSkeleton().GetPrim() == q;
				if (!bound)
					bindings.push_back(UsdSkelBinding(UsdSkelSkeleton(q), VtArray<UsdSkelSkinningQuery>()));
			}
		}
		for (const UsdSkelBinding &b : bindings) {
			const UsdSkelSkeleton &skel = b.GetSkeleton();
			UsdSkelSkeletonQuery sq = impl->cache.GetSkelQuery(skel);
			if (!sq) {
				r_notes += "skeleton " + skel.GetPath().GetString() + ": OpenUSD could not read it: left out\n";
				continue;
			}
			if (!seen_skel[skel.GetPath()]) {
				seen_skel[skel.GetPath()] = true;
				std::string problem;
				const bool valid = sq.GetTopology().Validate(&problem);
				VtMatrix4dArray bind, rest;
				sq.GetJointWorldBindTransforms(&bind);
				sq.ComputeJointLocalTransforms(&rest, t, true);
				VtIntArray parents(sq.GetTopology().GetParentIndices().begin(),
				                   sq.GetTopology().GetParentIndices().end());
				const UsdPrim anim = sq.GetAnimQuery() ? sq.GetAnimQuery().GetPrim() : UsdPrim();
				skels.push_back("{\"path\": " + js(skel.GetPath().GetString()) + ", \"root\": " +
				                js(p.GetPath().GetString()) + ", \"joints\": " + jtokens(sq.GetJointOrder()) +
				                ", \"parents\": " + jints(parents) + ", \"bind\": " + jmatrices(bind) +
				                ", \"rest\": " + jmatrices(rest) + ", \"has_bind\": " +
				                (sq.HasBindPose() ? "true" : "false") + ", \"has_rest\": " +
				                (sq.HasRestPose() ? "true" : "false") + ", \"animation\": " +
				                js(anim ? anim.GetPath().GetString() : std::string()) + ", \"world\": " +
				                jm(xf.GetLocalToWorldTransform(skel.GetPrim())) + ", \"valid\": " +
				                (valid ? "true" : "false") + ", \"problem\": " + js(problem) + "}");
			}
			for (const UsdSkelSkinningQuery &q : b.GetSkinningTargets()) {
				const UsdPrim mesh = q.GetPrim();
				if (!mesh.IsA<UsdGeomMesh>()) {
					r_notes += mesh.GetPath().GetString() + ": a skinned " + mesh.GetTypeName().GetString() +
					           ": only meshes are skinned here\n";
					continue;
				}
				impl->skinned[mesh.GetPath()] = std::make_pair(sq, q);
				VtIntArray idx;
				VtFloatArray w;
				q.ComputeJointInfluences(&idx, &w, t);
				VtTokenArray order;
				q.GetJointOrder(&order);
				skins.push_back("{\"path\": " + js(mesh.GetPath().GetString()) + ", \"skeleton\": " +
				                js(skel.GetPath().GetString()) + ", \"joints\": " + jtokens(order) +
				                ", \"interpolation\": " + js(q.GetInterpolation().GetString()) +
				                ", \"element_size\": " + std::to_string(q.GetNumInfluencesPerComponent()) +
				                ", \"indices\": " + jints(idx) + ", \"weights\": " + jfloats(w) + ", \"geom_bind\": " +
				                jm(q.GetGeomBindTransform(t)) + ", \"method\": " + js(q.GetSkinningMethod().GetString()) +
				                ", \"blend_shapes\": " + (q.HasBlendShapes() ? "true" : "false") + ", \"rigid\": " +
				                (q.IsRigidlyDeformed() ? "true" : "false") + "}");
			}
		}
	}
	return "{\"skeletons\": " + list(skels) + ",\n \"skinned\": " + list(skins) + ",\n \"animations\": " +
	       list(anims) + ",\n \"time\": {\"start\": " + jn(stage->GetStartTimeCode()) + ", \"end\": " +
	       jn(stage->GetEndTimeCode()) + ", \"fps\": " + jn(stage->GetTimeCodesPerSecond()) + ", \"authored\": " +
	       (stage->HasAuthoredTimeCodeRange() ? "true" : "false") + "}}";
}

int Skel::skinned_points(const char *mesh_path, double time, float *r_points, int max_points) const
{
	if (!mesh_path || !SdfPath::IsValidPathString(mesh_path))
		return -1;
	auto it = impl->skinned.find(SdfPath(mesh_path));
	if (it == impl->skinned.end())
		return -1;
	const UsdSkelSkeletonQuery &sq = it->second.first;
	const UsdSkelSkinningQuery &q = it->second.second;
	const UsdTimeCode t(time);
	VtMatrix4dArray xforms;
	if (!sq.ComputeSkinningTransforms(&xforms, t))
		return -1;
	VtVec3fArray points;
	UsdGeomMesh(q.GetPrim()).GetPointsAttr().Get(&points, t);
	if (!q.ComputeSkinnedPoints(xforms, &points, t))
		return -1;
	/* skinned points are in the skeleton's space */
	UsdGeomXformCache xf(t);
	const GfMatrix4d world = xf.GetLocalToWorldTransform(sq.GetPrim());
	const int n = int(points.size());
	for (int i = 0; i < n && i < max_points; i++) {
		const GfVec3d p = world.Transform(GfVec3d(points[size_t(i)]));
		for (int k = 0; k < 3; k++)
			r_points[i * 3 + k] = float(p[k]);
	}
	return n;
}

}  // namespace usd
}  // namespace brb
