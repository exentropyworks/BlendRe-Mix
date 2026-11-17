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

/** \file PxFluids.cpp
 *  \ingroup physphysx
 *
 * BGE-Remix P11 (B3): fluid volumes (PxFluids.h). Floating: each point of a
 * body's collision shapes (a 4 x 4 x 4 grid over each shape, the points
 * inside it) stands for a share of the shape's volume and a cell of its
 * size; the part of the cell under the surface (by the point's height over
 * it, the cell's size across) pushes up with the weight of the fluid it
 * displaces, where the point is. So an upright box floats at exactly the
 * depth its mass gives, and a body tips until it floats as a real one would.
 * Drag: the body's speed against the current falls off as exp(-drag x share
 * x time), its turning too, where share is how much of it is under. Added
 * mass: what floating and the weight do to its speed is shared with half
 * the fluid it displaces.
 */

#include "PxFluids.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <set>

#include "PxPhysicsAPI.h"

#include "PxCharacter.h"
#include "PxPhysicsController.h"
#include "PxPhysicsEnvironment.h"
#include "PxSystem.h"

using namespace physx;

namespace {

/* the Remix View holds a splash's colour this many frames */
const int HOLD = 10;
/* points along each side of a shape's box */
const int GRID = 4;
/* a body crossing the surface faster than this splashes (m/s); not again
 * for a while; at most so many splashes at a time (each lives SPLASH_LIFE) */
const float SPLASH_SPEED = 1.0f;
const double SPLASH_AGAIN = 0.5;
const int SPLASH_MAX = 8;
const double SPLASH_LIFE = 1.2;

PxVec3 newell(const std::vector<PxVec3> &loop)
{
	PxVec3 n(0.0f);
	for (size_t i = 0; i < loop.size(); i++) {
		const PxVec3 &a = loop[i], &b = loop[(i + 1) % loop.size()];
		n.x += (a.y - b.y) * (a.z + b.z);
		n.y += (a.z - b.z) * (a.x + b.x);
		n.z += (a.x - b.x) * (a.y + b.y);
	}
	return n;
}

/* a convex shape's faces in its actor's frame (a box or a convex mesh) */
bool shape_loops(const PxShape *s, std::vector<std::vector<PxVec3> > &loops)
{
	const PxTransform t = s->getLocalPose();
	const PxGeometry &g = s->getGeometry();
	if (g.getType() == PxGeometryType::eCONVEXMESH) {
		const PxConvexMeshGeometry &cg = static_cast<const PxConvexMeshGeometry &>(g);
		const PxConvexMesh *mesh = cg.convexMesh;
		const PxVec3 *verts = mesh->getVertices();
		const PxU8 *index = mesh->getIndexBuffer();
		for (PxU32 i = 0; i < mesh->getNbPolygons(); i++) {
			PxHullPolygon poly;
			if (!mesh->getPolygonData(i, poly) || poly.mNbVerts < 3) {
				continue;
			}
			std::vector<PxVec3> loop;
			for (PxU32 k = 0; k < poly.mNbVerts; k++) {
				loop.push_back(t.transform(cg.scale.transform(verts[index[poly.mIndexBase + k]])));
			}
			loops.push_back(loop);
		}
		return !loops.empty();
	}
	if (g.getType() == PxGeometryType::eBOX) {
		const PxVec3 h = static_cast<const PxBoxGeometry &>(g).halfExtents;
		PxVec3 c[8];
		for (int i = 0; i < 8; i++) {
			c[i] = t.transform(PxVec3((i & 1) ? h.x : -h.x, (i & 2) ? h.y : -h.y, (i & 4) ? h.z : -h.z));
		}
		static const int quads[6][4] = {{0, 2, 6, 4}, {1, 5, 7, 3}, {0, 4, 5, 1}, {2, 3, 7, 6}, {0, 1, 3, 2},
		                                {4, 6, 7, 5}};
		for (const int *q : quads) {
			loops.push_back({c[q[0]], c[q[1]], c[q[2]], c[q[3]]});
		}
		return true;
	}
	return false;
}

/* how far p is outside the part (its planes'; < 0 inside) */
float part_distance(const std::vector<PxPlane> &planes, const PxVec3 &p)
{
	float d = -PX_MAX_F32;
	for (const PxPlane &pl : planes) {
		d = std::max(d, pl.distance(p));
	}
	return d;
}

/* how far p is outside the volume (the nearest part's) */
float volume_distance(const PxFluidVolume *v, const PxVec3 &p)
{
	float d = PX_MAX_F32;
	for (const std::vector<PxPlane> &planes : v->worldPlanes) {
		d = std::min(d, part_distance(planes, p));
	}
	return d;
}

/* the volume where it is now */
void volume_world(PxFluidVolume *v, const PxVec3 &up)
{
	PxRigidActor *actor = v->ctrl ? v->ctrl->GetActor() : NULL;
	if (actor) {
		v->pose = actor->getGlobalPose();
	}
	v->worldPlanes.resize(v->parts.size());
	PxBounds3 local = PxBounds3::empty();
	for (size_t i = 0; i < v->parts.size(); i++) {
		std::vector<PxPlane> &wp = v->worldPlanes[i];
		wp.clear();
		for (const PxPlane &pl : v->parts[i].planes) {
			wp.push_back(pl.transform(v->pose));
		}
		local.include(v->parts[i].bounds);
	}
	v->worldBounds = PxBounds3::transformFast(v->pose, local);
	v->worldCurrent = v->pose.q.rotate(v->current);
	(void)up;
}

/* the actor's shapes and their bounds in its frame */
void shape_signature(PxRigidActor *actor, std::vector<const PxShape *> &r_shapes, std::vector<PxBounds3> &r_bounds)
{
	r_shapes.clear();
	r_bounds.clear();
	const PxU32 n = actor->getNbShapes();
	std::vector<PxShape *> shapes(n);
	if (n) {
		actor->getShapes(shapes.data(), n);
	}
	for (PxShape *s : shapes) {
		r_shapes.push_back(s);
		PxBounds3 b;
		PxGeometryQuery::computeGeomBounds(b, s->getGeometry(), s->getLocalPose(), 0.0f, 1.0f);
		r_bounds.push_back(b);
	}
}

bool same_bounds(const PxBounds3 &a, const PxBounds3 &b)
{
	return (a.minimum - b.minimum).abs().maxElement() < 1e-5f && (a.maximum - b.maximum).abs().maxElement() < 1e-5f;
}

/* the plane of the volume's surface (the one facing up most) */
const PxPlane *volume_top(const PxFluidVolume *v, const PxVec3 &up, const PxVec3 &near)
{
	const PxPlane *best = NULL;
	float best_dist = PX_MAX_F32;
	for (const std::vector<PxPlane> &planes : v->worldPlanes) {
		/* the part nearest to the point, its plane facing up most */
		const float d = part_distance(planes, near);
		if (d > best_dist) {
			continue;
		}
		const PxPlane *top = NULL;
		for (const PxPlane &pl : planes) {
			if (!top || pl.n.dot(up) > top->n.dot(up)) {
				top = &pl;
			}
		}
		if (top) {
			best = top;
			best_dist = d;
		}
	}
	return best;
}

/* grid points over a box (lo..hi) kept by inside(p), each standing for
 * vol / kept */
template<typename Inside>
void grid_samples(const PxTransform &t, const PxVec3 &lo, const PxVec3 &hi, float vol, Inside inside,
                  std::vector<PxFluidSample> &out)
{
	const PxVec3 cell = (hi - lo) * (1.0f / GRID);
	const float h = std::max((cell.x + cell.y + cell.z) / 3.0f, 1e-4f);
	std::vector<PxVec3> kept;
	for (int i = 0; i < GRID; i++) {
		for (int j = 0; j < GRID; j++) {
			for (int k = 0; k < GRID; k++) {
				const PxVec3 p(lo.x + cell.x * (i + 0.5f), lo.y + cell.y * (j + 0.5f), lo.z + cell.z * (k + 0.5f));
				if (inside(p)) {
					kept.push_back(p);
				}
			}
		}
	}
	if (kept.empty()) {
		PxFluidSample s;
		s.p = t.transform((lo + hi) * 0.5f);
		s.w = vol;
		s.h = std::max(std::cbrt(vol), 1e-4f);
		out.push_back(s);
		return;
	}
	for (const PxVec3 &p : kept) {
		PxFluidSample s;
		s.p = t.transform(p);
		s.w = vol / (float)kept.size();
		s.h = h;
		out.push_back(s);
	}
}

}  // namespace

