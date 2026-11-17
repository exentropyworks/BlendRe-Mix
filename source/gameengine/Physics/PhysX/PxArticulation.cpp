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

/** \file PxArticulation.cpp
 *  \ingroup physx
 *
 * BGE-Remix P11 (B1): articulations (PxArticulation.h), PxPhysicsEnvironment's
 * part. The Rigid Body Joint types map onto PhysX's articulation joints:
 *
 *   Ball                  spherical, every axis free
 *   Hinge                 revolute about the joint's X (its limits)
 *   Cone Twist            spherical, twist and both swings limited as set
 *   Generic 6DOF          every axis locked:       fixed
 *                         one linear axis moving:  prismatic
 *                         only the twist moving:   revolute
 *                         rotations only:          spherical
 *                         (anything else stays an ordinary joint)
 *
 * The 6DOF motors and springs become the joint's drives. The joint frames are
 * the ones P6 gives its PhysX joints (X along the constraint's axis).
 */

#include "PxArticulation.h"
#include "PxPhysicsEnvironment.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <deque>
#include <set>

#include "PxPhysicsAPI.h"

#include "PxPhysicsController.h"
#include "PxSystem.h"

#include "PHY_DynamicTypes.h"

using namespace physx;

namespace {

/* the articulation joint for a constraint (PxArticulationJointType), or -1 */
int joint_kind(int type, const float lim[6][2])
{
	switch (type) {
		case PHY_POINT2POINT_CONSTRAINT:
		case PHY_CONE_TWIST_CONSTRAINT:
			return PxArticulationJointType::eSPHERICAL;
		case PHY_LINEHINGE_CONSTRAINT:
			return PxArticulationJointType::eREVOLUTE;
		case PHY_GENERIC_6DOF_CONSTRAINT: {
			int lin = 0, ang = 0;
			for (int i = 0; i < 3; i++) {
				lin += lim[i][0] != lim[i][1] ? 1 : 0;
				ang += lim[i + 3][0] != lim[i + 3][1] ? 1 : 0;
			}
			if (lin == 0 && ang == 0) {
				return PxArticulationJointType::eFIX;
			}
			if (lin == 1 && ang == 0) {
				return PxArticulationJointType::ePRISMATIC;
			}
			if (lin == 0 && ang == 1 && lim[3][0] != lim[3][1]) {
				return PxArticulationJointType::eREVOLUTE;
			}
			if (lin == 0 && ang >= 2) {
				return PxArticulationJointType::eSPHERICAL;
			}
			return -1;
		}
		default:
			/* (the Angular hinge leaves the bodies free to move apart) */
			return -1;
	}
}

/* how many axes the joint leaves moving (an articulation's tree takes the
 * stiffest first); 6: none it can take */
int joint_freedom(int type, const float lim[6][2])
{
	if (joint_kind(type, lim) < 0) {
		return 6;
	}
	int n = 0;
	switch (type) {
		case PHY_POINT2POINT_CONSTRAINT:
			return 3;
		case PHY_LINEHINGE_CONSTRAINT:
			return 1;
		case PHY_CONE_TWIST_CONSTRAINT:
			for (int i = 3; i < 6; i++) {
				n += lim[i][0] != lim[i][1] ? 1 : 0;
			}
			return n;
		default:
			for (int i = 0; i < 6; i++) {
				n += lim[i][0] != lim[i][1] ? 1 : 0;
			}
			return n;
	}
}

const PxArticulationAxis::Enum AXES[6] = {PxArticulationAxis::eX, PxArticulationAxis::eY,
                                          PxArticulationAxis::eZ, PxArticulationAxis::eTWIST,
                                          PxArticulationAxis::eSWING1, PxArticulationAxis::eSWING2};

/* the axis asked for, or (-1) the joint's first moving one (turning first);
 * -1: none */
int moving_axis(PxArticulationJointReducedCoordinate *j, int axis)
{
	if (axis >= 0) {
		return axis <= 5 ? axis : -1;
	}
	const int order[6] = {3, 4, 5, 0, 1, 2};
	for (int i : order) {
		if (j->getMotion(AXES[i]) != PxArticulationMotion::eLOCKED) {
			return i;
		}
	}
	return -1;
}

PxArticulationLink *link_of(PxPhysicsController *ctrl)
{
	PxRigidActor *a = ctrl ? ctrl->GetActor() : nullptr;
	return (a && a->getType() == PxActorType::eARTICULATION_LINK) ? static_cast<PxArticulationLink *>(a) : nullptr;
}

}  /* namespace */

