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
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 *
 * The Original Code is Copyright (C) 2001-2002 by NaN Holding BV.
 * All rights reserved.
 *
 * The Original Code is: all of this file.
 *
 * Contributor(s): none yet.
 *
 * ***** END GPL LICENSE BLOCK *****
 */

/** \file gameengine/Converter/BL_ArmatureObject.cpp
 *  \ingroup bgeconv
 */


#include "BL_ArmatureObject.h"
#include "BL_ActionActuator.h"
#include "BL_Action.h"
#include "KX_BlenderSceneConverter.h"
#include "MEM_guardedalloc.h"
#include "BLI_blenlib.h"
#include "BLI_math.h"
#include "BLI_utildefines.h"
#include "BLI_ghash.h"
#include "BIK_api.h"
#include "BKE_action.h"
#include "BKE_armature.h"
#include "BKE_object.h"
#include "BKE_library.h"
#include "BKE_global.h"

extern "C" {
#include "BKE_animsys.h"
}

#include "BKE_constraint.h"
#include "CTR_Map.h"
#include "CTR_HashedPtr.h"
#include "MEM_guardedalloc.h"
#include "DNA_action_types.h"
#include "DNA_armature_types.h"
#include "DNA_object_types.h"
#include "DNA_scene_types.h"
#include "DNA_constraint_types.h"
#include "RNA_access.h"
#include "KX_PythonInit.h"
#include "KX_KetsjiEngine.h"

#include "EXP_ListWrapper.h"

#include "MT_Matrix4x4.h"
#include "KX_Scene.h"                        /* BGE-Remix P11 (B1) */
#include "KX_SG_BoneParentNodeRelationship.h"
#include "PHY_IPhysicsController.h"
#include "SG_Node.h"
extern "C" {
#include "BKE_idprop.h"
}

/** 
 * Move here pose function for game engine so that we can mix with GE objects
 * Principle is as follow:
 * Use Blender structures so that BKE_pose_where_is can be used unchanged
 * Copy the constraint so that they can be enabled/disabled/added/removed at runtime
 * Don't copy the constraints for the pose used by the Action actuator, it does not need them.
 * Scan the constraint structures so that the KX equivalent of target objects are identified and 
 * stored in separate list.
 * When it is about to evaluate the pose, set the KX object position in the obmat of the corresponding
 * Blender objects and restore after the evaluation.
 */
static void game_copy_pose(bPose **dst, bPose *src, int copy_constraint)
{
	bPose *out;
	bPoseChannel *pchan, *outpchan;
	GHash *ghash;
	
	/* the game engine copies the current armature pose and then swaps
	 * the object pose pointer. this makes it possible to change poses
	 * without affecting the original blender data. */

	if (!src) {
		*dst=NULL;
		return;
	}
	else if (*dst==src) {
		printf("game_copy_pose source and target are the same\n");
		*dst=NULL;
		return;
	}
	
	out= (bPose*)MEM_dupallocN(src);
	out->chanhash = NULL;
	out->agroups.first= out->agroups.last= NULL;
	out->ikdata = NULL;
	out->ikparam = MEM_dupallocN(src->ikparam);
	out->flag |= POSE_GAME_ENGINE;
	BLI_duplicatelist(&out->chanbase, &src->chanbase);

	/* remap pointers */
	ghash= BLI_ghash_new(BLI_ghashutil_ptrhash, BLI_ghashutil_ptrcmp, "game_copy_pose gh");

	pchan= (bPoseChannel *)src->chanbase.first;
	outpchan= (bPoseChannel *)out->chanbase.first;
	for (; pchan; pchan=pchan->next, outpchan=outpchan->next)
		BLI_ghash_insert(ghash, pchan, outpchan);

	for (pchan = (bPoseChannel *)out->chanbase.first; pchan; pchan = pchan->next) {
		pchan->parent= (bPoseChannel *)BLI_ghash_lookup(ghash, pchan->parent);
		pchan->child= (bPoseChannel *)BLI_ghash_lookup(ghash, pchan->child);

		if (copy_constraint) {
			ListBase listb;
			// copy all constraint for backward compatibility
			// BKE_constraints_copy NULLs listb, no need to make extern for this operation.
			BKE_constraints_copy(&listb, &pchan->constraints, false);
			pchan->constraints= listb;
		}
		else {
			BLI_listbase_clear(&pchan->constraints);
		}

		if (pchan->custom) {
			id_us_plus(&pchan->custom->id);
		}

		// fails to link, props are not used in the BGE yet.
#if 0
		if (pchan->prop)
			pchan->prop= IDP_CopyProperty(pchan->prop);
#endif
		pchan->prop= NULL;
	}

	BLI_ghash_free(ghash, NULL, NULL);
	// set acceleration structure for channel lookup
	BKE_pose_channels_hash_make(out);
	*dst=out;
}