PxFluidVolume::PxFluidVolume()
    : ctrl(NULL),
      type(0),
      density(1000.0f),
      drag(3.0f),
      current(0.0f),
      splashes(true),
      built(false),
      failed(false),
      pose(PxIdentity),
      worldBounds(PxBounds3::empty()),
      worldCurrent(0.0f),
      lastSplash(-1000000)
{
}

/* ------------------------------------------------------------------------- */

void PxPhysicsEnvironment::AddFluidVolume(PxPhysicsController *ctrl, int type, float density, float drag,
                                          const PxVec3 &current, bool splashes)
{
	if (!ctrl) {
		return;
	}
	PxFluidVolume *v = FluidOf(ctrl);
	if (!v) {
		v = new PxFluidVolume();
		v->ctrl = ctrl;
		m_fluids.push_back(v);
	}
	v->type = type;
	v->density = std::max(density, 0.0f);
	v->drag = std::max(drag, 0.0f);
	v->current = current;
	v->splashes = splashes;
	v->built = v->failed = false;
}

bool PxPhysicsEnvironment::BuildFluidVolume(PxFluidVolume *v)
{
	PxRigidActor *actor = v->ctrl ? v->ctrl->GetActor() : NULL;
	if (!actor) {
		return false;  /* (not in the scene yet) */
	}
	v->parts.clear();
	shape_signature(actor, v->shapes, v->shapeBounds);
	const PxU32 n = actor->getNbShapes();
	std::vector<PxShape *> shapes(n);
	if (n) {
		actor->getShapes(shapes.data(), n);
	}
	for (PxShape *s : shapes) {
		PxFluidPart part;
		if (!shape_loops(s, part.loops)) {
			continue;
		}
		part.bounds = PxBounds3::empty();
		PxVec3 centre(0.0f);
		int count = 0;
		for (const std::vector<PxVec3> &loop : part.loops) {
			for (const PxVec3 &p : loop) {
				part.bounds.include(p);
				centre += p;
				count++;
			}
		}
		centre *= 1.0f / (float)std::max(count, 1);
		for (std::vector<PxVec3> &loop : part.loops) {
			PxVec3 nrm = newell(loop);
			if (nrm.magnitude() < 1e-12f) {
				continue;
			}
			nrm.normalize();
			PxVec3 mid(0.0f);
			for (const PxVec3 &p : loop) {
				mid += p;
			}
			mid *= 1.0f / (float)loop.size();
			/* outward (a mirroring scale turns a loop over) */
			if (nrm.dot(mid - centre) < 0.0f) {
				nrm = -nrm;
				std::reverse(loop.begin(), loop.end());
			}
			part.planes.push_back(PxPlane(mid, nrm));
		}
		if (part.planes.size() >= 4) {
			v->parts.push_back(part);
		}
	}
	v->built = true;
	if (v->parts.empty()) {
		v->failed = true;
		PxSystem::WarnOnce("fluid-shape", "a fluid volume needs Box or Convex Hull bounds: it does nothing");
		return false;
	}
	return true;
}