/* ------------------------------------------------------------------------- */

bool PxPhysicsEnvironment::ApplyArticulationJoint(Constraint *c, int param)
{
	PxArticulationLink *link = link_of(c ? c->link : nullptr);
	PxArticulationJointReducedCoordinate *j = link ? link->getInboundJoint() : nullptr;
	if (!j) {
		return true;
	}
	const int kind = joint_kind(c->type, c->limits);
	if (kind < 0) {
		return false;
	}
	/* each axis: its motion and (limited) its range */
	PxArticulationMotion::Enum motion[6];
	float lo[6], hi[6];
	for (int i = 0; i < 6; i++) {
		motion[i] = PxArticulationMotion::eLOCKED;
		lo[i] = hi[i] = 0.0f;
	}
	/* (reversed: the articulation's coordinates are the joint's turned over) */
	const float sign = c->reversed ? -1.0f : 1.0f;
	auto from_limits = [&](int i, float scale) {
		float l = c->limits[i][0], h = c->limits[i][1];
		if (c->reversed && l <= h) {
			const float t = l;
			l = -h;
			h = -t;
		}
		if (l > h) {
			motion[i] = PxArticulationMotion::eFREE;
		}
		else if (l < h) {
			if (i >= 3) {
				/* (PhysX: strictly inside one turn either way) */
				l = std::max(l, -PxPi * 0.999f);
				h = std::min(h, PxPi * 0.999f);
			}
			motion[i] = PxArticulationMotion::eLIMITED;
			lo[i] = l * scale;
			hi[i] = h * scale;
		}
	};
	switch (c->type) {
		case PHY_POINT2POINT_CONSTRAINT:
			for (int i = 3; i < 6; i++) {
				motion[i] = PxArticulationMotion::eFREE;
			}
			break;
		case PHY_LINEHINGE_CONSTRAINT:
			from_limits(3, 1.0f);
			break;
		case PHY_CONE_TWIST_CONSTRAINT:
			/* (an unlimited swing: free; P6's cone twist starts free; a limited
			 * swing pair is a pyramid here, not Bullet's cone) */
			for (int i = 3; i < 6; i++) {
				from_limits(i, 1.0f);
			}
			break;
		case PHY_GENERIC_6DOF_CONSTRAINT:
			for (int i = 0; i < 6; i++) {
				from_limits(i, i < 3 ? c->linScale[i] : 1.0f);
			}
			break;
		default:
			break;
	}
	/* PhysX: the joint's type and its axes' motions change only while the
	 * articulation is out of the scene */
	bool reshape = j->getJointType() != (PxArticulationJointType::Enum)kind;
	for (int i = 0; i < 6 && !reshape; i++) {
		reshape = j->getMotion(AXES[i]) != motion[i];
	}
	PxArticulationReducedCoordinate *art = &link->getArticulation();
	PxScene *scene = art->getScene();
	if (reshape) {
		if (scene) {
			if (PxArticulationGroup *g = c->link->GetArticulation()) {
				for (PxPhysicsController *l : g->links) {
					ForgetPairs(l);
				}
			}
			scene->removeArticulation(*art);
		}
		j->setJointType((PxArticulationJointType::Enum)kind);
		for (int i = 0; i < 6; i++) {
			j->setMotion(AXES[i], motion[i]);
		}
	}
	for (int i = 0; i < 6; i++) {
		if (motion[i] == PxArticulationMotion::eLIMITED) {
			j->setLimitParams(AXES[i], PxArticulationLimit(lo[i], hi[i]));
		}
	}
	/* the 6DOF motors (a speed, a force) and springs (Bullet's: resting where
	 * the joint is when they are set) as drives */
	for (int i = 0; i < 6; i++) {
		const PxArticulationAxis::Enum axis = AXES[i];
		if (motion[i] == PxArticulationMotion::eLOCKED) {
			continue;
		}
		if (c->spring[i]) {
			j->setDriveParams(axis, PxArticulationDrive(c->springStiffness[i], c->springDamping[i], PX_MAX_F32));
			if (param < 0 || param == 12 + i) {
				j->setDriveTarget(axis, j->getJointPosition(axis));
			}
		}
		else if (c->motor[i]) {
			j->setDriveParams(axis, PxArticulationDrive(0.0f, 1e5f, c->motorForce[i]));
			const float v = i < 3 ? c->motorVelocity[i] / std::max(c->linScale[i], 1e-6f) : c->motorVelocity[i];
			j->setDriveVelocity(axis, v * sign);
		}
		else if (param < 0 || param == 6 + i || param == 12 + i) {
			/* (a drive the game set through the articulation is kept while
			 * other settings change) */
			j->setDriveParams(axis, PxArticulationDrive(0.0f, 0.0f, 0.0f, PxArticulationDriveType::eNONE));
		}
	}
	if (reshape && scene) {
		scene->addArticulation(*art);
	}
	return true;
}