/* Only allowed for Poses with identical channels */
static void game_blend_poses(bPose *dst, bPose *src, float srcweight, short mode)
{
	bPoseChannel *dchan;
	const bPoseChannel *schan;
	bConstraint *dcon, *scon;
	float dstweight;
	int i;

	if (mode == BL_Action::ACT_BLEND_BLEND)
	{
		dstweight = 1.0f - srcweight;
	} else if (mode == BL_Action::ACT_BLEND_ADD)
	{
		dstweight = 1.0f;
	} else {
		dstweight = 1.0f;
	}
	
	schan= (bPoseChannel *)src->chanbase.first;
	for (dchan = (bPoseChannel *)dst->chanbase.first; dchan; dchan=(bPoseChannel *)dchan->next, schan= (bPoseChannel *)schan->next) {
		// always blend on all channels since we don't know which one has been set
		/* quat interpolation done separate */
		if (schan->rotmode == ROT_MODE_QUAT) {
			float dquat[4], squat[4];
			
			copy_qt_qt(dquat, dchan->quat);
			copy_qt_qt(squat, schan->quat);
			// Normalize quaternions so that interpolation/multiplication result is correct.
			normalize_qt(dquat);
			normalize_qt(squat);

			if (mode==BL_Action::ACT_BLEND_BLEND)
				interp_qt_qtqt(dchan->quat, dquat, squat, srcweight);
			else {
				mul_fac_qt_fl(squat, srcweight);
				mul_qt_qtqt(dchan->quat, dquat, squat);
			}
			
			normalize_qt(dchan->quat);
		}

		for (i=0; i<3; i++) {
			/* blending for loc and scale are pretty self-explanatory... */
			dchan->loc[i] = (dchan->loc[i]*dstweight) + (schan->loc[i]*srcweight);
			dchan->size[i] = 1.0f + ((dchan->size[i]-1.0f)*dstweight) + ((schan->size[i]-1.0f)*srcweight);
			
			/* euler-rotation interpolation done here instead... */
			// FIXME: are these results decent?
			if (schan->rotmode)
				dchan->eul[i] = (dchan->eul[i]*dstweight) + (schan->eul[i]*srcweight);
		}
		for (dcon= (bConstraint *)dchan->constraints.first, scon= (bConstraint *)schan->constraints.first;
		     dcon && scon;
		     dcon = dcon->next, scon = scon->next)
		{
			/* no 'add' option for constraint blending */
			dcon->enforce= dcon->enforce*(1.0f-srcweight) + scon->enforce*srcweight;
		}
	}
	
	/* this pose is now in src time */
	dst->ctime= src->ctime;
}

BL_ArmatureObject::BL_ArmatureObject(
				void* sgReplicationInfo, 
				SG_Callbacks callbacks, 
				Object *armature,
				Scene *scene,
				int vert_deform_type)

:	KX_GameObject(sgReplicationInfo,callbacks),
	m_controlledConstraints(),
	m_poseChannels(),
	m_scene(scene), // maybe remove later. needed for BKE_pose_where_is
	m_lastframe(0.0),
	m_timestep(0.040),
	m_vert_deform_type(vert_deform_type),
	m_constraintNumber(0),
	m_channelNumber(0),
	m_lastapplyframe(0.0),
	m_ragdoll(false),
	m_ragdollSig(0.0),
	m_ragdollScanned(false)
{
	m_ragdollTimes[0] = m_ragdollTimes[1] = -1.0;
	m_origObjArma = armature; // Keep a copy of the original armature so we can fix drivers later
	m_objArma = BKE_object_copy(G.main, armature);
	m_objArma->data = BKE_armature_copy(G.main, (bArmature *)armature->data);
	// During object replication ob->data is increase, we decrease it now because we get a copy.
	id_us_min(&((bArmature *)m_origObjArma->data)->id);
	m_pose = m_objArma->pose;
	// need this to get iTaSC working ok in the BGE
	m_pose->flag |= POSE_GAME_ENGINE;
	memcpy(m_obmat, m_objArma->obmat, sizeof(m_obmat));

	// The side-effect of this method registers this object as "animatable" with the KX_Scene.
	GetActionManager();
}

BL_ArmatureObject::~BL_ArmatureObject()
{
	/* P11 (B1): the ragdoll's capsules forget it */
	for (KX_GameObject *c : m_ragdollWatched) {
		c->UnregisterObject(this);
	}
	m_ragdollWatched.clear();
	BL_ArmatureConstraint* constraint;
	while ((constraint = m_controlledConstraints.Remove()) != NULL) {
		delete constraint;
	}
	BL_ArmatureChannel* channel;
	while ((channel = static_cast<BL_ArmatureChannel*>(m_poseChannels.Remove())) != NULL) {
		delete channel;
	}

	if (m_objArma) {
		BKE_libblock_free(G.main, m_objArma->data);
		BKE_libblock_free(G.main, m_objArma);
	}
}