PxFluidVolume *PxPhysicsEnvironment::FluidOf(PHY_IPhysicsController *ctrl) const
{
	for (PxFluidVolume *v : m_fluids) {
		if (v->ctrl == ctrl) {
			return v;
		}
	}
	return NULL;
}

void PxPhysicsEnvironment::FluidRemove(PxPhysicsController *ctrl)
{
	for (size_t i = 0; i < m_fluids.size(); i++) {
		if (m_fluids[i]->ctrl == ctrl) {
			delete m_fluids[i];
			m_fluids.erase(m_fluids.begin() + i);
			break;
		}
	}
	if (m_fluidBodies && !ctrl->GetShard()) {
		if (PxRigidActor *a = ctrl->GetActor()) {
			m_fluidBodies->erase(a);
		}
	}
}

bool PxPhysicsEnvironment::FluidSamples(PxRigidActor *actor, PxFluidBody &b)
{
	b.samples.clear();
	b.shapes.clear();
	b.volume = 0.0f;
	const PxU32 n = actor->getNbShapes();
	std::vector<PxShape *> shapes(n);
	if (n) {
		actor->getShapes(shapes.data(), n);
	}
	for (PxShape *s : shapes) {
		b.shapes.push_back(s);
		const PxTransform t = s->getLocalPose();
		const PxGeometry &g = s->getGeometry();
		switch (g.getType()) {
			case PxGeometryType::eBOX: {
				const PxVec3 h = static_cast<const PxBoxGeometry &>(g).halfExtents;
				const float vol = 8.0f * h.x * h.y * h.z;
				grid_samples(t, -h, h, vol, [](const PxVec3 &) { return true; }, b.samples);
				b.volume += vol;
				break;
			}
			case PxGeometryType::eSPHERE: {
				const float r = static_cast<const PxSphereGeometry &>(g).radius;
				const float vol = 4.0f / 3.0f * PxPi * r * r * r;
				grid_samples(t, PxVec3(-r), PxVec3(r), vol, [r](const PxVec3 &p) { return p.magnitude() <= r; },
				             b.samples);
				b.volume += vol;
				break;
			}
			case PxGeometryType::eCAPSULE: {
				const PxCapsuleGeometry &c = static_cast<const PxCapsuleGeometry &>(g);
				const float r = c.radius, hh = c.halfHeight;
				const float vol = PxPi * r * r * (2.0f * hh) + 4.0f / 3.0f * PxPi * r * r * r;
				grid_samples(t, PxVec3(-hh - r, -r, -r), PxVec3(hh + r, r, r), vol,
				             [r, hh](const PxVec3 &p) {
					             const float x = std::max(std::fabs(p.x) - hh, 0.0f);
					             return x * x + p.y * p.y + p.z * p.z <= r * r;
				             },
				             b.samples);
				b.volume += vol;
				break;
			}
			case PxGeometryType::eCONVEXMESH: {
				const PxConvexMeshGeometry &cg = static_cast<const PxConvexMeshGeometry &>(g);
				const PxConvexMesh *mesh = cg.convexMesh;
				const PxMat33 m = cg.scale.toMat33();
				const float det = std::fabs(m.getDeterminant());
				if (det < 1e-12f) {
					break;
				}
				const PxMat33 inv = m.getInverse();
				PxReal mass;
				PxMat33 inertia;
				PxVec3 com;
				mesh->getMassInformation(mass, inertia, com);
				const float vol = std::fabs(mass) * det;  /* (the mass at density 1) */
				PxBounds3 bounds = PxBounds3::empty();
				const PxVec3 *verts = mesh->getVertices();
				for (PxU32 i = 0; i < mesh->getNbVertices(); i++) {
					bounds.include(m.transform(verts[i]));
				}
				std::vector<PxPlane> planes;
				for (PxU32 i = 0; i < mesh->getNbPolygons(); i++) {
					PxHullPolygon poly;
					if (mesh->getPolygonData(i, poly)) {
						planes.push_back(PxPlane(poly.mPlane[0], poly.mPlane[1], poly.mPlane[2], poly.mPlane[3]));
					}
				}
				grid_samples(t, bounds.minimum, bounds.maximum, vol,
				             [&planes, &inv](const PxVec3 &p) {
					             const PxVec3 q = inv.transform(p);
					             for (const PxPlane &pl : planes) {
						             if (pl.distance(q) > 1e-6f) {
							             return false;
						             }
					             }
					             return true;
				             },
				             b.samples);
				b.volume += vol;
				break;
			}
			default:
				break;  /* (triangle meshes and the rest: no volume) */
		}
	}
	return b.volume > 0.0f;
}