void PxPhysicsEnvironment::BuildArticulations()
{
	m_articulationsDirty = false;
	std::vector<PxPhysicsController *> roots;
	for (PxPhysicsController *ctrl : m_controllers) {
		if (ctrl->GetInfo().articulation && !ctrl->GetArticulation()) {
			roots.push_back(ctrl);
		}
	}
	for (PxPhysicsController *root : roots) {
		if (!root->GetArticulation()) {
			if (PxArticulationGroup *g = BuildArticulation(root)) {
				m_articulations.push_back(g);
			}
		}
	}
}

PxArticulationGroup *PxPhysicsEnvironment::BuildArticulation(PxPhysicsController *root)
{
	PxSystem *sys = PxSystem::Get();
	if (root->IsSuspended() || root->m_articulationFailed) {
		/* (parented, or a ragdoll following its bones: none until it is let go) */
		return nullptr;
	}
	if (!sys || !m_scene || !root->GetDynamic() || root->IsKinematic() || root->GetCharacter() ||
	    root->GetDeformable())
	{
		if (!root->m_articulationWarned) {
			root->m_articulationWarned = true;
			printf("BGE-Remix PhysX: an articulation's root must be a Rigid Body or Dynamic object; left as it is\n");
		}
		return nullptr;
	}
	/* the tree, from the root: the stiffest joint reachable first (fewest
	 * moving axes, then the oldest), so that where joints close a loop the
	 * loosest one is left ordinary (a rope bridge's tie, not its hinges) */
	PxArticulationGroup *g = new PxArticulationGroup();
	g->root = root;
	g->fixed = root->GetInfo().articulation == 2;
	g->links.push_back(root);
	g->joints.push_back(0);
	g->parents.push_back(-1);
	std::set<PxPhysicsController *> inTree = {root};
	std::set<int> seen;
	struct Edge {
		int freedom, id, at;
		bool operator<(const Edge &o) const { return freedom != o.freedom ? freedom < o.freedom : id < o.id; }
	};
	std::set<Edge> frontier;
	auto reach = [&](int at) {
		for (int id : g->links[at]->m_constraints) {
			Constraint *c = GetConstraint(id);
			if (c && !seen.count(id)) {
				frontier.insert({joint_freedom(c->type, c->limits), id, at});
			}
		}
	};
	reach(0);
	while (!frontier.empty()) {
		const Edge e = *frontier.begin();
		frontier.erase(frontier.begin());
		if (seen.count(e.id)) {
			continue;
		}
		seen.insert(e.id);
		const int at = e.at;
		PxPhysicsController *node = g->links[at];
		const int id = e.id;
		{
			Constraint *c = GetConstraint(id);
			if (!c || !c->joint || c->link) {
				continue;
			}
			PxPhysicsController *other = c->c0 == node ? c->c1 : c->c0;
			c->notArticulated = nullptr;
			if (other && inTree.count(other)) {
				c->notArticulated = "it closes a loop (an articulation is a tree)";
			}
			else if (other && (other->GetArticulation() || other->GetInfo().articulation || other->GetCharacter() ||
			                   other->GetDeformable() || other->IsSuspended()))
			{
				c->notArticulated = "the object it joins cannot be a link (another articulation, a character, "
				                    "a soft body or a suspended object)";
			}
			else if (!other || !other->GetDynamic() || other->IsKinematic()) {
				/* to the world or a still object: an ordinary joint */
				c->notArticulated = "joined to the world or to an object that does not move";
			}
			else if (joint_kind(c->type, c->limits) < 0) {
				c->notArticulated = "an articulation has no joint of this kind (Angular, or a 6DOF with "
				                    "more than one sliding axis or sliding and turning together)";
			}
			if (c->notArticulated) {
				g->others.push_back(id);
				continue;
			}
			inTree.insert(other);
			g->links.push_back(other);
			g->joints.push_back(id);
			g->parents.push_back(at);
			reach((int)g->links.size() - 1);
		}
	}
	if (g->links.size() < 2) {
		/* nothing joined to it: the root stays a rigid body */
		delete g;
		return nullptr;
	}

	PxArticulationReducedCoordinate *art = sys->Physics()->createArticulationReducedCoordinate();
	if (!art) {
		delete g;
		return nullptr;
	}
	g->art = art;
	art->setArticulationFlag(PxArticulationFlag::eFIX_BASE, g->fixed);
	/* a drive's maxForce is a force (as the 6DOF motors'), not an impulse */
	art->setArticulationFlag(PxArticulationFlag::eDRIVE_LIMITS_ARE_FORCES, true);
	art->setSolverIterationCounts((PxU32)std::max(4, std::min(m_numIterations * 2, 64)), 1);
	std::vector<PxArticulationLink *> links(g->links.size(), nullptr);
	/* where each body is and how it moves (the articulation goes on from there) */
	std::vector<PxTransform> poses(g->links.size());
	std::vector<PxVec3> lin(g->links.size(), PxVec3(0.0f)), ang(g->links.size(), PxVec3(0.0f));
	for (size_t i = 0; i < g->links.size(); i++) {
		PxPhysicsController *ctrl = g->links[i];
		poses[i] = ctrl->GetActor()->getGlobalPose();
		if (PxRigidDynamic *body = ctrl->GetDynamic()) {
			lin[i] = body->getLinearVelocity();
			ang[i] = body->getAngularVelocity();
		}
	}
	for (size_t i = 0; i < g->links.size(); i++) {
		const PxTransform &pose = poses[i];
		links[i] = art->createLink(i ? links[g->parents[i]] : nullptr, pose);
		if (!links[i]) {
			art->release();
			delete g;
			return nullptr;
		}
	}
	/* the tree's joints go (each becomes a link's inbound joint) and the ones
	 * left ordinary move onto the links, before the old rigid bodies are
	 * released (no joint is left on one) */
	for (size_t i = 1; i < g->links.size(); i++) {
		Constraint *c = GetConstraint(g->joints[i]);
		if (c->joint) {
			c->joint->release();
			c->joint = nullptr;
		}
	}
	auto actor_for = [&](PxPhysicsController *ctrl) -> PxRigidActor * {
		if (!ctrl) {
			return nullptr;
		}
		const int at = g->LinkIndex(ctrl);
		return at >= 0 ? static_cast<PxRigidActor *>(links[at]) : ctrl->GetActor();
	};
	for (int id : g->others) {
		Constraint *c = GetConstraint(id);
		if (c && c->joint) {
			c->joint->setActors(actor_for(c->c0), actor_for(c->c1));
		}
	}
	/* the bodies become the links (their old rigid bodies leave the scene) */
	for (size_t i = 0; i < g->links.size(); i++) {
		PxPhysicsController *ctrl = g->links[i];
		ForgetPairs(ctrl);
		ctrl->BecomeLink(links[i], g);
		if (i == 0) {
			continue;
		}
		Constraint *c = GetConstraint(g->joints[i]);
		PxPhysicsController *parent = g->links[g->parents[i]];
		PxArticulationJointReducedCoordinate *j = links[i]->getInboundJoint();
		if (c->c0 == parent) {
			j->setParentPose(c->frameA);
			j->setChildPose(c->frameB);
		}
		else {
			j->setParentPose(c->frameB);
			j->setChildPose(c->frameA);
		}
		c->reversed = c->c0 != parent;
		c->link = ctrl;
		ApplyArticulationJoint(c);
	}
	if (!m_scene->addArticulation(*art)) {
		printf("BGE-Remix PhysX: the articulation from \"%s\" could not join the scene; its bodies and joints "
		       "stay ordinary ones\n", root->GetActor() && root->GetActor()->getName() ? root->GetActor()->getName() : "?");
		fflush(stdout);
		/* (the bodies and joints back as they were; not tried again) */
		root->m_articulationFailed = true;
		DismantleArticulation(g);
		return nullptr;
	}
	else {
		/* the bodies' motion: the root's speed, and each joint's from the
		 * difference between its two bodies' (in the joint's frame) */
		if (!g->fixed) {
			art->setRootLinearVelocity(lin[0], false);
			art->setRootAngularVelocity(ang[0], false);
		}
		for (size_t i = 1; i < g->links.size(); i++) {
			PxArticulationJointReducedCoordinate *j = links[i]->getInboundJoint();
			const int p = g->parents[i];
			const PxTransform frame = poses[p] * j->getParentPose();
			const PxVec3 w = frame.q.rotateInv(ang[i] - ang[p]);
			/* (a slide: the child's speed against the point of the parent under it) */
			const PxVec3 at = poses[i].p - poses[p].p;
			const PxVec3 v = frame.q.rotateInv(lin[i] - (lin[p] + ang[p].cross(at)));
			const float rel[6] = {v.x, v.y, v.z, w.x, w.y, w.z};
			for (int k = 0; k < 6; k++) {
				if (j->getMotion(AXES[k]) != PxArticulationMotion::eLOCKED && std::fabs(rel[k]) > 1e-5f) {
					j->setJointVelocity(AXES[k], rel[k]);
				}
			}
		}
		art->updateKinematic(PxArticulationKinematicFlag::eVELOCITY);
	}
	printf("BGE-Remix PhysX: articulation of %d links (%s)%s\n", (int)g->links.size(),
	       g->fixed ? "fixed to the world" : "free", g->others.empty() ? "" : ", some joints left ordinary");
	fflush(stdout);
	return g;
}

