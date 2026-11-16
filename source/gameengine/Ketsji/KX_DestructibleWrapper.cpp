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

/** \file gameengine/Ketsji/KX_DestructibleWrapper.cpp
 *  \ingroup ketsji
 *
 * BGE-Remix P11 (B2): see KX_DestructibleWrapper.h.
 */

#include "KX_DestructibleWrapper.h"

#include "EXP_ListValue.h"
#include "KX_ClientObjectInfo.h"
#include "KX_GameObject.h"
#include "KX_PyMath.h"
#include "KX_Scene.h"
#include "PHY_IPhysicsController.h"
#include "PHY_IPhysicsEnvironment.h"

KX_DestructibleWrapper::KX_DestructibleWrapper(const std::vector<KX_GameObject *> &pieces)
    : PyObjectPlus()
{
#ifdef WITH_PYTHON
	for (KX_GameObject *ob : pieces) {
		m_pieces.push_back(ob->GetProxy());  /* (new references) */
	}
#else
	(void)pieces;
#endif
}

KX_DestructibleWrapper::~KX_DestructibleWrapper()
{
#ifdef WITH_PYTHON
	for (PyObject *p : m_pieces) {
		Py_XDECREF(p);
	}
#endif
}

#ifdef WITH_PYTHON

PyTypeObject KX_DestructibleWrapper::Type = {
	PyVarObject_HEAD_INIT(NULL, 0)
	"KX_DestructibleWrapper",
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

PyMethodDef KX_DestructibleWrapper::Methods[] = {
	KX_PYMETHODTABLE_KEYWORDS(KX_DestructibleWrapper, damage),
	{NULL, NULL}  /* Sentinel */
};

PyAttributeDef KX_DestructibleWrapper::Attributes[] = {
	KX_PYATTRIBUTE_RO_FUNCTION("root", KX_DestructibleWrapper, pyattr_get_root),
	KX_PYATTRIBUTE_RO_FUNCTION("pieces", KX_DestructibleWrapper, pyattr_get_pieces),
	KX_PYATTRIBUTE_RO_FUNCTION("brokenOff", KX_DestructibleWrapper, pyattr_get_broken_off),
	KX_PYATTRIBUTE_RO_FUNCTION("groups", KX_DestructibleWrapper, pyattr_get_groups),
	KX_PYATTRIBUTE_RO_FUNCTION("broken", KX_DestructibleWrapper, pyattr_get_broken),
	KX_PYATTRIBUTE_RO_FUNCTION("bonds", KX_DestructibleWrapper, pyattr_get_bonds),
	KX_PYATTRIBUTE_RO_FUNCTION("bondsBroken", KX_DestructibleWrapper, pyattr_get_bonds_broken),
	KX_PYATTRIBUTE_RO_FUNCTION("anchored", KX_DestructibleWrapper, pyattr_get_anchored),
	KX_PYATTRIBUTE_RW_FUNCTION("strength", KX_DestructibleWrapper, pyattr_get_strength, pyattr_set_strength),
	{NULL}  /* Sentinel */
};

static KX_GameObject *object_of(PHY_IPhysicsController *ctrl)
{
	return ctrl ? KX_GameObject::GetClientObject((KX_ClientObjectInfo *)ctrl->GetNewClientInfo()) : NULL;
}

bool KX_DestructibleWrapper::Info(PHY_DestructibleInfo &info, PHY_IPhysicsEnvironment **r_env,
                                  PHY_IPhysicsController **r_piece, const char *what)
{
	for (PyObject *p : m_pieces) {
		KX_GameObject *ob = p ? (KX_GameObject *)BGE_PROXY_REF(p) : NULL;
		PHY_IPhysicsEnvironment *env = (ob && ob->GetScene()) ? ob->GetScene()->GetPhysicsEnvironment() : NULL;
		if (env && ob->GetPhysicsController() && env->GetDestructible(ob->GetPhysicsController(), &info)) {
			if (r_env) {
				*r_env = env;
			}
			if (r_piece) {
				*r_piece = ob->GetPhysicsController();
			}
			return true;
		}
	}
	PyErr_Format(PyExc_RuntimeError, "KX_DestructibleWrapper.%s: the destructible is gone (none of its pieces is "
	             "in the game)", what);
	return false;
}

KX_PYMETHODDEF_DOC(KX_DestructibleWrapper, damage,
                   "damage(point, radius=1.0, amount=1.0): damage around a point (world): 1 breaks a bond at the "
                   "point, less towards the radius")
{
	PyObject *pypoint;
	float radius = 1.0f, amount = 1.0f;
	static const char *kwlist[] = {"point", "radius", "amount", NULL};
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|ff:damage", const_cast<char **>(kwlist), &pypoint, &radius,
	                                 &amount))
	{
		return NULL;
	}
	MT_Vector3 point;
	if (!PyVecTo(pypoint, point)) {
		return NULL;
	}
	PHY_DestructibleInfo info;
	PHY_IPhysicsEnvironment *env;
	PHY_IPhysicsController *piece;
	if (!Info(info, &env, &piece, "damage")) {
		return NULL;
	}
	env->DamageDestructible(piece, point, radius, amount);
	Py_RETURN_NONE;
}