void BL_ArmatureObject::LoadConstraints(KX_BlenderSceneConverter* converter)
{
	// first delete any existing constraint (should not have any)
	while (!m_controlledConstraints.Empty()) {
		BL_ArmatureConstraint* constraint = m_controlledConstraints.Remove();
		delete constraint;
	}
	m_constraintNumber = 0;

	// list all the constraint and convert them to BL_ArmatureConstraint
	// get the persistent pose structure
	bPoseChannel* pchan;
	bConstraint* pcon;
	const bConstraintTypeInfo* cti;
	Object* blendtarget;
	KX_GameObject* gametarget;
	KX_GameObject* gamesubtarget;

	// and locate the constraint
	for (pchan = (bPoseChannel *)m_pose->chanbase.first; pchan; pchan = pchan->next) {
		for (pcon = (bConstraint *)pchan->constraints.first; pcon; pcon = pcon->next) {
			if (pcon->flag & CONSTRAINT_DISABLE)
				continue;
			// which constraint should we support?
			switch (pcon->type) {
			case CONSTRAINT_TYPE_TRACKTO:
			case CONSTRAINT_TYPE_DAMPTRACK:
			case CONSTRAINT_TYPE_KINEMATIC:
			case CONSTRAINT_TYPE_ROTLIKE:
			case CONSTRAINT_TYPE_LOCLIKE:
			case CONSTRAINT_TYPE_MINMAX:
			case CONSTRAINT_TYPE_SIZELIKE:
			case CONSTRAINT_TYPE_LOCKTRACK:
			case CONSTRAINT_TYPE_STRETCHTO:
			case CONSTRAINT_TYPE_CLAMPTO:
			case CONSTRAINT_TYPE_TRANSFORM:
			case CONSTRAINT_TYPE_DISTLIMIT:
			case CONSTRAINT_TYPE_TRANSLIKE:
				cti = BKE_constraint_typeinfo_get(pcon);
				gametarget = gamesubtarget = NULL;
				if (cti && cti->get_constraint_targets) {
					ListBase listb = { NULL, NULL };
					cti->get_constraint_targets(pcon, &listb);
					if (listb.first) {
						bConstraintTarget* target = (bConstraintTarget*)listb.first;
						if (target->tar && target->tar != m_objArma) {
							// only remember external objects, self target is handled automatically
							blendtarget = target->tar;
							gametarget = converter->FindGameObject(blendtarget);
						}
						if (target->next != NULL) {
							// secondary target
							target = target->next;
							if (target->tar && target->tar != m_objArma) {
								// only track external object
								blendtarget = target->tar;
								gamesubtarget = converter->FindGameObject(blendtarget);
							}
						}
					}
					if (cti->flush_constraint_targets)
						cti->flush_constraint_targets(pcon, &listb, 1);
				}
				BL_ArmatureConstraint* constraint = new BL_ArmatureConstraint(this, pchan, pcon, gametarget, gamesubtarget);
				m_controlledConstraints.AddBack(constraint);
				m_constraintNumber++;
			}
		}
	}

	// If we have constraints, make sure we get treated as an "animated" object
	if (m_constraintNumber > 0)
		GetActionManager();
}

BL_ArmatureConstraint* BL_ArmatureObject::GetConstraint(const char* posechannel, const char* constraintname)
{
	SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
	for (cit.begin(); !cit.end(); ++cit) {
		BL_ArmatureConstraint* constraint = *cit;
		if (constraint->Match(posechannel, constraintname))
			return constraint;
	}
	return NULL;
}

BL_ArmatureConstraint* BL_ArmatureObject::GetConstraint(const char* posechannelconstraint)
{
	// performance: use hash string instead of plain string compare
	SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
	for (cit.begin(); !cit.end(); ++cit) {
		BL_ArmatureConstraint* constraint = *cit;
		if (!strcmp(constraint->GetName(), posechannelconstraint))
			return constraint;
	}
	return NULL;
}

BL_ArmatureConstraint* BL_ArmatureObject::GetConstraint(int index)
{
	SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
	for (cit.begin(); !cit.end() && index; ++cit, --index);
	return (cit.end()) ? NULL : *cit;
}

/* this function is called to populate the m_poseChannels list */
void BL_ArmatureObject::LoadChannels()
{
	if (m_poseChannels.Empty()) {
		bPoseChannel* pchan;
		BL_ArmatureChannel* proxy;
	
		m_channelNumber = 0;
		for (pchan = (bPoseChannel *)m_pose->chanbase.first; pchan; pchan=(bPoseChannel *)pchan->next) {
			proxy = new BL_ArmatureChannel(this, pchan);
			m_poseChannels.AddBack(proxy);
			m_channelNumber++;
		}
	}
}