void PxPhysicsEnvironment::DismantleArticulation(PxArticulationGroup *g)
{
	if (!g) {
		return;
	}
	m_articulations.erase(std::remove(m_articulations.begin(), m_articulations.end(), g), m_articulations.end());
	struct State {
		PxTransform pose;
		PxVec3 lin, ang;
	};
	std::vector<State> state(g->links.size());
	for (size_t i = 0; i < g->links.size(); i++) {
		PxArticulationLink *l = link_of(g->links[i]);
		state[i].pose = l ? l->getGlobalPose() : PxTransform(PxIdentity);
		state[i].lin = l ? l->getLinearVelocity() : PxVec3(0.0f);
		state[i].ang = l ? l->getAngularVelocity() : PxVec3(0.0f);
		ForgetPairs(g->links[i]);
	}
	if (g->art) {
		if (g->art->getScene()) {
			g->art->getScene()->removeArticulation(*g->art);
		}
	}
	for (size_t i = 0; i < g->links.size(); i++) {
		PxPhysicsController *ctrl = g->links[i];
		ctrl->LeaveLink(state[i].pose, state[i].lin, state[i].ang);
		if (ctrl->m_inScene && ctrl->GetActor()) {
			m_scene->addActor(*ctrl->GetActor());
			if (PxRigidDynamic *body = ctrl->GetDynamic()) {
				body->setSolverIterationCounts((PxU32)std::max(1, std::min(m_numIterations, 32)), 1);
				body->setRigidBodyFlag(PxRigidBodyFlag::eENABLE_CCD, m_ccdMode != 0);
			}
		}
	}
	/* the joints left ordinary move back onto the bodies before the links
	 * are released */
	for (int id : g->others) {
		Constraint *c = GetConstraint(id);
		if (c && c->joint) {
			c->joint->setActors(c->c0 ? c->c0->GetActor() : nullptr, c->c1 ? c->c1->GetActor() : nullptr);
		}
		if (c) {
			c->notArticulated = nullptr;
		}
	}
	if (g->art) {
		g->art->release();  /* (its links with it) */
		g->art = nullptr;
	}
	/* the tree's joints come back as P6 makes them */
	for (size_t i = 1; i < g->joints.size(); i++) {
		if (Constraint *c = GetConstraint(g->joints[i])) {
			c->link = nullptr;
			RestoreJoint(c);
		}
	}
	delete g;
	/* (the rest is built again at the next step, without what was removed) */
	m_articulationsDirty = true;
}

