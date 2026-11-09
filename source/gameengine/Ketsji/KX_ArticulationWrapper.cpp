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

/** \file gameengine/Ketsji/KX_ArticulationWrapper.cpp
 *  \ingroup ketsji
 *
 * BGE-Remix P11 (B1): see KX_ArticulationWrapper.h. Joint axes as the 6DOF
 * joint's: 0-2 sliding along X Y Z, 3-5 turning about X Y Z (a hinge turns
 * about its X: 3); left out, the joint's first moving axis.
 */

#include "KX_ArticulationWrapper.h"

#include "BL_ArmatureObject.h"
#include "EXP_ListValue.h"
#include "KX_ClientObjectInfo.h"
#include "KX_GameObject.h"
#include "KX_Scene.h"
#include "PHY_IPhysicsController.h"
#include "PHY_IPhysicsEnvironment.h"

KX_ArticulationWrapper::KX_ArticulationWrapper(KX_GameObject *root, KX_GameObject *armature)
    : PyObjectPlus()
{
#ifdef WITH_PYTHON
	m_root = root ? root->GetProxy() : NULL;  /* (new references) */
	m_armature = armature ? armature->GetProxy() : NULL;
#else
	(void)root;
	(void)armature;
#endif
}

KX_ArticulationWrapper::~KX_ArticulationWrapper()
{
#ifdef WITH_PYTHON
	Py_XDECREF(m_root);
	Py_XDECREF(m_armature);
#endif
}

#ifdef WITH_PYTHON

PyTypeObject KX_ArticulationWrapper::Type = {
	PyVarObject_HEAD_INIT(NULL, 0)
	"KX_ArticulationWrapper",
	sizeof(PyObjectPlus_Proxy),
	0,
	py_base_dealloc,
	0,
	0,
	0,
	0,
	py_base_repr,
	0,0,0,0,0,0,0,0,0,
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	0,0,0,0,0,0,0,
	Methods,
	0,
	0,
	&PyObjectPlus::Type,
	0,0,0,0,0,0,
	py_base_new
};

PyMethodDef KX_ArticulationWrapper::Methods[] = {
	KX_PYMETHODTABLE_KEYWORDS(KX_ArticulationWrapper, getJointPosition),
	KX_PYMETHODTABLE_KEYWORDS(KX_ArticulationWrapper, getJointSpeed),
	KX_PYMETHODTABLE_KEYWORDS(KX_ArticulationWrapper, setJointTarget),
	KX_PYMETHODTABLE_KEYWORDS(KX_ArticulationWrapper, setJointSpeed),
	{NULL, NULL}  /* Sentinel */
};

PyAttributeDef KX_ArticulationWrapper::Attributes[] = {
	KX_PYATTRIBUTE_RO_FUNCTION("root", KX_ArticulationWrapper, pyattr_get_root),
	KX_PYATTRIBUTE_RO_FUNCTION("fixed", KX_ArticulationWrapper, pyattr_get_fixed),
	KX_PYATTRIBUTE_RO_FUNCTION("links", KX_ArticulationWrapper, pyattr_get_links),
	KX_PYATTRIBUTE_RO_FUNCTION("joints", KX_ArticulationWrapper, pyattr_get_joints),
	KX_PYATTRIBUTE_RO_FUNCTION("parents", KX_ArticulationWrapper, pyattr_get_parents),
	KX_PYATTRIBUTE_RO_FUNCTION("ordinaryJoints", KX_ArticulationWrapper, pyattr_get_ordinary),
	KX_PYATTRIBUTE_RW_FUNCTION("ragdoll", KX_ArticulationWrapper, pyattr_get_ragdoll, pyattr_set_ragdoll),
	{NULL}  /* Sentinel */
};

static KX_GameObject *object_of(PHY_IPhysicsController *ctrl)
{
	return ctrl ? KX_GameObject::GetClientObject((KX_ClientObjectInfo *)ctrl->GetNewClientInfo()) : NULL;
}