BL_ArmatureChannel* BL_ArmatureObject::GetChannel(bPoseChannel* pchan)
{
	LoadChannels();
	SG_DList::iterator<BL_ArmatureChannel> cit(m_poseChannels);
	for (cit.begin(); !cit.end(); ++cit) 
	{
		BL_ArmatureChannel* channel = *cit;
		if (channel->m_posechannel == pchan)
			return channel;
	}
	return NULL;
}

BL_ArmatureChannel* BL_ArmatureObject::GetChannel(const char* str)
{
	LoadChannels();
	SG_DList::iterator<BL_ArmatureChannel> cit(m_poseChannels);
	for (cit.begin(); !cit.end(); ++cit) 
	{
		BL_ArmatureChannel* channel = *cit;
		if (!strcmp(channel->m_posechannel->name, str))
			return channel;
	}
	return NULL;
}

BL_ArmatureChannel* BL_ArmatureObject::GetChannel(int index)
{
	LoadChannels();
	if (index < 0 || index >= m_channelNumber)
		return NULL;
	SG_DList::iterator<BL_ArmatureChannel> cit(m_poseChannels);
	for (cit.begin(); !cit.end() && index; ++cit, --index);
	return (cit.end()) ? NULL : *cit;
}

CValue* BL_ArmatureObject::GetReplica()
{
	BL_ArmatureObject* replica = new BL_ArmatureObject(*this);
	replica->ProcessReplica();
	return replica;
}

void BL_ArmatureObject::ProcessReplica()
{
	KX_GameObject::ProcessReplica();

	bArmature* tmp = (bArmature*)m_objArma->data;
	m_objArma = BKE_object_copy(G.main, m_objArma);
	m_objArma->data = BKE_armature_copy(G.main, tmp);
	m_pose = m_objArma->pose;
	/* P11 (B1): a copy starts with its capsules on its bones (it has its
	 * own, or none) */
	m_ragdollParts.clear();
	m_ragdoll = false;
	m_ragdollKids.clear();
	m_ragdollScanned = false;
	m_ragdollTimes[0] = m_ragdollTimes[1] = -1.0;
	m_ragdollWatched.clear();  /* (the copy registered with nothing) */
}

void BL_ArmatureObject::ReParentLogic()
{
	SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
	for (cit.begin(); !cit.end(); ++cit) {
		(*cit)->ReParent(this);
	}
	KX_GameObject::ReParentLogic();
}

void BL_ArmatureObject::Relink(CTR_Map<CTR_HashedPtr, void*> *obj_map)
{
	SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
	for (cit.begin(); !cit.end(); ++cit) {
		(*cit)->Relink(obj_map);
	}
	KX_GameObject::Relink(obj_map);
}

bool BL_ArmatureObject::UnlinkObject(SCA_IObject* clientobj)
{
	// clientobj is being deleted, make sure we don't hold any reference to it
	bool res = false;
	SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
	for (cit.begin(); !cit.end(); ++cit) {
		res |= (*cit)->UnlinkObject(clientobj);
	}
	/* P11 (B1): a ragdoll's capsule removed: its bone is animated again */
	for (size_t i = 0; i < m_ragdollParts.size();) {
		if (m_ragdollParts[i].capsule == clientobj) {
			m_ragdollParts.erase(m_ragdollParts.begin() + i);
			res = true;
		}
		else {
			i++;
		}
	}
	for (size_t i = 0; i < m_ragdollKids.size();) {
		if (m_ragdollKids[i].capsule == clientobj) {
			m_ragdollKids.erase(m_ragdollKids.begin() + i);
		}
		else {
			i++;
		}
	}
	m_ragdollWatched.erase(std::remove(m_ragdollWatched.begin(), m_ragdollWatched.end(), clientobj),
	                       m_ragdollWatched.end());
	return res;
}

void BL_ArmatureObject::ApplyPose()
{
	m_armpose = m_objArma->pose;
	m_objArma->pose = m_pose;
	// in the GE, we use ctime to store the timestep
	m_pose->ctime = (float)m_timestep;
	//m_scene->r.cfra++;
	/* P11 (B1): a ragdoll's pose again whenever its capsules moved (a physics
	 * step), so what follows the bones is not a step behind */
	if (m_ragdoll) {
		double sig = 0.0;
		for (const RagdollPart &part : m_ragdollParts) {
			if (part.capsule && part.capsule->GetSGNode()) {
				const MT_Point3 &p = part.capsule->GetSGNode()->GetWorldPosition();
				const MT_Matrix3x3 &o = part.capsule->GetSGNode()->GetWorldOrientation();
				sig += p[0] * 1.3 + p[1] * 1.7 + p[2] * 2.3 + o[0][0] + o[1][1] * 0.7 + o[2][2] * 0.3 + o[0][1] * 0.11;
			}
		}
		if (sig != m_ragdollSig) {
			m_ragdollSig = sig;
			m_lastapplyframe = -1.0;
		}
	}
	if (m_lastapplyframe != m_lastframe) {
		// update the constraint if any, first put them all off so that only the active ones will be updated
		SG_DList::iterator<BL_ArmatureConstraint> cit(m_controlledConstraints);
		for (cit.begin(); !cit.end(); ++cit) {
			(*cit)->UpdateTarget();
		}
		// update ourself
		UpdateBlenderObjectMatrix(m_objArma);
		BKE_pose_where_is(m_scene, m_objArma); // XXX
		if (m_ragdoll) {
			ApplyRagdoll();  /* P11 (B1) */
		}
		// restore ourself
		memcpy(m_objArma->obmat, m_obmat, sizeof(m_obmat));
		// restore active targets
		for (cit.begin(); !cit.end(); ++cit) {
			(*cit)->RestoreTarget();
		}
		m_lastapplyframe = m_lastframe;
	}
}