void PxPhysicsEnvironment::ArticulationTeleport(PxPhysicsController *ctrl, const PxTransform &t)
{
	PxArticulationGroup *g = ctrl->GetArticulation();
	if (!g || !g->art) {
		return;
	}
	if (ctrl != g->root) {
		PxSystem::WarnOnce("art-move", "an articulation's links follow their joints: move its root instead");
		return;
	}
	g->art->setRootGlobalPose(t, true);
	if (g->art->getScene()) {
		g->art->updateKinematic(PxArticulationKinematicFlag::ePOSITION);
	}
}

void PxPhysicsEnvironment::ArticulationSetVelocity(PxPhysicsController *ctrl, const PxVec3 *lin, const PxVec3 *ang)
{
	PxArticulationGroup *g = ctrl->GetArticulation();
	if (!g || !g->art) {
		return;
	}
	if (ctrl != g->root || g->fixed) {
		PxSystem::WarnOnce("art-velocity", "an articulation's links move by their joints: set the speed of a free "
		                                   "articulation's root, or push a link (a force)");
		return;
	}
	if (lin) {
		g->art->setRootLinearVelocity(*lin, true);
	}
	if (ang) {
		g->art->setRootAngularVelocity(*ang, true);
	}
	if (g->art->getScene()) {
		g->art->updateKinematic(PxArticulationKinematicFlag::eVELOCITY);
	}
}