bool KX_ArticulationWrapper::Info(PHY_ArticulationInfo &info, PHY_IPhysicsEnvironment **r_env, const char *what)
{
	KX_GameObject *root = m_root ? (KX_GameObject *)BGE_PROXY_REF(m_root) : NULL;
	PHY_IPhysicsEnvironment *env = (root && root->GetScene()) ? root->GetScene()->GetPhysicsEnvironment() : NULL;
	if (!env || !root->GetPhysicsController() || !env->GetArticulation(root->GetPhysicsController(), &info)) {
		BL_ArmatureObject *arm = root ? Armature() : NULL;
		if (arm && !arm->IsRagdoll()) {
			PyErr_Format(PyExc_RuntimeError, "KX_ArticulationWrapper.%s: the ragdoll is on its bones (ragdoll = "
			             "True lets it go)", what);
		}
		else {
			PyErr_Format(PyExc_RuntimeError, "KX_ArticulationWrapper.%s: the articulation is gone (its root was "
			             "removed or is no longer joined to anything)", what);
		}
		return false;
	}
	if (r_env) {
		*r_env = env;
	}
	return true;
}

int KX_ArticulationWrapper::JointOf(PyObject *link, const PHY_ArticulationInfo &info, const char *what)
{
	int at = -1;
	if (PyLong_Check(link)) {
		at = (int)PyLong_AsLong(link);
		if (at < 0 || at >= (int)info.links.size()) {
			PyErr_Format(PyExc_IndexError, "KX_ArticulationWrapper.%s: link index %d, the articulation has %d links",
			             what, at, (int)info.links.size());
			return 0;
		}
	}
	else {
		KX_GameObject *ob = NULL;
		KX_GameObject *root = (KX_GameObject *)BGE_PROXY_REF(m_root);
		if (!ConvertPythonToGameObject(root->GetScene()->GetLogicManager(), link, &ob, false,
		                               "KX_ArticulationWrapper: link"))
		{
			return 0;
		}
		for (size_t i = 0; i < info.links.size(); i++) {
			if (info.links[i] == ob->GetPhysicsController()) {
				at = (int)i;
			}
		}
		if (at < 0) {
			PyErr_Format(PyExc_ValueError, "KX_ArticulationWrapper.%s: \"%s\" is not a link of this articulation",
			             what, ob->GetName().ReadPtr());
			return 0;
		}
	}
	if (at == 0) {
		PyErr_Format(PyExc_ValueError, "KX_ArticulationWrapper.%s: the root has no joint (its links do)", what);
		return 0;
	}
	return info.joints[at];
}

PyObject *KX_ArticulationWrapper::JointState(PyObject *args, PyObject *kwds, bool speed, const char *what)
{
	static const char *kwlist[] = {"link", "axis", NULL};
	PyObject *link;
	int axis = -1;
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|i:KX_ArticulationWrapper", const_cast<char **>(kwlist), &link,
	                                 &axis))
	{
		return NULL;
	}
	PHY_ArticulationInfo info;
	PHY_IPhysicsEnvironment *env;
	if (!Info(info, &env, what)) {
		return NULL;
	}
	const int id = JointOf(link, info, what);
	if (!id) {
		return NULL;
	}
	float pos = 0.0f, vel = 0.0f;
	if (!env->GetArticulationJoint(id, axis, &pos, &vel)) {
		PyErr_Format(PyExc_ValueError, "KX_ArticulationWrapper.%s: the joint does not move on axis %d", what, axis);
		return NULL;
	}
	return PyFloat_FromDouble(speed ? vel : pos);
}

KX_PYMETHODDEF_DOC(KX_ArticulationWrapper, getJointPosition,
                   "getJointPosition(link, axis=-1)\n"
                   "The position of a link's joint to its parent on one axis: an angle in radians (axes 3-5) or "
                   "a distance (axes 0-2). link: the link object or its index in links.")
{
	return JointState(args, kwds, false, "getJointPosition()");
}

