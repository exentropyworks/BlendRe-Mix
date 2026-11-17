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

/** \file PxArticulation.h
 *  \ingroup physx
 *
 * BGE-Remix P11 (B1): a tree of bodies joined by Rigid Body Joint
 * constraints, solved by PhysX as one articulation (its joints never drift
 * apart, whatever the masses). The object whose bge_articulation is set is
 * the root: 1 it moves freely (a ragdoll), 2 it is fixed to the world (a
 * robot arm, a hanging chain). Built by PxPhysicsEnvironment at the step
 * after the root and its joints exist; taken apart again (bodies and
 * ordinary joints back) when one of its objects or joints is removed.
 */

#ifndef __PXARTICULATION_H__
#define __PXARTICULATION_H__

#include <cstddef>
#include <vector>

class PxPhysicsController;

namespace physx {
class PxArticulationReducedCoordinate;
}

struct PxArticulationGroup {
	physx::PxArticulationReducedCoordinate *art;
	PxPhysicsController *root;
	bool fixed;
	/* the links, the root first, each after its parent */
	std::vector<PxPhysicsController *> links;
	/* each link's inbound joint (its constraint id; 0 for the root) and parent
	 * (an index in links; -1 for the root) */
	std::vector<int> joints;
	std::vector<int> parents;
	/* joints of its bodies left as ordinary joints (a loop, a type an
	 * articulation has no joint for, a joint to an object outside it) */
	std::vector<int> others;

	PxArticulationGroup() : art(nullptr), root(nullptr), fixed(false) {}
	int LinkIndex(const PxPhysicsController *ctrl) const
	{
		for (std::size_t i = 0; i < links.size(); i++) {
			if (links[i] == ctrl) {
				return (int)i;
			}
		}
		return -1;
	}
};

#endif  /* __PXARTICULATION_H__ */
