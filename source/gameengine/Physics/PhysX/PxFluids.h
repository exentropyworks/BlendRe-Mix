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

/** \file PxFluids.h
 *  \ingroup physphysx
 *
 * BGE-Remix P11 (B3): fluid volumes, water and lava. Make Fluid Volume
 * (Python) marks a mesh (ID property bge_fluid, with its type, density,
 * drag, current and splashes); the object is a ghost, its collision shape
 * the volume (a box or a convex hull) and its surface the top of it. Every
 * physics step each moving body in a volume is pushed up by the weight of
 * the fluid it displaces (points spread through its collision shapes, each
 * a share of its volume, pushing where they are, so things turn upright),
 * slowed by the drag, measured against the current, and so carried along.
 * A body crossing the surface fast makes a splash (the game shows it, with
 * Remix's GPU particles). Volumes with forces, not a liquid.
 */

#ifndef __PXFLUIDS_H__
#define __PXFLUIDS_H__

#include <map>
#include <vector>

#include "foundation/PxBounds3.h"
#include "foundation/PxPlane.h"
#include "foundation/PxTransform.h"
#include "foundation/PxVec3.h"

class PxPhysicsController;

namespace physx {
class PxRigidActor;
class PxShape;
}

/* one convex part of a volume (one of its collision shapes) */
struct PxFluidPart
{
	std::vector<physx::PxPlane> planes;  /* the actor's frame, normals outward */
	std::vector<std::vector<physx::PxVec3> > loops;  /* its faces (the actor's frame) */
	physx::PxBounds3 bounds;             /* the actor's frame */
};

/* a fluid volume */
struct PxFluidVolume
{
	PxPhysicsController *ctrl;
	int type;                            /* 0 water, 1 lava */
	float density;                       /* kg/m3 */
	float drag;                          /* per second */
	physx::PxVec3 current;               /* m/s, along the volume's own axes */
	bool splashes;
	std::vector<PxFluidPart> parts;
	/* what the parts were read from: each shape and its bounds in the
	 * actor's frame (read again when they change: a rescaled volume) */
	std::vector<const physx::PxShape *> shapes;
	std::vector<physx::PxBounds3> shapeBounds;
	bool built, failed;
	/* this step */
	physx::PxTransform pose;
	std::vector<std::vector<physx::PxPlane> > worldPlanes;  /* per part */
	physx::PxBounds3 worldBounds;
	physx::PxVec3 worldCurrent;
	std::map<const physx::PxRigidActor *, float> share;  /* each body's share under its surface */
	int lastSplash;                      /* the frame (the Remix View) */
	PxFluidVolume();
};

/* a point of a body's collision shapes: its place (the actor's frame), the
 * volume it stands for, the size of its cell */
struct PxFluidSample
{
	physx::PxVec3 p;
	float w;
	float h;
};

/* what a body's points are, and what it did in the volumes */
struct PxFluidBody
{
	std::vector<const physx::PxShape *> shapes;  /* what the points were made from */
	std::vector<PxFluidSample> samples;
	float volume;                        /* m3 */
	float sub;                           /* the share under a surface at the last step */
	double lastSplash;                   /* the fluid time of its last splash */
	int state;                           /* -1 in none, 1 it floats, 2 it sinks */
	bool seen;
	PxFluidBody() : volume(0.0f), sub(0.0f), lastSplash(-1e9), state(-1), seen(false) {}
};

#endif  /* __PXFLUIDS_H__ */