KX_PYMETHODDEF_DOC(KX_ArticulationWrapper, getJointSpeed,
                   "getJointSpeed(link, axis=-1)\n"
                   "The speed of a link's joint on one axis (radians or units a second).")
{
	return JointState(args, kwds, true, "getJointSpeed()");
}

KX_PYMETHODDEF_DOC(KX_ArticulationWrapper, setJointTarget,
                   "setJointTarget(link, target, axis=-1, stiffness=1000.0, damping=100.0, maxForce=0.0)\n"
                   "Drives a link's joint to a position like a spring (stiffness and damping); maxForce 0: no "
                   "limit. Stiffness and damping 0 turn the drive off.")
{
	static const char *kwlist[] = {"link", "target", "axis", "stiffness", "damping", "maxForce", NULL};
	PyObject *link;
	float target, stiffness = 1000.0f, damping = 100.0f, maxForce = 0.0f;
	int axis = -1;
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "Of|ifff:setJointTarget", const_cast<char **>(kwlist), &link,
	                                 &target, &axis, &stiffness, &damping, &maxForce))
	{
		return NULL;
	}
	PHY_ArticulationInfo info;
	PHY_IPhysicsEnvironment *env;
	if (!Info(info, &env, "setJointTarget()")) {
		return NULL;
	}
	const int id = JointOf(link, info, "setJointTarget()");
	if (!id) {
		return NULL;
	}
	const float still = 0.0f;
	if (!env->SetArticulationDrive(id, axis, &target, &still, stiffness, damping, maxForce)) {
		PyErr_Format(PyExc_ValueError, "KX_ArticulationWrapper.setJointTarget(): the joint does not move on axis %d",
		             axis);
		return NULL;
	}
	Py_RETURN_NONE;
}

KX_PYMETHODDEF_DOC(KX_ArticulationWrapper, setJointSpeed,
                   "setJointSpeed(link, speed, axis=-1, maxForce=0.0)\n"
                   "Turns (or slides) a link's joint at a speed like a motor, with at most maxForce (0: no "
                   "limit).")
{
	static const char *kwlist[] = {"link", "speed", "axis", "maxForce", NULL};
	PyObject *link;
	float speed, maxForce = 0.0f;
	int axis = -1;
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "Of|if:setJointSpeed", const_cast<char **>(kwlist), &link, &speed,
	                                 &axis, &maxForce))
	{
		return NULL;
	}
	PHY_ArticulationInfo info;
	PHY_IPhysicsEnvironment *env;
	if (!Info(info, &env, "setJointSpeed()")) {
		return NULL;
	}
	const int id = JointOf(link, info, "setJointSpeed()");
	if (!id) {
		return NULL;
	}
	/* (as the 6DOF motors: no stiffness, strong damping) */
	if (!env->SetArticulationDrive(id, axis, NULL, &speed, 0.0f, 1e5f, maxForce)) {
		PyErr_Format(PyExc_ValueError, "KX_ArticulationWrapper.setJointSpeed(): the joint does not move on axis %d",
		             axis);
		return NULL;
	}
	Py_RETURN_NONE;
}

BL_ArmatureObject *KX_ArticulationWrapper::Armature()
{
	KX_GameObject *arm = m_armature ? (KX_GameObject *)BGE_PROXY_REF(m_armature) : NULL;
	if (arm && arm->GetGameObjectType() == SCA_IObject::OBJ_ARMATURE) {
		return static_cast<BL_ArmatureObject *>(arm);
	}
	/* (from a capsule: the armature whose ragdoll it is) */
	KX_GameObject *root = m_root ? (KX_GameObject *)BGE_PROXY_REF(m_root) : NULL;
	CListValue *objects = (root && root->GetScene()) ? root->GetScene()->GetObjectList() : NULL;
	for (int i = 0; objects && i < objects->GetCount(); i++) {
		KX_GameObject *ob = (KX_GameObject *)objects->GetValue(i);
		if (ob->GetGameObjectType() == SCA_IObject::OBJ_ARMATURE &&
		    static_cast<BL_ArmatureObject *>(ob)->OwnsRagdollCapsule(root))
		{
			return static_cast<BL_ArmatureObject *>(ob);
		}
	}
	return NULL;
}