#define GET_INFO(what) \
	KX_DestructibleWrapper *self = static_cast<KX_DestructibleWrapper *>(self_v); \
	PHY_DestructibleInfo info; \
	if (!self->Info(info, NULL, NULL, what)) { \
		return NULL; \
	} (void)0

PyObject *KX_DestructibleWrapper::pyattr_get_root(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("root");
	KX_GameObject *ob = object_of(info.root);
	if (!ob) {
		Py_RETURN_NONE;
	}
	return ob->GetProxy();
}

PyObject *KX_DestructibleWrapper::pyattr_get_pieces(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("pieces");
	PyObject *list = PyList_New(0);
	for (PHY_IPhysicsController *c : info.pieces) {
		if (KX_GameObject *ob = object_of(c)) {
			PyObject *p = ob->GetProxy();
			PyList_Append(list, p);
			Py_DECREF(p);
		}
	}
	return list;
}

PyObject *KX_DestructibleWrapper::pyattr_get_broken_off(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("brokenOff");
	PyObject *list = PyList_New(0);
	for (size_t i = 0; i < info.pieces.size(); i++) {
		if (i < info.groupOf.size() && info.groupOf[i] <= 0) {
			continue;  /* (still in the destructible itself) */
		}
		if (KX_GameObject *ob = object_of(info.pieces[i])) {
			PyObject *p = ob->GetProxy();
			PyList_Append(list, p);
			Py_DECREF(p);
		}
	}
	return list;
}

PyObject *KX_DestructibleWrapper::pyattr_get_groups(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("groups");
	return PyLong_FromLong(info.groups);
}

PyObject *KX_DestructibleWrapper::pyattr_get_broken(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("broken");
	return PyBool_FromLong(info.groups > 1 || info.bondsBroken > 0);
}

PyObject *KX_DestructibleWrapper::pyattr_get_bonds(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("bonds");
	return PyLong_FromLong(info.bonds);
}

PyObject *KX_DestructibleWrapper::pyattr_get_bonds_broken(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("bondsBroken");
	return PyLong_FromLong(info.bondsBroken);
}

PyObject *KX_DestructibleWrapper::pyattr_get_anchored(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("anchored");
	return PyBool_FromLong(info.anchored);
}

PyObject *KX_DestructibleWrapper::pyattr_get_strength(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("strength");
	return PyFloat_FromDouble(info.strength);
}

int KX_DestructibleWrapper::pyattr_set_strength(void *self_v, const KX_PYATTRIBUTE_DEF *, PyObject *value)
{
	KX_DestructibleWrapper *self = static_cast<KX_DestructibleWrapper *>(self_v);
	const double v = PyFloat_AsDouble(value);
	if (v == -1.0 && PyErr_Occurred()) {
		PyErr_SetString(PyExc_TypeError, "KX_DestructibleWrapper.strength: a number (N s)");
		return PY_SET_ATTR_FAIL;
	}
	PHY_DestructibleInfo info;
	PHY_IPhysicsEnvironment *env;
	PHY_IPhysicsController *piece;
	if (!self->Info(info, &env, &piece, "strength")) {
		return PY_SET_ATTR_FAIL;
	}
	env->SetDestructibleStrength(piece, (float)v);
	return PY_SET_ATTR_SUCCESS;
}

#endif  /* WITH_PYTHON */