float PxPhysicsEnvironment::FluidShare(const PxFluidVolume *v, PxRigidActor *actor, PxFluidBody &b)
{
	if (b.samples.empty() && !FluidSamples(actor, b)) {
		return 0.0f;
	}
	const PxTransform pose = actor->getGlobalPose();
	float wv = 0.0f;
	for (const PxFluidSample &s : b.samples) {
		const float f = std::min(std::max(0.5f - volume_distance(v, pose.transform(s.p)) / s.h, 0.0f), 1.0f);
		wv += s.w * f;
	}
	return b.volume > 0.0f ? std::min(wv / b.volume, 1.0f) : 0.0f;
}

void PxPhysicsEnvironment::FluidStep(float dt)
{
	if (!m_scene || dt <= 0.0f) {
		return;
	}
	m_fluidTime += dt;
	const PxVec3 grav = m_scene->getGravity();
	const float g = grav.magnitude();
	const PxVec3 up = g > 1e-6f ? -grav / g : PxVec3(0.0f, 0.0f, 1.0f);

	/* the volumes, where they are now */
	std::vector<PxFluidVolume *> live;
	for (PxFluidVolume *v : m_fluids) {
		/* (review R3) its shape changed (rescaled, a new mesh): read again */
		if (v->built && v->ctrl->GetActor()) {
			std::vector<const PxShape *> shapes;
			std::vector<PxBounds3> bounds;
			shape_signature(v->ctrl->GetActor(), shapes, bounds);
			bool same = shapes == v->shapes && bounds.size() == v->shapeBounds.size();
			for (size_t i = 0; same && i < bounds.size(); i++) {
				same = same_bounds(bounds[i], v->shapeBounds[i]);
			}
			if (!same) {
				v->built = v->failed = false;
			}
		}
		if (!v->built) {
			BuildFluidVolume(v);
		}
		if (!v->built || v->failed || !v->ctrl->GetActor()) {
			continue;
		}
		volume_world(v, up);
		v->share.clear();
		live.push_back(v);
	}
	if (live.empty()) {
		return;
	}

	/* the moving bodies (a destructible's pieces share their group's) */
	std::set<PxRigidBody *> bodies;
	for (PxPhysicsController *c : m_controllers) {
		if (c->GetCharacter() || c->GetDeformable() || FluidOf(c)) {
			continue;
		}
		PxRigidBody *b = c->GetBody();
		if (!b || !b->getScene()) {
			continue;
		}
		if (b->getRigidBodyFlags() & PxRigidBodyFlag::eKINEMATIC) {
			continue;
		}
		bodies.insert(b);
	}
	for (auto &it : *m_fluidBodies) {
		it.second.seen = false;
	}

	int live_splashes = 0;
	for (double t : m_splashTimes) {
		live_splashes += (m_fluidTime - t) < SPLASH_LIFE ? 1 : 0;
	}

	for (PxRigidBody *body : bodies) {
		PxFluidBody &fb = (*m_fluidBodies)[body];
		fb.seen = true;
		/* its points again when its shapes changed (a destructible's group) */
		{
			const PxU32 n = body->getNbShapes();
			bool same = n == fb.shapes.size() && !fb.samples.empty();
			if (same) {
				std::vector<PxShape *> shapes(n);
				body->getShapes(shapes.data(), n);
				for (PxU32 i = 0; i < n && same; i++) {
					same = shapes[i] == fb.shapes[i];
				}
			}
			if (!same) {
				FluidSamples(body, fb);
			}
		}
		if (fb.volume <= 0.0f) {
			continue;
		}
		const PxBounds3 bb = body->getWorldBounds();
		const PxTransform pose = body->getGlobalPose();
		const PxVec3 com = pose.transform(body->getCMassLocalPose().p);
		PxVec3 force(0.0f), torque(0.0f), current(0.0f);
		float sub = 0.0f, drag = 0.0f, best_w = 0.0f, displaced = 0.0f;
		PxFluidVolume *best = NULL;
		for (PxFluidVolume *v : live) {
			if (!v->worldBounds.intersects(bb)) {
				continue;
			}
			float wv = 0.0f;
			for (const PxFluidSample &s : fb.samples) {
				const PxVec3 p = pose.transform(s.p);
				const float f = std::min(std::max(0.5f - volume_distance(v, p) / s.h, 0.0f), 1.0f);
				if (f <= 0.0f) {
					continue;
				}
				const float w = s.w * f;
				wv += w;
				displaced += v->density * w;
				const PxVec3 F = up * (v->density * g * w);
				force += F;
				torque += (p - com).cross(F);
			}
			if (wv <= 0.0f) {
				continue;
			}
			v->share[body] = std::min(wv / fb.volume, 1.0f);
			sub += wv;
			drag += wv * v->drag;
			current += v->worldCurrent * wv;
			if (wv > best_w) {
				best_w = wv;
				best = v;
			}
		}
		const float share = std::min(sub / fb.volume, 1.0f);
		if (share > 0.0f && best) {
			const PxVec3 vel = body->getLinearVelocity();
			/* a splash: it went in, fast */
			const float down = -vel.dot(up);
			if (fb.sub <= 0.0f && best->splashes && down > SPLASH_SPEED && m_fluidTime - fb.lastSplash > SPLASH_AGAIN &&
			    live_splashes < SPLASH_MAX)
			{
				const PxPlane *top = volume_top(best, up, com);
				PHY_FluidSplash sp;
				PxVec3 at = com;
				if (top) {
					at = com - top->n * top->distance(com);
				}
				sp.point = MT_Vector3(at.x, at.y, at.z);
				sp.up = top ? MT_Vector3(top->n.x, top->n.y, top->n.z) : MT_Vector3(up.x, up.y, up.z);
				const PxVec3 ext = bb.getDimensions();
				sp.size = std::max(std::max(ext.x, ext.y), ext.z);
				sp.speed = down;
				sp.type = best->type;
				m_splashes.push_back(sp);
				m_splashTimes.push_back(m_fluidTime);
				live_splashes++;
				fb.lastSplash = m_fluidTime;
				best->lastSplash = m_fluidFrame;
			}
			/* floating; the water it moves with it (its added mass, half the
			 * fluid it displaces) slows how fast floating and its weight
			 * change its speed, so a light body does not leap out again */
			const float mass = body->getMass();
			const float slow = mass > 0.0f ? mass / (mass + 0.5f * displaced) : 1.0f;
			body->addForce((force + grav * mass) * slow - grav * mass, PxForceMode::eFORCE);
			body->addTorque(torque * slow, PxForceMode::eFORCE);
			/* drag, against the current */
			const float k = drag / fb.volume;
			const float fall = 1.0f - std::exp(-k * dt);
			const PxVec3 cur = current * (1.0f / sub);
			if (body->getConcreteType() == PxConcreteType::eARTICULATION_LINK) {
				/* (review R2) PhysX takes no velocity change on an
				 * articulation's link: the same as an acceleration over the step */
				body->addForce(-(vel - cur) * (fall / dt), PxForceMode::eACCELERATION);
				body->addTorque(-body->getAngularVelocity() * (fall / dt), PxForceMode::eACCELERATION);
			}
			else {
				body->addForce(-(vel - cur) * fall, PxForceMode::eVELOCITY_CHANGE);
				body->addTorque(-body->getAngularVelocity() * fall, PxForceMode::eVELOCITY_CHANGE);
			}
			fb.state = body->getMass() <= best->density * fb.volume ? 1 : 2;
		}
		else {
			fb.state = -1;
		}
		fb.sub = share;
	}
	/* bodies gone or out of the scene */
	for (auto it = m_fluidBodies->begin(); it != m_fluidBodies->end();) {
		if (!it->second.seen) {
			it = m_fluidBodies->erase(it);
		}
		else {
			++it;
		}
	}
	/* (the splash times kept only while they count) */
	m_splashTimes.erase(std::remove_if(m_splashTimes.begin(), m_splashTimes.end(),
	                                   [this](double t) { return m_fluidTime - t >= SPLASH_LIFE; }),
	                    m_splashTimes.end());
}