PyObject *KX_ArticulationWrapper::pyattr_get_ragdoll(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	BL_ArmatureObject *arm = self->Armature();
	if (!arm) {
		Py_RETURN_NONE;  /* (not a ragdoll's) */
	}
	return PyBool_FromLong(arm->IsRagdoll());
}

int KX_ArticulationWrapper::pyattr_set_ragdoll(void *self_v, const KX_PYATTRIBUTE_DEF *, PyObject *value)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	const int on = PyObject_IsTrue(value);
	if (on == -1) {
		PyErr_SetString(PyExc_TypeError, "KX_ArticulationWrapper.ragdoll = bool: expected True or False");
		return PY_SET_ATTR_FAIL;
	}
	BL_ArmatureObject *arm = self->Armature();
	if (!arm) {
		PyErr_SetString(PyExc_ValueError, "KX_ArticulationWrapper.ragdoll: not a ragdoll's articulation (Make "
		                "Ragdoll, on an armature's Physics tab)");
		return PY_SET_ATTR_FAIL;
	}
	if (!arm->SetRagdoll(on != 0)) {
		PyErr_Format(PyExc_ValueError, "KX_ArticulationWrapper.ragdoll: \"%s\" has no capsules on its bones",
		             arm->GetName().ReadPtr());
		return PY_SET_ATTR_FAIL;
	}
	return PY_SET_ATTR_SUCCESS;
}

PyObject *KX_ArticulationWrapper::pyattr_get_root(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	PHY_ArticulationInfo info;
	if (!self->Info(info, NULL, "root")) {
		return NULL;
	}
	KX_GameObject *ob = object_of(info.root);
	if (!ob) {
		Py_RETURN_NONE;
	}
	return ob->GetProxy();
}

PyObject *KX_ArticulationWrapper::pyattr_get_fixed(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	PHY_ArticulationInfo info;
	if (!self->Info(info, NULL, "fixed")) {
		return NULL;
	}
	return PyBool_FromLong(info.fixed);
}

PyObject *KX_ArticulationWrapper::pyattr_get_links(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	PHY_ArticulationInfo info;
	if (!self->Info(info, NULL, "links")) {
		return NULL;
	}
	PyObject *list = PyList_New(info.links.size());
	for (size_t i = 0; i < info.links.size(); i++) {
		KX_GameObject *ob = object_of(info.links[i]);
		PyObject *item = ob ? ob->GetProxy() : (Py_INCREF(Py_None), Py_None);
		PyList_SET_ITEM(list, i, item);
	}
	return list;
}

static PyObject *int_list(const std::vector<int> &v)
{
	PyObject *list = PyList_New(v.size());
	for (size_t i = 0; i < v.size(); i++) {
		PyList_SET_ITEM(list, i, PyLong_FromLong(v[i]));
	}
	return list;
}

PyObject *KX_ArticulationWrapper::pyattr_get_joints(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	PHY_ArticulationInfo info;
	return self->Info(info, NULL, "joints") ? int_list(info.joints) : NULL;
}

PyObject *KX_ArticulationWrapper::pyattr_get_parents(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	PHY_ArticulationInfo info;
	return self->Info(info, NULL, "parents") ? int_list(info.parents) : NULL;
}

PyObject *KX_ArticulationWrapper::pyattr_get_ordinary(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	KX_ArticulationWrapper *self = static_cast<KX_ArticulationWrapper *>(self_v);
	PHY_ArticulationInfo info;
	return self->Info(info, NULL, "ordinaryJoints") ? int_list(info.ordinary) : NULL;
}

#endif  /* WITH_PYTHON */