/* P11 (B1): each ragdoll bone where its capsule is (pose_mat = armature^-1 *
 * capsule * local^-1 * tail^-1); the bones under them without a capsule come
 * along; then the deform matrices again */
void BL_ArmatureObject::ApplyRagdoll()
{
	bPose *pose = m_objArma->pose;
	if (!pose || m_ragdollParts.empty()) {
		return;
	}
	float arm_inv[4][4];
	invert_m4_m4(arm_inv, m_objArma->obmat);
	/* the old pose matrices, for the bones that come along */
	std::vector<std::pair<bPoseChannel *, std::vector<float> > > old;
	for (bPoseChannel *pchan = (bPoseChannel *)pose->chanbase.first; pchan; pchan = pchan->next) {
		old.push_back(std::make_pair(pchan, std::vector<float>(&pchan->pose_mat[0][0], &pchan->pose_mat[0][0] + 16)));
	}
	auto old_of = [&](bPoseChannel *pchan, float r[4][4]) {
		for (auto &o : old) {
			if (o.first == pchan) {
				memcpy(r, o.second.data(), sizeof(float[4][4]));
				return;
			}
		}
		copy_m4_m4(r, pchan->pose_mat);
	};
	std::vector<bPoseChannel *> moved;
	for (const RagdollPart &part : m_ragdollParts) {
		bPoseChannel *pchan = BKE_pose_channel_find_name(pose, part.bone->name);
		if (!pchan || !part.capsule || !part.capsule->GetSGNode()) {
			continue;
		}
		float capsule[4][4], local_inv[4][4], tail_inv[4][4], m[4][4];
		part.capsule->GetSGNode()->GetWorldTransform().getValue(&capsule[0][0]);
		invert_m4_m4(local_inv, const_cast<float (*)[4]>(part.local));
		unit_m4(tail_inv);
		tail_inv[3][1] = -GetBoneLength(part.bone);
		mul_m4_series(m, arm_inv, capsule, local_inv, tail_inv);
		copy_m4_m4(pchan->pose_mat, m);
		moved.push_back(pchan);
	}
	/* (the channels are in the bones' order: a parent before its children) */
	for (bPoseChannel *pchan = (bPoseChannel *)pose->chanbase.first; pchan; pchan = pchan->next) {
		if (std::find(moved.begin(), moved.end(), pchan) != moved.end() || !pchan->parent ||
		    std::find(moved.begin(), moved.end(), pchan->parent) == moved.end())
		{
			continue;
		}
		float parent_old[4][4], parent_old_inv[4][4], own_old[4][4], rel[4][4];
		old_of(pchan->parent, parent_old);
		old_of(pchan, own_old);
		invert_m4_m4(parent_old_inv, parent_old);
		mul_m4_m4m4(rel, parent_old_inv, own_old);
		mul_m4_m4m4(pchan->pose_mat, pchan->parent->pose_mat, rel);
		moved.push_back(pchan);
	}
	for (bPoseChannel *pchan : moved) {
		/* as BKE_pose_where_is: the deform matrix, and the head and tail */
		if (pchan->bone) {
			float imat[4][4];
			invert_m4_m4(imat, pchan->bone->arm_mat);
			mul_m4_m4m4(pchan->chan_mat, pchan->pose_mat, imat);
		}
		copy_v3_v3(pchan->pose_head, pchan->pose_mat[3]);
		float tail[3] = {0.0f, pchan->bone ? pchan->bone->length : 0.0f, 0.0f};
		mul_v3_m4v3(pchan->pose_tail, pchan->pose_mat, tail);
	}
}

