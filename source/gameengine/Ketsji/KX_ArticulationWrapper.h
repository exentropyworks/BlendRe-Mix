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

/** \file KX_ArticulationWrapper.h
 *  \ingroup ketsji
 *
 * BGE-Remix P11 (B1): bge.constraints.getArticulation(ob), an articulation
 * (PhysX: a tree of bodies joined by Rigid Body Joints, solved as one) for
 * Python. It holds its root object, not the articulation itself: PhysX builds
 * the articulation again when a body or joint of it is added or removed.
 * getArticulation(armature) gives a ragdoll's (Make Ragdoll): its ragdoll
 * attribute lets the capsules go (True) or puts them back on the bones.
 */

#ifndef __KX_ARTICULATIONWRAPPER_H__
#define __KX_ARTICULATIONWRAPPER_H__

#include "EXP_Value.h"

class KX_GameObject;
class PHY_IPhysicsEnvironment;
struct PHY_ArticulationInfo;

class KX_ArticulationWrapper : public PyObjectPlus
{
	Py_Header

public:
	/* armature: the ragdoll's (getArticulation(armature)), or NULL */
	KX_ArticulationWrapper(KX_GameObject *root, KX_GameObject *armature = NULL);
	virtual ~KX_ArticulationWrapper();

#ifdef WITH_PYTHON
	KX_PYMETHOD_DOC(KX_ArticulationWrapper, getJointPosition);
	KX_PYMETHOD_DOC(KX_ArticulationWrapper, getJointSpeed);
	KX_PYMETHOD_DOC(KX_ArticulationWrapper, setJointTarget);
	KX_PYMETHOD_DOC(KX_ArticulationWrapper, setJointSpeed);

	static PyObject *pyattr_get_root(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_fixed(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_links(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_joints(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_parents(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_ordinary(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_ragdoll(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static int pyattr_set_ragdoll(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef, PyObject *value);
#endif

private:
#ifdef WITH_PYTHON
	/* the root and its articulation now (false and a Python error: gone) */
	bool Info(PHY_ArticulationInfo &info, PHY_IPhysicsEnvironment **r_env, const char *what);
	/* the constraint id of a link's joint (a link object or an index; 0 and a
	 * Python error: none) */
	int JointOf(PyObject *link, const PHY_ArticulationInfo &info, const char *what);
	PyObject *JointState(PyObject *args, PyObject *kwds, bool speed, const char *what);

	/* the ragdoll's armature (given, or found from the root capsule) */
	class BL_ArmatureObject *Armature();

	PyObject *m_root;      /* the root object's proxy (its object NULL once freed) */
	PyObject *m_armature;  /* a ragdoll's armature's proxy, or NULL */
#endif
};

#endif  /* __KX_ARTICULATIONWRAPPER_H__ */
