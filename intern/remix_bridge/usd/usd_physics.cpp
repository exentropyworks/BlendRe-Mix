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

/** \file usd_physics.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12 round 7: a stage's physics (UsdPhysics) as JSON, for File >
 * Import > Universal Scene Description (bge_remix_usd.h bru_scene_api
 * physics). Read with OpenUSD's own physics reader (usdPhysics/parseUtils:
 * UsdPhysicsLoadUsdPhysicsFromRange, the one PhysX tools use): the scene,
 * rigid bodies, shapes, joints, physics materials, articulations, collision
 * groups. With it, what the reader leaves to the caller: each body's and
 * collider's MassAPI, each joint's authored frames (localPos/localRot in
 * the prims its relationships name, and those prims' local to world), and
 * every prim's attributes and relationships of our own (bgeRemix:*). All
 * in the stage's own units (metres per unit, kilograms per unit, degrees).
 */

#include <cmath>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

#include "pxr/pxr.h"
#include "pxr/base/gf/matrix4d.h"
#include "pxr/base/gf/quatf.h"
#include "pxr/base/vt/types.h"
#include "pxr/usd/usd/primRange.h"
#include "pxr/usd/usd/relationship.h"
#include "pxr/usd/usd/stage.h"
#include "pxr/usd/usdGeom/xformCache.h"
#include "pxr/usd/usdPhysics/joint.h"
#include "pxr/usd/usdPhysics/massAPI.h"
#include "pxr/usd/usdPhysics/metrics.h"
#include "pxr/usd/usdPhysics/parseDesc.h"
#include "pxr/usd/usdPhysics/parseUtils.h"

#include "bge_remix_usd.h"
#include "usd_read.h"

PXR_NAMESPACE_USING_DIRECTIVE