bool PxPhysicsEnvironment::ArticulationJointState(int constraintId, int axis, float *r_pos, float *r_vel)
{
	Constraint *c = GetConstraint(constraintId);
	PxArticulationLink *link = link_of(c ? c->link : nullptr);
	PxArticulationJointReducedCoordinate *j = link ? link->getInboundJoint() : nullptr;
	axis = j ? moving_axis(j, axis) : -1;
	if (axis < 0) {
		return false;
	}
	const float scale = (axis < 3 ? std::max(c->linScale[axis], 1e-6f) : 1.0f) * (c->reversed ? -1.0f : 1.0f);
	if (r_pos) {
		*r_pos = j->getJointPosition(AXES[axis]) / scale;
	}
	if (r_vel) {
		*r_vel = j->getJointVelocity(AXES[axis]) / scale;
	}
	return true;
}

bool PxPhysicsEnvironment::ArticulationSetDrive(int constraintId, int axis, const float *target, const float *velocity,
                                                float stiffness, float damping, float maxForce)
{
	Constraint *c = GetConstraint(constraintId);
	PxArticulationLink *link = link_of(c ? c->link : nullptr);
	PxArticulationJointReducedCoordinate *j = link ? link->getInboundJoint() : nullptr;
	axis = j ? moving_axis(j, axis) : -1;
	if (axis < 0 || j->getMotion(AXES[axis]) == PxArticulationMotion::eLOCKED) {
		return false;
	}
	const float scale = (axis < 3 ? std::max(c->linScale[axis], 1e-6f) : 1.0f) * (c->reversed ? -1.0f : 1.0f);
	j->setDriveParams(AXES[axis], PxArticulationDrive(std::max(stiffness, 0.0f), std::max(damping, 0.0f),
	                                                  maxForce > 0.0f ? maxForce : PX_MAX_F32));
	if (target) {
		j->setDriveTarget(AXES[axis], *target * scale, true);
	}
	if (velocity) {
		j->setDriveVelocity(AXES[axis], *velocity * scale, true);
	}
	return true;
}