bool BL_ArmatureObject::SetRagdoll(bool on)
{
	KX_Scene *scene = KX_GameObject::GetScene();
	if (on == m_ragdoll) {
		return on ? !m_ragdollParts.empty() : true;
	}
	if (on) {
		/* the capsules: bone-parented children naming their bone */
		std::vector<RagdollPart> parts;
		std::vector<KX_GameObject *> capsules = RagdollCapsules();
		for (KX_GameObject *child : capsules) {
			Object *ob = child->GetBlenderObject();
			IDProperty *prop = (ob && ob->id.properties) ?
			        IDP_GetPropertyFromGroup(ob->id.properties, "bge_ragdoll_bone") : NULL;
			Bone *bone = (prop && prop->type == IDP_STRING) ?
			        BKE_armature_find_bone_name(GetArmature(), IDP_String(prop)) : NULL;
			if (!bone || !child->GetPhysicsController()) {
				continue;
			}
			MT_Matrix4x4 pose;
			if (!GetBoneMatrix(bone, pose)) {
				continue;
			}
			/* local = (armature * pose * tail)^-1 * capsule */
			float arm[4][4], pose_mat[4][4], tail[4][4], frame[4][4], frame_inv[4][4], capsule[4][4];
			GetSGNode()->GetWorldTransform().getValue(&arm[0][0]);
			pose.getValue(&pose_mat[0][0]);
			unit_m4(tail);
			tail[3][1] = GetBoneLength(bone);
			mul_m4_series(frame, arm, pose_mat, tail);
			invert_m4_m4(frame_inv, frame);
			child->GetSGNode()->GetWorldTransform().getValue(&capsule[0][0]);
			RagdollPart part;
			part.bone = bone;
			part.capsule = child;
			mul_m4_m4m4(part.local, frame_inv, capsule);
			parts.push_back(part);
		}
		if (parts.empty()) {
			return false;
		}
		/* let go: dynamic again (PhysX builds the articulation at the next
		 * step), at the speed the bones moved them over the last frame */
		const double dt = m_ragdollTimes[1] - m_ragdollTimes[0];
		for (RagdollPart &part : parts) {
			part.capsule->RemoveParent(scene);
			PHY_IPhysicsController *ctrl = part.capsule->GetPhysicsController();
			if (!ctrl || dt <= 1e-6 || dt > 0.5) {
				continue;
			}
			for (const RagdollSample &k : m_ragdollKids) {
				if (k.capsule != part.capsule) {
					continue;
				}
				const MT_Vector3 v = (k.pos[1] - k.pos[0]) / (MT_Scalar)dt;
				MT_Quaternion q = (k.ori[1] * k.ori[0].transposed()).getRotation();
				if (q.w() < 0.0f) {
					q = -q;
				}
				const MT_Scalar angle = 2.0f * acosf(CLAMPIS((float)q.w(), -1.0f, 1.0f));
				const MT_Vector3 axis(q.x(), q.y(), q.z());
				const MT_Vector3 w = axis.length() > 1e-6f ? axis.normalized() * (angle / (MT_Scalar)dt) :
				                     MT_Vector3(0.0f, 0.0f, 0.0f);
				ctrl->SetLinearVelocity(v, false);
				ctrl->SetAngularVelocity(w, false);
			}
		}
		m_ragdollParts = parts;
		for (RagdollPart &part : m_ragdollParts) {
			RagdollWatch(part.capsule);
		}
		m_ragdoll = true;
	}
	else {
		/* back onto the bones, as they were (and still now); the bones posed
		 * by their animation again at once */
		m_ragdoll = false;
		m_lastapplyframe = -1.0;
		for (RagdollPart &part : m_ragdollParts) {
			KX_GameObject *capsule = part.capsule;
			if (!capsule || !capsule->GetSGNode() || !GetSGNode()) {
				continue;
			}
			capsule->RemoveParent(scene);  /* (none: no effect) */
			GetSGNode()->AddChild(capsule->GetSGNode());
			capsule->GetSGNode()->SetParentRelation(KX_BoneParentRelation::New(part.bone));
			if (capsule->GetPhysicsController()) {
				capsule->GetPhysicsController()->SuspendDynamics(false);
			}
			MT_Transform local;
			local.setValue(&part.local[0][0]);
			MT_Matrix3x3 basis = local.getBasis();
			MT_Vector3 size(basis.getColumn(0).length(), basis.getColumn(1).length(), basis.getColumn(2).length());
			basis.scale(1.0f / size[0], 1.0f / size[1], 1.0f / size[2]);
			capsule->NodeSetLocalScale(size);
			capsule->NodeSetLocalOrientation(basis);
			capsule->NodeSetLocalPosition(MT_Point3(local.getOrigin()));
			capsule->NodeUpdateGS(0.0f);
			CListValue *rootlist = scene->GetRootParentList();
			if (rootlist->RemoveValue(capsule)) {
				capsule->Release();
			}
		}
		m_ragdollParts.clear();
		m_ragdoll = false;
		m_ragdollTimes[0] = m_ragdollTimes[1] = -1.0;
	}
	m_lastapplyframe = -1.0;
	return true;
}