namespace brb {
namespace usd {

namespace {

std::string js(const std::string &s)
{
	std::string o = "\"";
	for (char c : s) {
		switch (c) {
			case '"': o += "\\\""; break;
			case '\\': o += "\\\\"; break;
			case '\n': o += "\\n"; break;
			case '\r': o += "\\r"; break;
			case '\t': o += "\\t"; break;
			default:
				if ((unsigned char)c < 0x20) {
					char buf[8];
					snprintf(buf, sizeof(buf), "\\u%04x", c);
					o += buf;
				}
				else {
					o += c;
				}
		}
	}
	return o + "\"";
}

std::string jn(double v)
{
	if (!std::isfinite(v))
		return v > 0 ? "1e300" : (v < 0 ? "-1e300" : "null");
	char buf[64];
	snprintf(buf, sizeof(buf), "%.9g", v);
	return buf;
}

std::string jb(bool b)
{
	return b ? "true" : "false";
}

std::string jv3(const GfVec3f &v)
{
	return "[" + jn(v[0]) + ", " + jn(v[1]) + ", " + jn(v[2]) + "]";
}

/* w, x, y, z */
std::string jq(const GfQuatf &q)
{
	const GfVec3f &i = q.GetImaginary();
	return "[" + jn(q.GetReal()) + ", " + jn(i[0]) + ", " + jn(i[1]) + ", " + jn(i[2]) + "]";
}

std::string jm(const GfMatrix4d &m)
{
	std::string o = "[";
	const double *d = m.GetArray();
	for (int i = 0; i < 16; i++)
		o += (i ? ", " : "") + jn(d[i]);
	return o + "]";
}

std::string jpaths(const SdfPathVector &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++)
		o += (i ? ", " : "") + js(v[i].GetString());
	return o + "]";
}

const char *axis_name(UsdPhysicsAxis a)
{
	return a == UsdPhysicsAxis::X ? "X" : (a == UsdPhysicsAxis::Y ? "Y" : "Z");
}

const char *dof_name(UsdPhysicsJointDOF d)
{
	switch (d) {
		case UsdPhysicsJointDOF::Distance: return "distance";
		case UsdPhysicsJointDOF::TransX: return "transX";
		case UsdPhysicsJointDOF::TransY: return "transY";
		case UsdPhysicsJointDOF::TransZ: return "transZ";
		case UsdPhysicsJointDOF::RotX: return "rotX";
		case UsdPhysicsJointDOF::RotY: return "rotY";
		case UsdPhysicsJointDOF::RotZ: return "rotZ";
	}
	return "?";
}

std::string jlimit(const UsdPhysicsJointLimit &l)
{
	return "{\"enabled\": " + jb(l.enabled) + ", \"lower\": " + jn(l.lower) + ", \"upper\": " + jn(l.upper) + "}";
}

std::string jdrive(const UsdPhysicsJointDrive &d)
{
	return "{\"enabled\": " + jb(d.enabled) + ", \"target_position\": " + jn(d.targetPosition) +
	       ", \"target_velocity\": " + jn(d.targetVelocity) + ", \"force_limit\": " + jn(d.forceLimit) +
	       ", \"stiffness\": " + jn(d.stiffness) + ", \"damping\": " + jn(d.damping) + ", \"acceleration\": " +
	       jb(d.acceleration) + "}";
}

/* a value of ours (bgeRemix:*) as JSON */
std::string jvalue(const UsdAttribute &attr, double time)
{
	VtValue v;
	if (!attr.Get(&v, UsdTimeCode(time)) || v.IsEmpty())
		return "null";
	if (v.IsHolding<float>())
		return jn(v.UncheckedGet<float>());
	if (v.IsHolding<double>())
		return jn(v.UncheckedGet<double>());
	if (v.IsHolding<int>())
		return std::to_string(v.UncheckedGet<int>());
	if (v.IsHolding<bool>())
		return jb(v.UncheckedGet<bool>());
	if (v.IsHolding<std::string>())
		return js(v.UncheckedGet<std::string>());
	if (v.IsHolding<TfToken>())
		return js(v.UncheckedGet<TfToken>().GetString());
	if (v.IsHolding<GfVec3f>())
		return jv3(v.UncheckedGet<GfVec3f>());
	if (v.IsHolding<GfVec3d>()) {
		const GfVec3d &d = v.UncheckedGet<GfVec3d>();
		return "[" + jn(d[0]) + ", " + jn(d[1]) + ", " + jn(d[2]) + "]";
	}
	if (v.IsHolding<VtFloatArray>()) {
		std::string o = "[";
		const VtFloatArray &a = v.UncheckedGet<VtFloatArray>();
		for (size_t i = 0; i < a.size(); i++)
			o += (i ? ", " : "") + jn(a[i]);
		return o + "]";
	}
	/* (round 8) the bones' names, lengths and switches */
	if (v.IsHolding<VtIntArray>()) {
		std::string o = "[";
		const VtIntArray &a = v.UncheckedGet<VtIntArray>();
		for (size_t i = 0; i < a.size(); i++)
			o += (i ? ", " : "") + std::to_string(a[i]);
		return o + "]";
	}
	if (v.IsHolding<VtStringArray>()) {
		std::string o = "[";
		const VtStringArray &a = v.UncheckedGet<VtStringArray>();
		for (size_t i = 0; i < a.size(); i++)
			o += (i ? ", " : "") + js(a[i]);
		return o + "]";
	}
	if (v.IsHolding<VtTokenArray>()) {
		std::string o = "[";
		const VtTokenArray &a = v.UncheckedGet<VtTokenArray>();
		for (size_t i = 0; i < a.size(); i++)
			o += (i ? ", " : "") + js(a[i].GetString());
		return o + "]";
	}
	return "null";
}

struct Collect {
	std::vector<std::string> scenes, bodies, shapes, materials, joints, articulations, groups;
	UsdStageRefPtr stage;
	UsdGeomXformCache *xf = nullptr;
	double time = 0.0;
};

std::string mass_of(const UsdPrim &prim, double time)
{
	if (!prim || !prim.HasAPI<UsdPhysicsMassAPI>())
		return "\"mass\": null, \"density\": null";
	UsdPhysicsMassAPI m(prim);
	float mass = 0.0f, density = 0.0f;
	const bool has_mass = m.GetMassAttr().HasAuthoredValue() && m.GetMassAttr().Get(&mass, UsdTimeCode(time));
	const bool has_density = m.GetDensityAttr().HasAuthoredValue() &&
	                         m.GetDensityAttr().Get(&density, UsdTimeCode(time));
	return std::string("\"mass\": ") + (has_mass && mass > 0.0f ? jn(mass) : "null") + ", \"density\": " +
	       (has_density && density > 0.0f ? jn(density) : "null");
}

std::string shape_json(Collect &c, const SdfPath &path, const UsdPhysicsShapeDesc &s, const char *kind,
                       const std::string &extra)
{
	const UsdPrim prim = c.stage->GetPrimAtPath(path);
	return "{\"path\": " + js(path.GetString()) + ", \"kind\": " + js(kind) + ", \"body\": " +
	       js(s.rigidBody.GetString()) + ", \"local_pos\": " + jv3(s.localPos) + ", \"local_rot\": " +
	       jq(s.localRot) + ", \"local_scale\": " + jv3(s.localScale) + ", \"materials\": " + jpaths(s.materials) +
	       ", \"collision_enabled\": " + jb(s.collisionEnabled) + ", \"groups\": " + jpaths(s.collisionGroups) +
	       ", \"filtered\": " + jpaths(s.filteredCollisions) + ", " + mass_of(prim, c.time) +
	       (extra.empty() ? "" : ", " + extra) + "}";
}

std::string joint_base(Collect &c, const SdfPath &path, const UsdPhysicsJointDesc &j, const char *kind)
{
	const UsdPrim prim = c.stage->GetPrimAtPath(path);
	UsdPhysicsJoint joint(prim);
	const UsdTimeCode t(c.time);
	GfVec3f p0(0.0f), p1(0.0f);
	GfQuatf r0(1.0f), r1(1.0f);
	joint.GetLocalPos0Attr().Get(&p0, t);
	joint.GetLocalPos1Attr().Get(&p1, t);
	joint.GetLocalRot0Attr().Get(&r0, t);
	joint.GetLocalRot1Attr().Get(&r1, t);
	auto world = [&](const SdfPath &rel) {
		const UsdPrim p = rel.IsEmpty() ? UsdPrim() : c.stage->GetPrimAtPath(rel);
		return p ? jm(c.xf->GetLocalToWorldTransform(p)) : std::string("null");
	};
	return "{\"path\": " + js(path.GetString()) + ", \"kind\": " + js(kind) + ", \"rel0\": " +
	       js(j.rel0.GetString()) + ", \"rel1\": " + js(j.rel1.GetString()) + ", \"body0\": " +
	       js(j.body0.GetString()) + ", \"body1\": " + js(j.body1.GetString()) + ", \"local_pos0\": " + jv3(p0) +
	       ", \"local_rot0\": " + jq(r0) + ", \"local_pos1\": " + jv3(p1) + ", \"local_rot1\": " + jq(r1) +
	       ", \"world0\": " + world(j.rel0) + ", \"world1\": " + world(j.rel1) + ", \"enabled\": " +
	       jb(j.jointEnabled) + ", \"collision_enabled\": " + jb(j.collisionEnabled) + ", \"break_force\": " +
	       jn(j.breakForce) + ", \"break_torque\": " + jn(j.breakTorque) + ", \"exclude_from_articulation\": " +
	       jb(j.excludeFromArticulation);
}

/* the i-th descriptor: the span holds the reported type's own descriptors
 * (a TfSpan of the base type steps by the base's size: never index it) */
template<typename T> const T &at(TfSpan<const UsdPhysicsObjectDesc> descs, size_t i)
{
	return reinterpret_cast<const T *>(descs.data())[i];
}

const UsdPhysicsObjectDesc &desc_at(UsdPhysicsObjectType type, TfSpan<const UsdPhysicsObjectDesc> descs, size_t i)
{
	switch (type) {
		case UsdPhysicsObjectType::Scene: return at<UsdPhysicsSceneDesc>(descs, i);
		case UsdPhysicsObjectType::RigidBody: return at<UsdPhysicsRigidBodyDesc>(descs, i);
		case UsdPhysicsObjectType::SphereShape: return at<UsdPhysicsSphereShapeDesc>(descs, i);
		case UsdPhysicsObjectType::CubeShape: return at<UsdPhysicsCubeShapeDesc>(descs, i);
		case UsdPhysicsObjectType::CapsuleShape: return at<UsdPhysicsCapsuleShapeDesc>(descs, i);
		case UsdPhysicsObjectType::Capsule1Shape: return at<UsdPhysicsCapsule1ShapeDesc>(descs, i);
		case UsdPhysicsObjectType::CylinderShape: return at<UsdPhysicsCylinderShapeDesc>(descs, i);
		case UsdPhysicsObjectType::Cylinder1Shape: return at<UsdPhysicsCylinder1ShapeDesc>(descs, i);
		case UsdPhysicsObjectType::ConeShape: return at<UsdPhysicsConeShapeDesc>(descs, i);
		case UsdPhysicsObjectType::MeshShape: return at<UsdPhysicsMeshShapeDesc>(descs, i);
		case UsdPhysicsObjectType::PlaneShape: return at<UsdPhysicsPlaneShapeDesc>(descs, i);
		case UsdPhysicsObjectType::CustomShape: return at<UsdPhysicsCustomShapeDesc>(descs, i);
		case UsdPhysicsObjectType::SpherePointsShape: return at<UsdPhysicsSpherePointsShapeDesc>(descs, i);
		case UsdPhysicsObjectType::FixedJoint: return at<UsdPhysicsFixedJointDesc>(descs, i);
		case UsdPhysicsObjectType::RevoluteJoint: return at<UsdPhysicsRevoluteJointDesc>(descs, i);
		case UsdPhysicsObjectType::PrismaticJoint: return at<UsdPhysicsPrismaticJointDesc>(descs, i);
		case UsdPhysicsObjectType::SphericalJoint: return at<UsdPhysicsSphericalJointDesc>(descs, i);
		case UsdPhysicsObjectType::DistanceJoint: return at<UsdPhysicsDistanceJointDesc>(descs, i);
		case UsdPhysicsObjectType::D6Joint: return at<UsdPhysicsD6JointDesc>(descs, i);
		case UsdPhysicsObjectType::CustomJoint: return at<UsdPhysicsCustomJointDesc>(descs, i);
		case UsdPhysicsObjectType::RigidBodyMaterial: return at<UsdPhysicsRigidBodyMaterialDesc>(descs, i);
		case UsdPhysicsObjectType::Articulation: return at<UsdPhysicsArticulationDesc>(descs, i);
		case UsdPhysicsObjectType::CollisionGroup: return at<UsdPhysicsCollisionGroupDesc>(descs, i);
		default: break;
	}
	return descs[i];
}

void report(Collect &c, UsdPhysicsObjectType type, TfSpan<const SdfPath> paths,
            TfSpan<const UsdPhysicsObjectDesc> descs)
{
	switch (type) {
		case UsdPhysicsObjectType::Undefined:
		case UsdPhysicsObjectType::Last:
			return;
		default:
			break;
	}
	for (size_t i = 0; i < paths.size(); i++) {
		const SdfPath &path = paths[i];
		const UsdPhysicsObjectDesc &d = desc_at(type, descs, i);
		if (!d.isValid)
			continue;
		switch (type) {
			case UsdPhysicsObjectType::Scene: {
				const auto &s = static_cast<const UsdPhysicsSceneDesc &>(d);
				c.scenes.push_back("{\"path\": " + js(path.GetString()) + ", \"gravity_direction\": " +
				                   jv3(s.gravityDirection) + ", \"gravity_magnitude\": " + jn(s.gravityMagnitude) +
				                   "}");
				break;
			}
			case UsdPhysicsObjectType::RigidBody: {
				const auto &b = static_cast<const UsdPhysicsRigidBodyDesc &>(d);
				c.bodies.push_back("{\"path\": " + js(path.GetString()) + ", \"enabled\": " + jb(b.rigidBodyEnabled) +
				                   ", \"kinematic\": " + jb(b.kinematicBody) + ", \"collisions\": " +
				                   jpaths(b.collisions) + ", \"filtered\": " + jpaths(b.filteredCollisions) +
				                   ", \"velocity\": " + jv3(b.linearVelocity) + ", \"angular_velocity\": " +
				                   jv3(b.angularVelocity) + ", " + mass_of(c.stage->GetPrimAtPath(path), c.time) + "}");
				break;
			}
			case UsdPhysicsObjectType::SphereShape: {
				const auto &s = static_cast<const UsdPhysicsSphereShapeDesc &>(d);
				c.shapes.push_back(shape_json(c, path, s, "sphere", "\"radius\": " + jn(s.radius)));
				break;
			}
			case UsdPhysicsObjectType::CubeShape: {
				const auto &s = static_cast<const UsdPhysicsCubeShapeDesc &>(d);
				c.shapes.push_back(shape_json(c, path, s, "cube", "\"half_extents\": " + jv3(s.halfExtents)));
				break;
			}
			case UsdPhysicsObjectType::CapsuleShape: {
				const auto &s = static_cast<const UsdPhysicsCapsuleShapeDesc &>(d);
				c.shapes.push_back(shape_json(c, path, s, "capsule", "\"radius\": " + jn(s.radius) +
				                                                      ", \"half_height\": " + jn(s.halfHeight) +
				                                                      ", \"axis\": " + js(axis_name(s.axis))));
				break;
			}
			case UsdPhysicsObjectType::CylinderShape: {
				const auto &s = static_cast<const UsdPhysicsCylinderShapeDesc &>(d);
				c.shapes.push_back(shape_json(c, path, s, "cylinder", "\"radius\": " + jn(s.radius) +
				                                                       ", \"half_height\": " + jn(s.halfHeight) +
				                                                       ", \"axis\": " + js(axis_name(s.axis))));
				break;
			}
			case UsdPhysicsObjectType::ConeShape: {
				const auto &s = static_cast<const UsdPhysicsConeShapeDesc &>(d);
				c.shapes.push_back(shape_json(c, path, s, "cone", "\"radius\": " + jn(s.radius) +
				                                                   ", \"half_height\": " + jn(s.halfHeight) +
				                                                   ", \"axis\": " + js(axis_name(s.axis))));
				break;
			}
			case UsdPhysicsObjectType::MeshShape: {
				const auto &s = static_cast<const UsdPhysicsMeshShapeDesc &>(d);
				c.shapes.push_back(shape_json(c, path, s, "mesh", "\"approximation\": " +
				                                                   js(s.approximation.GetString())));
				break;
			}
			case UsdPhysicsObjectType::Capsule1Shape:
				c.shapes.push_back(shape_json(c, path, static_cast<const UsdPhysicsShapeDesc &>(d), "capsule1", ""));
				break;
			case UsdPhysicsObjectType::Cylinder1Shape:
				c.shapes.push_back(shape_json(c, path, static_cast<const UsdPhysicsShapeDesc &>(d), "cylinder1", ""));
				break;
			case UsdPhysicsObjectType::PlaneShape:
				c.shapes.push_back(shape_json(c, path, static_cast<const UsdPhysicsShapeDesc &>(d), "plane", ""));
				break;
			case UsdPhysicsObjectType::CustomShape:
				c.shapes.push_back(shape_json(c, path, static_cast<const UsdPhysicsShapeDesc &>(d), "custom", ""));
				break;
			case UsdPhysicsObjectType::SpherePointsShape:
				c.shapes.push_back(shape_json(c, path, static_cast<const UsdPhysicsShapeDesc &>(d), "points", ""));
				break;
			case UsdPhysicsObjectType::RigidBodyMaterial: {
				const auto &m = static_cast<const UsdPhysicsRigidBodyMaterialDesc &>(d);
				c.materials.push_back("{\"path\": " + js(path.GetString()) + ", \"static_friction\": " +
				                      jn(m.staticFriction) + ", \"dynamic_friction\": " + jn(m.dynamicFriction) +
				                      ", \"restitution\": " + jn(m.restitution) + ", \"density\": " + jn(m.density) +
				                      "}");
				break;
			}
			case UsdPhysicsObjectType::FixedJoint:
				c.joints.push_back(joint_base(c, path, static_cast<const UsdPhysicsJointDesc &>(d), "fixed") + "}");
				break;
			case UsdPhysicsObjectType::RevoluteJoint: {
				const auto &j = static_cast<const UsdPhysicsRevoluteJointDesc &>(d);
				c.joints.push_back(joint_base(c, path, j, "revolute") + ", \"axis\": " + js(axis_name(j.axis)) +
				                   ", \"limit\": " + jlimit(j.limit) + ", \"drive\": " + jdrive(j.drive) + "}");
				break;
			}
			case UsdPhysicsObjectType::PrismaticJoint: {
				const auto &j = static_cast<const UsdPhysicsPrismaticJointDesc &>(d);
				c.joints.push_back(joint_base(c, path, j, "prismatic") + ", \"axis\": " + js(axis_name(j.axis)) +
				                   ", \"limit\": " + jlimit(j.limit) + ", \"drive\": " + jdrive(j.drive) + "}");
				break;
			}
			case UsdPhysicsObjectType::SphericalJoint: {
				const auto &j = static_cast<const UsdPhysicsSphericalJointDesc &>(d);
				c.joints.push_back(joint_base(c, path, j, "spherical") + ", \"axis\": " + js(axis_name(j.axis)) +
				                   ", \"limit\": " + jlimit(j.limit) + "}");
				break;
			}
			case UsdPhysicsObjectType::DistanceJoint: {
				const auto &j = static_cast<const UsdPhysicsDistanceJointDesc &>(d);
				c.joints.push_back(joint_base(c, path, j, "distance") + ", \"limit\": " + jlimit(j.limit) + "}");
				break;
			}
			case UsdPhysicsObjectType::D6Joint: {
				const auto &j = static_cast<const UsdPhysicsD6JointDesc &>(d);
				std::string limits = "{", drives = "{";
				for (size_t k = 0; k < j.jointLimits.size(); k++)
					limits += std::string(k ? ", " : "") + js(dof_name(j.jointLimits[k].first)) + ": " +
					          jlimit(j.jointLimits[k].second);
				for (size_t k = 0; k < j.jointDrives.size(); k++)
					drives += std::string(k ? ", " : "") + js(dof_name(j.jointDrives[k].first)) + ": " +
					          jdrive(j.jointDrives[k].second);
				c.joints.push_back(joint_base(c, path, j, "d6") + ", \"limits\": " + limits + "}, \"drives\": " +
				                   drives + "}}");
				break;
			}
			case UsdPhysicsObjectType::CustomJoint:
				c.joints.push_back(joint_base(c, path, static_cast<const UsdPhysicsJointDesc &>(d), "custom") + "}");
				break;
			case UsdPhysicsObjectType::Articulation: {
				const auto &a = static_cast<const UsdPhysicsArticulationDesc &>(d);
				c.articulations.push_back("{\"path\": " + js(path.GetString()) + ", \"roots\": " +
				                          jpaths(a.rootPrims) + ", \"bodies\": " + jpaths(a.articulatedBodies) +
				                          ", \"joints\": " + jpaths(a.articulatedJoints) + "}");
				break;
			}
			case UsdPhysicsObjectType::CollisionGroup: {
				const auto &g = static_cast<const UsdPhysicsCollisionGroupDesc &>(d);
				c.groups.push_back("{\"path\": " + js(path.GetString()) + ", \"filtered\": " +
				                   jpaths(g.filteredGroups) + ", \"invert\": " + jb(g.invertFilteredGroups) + "}");
				break;
			}
			default:
				break;
		}
	}
}

std::string list(const std::vector<std::string> &v)
{
	std::string o = "[";
	for (size_t i = 0; i < v.size(); i++)
		o += std::string(i ? ",\n  " : "\n  ") + v[i];
	return o + "]";
}

}  // namespace

std::string physics_json(const UsdStageRefPtr &stage, double time, std::string &r_notes)
{
	Collect c;
	c.stage = stage;
	c.time = time;
	const UsdTimeCode t(time);
	UsdGeomXformCache xf(t);
	c.xf = &xf;
	const bool ok = LoadUsdPhysicsFromRange(
	    stage, {SdfPath::AbsoluteRootPath()},
	    [&](UsdPhysicsObjectType type, TfSpan<const SdfPath> paths, TfSpan<const UsdPhysicsObjectDesc> descs,
	        const VtValue &) { report(c, type, paths, descs); },
	    VtValue());
	if (!ok)
		r_notes += "OpenUSD's physics reader could not read the file's physics\n";

	/* ours: every prim's bgeRemix:* attributes and relationships */
	std::string custom = "{";
	bool first = true;
	for (const UsdPrim &p : UsdPrimRange(stage->GetPseudoRoot(), UsdTraverseInstanceProxies())) {
		std::string fields;
		for (const UsdProperty &prop : p.GetPropertiesInNamespace("bgeRemix")) {
			std::string value;
			if (UsdAttribute a = prop.As<UsdAttribute>()) {
				value = jvalue(a, time);
			}
			else if (UsdRelationship r = prop.As<UsdRelationship>()) {
				SdfPathVector targets;
				r.GetTargets(&targets);
				value = jpaths(targets);
			}
			else {
				continue;
			}
			fields += (fields.empty() ? "" : ", ") + js(prop.GetName().GetString().substr(9)) + ": " + value;
		}
		if (fields.empty())
			continue;
		custom += std::string(first ? "\n  " : ",\n  ") + js(p.GetPath().GetString()) + ": {" + fields + "}";
		first = false;
	}
	custom += "}";

	return "{\"read\": " + jb(ok) + ", \"kilograms_per_unit\": " + jn(UsdPhysicsGetStageKilogramsPerUnit(stage)) +
	       ",\n \"scenes\": " + list(c.scenes) + ",\n \"bodies\": " + list(c.bodies) + ",\n \"shapes\": " +
	       list(c.shapes) + ",\n \"materials\": " + list(c.materials) + ",\n \"joints\": " + list(c.joints) +
	       ",\n \"articulations\": " + list(c.articulations) + ",\n \"groups\": " + list(c.groups) +
	       ",\n \"custom\": " + custom + "}";
}

}  // namespace usd
}  // namespace brb
