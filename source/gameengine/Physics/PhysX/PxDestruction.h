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

/** \file PxDestruction.h
 *  \ingroup physphysx
 *
 * BGE-Remix P11 (B2): destructibles, broken by NVIDIA Blast (BSD 3-clause,
 * from the PhysX repo). Make Destructible (Python) cuts an object into
 * pieces with Cell Fracture and parents them to the largest; each piece is
 * a game object with its own controller. Here, the pieces become one Blast
 * asset (its bonds found from the pieces' shared faces), and the pieces
 * Blast holds together (an actor) share one PhysX rigid body, a group: each
 * piece's controller is a shard of it (no actor of its own; its shapes on
 * the group's body). Impacts, explosions and script damage break bonds; the
 * stress solver loads an anchored group with its weight; when Blast splits
 * a group, each new one gets its own body, at the old one's speed there.
 * Without Blast (WITH_BLAST off) a destructible stays whole.
 */

#ifndef __PXDESTRUCTION_H__
#define __PXDESTRUCTION_H__

#include <string>
#include <vector>

#include "foundation/PxTransform.h"
#include "foundation/PxVec3.h"

class PxPhysicsController;
struct PxDestructible;
struct NvBlastActor;

namespace physx {
class PxRigidDynamic;
class PxShape;
}

/* the pieces Blast holds together: one rigid body */
struct PxDestructionGroup
{
	PxDestructible *owner;
	physx::PxRigidDynamic *body;     /* kinematic while anchored (bonded to the world) */
	physx::PxTransform bodyFromRest; /* rest space (the pieces as the game started) to the body's frame */
	std::vector<int> pieces;         /* indices into owner->pieces */
	NvBlastActor *actor;
	bool anchored;
	bool original;                   /* the destructible as it started (not broken off) */
	bool removing;                   /* the budget took it: its pieces' objects are being ended */
	double born;                     /* the game time it was made */
	int serial;                      /* (oldest first, then this) */
	PxDestructionGroup();
	/* rest space to the world now */
	physx::PxTransform RestToWorld() const;
};

/* a piece's place in its group */
struct PxShard
{
	PxDestructible *owner;
	int index;                       /* into owner->pieces */
	PxDestructionGroup *group;
	physx::PxTransform local;        /* the piece in its group's body's frame */
	PxShard() : owner(NULL), index(-1), group(NULL), local(physx::PxIdentity) {}
};

/* one destructible: its pieces, its Blast asset and family, its groups */
struct PxDestructible
{
	std::string key;                 /* the parent piece's name */
	std::vector<PxPhysicsController *> pieces;  /* NULL once removed */
	std::vector<PxShard> shards;
	std::vector<physx::PxTransform> rest;       /* each piece's pose as the game started */
	std::vector<float> volume;
	std::vector<physx::PxVec3> centroid;        /* rest space */
	int root;                        /* the parent piece */
	float strength;                  /* impulse (N s) that breaks a bond where it lands */
	bool anchored;                   /* its bottom pieces held by the world */
	float size;                      /* a piece's typical size (m) */
	float mass;
	int bonds;
	int bondsBroken;
	std::vector<PxDestructionGroup *> groups;
	bool built, failed;
	/* the Remix View: the frames of the last split, budget removal, script damage */
	int lastSplit, lastBudget, lastScript;
	/* Blast (NvBlast.h types, kept opaque here) */
	void *assetMem, *familyMem;
	void *asset, *family;
	void *stress;                    /* Nv::Blast::ExtStressSolver */
	std::vector<char> scratch;
	PxDestructible();
};

#endif  /* __PXDESTRUCTION_H__ */