void BL_ArmatureObject::RagdollWatch(KX_GameObject *capsule)
{
	if (capsule && std::find(m_ragdollWatched.begin(), m_ragdollWatched.end(), capsule) == m_ragdollWatched.end()) {
		capsule->RegisterObject(this);
		m_ragdollWatched.push_back(capsule);
	}
}

std::vector<KX_GameObject *> BL_ArmatureObject::RagdollCapsules()
{
	std::vector<KX_GameObject *> out;
	CListValue *children = GetChildren();
	for (int i = 0; i < children->GetCount(); i++) {
		KX_GameObject *child = (KX_GameObject *)children->GetValue(i);
		Object *ob = child->GetBlenderObject();
		IDProperty *prop = (ob && ob->id.properties) ?
		        IDP_GetPropertyFromGroup(ob->id.properties, "bge_ragdoll_bone") : NULL;
		if (prop && prop->type == IDP_STRING && child->GetPhysicsController()) {
			out.push_back(child);
		}
	}
	children->Release();
	return out;
}

bool BL_ArmatureObject::HasRagdoll()
{
	if (m_ragdoll) {
		return !m_ragdollParts.empty();
	}
	return !RagdollCapsules().empty();
}

KX_GameObject *BL_ArmatureObject::RagdollRoot()
{
	std::vector<KX_GameObject *> capsules;
	if (m_ragdoll) {
		for (const RagdollPart &part : m_ragdollParts) {
			capsules.push_back(part.capsule);
		}
	}
	else {
		capsules = RagdollCapsules();
	}
	for (KX_GameObject *c : capsules) {
		Object *ob = c ? c->GetBlenderObject() : NULL;
		IDProperty *prop = (ob && ob->id.properties) ?
		        IDP_GetPropertyFromGroup(ob->id.properties, "bge_articulation") : NULL;
		if (prop && prop->type == IDP_INT && IDP_Int(prop) != 0) {
			return c;
		}
	}
	return capsules.empty() ? NULL : capsules[0];
}

bool BL_ArmatureObject::OwnsRagdollCapsule(KX_GameObject *ob)
{
	for (const RagdollPart &part : m_ragdollParts) {
		if (part.capsule == ob) {
			return true;
		}
	}
	for (const RagdollSample &k : m_ragdollKids) {
		if (k.capsule == ob) {
			return true;
		}
	}
	return false;
}

void BL_ArmatureObject::RagdollTick(double curtime)
{
	if (m_ragdoll) {
		UpdateTimestep(curtime);
		m_lastapplyframe = -1.0;
		return;
	}
	/* off: the capsules found once (a copy finds its own), then where they
	 * are each frame */
	if (!m_ragdollScanned) {
		m_ragdollScanned = true;
		m_ragdollKids.clear();
		for (KX_GameObject *c : RagdollCapsules()) {
			RagdollSample k;
			k.capsule = c;
			m_ragdollKids.push_back(k);
			RagdollWatch(c);
		}
	}
	if (m_ragdollKids.empty() || curtime == m_ragdollTimes[1]) {
		return;
	}
	m_ragdollTimes[0] = m_ragdollTimes[1];
	m_ragdollTimes[1] = curtime;
	for (RagdollSample &k : m_ragdollKids) {
		if (!k.capsule || !k.capsule->GetSGNode()) {
			continue;
		}
		k.pos[0] = k.pos[1];
		k.ori[0] = k.ori[1];
		k.pos[1] = k.capsule->NodeGetWorldPosition();
		k.ori[1] = k.capsule->NodeGetWorldOrientation();
	}
}

void BL_ArmatureObject::RestorePose()
{
	m_objArma->pose = m_armpose;
	m_armpose = NULL;
}

void BL_ArmatureObject::SetPose(bPose *pose)
{
	extract_pose_from_pose(m_pose, pose);
	m_lastapplyframe = -1.0;
}

void BL_ArmatureObject::SetPoseByAction(bAction *action, float localtime)
{
	Object *arm = GetArmatureObject();

	PointerRNA ptrrna;
	RNA_id_pointer_create(&arm->id, &ptrrna);

	animsys_evaluate_action(&ptrrna, action, NULL, localtime);
}

void BL_ArmatureObject::BlendInPose(bPose *blend_pose, float weight, short mode)
{
	game_blend_poses(m_pose, blend_pose, weight, mode);
}

bool BL_ArmatureObject::UpdateTimestep(double curtime)
{
	if (curtime != m_lastframe) {
		// compute the timestep for the underlying IK algorithm
		m_timestep = curtime-m_lastframe;
		m_lastframe= curtime;
	}

	return false;
}

