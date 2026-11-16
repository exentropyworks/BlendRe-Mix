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

/** \file PxDestruction.cpp
 *  \ingroup physphysx
 *
 * BGE-Remix P11 (B2): destructibles (see PxDestruction.h). NVIDIA Blast's
 * low-level API: the asset (pieces = support chunks, bonds found here from
 * the pieces' shared faces, bonds to the world for an anchored base), its
 * family and actors; fracture commands made here (impacts, explosions,
 * script damage: a radial fall-off on the bonds) or by Blast's stress
 * solver (an anchored group's weight); splits make new groups.
 */

#include "PxDestruction.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>

#include "PxPhysicsAPI.h"

#include "PxPhysicsController.h"
#include "PxPhysicsEnvironment.h"
#include "PxShapes.h"
#include "PxSystem.h"

#ifdef WITH_BLAST
#  include "NvBlast.h"
#  include "NvBlastExtStressSolver.h"
#endif

using namespace physx;

namespace {

/* the frames a Remix View colour holds after its event */
const int HOLD = 10;

#ifdef WITH_BLAST
void blast_log(int type, const char *msg, const char *file, int line)
{
	if (type <= NvBlastMessage::Warning) {
		printf("BGE-Remix destruction (Blast): %s (%s:%d)\n", msg ? msg : "", file ? file : "", line);
	}
}
#endif

/* a piece's faces (convex polygons, world space) */
struct Face {
	PxVec3 n;                   /* outward */
	float d;                    /* n . x = d on the face */
	std::vector<PxVec3> loop;
};

PxVec3 newell(const std::vector<PxVec3> &p)
{
	PxVec3 n(0.0f);
	for (size_t i = 0; i < p.size(); i++) {
		const PxVec3 &a = p[i], &b = p[(i + 1) % p.size()];
		n.x += (a.y - b.y) * (a.z + b.z);
		n.y += (a.z - b.z) * (a.x + b.x);
		n.z += (a.x - b.x) * (a.y + b.y);
	}
	return n;
}

void add_face(std::vector<Face> &faces, const std::vector<PxVec3> &loop)
{
	if (loop.size() < 3) {
		return;
	}
	PxVec3 n = newell(loop);
	const float len = n.magnitude();
	if (len < 1e-12f) {
		return;
	}
	n *= 1.0f / len;
	PxVec3 c(0.0f);
	for (const PxVec3 &v : loop) {
		c += v;
	}
	c *= 1.0f / (float)loop.size();
	Face f;
	f.n = n;
	f.d = n.dot(c);
	f.loop = loop;
	faces.push_back(f);
}

/* the faces of an actor's shapes (convex hulls and boxes) */
void actor_faces(PxRigidActor *actor, std::vector<Face> &faces, PxBounds3 &bounds)
{
	bounds = PxBounds3::empty();
	const PxU32 n = actor->getNbShapes();
	std::vector<PxShape *> shapes(n);
	if (n) {
		actor->getShapes(shapes.data(), n);
	}
	const PxTransform pose = actor->getGlobalPose();
	for (PxShape *s : shapes) {
		const PxTransform t = pose * s->getLocalPose();
		const PxGeometry &g = s->getGeometry();
		if (g.getType() == PxGeometryType::eCONVEXMESH) {
			const PxConvexMeshGeometry &cg = static_cast<const PxConvexMeshGeometry &>(g);
			const PxConvexMesh *mesh = cg.convexMesh;
			const PxVec3 *verts = mesh->getVertices();
			const PxU8 *index = mesh->getIndexBuffer();
			for (PxU32 i = 0; i < mesh->getNbVertices(); i++) {
				bounds.include(t.transform(cg.scale.transform(verts[i])));
			}
			for (PxU32 i = 0; i < mesh->getNbPolygons(); i++) {
				PxHullPolygon poly;
				if (!mesh->getPolygonData(i, poly)) {
					continue;
				}
				std::vector<PxVec3> loop;
				for (PxU32 k = 0; k < poly.mNbVerts; k++) {
					loop.push_back(t.transform(cg.scale.transform(verts[index[poly.mIndexBase + k]])));
				}
				/* (a mirroring scale turns the loop over) */
				const PxVec3 out = t.rotate(cg.scale.transform(PxVec3(poly.mPlane[0], poly.mPlane[1], poly.mPlane[2])));
				if (newell(loop).dot(out) < 0.0f) {
					std::reverse(loop.begin(), loop.end());
				}
				add_face(faces, loop);
			}
		}
		else if (g.getType() == PxGeometryType::eBOX) {
			const PxVec3 h = static_cast<const PxBoxGeometry &>(g).halfExtents;
			PxVec3 c[8];
			for (int i = 0; i < 8; i++) {
				c[i] = t.transform(PxVec3((i & 1) ? h.x : -h.x, (i & 2) ? h.y : -h.y, (i & 4) ? h.z : -h.z));
				bounds.include(c[i]);
			}
			static const int quads[6][4] = {{0, 2, 6, 4}, {1, 5, 7, 3}, {0, 4, 5, 1}, {2, 3, 7, 6}, {0, 1, 3, 2},
			                                {4, 6, 7, 5}};
			for (const int *q : quads) {
				std::vector<PxVec3> loop = {c[q[0]], c[q[1]], c[q[2]], c[q[3]]};
				/* outward */
				if (newell(loop).dot((loop[0] + loop[2]) * 0.5f - t.p) < 0.0f) {
					std::reverse(loop.begin(), loop.end());
				}
				add_face(faces, loop);
			}
		}
		else {
			PxBounds3 b;
			if (PxGeometryQuery::computeGeomBounds(b, g, t)) {
				bounds.include(b);
			}
		}
	}
}

/* 2D (the face's plane) */
struct P2 {
	float x, y;
};

float cross2(const P2 &o, const P2 &a, const P2 &b)
{
	return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

/* a counter-clockwise loop */
void ccw(std::vector<P2> &p)
{
	float a = 0.0f;
	for (size_t i = 0; i < p.size(); i++) {
		const P2 &u = p[i], &v = p[(i + 1) % p.size()];
		a += u.x * v.y - v.x * u.y;
	}
	if (a < 0.0f) {
		std::reverse(p.begin(), p.end());
	}
}

/* convex polygon a clipped by convex polygon b (both counter-clockwise) */
std::vector<P2> clip(std::vector<P2> a, const std::vector<P2> &b)
{
	for (size_t i = 0; i < b.size() && !a.empty(); i++) {
		const P2 &e0 = b[i], &e1 = b[(i + 1) % b.size()];
		std::vector<P2> out;
		for (size_t k = 0; k < a.size(); k++) {
			const P2 &p = a[k], &q = a[(k + 1) % a.size()];
			const float sp = cross2(e0, e1, p), sq = cross2(e0, e1, q);
			if (sp >= 0.0f) {
				out.push_back(p);
			}
			if ((sp >= 0.0f) != (sq >= 0.0f)) {
				const float t = sp / (sp - sq);
				out.push_back({p.x + (q.x - p.x) * t, p.y + (q.y - p.y) * t});
			}
		}
		a.swap(out);
	}
	return a;
}

/* a polygon's area and centroid */
float area2(const std::vector<P2> &p, P2 &r_c)
{
	float a = 0.0f, cx = 0.0f, cy = 0.0f;
	for (size_t i = 0; i < p.size(); i++) {
		const P2 &u = p[i], &v = p[(i + 1) % p.size()];
		const float c = u.x * v.y - v.x * u.y;
		a += c;
		cx += (u.x + v.x) * c;
		cy += (u.y + v.y) * c;
	}
	a *= 0.5f;
	if (fabsf(a) > 1e-12f) {
		r_c = {cx / (6.0f * a), cy / (6.0f * a)};
	}
	else {
		r_c = p.empty() ? P2{0.0f, 0.0f} : p[0];
	}
	return fabsf(a);
}

void plane_basis(const PxVec3 &n, PxVec3 &u, PxVec3 &v)
{
	u = (fabsf(n.x) < 0.9f ? PxVec3(1.0f, 0.0f, 0.0f) : PxVec3(0.0f, 1.0f, 0.0f)).cross(n).getNormalized();
	v = n.cross(u);
}

std::vector<P2> project(const std::vector<PxVec3> &loop, const PxVec3 &o, const PxVec3 &u, const PxVec3 &v)
{
	std::vector<P2> p;
	for (const PxVec3 &x : loop) {
		p.push_back({(x - o).dot(u), (x - o).dot(v)});
	}
	ccw(p);
	return p;
}

/* where two faces touch (opposite, on one plane): the area and its centre */
float touching(const Face &a, const Face &b, float eps, PxVec3 &r_centre)
{
	if (a.n.dot(b.n) > -0.985f || fabsf(a.d + b.d) > eps) {
		return 0.0f;
	}
	PxVec3 u, v;
	plane_basis(a.n, u, v);
	const PxVec3 o = a.loop[0];
	const std::vector<P2> pa = project(a.loop, o, u, v), pb = project(b.loop, o, u, v);
	const std::vector<P2> both = clip(pa, pb);
	if (both.size() < 3) {
		return 0.0f;
	}
	P2 c;
	const float area = area2(both, c);
	r_centre = o + u * c.x + v * c.y;
	return area;
}

}  /* namespace */

/* ------------------------------------------------------------------------- */

PxDestructionGroup::PxDestructionGroup()
    : owner(NULL), body(NULL), bodyFromRest(PxIdentity), actor(NULL), anchored(false), original(false),
      removing(false), born(0.0), serial(0)
{
}

PxTransform PxDestructionGroup::RestToWorld() const
{
	/* (a piece: body * local, local = bodyFromRest * rest) */
	return body ? body->getGlobalPose() * bodyFromRest : bodyFromRest;
}

PxDestructible::PxDestructible()
    : root(-1), strength(100.0f), anchored(false), size(0.1f), mass(0.0f), bonds(0), bondsBroken(0), built(false),
      failed(false), lastSplit(-1000), lastBudget(-1000), lastScript(-1000), assetMem(NULL), familyMem(NULL),
      asset(NULL), family(NULL), stress(NULL)
{
}

/* ------------------------------------------------------------------------- */
/* the environment's side */

void PxPhysicsEnvironment::AddDestructionPiece(PxPhysicsController *ctrl, const std::string &key, bool isRoot,
                                               float strength, bool anchored)
{
	PxDestructible *d = NULL;
	for (PxDestructible *x : m_destructibles) {
		if (x->key == key && !x->built) {
			d = x;
		}
	}
	if (!d) {
		d = new PxDestructible();
		d->key = key;
		m_destructibles.push_back(d);
	}
	d->pieces.push_back(ctrl);
	if (isRoot) {
		d->root = (int)d->pieces.size() - 1;
		d->strength = strength;
		d->anchored = anchored;
	}
	m_destructionDirty = true;
}

bool PxPhysicsEnvironment::HandlesDestruction()
{
	return true;
}

void PxPhysicsEnvironment::SetDestructionBudget(int maxPieces, float lifetime)
{
	m_maxPieces = std::max(maxPieces, 0);
	m_debrisLifetime = std::max(lifetime, 0.0f);
}

PxPhysicsController *PxPhysicsEnvironment::ShapeOwner(const PxShape *shape, PxPhysicsController *actorOwner) const
{
	if (shape && !m_shardShapes.empty()) {
		std::map<const PxShape *, PxPhysicsController *>::const_iterator it = m_shardShapes.find(shape);
		if (it != m_shardShapes.end()) {
			return it->second;
		}
	}
	return actorOwner;
}

void PxPhysicsEnvironment::DestructionImpact(PxPhysicsController *piece, const PxVec3 &point, float impulse)
{
	m_impacts.push_back({piece, point, impulse});
}

PxDestructible *PxPhysicsEnvironment::DestructibleOf(PHY_IPhysicsController *piece) const
{
	PxPhysicsController *ctrl = dynamic_cast<PxPhysicsController *>(piece);
	if (!ctrl) {
		return NULL;
	}
	if (ctrl->GetShard()) {
		return ctrl->GetShard()->owner;
	}
	for (PxDestructible *d : m_destructibles) {
		if (std::find(d->pieces.begin(), d->pieces.end(), ctrl) != d->pieces.end()) {
			return d;
		}
	}
	return NULL;
}

void PxPhysicsEnvironment::BuildDestructibles()
{
	m_destructionDirty = false;
	for (PxDestructible *d : m_destructibles) {
		if (!d->built && !d->failed) {
			if (!BuildDestructible(d)) {
				d->failed = true;
			}
		}
	}
}

/* a new group: these pieces on one body, at the speed the old one had there */
PxDestructionGroup *PxPhysicsEnvironment::MakeDestructionGroup(PxDestructible *d, const std::vector<int> &pieces,
                                                                void *actor, const PxTransform &restToWorld,
                                                                const PxVec3 &lin, const PxVec3 &ang,
                                                                const PxVec3 &comWas, bool original)
{
	PxSystem *sys = PxSystem::Get();
	if (!sys || pieces.empty() || !m_scene) {
		return NULL;
	}
	PxDestructionGroup *g = new PxDestructionGroup();
	g->owner = d;
	g->pieces = pieces;
	g->actor = (NvBlastActor *)actor;
	g->original = original;
	g->born = m_destructionTime;
	g->serial = m_groupSerial++;
#ifdef WITH_BLAST
	g->anchored = g->actor && NvBlastActorHasExternalBonds(g->actor, blast_log);
#else
	g->anchored = d->anchored;
#endif
	/* the body at the pieces' centre (by volume), turned as the rest space is */
	PxVec3 com(0.0f);
	float vol = 0.0f, mass = 0.0f;
	for (int i : pieces) {
		com += restToWorld.transform(d->centroid[i]) * d->volume[i];
		vol += d->volume[i];
		mass += std::max(d->pieces[i]->GetInfo().mass, 1e-3f);
	}
	com = vol > 0.0f ? com * (1.0f / vol) : restToWorld.transform(d->centroid[pieces[0]]);
	const PxTransform bodyPose(com, restToWorld.q);
	g->bodyFromRest = bodyPose.getInverse() * restToWorld;
	PxRigidDynamic *body = sys->Physics()->createRigidDynamic(bodyPose);
	g->body = body;
	body->userData = d->pieces[pieces[0]];
	if (g->anchored) {
		body->setRigidBodyFlag(PxRigidBodyFlag::eKINEMATIC, true);
	}
	const PxShapeFlags flags = PxShapeFlag::eSCENE_QUERY_SHAPE | PxShapeFlag::eVISUALIZATION |
	                           PxShapeFlag::eSIMULATION_SHAPE;
	for (int i : pieces) {
		PxPhysicsController *ctrl = d->pieces[i];
		PxShard &shard = d->shards[i];
		shard.owner = d;
		shard.index = i;
		shard.group = g;
		shard.local = g->bodyFromRest * d->rest[i];
		ctrl->BecomeShard(&shard);
		std::vector<PxShape *> made;
		const PxCtrlInfo &ci = ctrl->GetInfo();
		if (ci.shape) {
			ci.shape->CreateShapes(body, ci.scaling, sys->Material(ci.friction, ci.restitution), ctrl->FilterData(),
			                       flags, true, made);
		}
		for (PxShape *s : made) {
			s->setLocalPose(shard.local * s->getLocalPose());
			m_shardShapes[s] = ctrl;
		}
		ctrl->SetShardShapes(made);
	}
	if (body->getNbShapes()) {
		PxRigidBodyExt::setMassAndUpdateInertia(*body, mass);
	}
	else {
		body->setMass(mass);
	}
	if (!g->anchored) {
		body->setSolverIterationCounts((PxU32)std::max(1, std::min(m_numIterations, 32)), 1);
		body->setRigidBodyFlag(PxRigidBodyFlag::eENABLE_CCD, m_ccdMode != 0);
		const PxVec3 c = body->getGlobalPose().transform(body->getCMassLocalPose().p);
		body->setLinearVelocity(lin + ang.cross(c - comWas));
		body->setAngularVelocity(ang);
	}
	m_scene->addActor(*body);
	d->groups.push_back(g);
	return g;
}

void PxPhysicsEnvironment::ReleaseDestructionGroup(PxDestructionGroup *g)
{
	PxDestructible *d = g->owner;
	for (int i : g->pieces) {
		if (i >= 0 && i < (int)d->shards.size() && d->shards[i].group == g) {
			d->shards[i].group = NULL;
		}
	}
	if (g->body) {
		const PxU32 n = g->body->getNbShapes();
		std::vector<PxShape *> shapes(n);
		if (n) {
			g->body->getShapes(shapes.data(), n);
		}
		for (PxShape *s : shapes) {
			m_shardShapes.erase(s);
		}
		if (g->body->getScene()) {
			g->body->getScene()->removeActor(*g->body);
		}
		g->body->release();
		g->body = NULL;
	}
	d->groups.erase(std::remove(d->groups.begin(), d->groups.end(), g), d->groups.end());
	delete g;
}

bool PxPhysicsEnvironment::BuildDestructible(PxDestructible *d)
{
	const int n = (int)d->pieces.size();
	if (n == 0) {
		return false;
	}
	d->shards.assign(n, PxShard());
	d->rest.resize(n);
	d->volume.assign(n, 0.0f);
	d->centroid.assign(n, PxVec3(0.0f));
	if (d->root < 0) {
		d->root = 0;
	}
	/* each piece as the game starts: pose, volume, centre, faces */
	std::vector<std::vector<Face> > faces(n);
	std::vector<PxBounds3> bounds(n);
	PxBounds3 all = PxBounds3::empty();
	float vol = 0.0f;
	d->mass = 0.0f;
	for (int i = 0; i < n; i++) {
		PxPhysicsController *ctrl = d->pieces[i];
		PxRigidActor *actor = ctrl->GetActor();
		d->rest[i] = actor ? actor->getGlobalPose() : ctrl->MotionStateTransform();
		d->mass += std::max(ctrl->GetInfo().mass, 1e-3f);
		if (!actor) {
			bounds[i] = PxBounds3::centerExtents(d->rest[i].p, PxVec3(0.05f));
			d->volume[i] = 1e-3f;
			d->centroid[i] = d->rest[i].p;
			continue;
		}
		actor_faces(actor, faces[i], bounds[i]);
		const PxU32 ns = actor->getNbShapes();
		std::vector<PxShape *> shapes(ns);
		if (ns) {
			actor->getShapes(shapes.data(), ns);
		}
		PxMassProperties mp = ns ? PxRigidBodyExt::computeMassPropertiesFromShapes(shapes.data(), ns) :
		                           PxMassProperties();
		d->volume[i] = std::max(mp.mass, 1e-6f);  /* (density 1: the volume) */
		d->centroid[i] = d->rest[i].transform(mp.centerOfMass);
		vol += d->volume[i];
		all.include(bounds[i]);
	}
	d->size = std::max(cbrtf(std::max(vol, 1e-6f) / (float)n), 0.01f);
	const float eps = std::max(0.02f * d->size, 2e-3f);

	/* the bonds: faces that touch (on one plane, opposite) */
	struct Bond {
		int a, b;  /* b -1: the world */
		PxVec3 normal, centroid;
		float area;
	};
	std::vector<Bond> bonds;
	for (int i = 0; i < n; i++) {
		PxBounds3 bi = bounds[i];
		bi.fattenFast(eps);
		for (int j = i + 1; j < n; j++) {
			if (!bi.intersects(bounds[j])) {
				continue;
			}
			float area = 0.0f;
			PxVec3 c(0.0f), nrm(0.0f);
			for (const Face &fa : faces[i]) {
				for (const Face &fb : faces[j]) {
					PxVec3 at;
					const float s = touching(fa, fb, eps, at);
					if (s > 0.0f) {
						area += s;
						c += at * s;
						nrm += fa.n * s;
					}
				}
			}
			if (area > 1e-4f * d->size * d->size) {
				bonds.push_back({i, j, nrm.getNormalized(), c * (1.0f / area), area});
			}
		}
	}
	/* an anchored base: the faces down at the bottom are held by the world */
	if (d->anchored && !all.isEmpty()) {
		for (int i = 0; i < n; i++) {
			float area = 0.0f;
			PxVec3 c(0.0f);
			for (const Face &f : faces[i]) {
				if (f.n.z > -0.985f || fabsf(-f.d - all.minimum.z) > eps) {  /* (n . x = d, n down: z = -d) */
					continue;
				}
				PxVec3 u, v;
				plane_basis(f.n, u, v);
				const std::vector<P2> p = project(f.loop, f.loop[0], u, v);
				P2 pc;
				const float s = area2(p, pc);
				area += s;
				c += (f.loop[0] + u * pc.x + v * pc.y) * s;
			}
			if (area > 1e-4f * d->size * d->size) {
				bonds.push_back({i, -1, PxVec3(0.0f, 0.0f, -1.0f), c * (1.0f / area), area});
			}
		}
	}
	d->bonds = (int)bonds.size();

	const PxVec3 linStart = d->pieces[d->root]->GetActor() && d->pieces[d->root]->GetDynamic() ?
	                        d->pieces[d->root]->GetDynamic()->getLinearVelocity() : PxVec3(0.0f);
	std::vector<int> every(n);
	for (int i = 0; i < n; i++) {
		every[i] = i;
	}

#ifdef WITH_BLAST
	/* the asset: every piece a support chunk (no parent) */
	std::vector<NvBlastChunkDesc> chunks(n);
	for (int i = 0; i < n; i++) {
		NvBlastChunkDesc &c = chunks[i];
		c.centroid[0] = d->centroid[i].x;
		c.centroid[1] = d->centroid[i].y;
		c.centroid[2] = d->centroid[i].z;
		c.volume = d->volume[i];
		c.parentChunkDescIndex = UINT32_MAX;
		c.flags = NvBlastChunkDesc::SupportFlag;
		c.userData = (uint32_t)i;
	}
	std::vector<NvBlastBondDesc> bdesc(bonds.size());
	for (size_t k = 0; k < bonds.size(); k++) {
		NvBlastBondDesc &b = bdesc[k];
		const Bond &s = bonds[k];
		b.bond.normal[0] = s.normal.x;
		b.bond.normal[1] = s.normal.y;
		b.bond.normal[2] = s.normal.z;
		b.bond.area = s.area;
		b.bond.centroid[0] = s.centroid.x;
		b.bond.centroid[1] = s.centroid.y;
		b.bond.centroid[2] = s.centroid.z;
		b.bond.userData = (uint32_t)k;
		b.chunkIndices[0] = (uint32_t)s.a;
		b.chunkIndices[1] = s.b < 0 ? UINT32_MAX : (uint32_t)s.b;
	}
	std::vector<uint32_t> reorder(n);
	std::vector<char> scratch((size_t)n * 64 + bdesc.size() * 32 + 4096);
	NvBlastReorderAssetDescChunks(chunks.data(), (uint32_t)n, bdesc.data(), (uint32_t)bdesc.size(), reorder.data(),
	                              true, scratch.data(), blast_log);
	NvBlastAssetDesc desc;
	desc.chunkCount = (uint32_t)n;
	desc.chunkDescs = chunks.data();
	desc.bondCount = (uint32_t)bdesc.size();
	desc.bondDescs = bdesc.empty() ? NULL : bdesc.data();
	scratch.resize(std::max(scratch.size(), NvBlastGetRequiredScratchForCreateAsset(&desc, blast_log)));
	const size_t assetSize = NvBlastGetAssetMemorySize(&desc, blast_log);
	d->assetMem = assetSize ? malloc(assetSize) : NULL;
	NvBlastAsset *asset = d->assetMem ? NvBlastCreateAsset(d->assetMem, &desc, scratch.data(), blast_log) : NULL;
	if (!asset) {
		printf("BGE-Remix destruction: \"%s\" could not be made into a Blast asset; it stays whole\n", d->key.c_str());
		free(d->assetMem);
		d->assetMem = NULL;
		MakeDestructionGroup(d, every, NULL, PxTransform(PxIdentity), linStart, PxVec3(0.0f), PxVec3(0.0f), true);
		d->built = true;
		return true;
	}
	d->asset = asset;
	const size_t familySize = NvBlastAssetGetFamilyMemorySize(asset, blast_log);
	d->familyMem = malloc(familySize);
	NvBlastFamily *family = NvBlastAssetCreateFamily(d->familyMem, asset, blast_log);
	d->family = family;
	NvBlastActorDesc ad;
	memset(&ad, 0, sizeof(ad));
	ad.uniformInitialBondHealth = 1.0f;
	ad.initialBondHealths = NULL;
	ad.uniformInitialLowerSupportChunkHealth = 1.5f * Nv::Blast::kUnbreakableLimit;  /* (pieces never break) */
	ad.initialSupportChunkHealths = NULL;
	scratch.resize(std::max(scratch.size(), NvBlastFamilyGetRequiredScratchForCreateFirstActor(family, blast_log)));
	NvBlastActor *first = NvBlastFamilyCreateFirstActor(family, &ad, scratch.data(), blast_log);
	if (!first) {
		printf("BGE-Remix destruction: \"%s\": Blast made no actor; it stays whole\n", d->key.c_str());
		MakeDestructionGroup(d, every, NULL, PxTransform(PxIdentity), linStart, PxVec3(0.0f), PxVec3(0.0f), true);
		d->built = true;
		return true;
	}
	/* the stress solver: an anchored destructible's weight on its bonds.
	 * Its limits from the intact weight on the base (a bond takes twenty
	 * times the pressure the base takes as it stands, before it breaks) */
	if (d->anchored) {
		float baseArea = 0.0f;
		for (const Bond &b : bonds) {
			baseArea += b.b < 0 ? b.area : 0.0f;
		}
		const float g = m_scene->getGravity().magnitude();
		const float p0 = baseArea > 0.0f ? d->mass * std::max(g, 1e-3f) / baseArea : 1.0f;
		Nv::Blast::ExtStressSolverSettings st;
		st.maxSolverIterationsPerFrame = 32;
		st.graphReductionLevel = 0;
		st.compressionElasticLimit = 10.0f * p0;
		st.compressionFatalLimit = 20.0f * p0;
		st.tensionElasticLimit = -1.0f;
		st.tensionFatalLimit = -1.0f;
		st.shearElasticLimit = -1.0f;
		st.shearFatalLimit = -1.0f;
		Nv::Blast::ExtStressSolver *solver = Nv::Blast::ExtStressSolver::create(*family, st);
		if (solver) {
			solver->setAllNodesInfoFromLL(vol > 0.0f ? d->mass / vol : 1.0f);
			solver->notifyActorCreated(*first);
		}
		d->stress = solver;
	}
	MakeDestructionGroup(d, every, first, PxTransform(PxIdentity), linStart, PxVec3(0.0f), PxVec3(0.0f), true);
#else
	PxSystem::WarnOnce("blast", "destructibles stay whole: this build has no NVIDIA Blast");
	MakeDestructionGroup(d, every, NULL, PxTransform(PxIdentity), linStart, PxVec3(0.0f), PxVec3(0.0f), true);
#endif
	d->built = true;
	printf("BGE-Remix destruction: \"%s\": %d pieces, %d bonds%s\n", d->key.c_str(), n, (int)bonds.size(),
	       d->anchored ? " (anchored)" : "");
	return true;
}

/* bonds within the radius take the damage, less towards the edge */
bool PxPhysicsEnvironment::DamageGroups(PxDestructible *d, const PxVec3 &point, float radius, float amount)
{
#ifdef WITH_BLAST
	if (!d->built || !d->asset || radius <= 0.0f || amount <= 0.0f) {
		return false;
	}
	const NvBlastAsset *asset = (const NvBlastAsset *)d->asset;
	const NvBlastSupportGraph graph = NvBlastAssetGetSupportGraph(asset, blast_log);
	const NvBlastBond *bonds = NvBlastAssetGetBonds(asset, blast_log);
	bool hit = false;
	const std::vector<PxDestructionGroup *> groups = d->groups;
	for (PxDestructionGroup *g : groups) {
		if (!g->actor || g->removing) {
			continue;
		}
		const PxVec3 at = g->RestToWorld().transformInv(point);  /* (rest space) */
		const float *health = NvBlastActorGetBondHealths(g->actor, blast_log);
		const uint32_t nn = NvBlastActorGetGraphNodeCount(g->actor, blast_log);
		std::vector<uint32_t> nodes(nn);
		NvBlastActorGetGraphNodeIndices(nodes.data(), nn, g->actor, blast_log);
		std::vector<NvBlastBondFractureData> cmds;
		for (uint32_t u : nodes) {
			for (uint32_t k = graph.adjacencyPartition[u]; k < graph.adjacencyPartition[u + 1]; k++) {
				const uint32_t v = graph.adjacentNodeIndices[k], b = graph.adjacentBondIndices[k];
				const bool world = graph.chunkIndices[v] == UINT32_MAX;
				if ((!world && v < u) || !health || health[b] <= 0.0f) {
					continue;
				}
				const PxVec3 c(bonds[b].centroid[0], bonds[b].centroid[1], bonds[b].centroid[2]);
				const float dist = (c - at).magnitude();
				if (dist >= radius) {
					continue;
				}
				NvBlastBondFractureData f;
				f.userdata = 0;
				f.nodeIndex0 = u;
				f.nodeIndex1 = v;
				f.health = amount * (1.0f - dist / radius);
				cmds.push_back(f);
			}
		}
		if (cmds.empty()) {
			continue;
		}
		hit = true;
		NvBlastFractureBuffers buf;
		buf.bondFractureCount = (uint32_t)cmds.size();
		buf.chunkFractureCount = 0;
		buf.bondFractures = cmds.data();
		buf.chunkFractures = NULL;
		NvBlastActorApplyFracture(NULL, g->actor, &buf, blast_log, NULL);
		if (NvBlastActorIsSplitRequired(g->actor, blast_log)) {
			SplitDestructible(d, g->actor);
		}
	}
	return hit;
#else
	(void)d;
	(void)point;
	(void)radius;
	(void)amount;
	return false;
#endif
}

/* Blast splits an actor: its group becomes one group per new actor */
void PxPhysicsEnvironment::SplitDestructible(PxDestructible *d, void *actor_v)
{
#ifdef WITH_BLAST
	NvBlastActor *actor = (NvBlastActor *)actor_v;
	PxDestructionGroup *old = NULL;
	for (PxDestructionGroup *g : d->groups) {
		if (g->actor == actor) {
			old = g;
		}
	}
	if (!old) {
		return;
	}
	const uint32_t most = NvBlastActorGetMaxActorCountForSplit(actor, blast_log);
	std::vector<NvBlastActor *> made(std::max(most, 1u));
	d->scratch.resize(std::max(d->scratch.size(), NvBlastActorGetRequiredScratchForSplit(actor, blast_log)));
	Nv::Blast::ExtStressSolver *solver = (Nv::Blast::ExtStressSolver *)d->stress;
	if (solver) {
		solver->notifyActorDestroyed(*actor);
	}
	NvBlastActorSplitEvent ev;
	ev.deletedActor = NULL;
	ev.newActors = made.data();
	const uint32_t count = NvBlastActorSplit(&ev, actor, (uint32_t)made.size(), d->scratch.data(), blast_log, NULL);
	if (count == 0 || !ev.deletedActor) {
		if (solver) {
			solver->notifyActorCreated(*actor);
		}
		return;
	}
	/* where the old group was, how it moved */
	const PxTransform restToWorld = old->RestToWorld();
	PxVec3 lin(0.0f), ang(0.0f), comWas(0.0f);
	if (old->body) {
		comWas = old->body->getGlobalPose().transform(old->body->getCMassLocalPose().p);
		if (!old->anchored) {
			lin = old->body->getLinearVelocity();
			ang = old->body->getAngularVelocity();
		}
	}
	const bool wasOriginal = old->original;
	ReleaseDestructionGroup(old);
	const NvBlastAsset *asset = (const NvBlastAsset *)d->asset;
	const NvBlastChunk *chunks = NvBlastAssetGetChunks(asset, blast_log);
	size_t largest = 0, largestAt = 0;
	std::vector<PxDestructionGroup *> news;
	for (uint32_t k = 0; k < count; k++) {
		NvBlastActor *a = made[k];
		const uint32_t nv = NvBlastActorGetVisibleChunkCount(a, blast_log);
		std::vector<uint32_t> vis(nv);
		NvBlastActorGetVisibleChunkIndices(vis.data(), nv, a, blast_log);
		std::vector<int> pieces;
		for (uint32_t c : vis) {
			const int i = (int)chunks[c].userData;
			if (i >= 0 && i < (int)d->pieces.size() && d->pieces[i]) {
				pieces.push_back(i);
			}
		}
		if (solver) {
			solver->notifyActorCreated(*a);
		}
		if (pieces.empty()) {
			continue;
		}
		PxDestructionGroup *g = MakeDestructionGroup(d, pieces, a, restToWorld, lin, ang, comWas, false);
		if (g) {
			news.push_back(g);
			if (pieces.size() > largest || (g->anchored && pieces.size() == largest)) {
				largest = pieces.size();
				largestAt = news.size() - 1;
			}
		}
	}
	/* (the part still held, or the largest, is the destructible itself, not
	 * broken off: not counted by the budget) */
	if (wasOriginal && !news.empty()) {
		bool any = false;
		for (PxDestructionGroup *g : news) {
			if (g->anchored) {
				g->original = true;
				any = true;
			}
		}
		if (!any) {
			news[largestAt]->original = true;
		}
	}
	d->bondsBroken = 0;
	if (!d->groups.empty() && d->groups[0]->actor) {
		const uint32_t nb = NvBlastAssetGetBondCount(asset, blast_log);
		const float *h = NvBlastActorGetBondHealths(d->groups[0]->actor, blast_log);  /* (the family's) */
		for (uint32_t b = 0; h && b < nb; b++) {
			d->bondsBroken += h[b] <= 0.0f ? 1 : 0;
		}
	}
	d->lastSplit = m_destructionFrame;
#else
	(void)d;
	(void)actor_v;
#endif
}

void PxPhysicsEnvironment::DestructionStep(float dt)
{
	m_destructionFrame++;
	m_destructionTime += dt;
	/* impacts: the impulse over the destructible's strength breaks the
	 * bonds where it lands (within a piece's size) */
	std::vector<DestructionImpactRec> impacts;
	impacts.swap(m_impacts);
	std::map<PxDestructible *, std::vector<DestructionImpactRec> > by;
	for (const DestructionImpactRec &r : impacts) {
		if (!m_controllers.count(r.piece) || !r.piece->GetShard()) {
			continue;
		}
		PxDestructible *d = r.piece->GetShard()->owner;
		if (d && r.impulse >= 0.1f * d->strength) {
			by[d].push_back(r);
		}
	}
	for (auto &it : by) {
		PxDestructible *d = it.first;
		for (const DestructionImpactRec &r : it.second) {
			DamageGroups(d, r.point, 1.5f * d->size, r.impulse / d->strength);
		}
	}
#ifdef WITH_BLAST
	/* collapse: the anchored groups carry their weight down to the world */
	const PxVec3 grav = m_scene->getGravity();
	for (PxDestructible *d : m_destructibles) {
		Nv::Blast::ExtStressSolver *solver = (Nv::Blast::ExtStressSolver *)d->stress;
		if (!solver || !d->built) {
			continue;
		}
		std::vector<const NvBlastActor *> held;
		for (PxDestructionGroup *g : d->groups) {
			if (g->anchored && g->actor && !g->removing) {
				const PxVec3 lg = g->RestToWorld().rotateInv(grav);
				solver->addGravity(*g->actor, {lg.x, lg.y, lg.z});
				held.push_back(g->actor);
			}
		}
		if (held.empty()) {
			continue;
		}
		solver->update();
		if (solver->getOverstressedBondCount() == 0) {
			continue;
		}
		std::vector<NvBlastFractureBuffers> cmds(held.size());
		const uint32_t nc = solver->generateFractureCommandsPerActor(held.data(), cmds.data(), (uint32_t)held.size());
		for (uint32_t k = 0; k < nc; k++) {
			NvBlastActor *a = const_cast<NvBlastActor *>(held[k]);
			NvBlastActorApplyFracture(NULL, a, &cmds[k], blast_log, NULL);
			if (NvBlastActorIsSplitRequired(a, blast_log)) {
				SplitDestructible(d, a);
			}
		}
	}
#endif
	DestructionBudget();
}

/* the Destruction Budget: the broken-off pieces over the most, or older
 * than the lifetime, go (oldest first); their objects are ended by the game */
void PxPhysicsEnvironment::DestructionBudget()
{
	std::vector<PxDestructionGroup *> loose;
	int count = 0;
	for (PxDestructible *d : m_destructibles) {
		for (PxDestructionGroup *g : d->groups) {
			if (!g->original && !g->anchored && !g->removing) {
				loose.push_back(g);
				count += (int)g->pieces.size();
			}
		}
	}
	std::sort(loose.begin(), loose.end(), [](const PxDestructionGroup *a, const PxDestructionGroup *b) {
		return a->born != b->born ? a->born < b->born : a->serial < b->serial;
	});
	for (PxDestructionGroup *g : loose) {
		const bool over = m_maxPieces > 0 && count > m_maxPieces;
		const bool old = m_debrisLifetime > 0.0f && m_destructionTime - g->born > m_debrisLifetime;
		if (!over && !old) {
			continue;
		}
		g->removing = true;
		count -= (int)g->pieces.size();
		if (g->body && g->body->getScene()) {
			g->body->getScene()->removeActor(*g->body);
		}
		for (int i : g->pieces) {
			if (g->owner->pieces[i]) {
				m_destructionRemovals.push_back(g->owner->pieces[i]);
			}
		}
		g->owner->lastBudget = m_destructionFrame;
	}
}

void PxPhysicsEnvironment::TakeDestructionRemovals(std::vector<PHY_IPhysicsController *> &r_pieces)
{
	for (PHY_IPhysicsController *c : m_destructionRemovals) {
		r_pieces.push_back(c);
	}
	m_destructionRemovals.clear();
}

/* a piece's object is gone (ended, or removed from the scene): out of its group */
void PxPhysicsEnvironment::DestructionRemovePiece(PxPhysicsController *ctrl)
{
	PxShard *shard = ctrl->GetShard();
	if (!shard) {
		return;
	}
	PxDestructible *d = shard->owner;
	PxDestructionGroup *g = shard->group;
	const int i = shard->index;
	if (d && i >= 0 && i < (int)d->pieces.size()) {
		d->pieces[i] = NULL;
	}
	m_destructionRemovals.erase(std::remove(m_destructionRemovals.begin(), m_destructionRemovals.end(),
	                                        (PHY_IPhysicsController *)ctrl), m_destructionRemovals.end());
	for (DestructionImpactRec &r : m_impacts) {
		if (r.piece == ctrl) {
			r.piece = NULL;
		}
	}
	if (g && g->body) {
		std::vector<PxShape *> mine;
		const PxU32 n = g->body->getNbShapes();
		std::vector<PxShape *> shapes(n);
		if (n) {
			g->body->getShapes(shapes.data(), n);
		}
		for (PxShape *s : shapes) {
			std::map<const PxShape *, PxPhysicsController *>::iterator it = m_shardShapes.find(s);
			if (it != m_shardShapes.end() && it->second == ctrl) {
				m_shardShapes.erase(it);
				g->body->detachShape(*s);
			}
		}
		g->pieces.erase(std::remove(g->pieces.begin(), g->pieces.end(), i), g->pieces.end());
		if (g->pieces.empty()) {
			ReleaseDestructionGroup(g);
		}
		else if (g->body->getNbShapes()) {
			float mass = 0.0f;
			for (int k : g->pieces) {
				mass += d->pieces[k] ? std::max(d->pieces[k]->GetInfo().mass, 1e-3f) : 0.0f;
			}
			PxRigidBodyExt::setMassAndUpdateInertia(*g->body, std::max(mass, 1e-3f));
		}
	}
	ctrl->LeaveShard();
}

void PxPhysicsEnvironment::DismantleDestructible(PxDestructible *d)
{
	while (!d->groups.empty()) {
		ReleaseDestructionGroup(d->groups.back());
	}
	for (PxPhysicsController *ctrl : d->pieces) {
		if (ctrl) {
			ctrl->LeaveShard();
		}
	}
#ifdef WITH_BLAST
	if (d->stress) {
		((Nv::Blast::ExtStressSolver *)d->stress)->release();
	}
#endif
	free(d->familyMem);
	free(d->assetMem);
	m_destructibles.erase(std::remove(m_destructibles.begin(), m_destructibles.end(), d), m_destructibles.end());
	delete d;
}

/* ------------------------------------------------------------------------- */
/* the game's side (PHY_IPhysicsEnvironment) */

bool PxPhysicsEnvironment::GetDestructible(PHY_IPhysicsController *piece, PHY_DestructibleInfo *info)
{
	PxDestructible *d = DestructibleOf(piece);
	if (!d || !info) {
		return false;
	}
	info->root = (d->root >= 0 && d->root < (int)d->pieces.size()) ? d->pieces[d->root] : NULL;
	info->pieces.clear();
	info->groupOf.clear();
	/* (0: the destructible itself, what is still held or the largest part;
	 * then each broken-off group) */
	std::vector<PxDestructionGroup *> order(1, (PxDestructionGroup *)NULL);
	for (PxDestructionGroup *g : d->groups) {
		if (!g->original) {
			order.push_back(g);
		}
	}
	for (int i = 0; i < (int)d->pieces.size(); i++) {
		if (!d->pieces[i]) {
			continue;
		}
		if (d->built && i < (int)d->shards.size() && d->shards[i].group && d->shards[i].group->removing) {
			continue;  /* (the budget took it: its object is being ended) */
		}
		int at = -1;
		if (d->built && i < (int)d->shards.size() && d->shards[i].group) {
			const PxDestructionGroup *g = d->shards[i].group;
			at = g->original ? 0 : (int)(std::find(order.begin(), order.end(), g) - order.begin());
		}
		info->pieces.push_back(d->pieces[i]);
		info->groupOf.push_back(at);
	}
	info->groups = d->built ? (int)d->groups.size() : 1;
	info->bonds = d->bonds;
	info->bondsBroken = d->bondsBroken;
	info->anchored = d->anchored;
	info->strength = d->strength;
	return true;
}

bool PxPhysicsEnvironment::DamageDestructible(PHY_IPhysicsController *piece, const MT_Vector3 &point, float radius,
                                              float amount)
{
	PxDestructible *d = DestructibleOf(piece);
	if (!d) {
		return false;
	}
	if (m_destructionDirty) {
		BuildDestructibles();
	}
	d->lastScript = m_destructionFrame;
	DamageGroups(d, PxVec3((float)point[0], (float)point[1], (float)point[2]), radius, amount);
	return true;
}

void PxPhysicsEnvironment::SetDestructibleStrength(PHY_IPhysicsController *piece, float strength)
{
	if (PxDestructible *d = DestructibleOf(piece)) {
		d->strength = std::max(strength, 1e-3f);
	}
}

int PxPhysicsEnvironment::Explode(const MT_Vector3 &point, float radius, float amount)
{
	if (m_destructionDirty) {
		BuildDestructibles();
	}
	const PxVec3 p((float)point[0], (float)point[1], (float)point[2]);
	int hit = 0;
	const std::vector<PxDestructible *> all = m_destructibles;
	for (PxDestructible *d : all) {
		if (!d->built) {
			continue;
		}
		bool near = false;
		for (PxDestructionGroup *g : d->groups) {
			if (g->body && !g->removing) {
				PxBounds3 b = g->body->getWorldBounds();
				b.fattenFast(radius);
				near = near || b.contains(p);
			}
		}
		if (near && DamageGroups(d, p, radius, amount)) {
			d->lastScript = m_destructionFrame;
			hit++;
			/* what broke loose is thrown out from the centre (1 m/s for each
			 * unit of damage there, less further out) */
			const float reach = radius + d->size;
			for (PxDestructionGroup *g : d->groups) {
				if (g->anchored || g->removing || !g->body) {
					continue;
				}
				const PxVec3 c = g->body->getGlobalPose().transform(g->body->getCMassLocalPose().p);
				const PxVec3 out = c - p;
				const float dist = out.magnitude();
				if (dist >= reach || dist < 1e-6f) {
					continue;
				}
				g->body->setLinearVelocity(g->body->getLinearVelocity() + out * (amount * (1.0f - dist / reach) / dist));
			}
		}
	}
	return hit;
}

int PxPhysicsEnvironment::GetDestructionActivity(PHY_IPhysicsController *piece)
{
	PxDestructible *d = DestructibleOf(piece);
	if (!d) {
		return -1;
	}
	/* Green breaking (a split in the last frames), Blue damaged by a script
	 * (just now), Yellow once the Destruction Budget took broken-off pieces
	 * of it (its debris is kept down), White whole or at rest */
	const int f = m_destructionFrame;
	if (f - d->lastSplit < HOLD) {
		return 1;
	}
	if (f - d->lastScript < HOLD) {
		return 3;
	}
	if (d->lastBudget >= 0) {
		return 2;
	}
	return 0;
}