/* ------------------------------------------------------------------------- */
/* for Python (PHY_IPhysicsEnvironment) */

bool PxPhysicsEnvironment::GetArticulation(PHY_IPhysicsController *ctrl, PHY_ArticulationInfo *info)
{
	if (m_articulationsDirty) {
		BuildArticulations();
	}
	PxPhysicsController *px = static_cast<PxPhysicsController *>(ctrl);
	PxArticulationGroup *g = (px && m_controllers.count(px)) ? px->GetArticulation() : nullptr;
	if (!g) {
		return false;
	}
	if (info) {
		info->root = g->root;
		info->fixed = g->fixed;
		info->links.assign(g->links.begin(), g->links.end());
		info->joints = g->joints;
		info->parents = g->parents;
		info->ordinary = g->others;
	}
	return true;
}

bool PxPhysicsEnvironment::GetArticulationJoint(int constraintId, int axis, float *pos, float *vel)
{
	if (m_articulationsDirty) {
		BuildArticulations();
	}
	return ArticulationJointState(constraintId, axis, pos, vel);
}

bool PxPhysicsEnvironment::SetArticulationDrive(int constraintId, int axis, const float *target,
                                                const float *velocity, float stiffness, float damping,
                                                float maxForce)
{
	if (m_articulationsDirty) {
		BuildArticulations();
	}
	return ArticulationSetDrive(constraintId, axis, target, velocity, stiffness, damping, maxForce);
}

const char *PxPhysicsEnvironment::GetArticulationNote(int constraintId)
{
	if (m_articulationsDirty) {
		BuildArticulations();
	}
	Constraint *c = GetConstraint(constraintId);
	return c ? c->notArticulated : nullptr;
}

int PxPhysicsEnvironment::GetArticulationJointActivity(int constraintId, int *r_axis, float *r_pos)
{
	if (m_articulationsDirty) {
		BuildArticulations();
	}
	Constraint *c = GetConstraint(constraintId);
	PxArticulationLink *link = link_of(c ? c->link : nullptr);
	PxArticulationJointReducedCoordinate *j = link ? link->getInboundJoint() : nullptr;
	if (!j) {
		return -1;
	}
	const int first = moving_axis(j, -1);
	if (r_axis) {
		*r_axis = first;
	}
	if (r_pos) {
		*r_pos = first >= 0 ? j->getJointPosition(AXES[first]) * (c->reversed ? -1.0f : 1.0f) /
		                      (first < 3 ? std::max(c->linScale[first], 1e-6f) : 1.0f) : 0.0f;
	}
	bool limit = false, driven = false, moving = false;
	for (int i = 0; i < 6; i++) {
		const PxArticulationAxis::Enum axis = AXES[i];
		const PxArticulationMotion::Enum motion = j->getMotion(axis);
		if (motion == PxArticulationMotion::eLOCKED) {
			continue;
		}
		const float pos = j->getJointPosition(axis), vel = j->getJointVelocity(axis);
		/* (about a degree, or a centimetre in the joint's own units) */
		const float close_by = i < 3 ? 0.01f * std::max(c->linScale[i], 1e-6f) : 0.0175f;
		if (motion == PxArticulationMotion::eLIMITED) {
			const PxArticulationLimit l = j->getLimitParams(axis);
			limit |= pos <= l.low + close_by || pos >= l.high - close_by;
		}
		const PxArticulationDrive d = j->getDriveParams(axis);
		driven |= d.driveType != PxArticulationDriveType::eNONE && d.maxForce > 0.0f &&
		          (d.stiffness > 0.0f || (d.damping > 0.0f && j->getDriveVelocity(axis) != 0.0f));
		moving |= fabsf(vel) > 0.05f;
	}
	return limit ? 2 : (driven ? 3 : (moving ? 1 : 0));
}