void BL_ArmatureObject::GetPose(bPose **pose)
{
	/* If the caller supplies a null pose, create a new one. */
	/* Otherwise, copy the armature's pose channels into the caller-supplied pose */
		
	if (!*pose) {
		/* probably not to good of an idea to
		 * duplicate everything, but it clears up 
		 * a crash and memory leakage when 
		 * &BL_ActionActuator::m_pose is freed
		 */
		game_copy_pose(pose, m_pose, 0);
	}
	else {
		if (*pose == m_pose)
			// no need to copy if the pointers are the same
			return;

		extract_pose_from_pose(*pose, m_pose);
	}
}

double BL_ArmatureObject::GetLastFrame()
{
	return m_lastframe;
}

bool BL_ArmatureObject::GetBoneMatrix(Bone* bone, MT_Matrix4x4& matrix)
{
	bPoseChannel *pchan;

	ApplyPose();
	pchan = BKE_pose_channel_find_name(m_objArma->pose, bone->name);
	if (pchan)
		matrix.setValue(&pchan->pose_mat[0][0]);
	RestorePose();

	return (pchan != NULL);
}

float BL_ArmatureObject::GetBoneLength(Bone* bone) const
{
	return (float)(MT_Point3(bone->head) - MT_Point3(bone->tail)).length();
}

#ifdef WITH_PYTHON

// PYTHON

PyTypeObject BL_ArmatureObject::Type = {
	PyVarObject_HEAD_INIT(NULL, 0)
	"BL_ArmatureObject",
	sizeof(PyObjectPlus_Proxy),
	0,
	py_base_dealloc,
	0,
	0,
	0,
	0,
	py_base_repr,
	0,
	&KX_GameObject::Sequence,
	&KX_GameObject::Mapping,
	0,0,0,
	NULL,
	NULL,
	0,
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	0,0,0,0,0,0,0,
	Methods,
	0,
	0,
	&KX_GameObject::Type,
	0,0,0,0,0,0,
	py_base_new
};

PyMethodDef BL_ArmatureObject::Methods[] = {
	KX_PYMETHODTABLE_NOARGS(BL_ArmatureObject, update),
	{NULL,NULL} //Sentinel
};

PyAttributeDef BL_ArmatureObject::Attributes[] = {

	KX_PYATTRIBUTE_RO_FUNCTION("constraints",		BL_ArmatureObject, pyattr_get_constraints),
	KX_PYATTRIBUTE_RO_FUNCTION("channels",		BL_ArmatureObject, pyattr_get_channels),
	{NULL} //Sentinel
};

static int bl_armature_object_get_constraints_size_cb(void *self_v)
{
	return ((BL_ArmatureObject *)self_v)->GetConstraintNumber();
}

static PyObject *bl_armature_object_get_constraints_item_cb(void *self_v, int index)
{
	return ((BL_ArmatureObject *)self_v)->GetConstraint(index)->GetProxy();
}

static const char *bl_armature_object_get_constraints_item_name_cb(void *self_v, int index)
{
	return ((BL_ArmatureObject *)self_v)->GetConstraint(index)->GetName();
}

PyObject *BL_ArmatureObject::pyattr_get_constraints(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef)
{
	return (new CListWrapper(self_v,
							 ((BL_ArmatureObject *)self_v)->GetProxy(),
							 NULL,
							 bl_armature_object_get_constraints_size_cb,
							 bl_armature_object_get_constraints_item_cb,
							 bl_armature_object_get_constraints_item_name_cb,
							 NULL))->NewProxy(true);
}

static int bl_armature_object_get_channels_size_cb(void *self_v)
{
	return ((BL_ArmatureObject *)self_v)->GetChannelNumber();
}

static PyObject *bl_armature_object_get_channels_item_cb(void *self_v, int index)
{
	return ((BL_ArmatureObject *)self_v)->GetChannel(index)->GetProxy();
}

static const char *bl_armature_object_get_channels_item_name_cb(void *self_v, int index)
{
	return ((BL_ArmatureObject *)self_v)->GetChannel(index)->GetName();
}

PyObject *BL_ArmatureObject::pyattr_get_channels(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef)
{
	BL_ArmatureObject *self = static_cast<BL_ArmatureObject *>(self_v);
	self->LoadChannels(); // make sure we have the channels
	return (new CListWrapper(self_v,
							 self->GetProxy(),
							 NULL,
							 bl_armature_object_get_channels_size_cb,
							 bl_armature_object_get_channels_item_cb,
							 bl_armature_object_get_channels_item_name_cb,
							 NULL))->NewProxy(true);
}

KX_PYMETHODDEF_DOC_NOARGS(BL_ArmatureObject, update, 
						  "update()\n"
						  "Make sure that the armature will be updated on next graphic frame.\n"
						  "This is automatically done if a KX_ArmatureActuator with mode run is active\n"
						  "or if an action is playing. This function is useful in other cases.\n")
{
	UpdateTimestep(KX_GetActiveEngine()->GetFrameTime());
	Py_RETURN_NONE;
}

#endif // WITH_PYTHON