/* ------------------------------------------------------------------------- */
/* the interface */

bool PxPhysicsEnvironment::GetFluid(PHY_IPhysicsController *volume, PHY_FluidInfo *info)
{
	PxFluidVolume *v = FluidOf(volume);
	if (!v || !info) {
		return false;
	}
	info->type = v->type;
	info->density = v->density;
	info->drag = v->drag;
	info->current = MT_Vector3(v->current.x, v->current.y, v->current.z);
	info->splashes = v->splashes;
	info->inside.clear();
	for (PxPhysicsController *c : m_controllers) {
		PxRigidBody *b = c->GetBody();
		if (b && v->share.count(b) && !FluidOf(c)) {
			info->inside.push_back(c);
		}
	}
	return true;
}

void PxPhysicsEnvironment::SetFluidCurrent(PHY_IPhysicsController *volume, const MT_Vector3 &current)
{
	if (PxFluidVolume *v = FluidOf(volume)) {
		v->current = PxVec3((float)current.x(), (float)current.y(), (float)current.z());
		v->worldCurrent = v->pose.q.rotate(v->current);
	}
}

float PxPhysicsEnvironment::GetSubmerged(PHY_IPhysicsController *volume, PHY_IPhysicsController *ctrl)
{
	PxFluidVolume *v = FluidOf(volume);
	PxPhysicsController *c = static_cast<PxPhysicsController *>(ctrl);
	if (!v || !c || c == v->ctrl) {
		return 0.0f;
	}
	if (!v->built) {
		BuildFluidVolume(v);
	}
	if (v->failed || !v->built) {
		return 0.0f;
	}
	/* a moving body: as the last step found it */
	if (PxRigidBody *b = c->GetBody()) {
		if (m_fluidBodies->count(b)) {
			std::map<const PxRigidActor *, float>::const_iterator it = v->share.find(b);
			return it == v->share.end() ? 0.0f : it->second;
		}
	}
	/* a character (or anything else with an actor): worked out now */
	PxRigidActor *actor = c->GetCharacter() ? (PxRigidActor *)c->GetCharacter()->Actor() : c->GetActor();
	if (!actor) {
		return 0.0f;
	}
	const PxVec3 grav = m_scene ? m_scene->getGravity() : PxVec3(0.0f, 0.0f, -9.81f);
	volume_world(v, grav.magnitude() > 1e-6f ? -grav.getNormalized() : PxVec3(0.0f, 0.0f, 1.0f));
	PxFluidBody b;
	return FluidShare(v, actor, b);
}

void PxPhysicsEnvironment::TakeFluidSplashes(std::vector<PHY_FluidSplash> &r_splashes)
{
	r_splashes.insert(r_splashes.end(), m_splashes.begin(), m_splashes.end());
	m_splashes.clear();
}

int PxPhysicsEnvironment::GetFluidActivity(PHY_IPhysicsController *volume)
{
	PxFluidVolume *v = FluidOf(volume);
	if (!v) {
		return -1;
	}
	if (m_fluidFrame - v->lastSplash < HOLD) {
		return 3;
	}
	return v->share.empty() ? 0 : 1;
}

int PxPhysicsEnvironment::GetFluidState(PHY_IPhysicsController *ctrl)
{
	PxPhysicsController *c = static_cast<PxPhysicsController *>(ctrl);
	PxRigidBody *b = c ? c->GetBody() : NULL;
	if (!b) {
		return -1;
	}
	std::map<const PxRigidActor *, PxFluidBody>::const_iterator it = m_fluidBodies->find(b);
	return it == m_fluidBodies->end() ? -1 : it->second.state;
}
