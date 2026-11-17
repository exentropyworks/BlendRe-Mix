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

/** \file gameengine/Ketsji/KX_FluidWrapper.cpp
 *  \ingroup ketsji
 *
 * BGE-Remix P11 (B3): see KX_FluidWrapper.h.
 */

#include "KX_FluidWrapper.h"

#include "KX_ClientObjectInfo.h"
#include "KX_GameObject.h"
#include "KX_PyMath.h"
#include "KX_PythonInit.h"
#include "KX_Scene.h"
#include "PHY_IPhysicsController.h"
#include "PHY_IPhysicsEnvironment.h"

KX_FluidWrapper::KX_FluidWrapper(KX_GameObject *volume)
    : PyObjectPlus()
{
#ifdef WITH_PYTHON
	m_volume = volume ? volume->GetProxy() : NULL;  /* (a new reference) */
#else
	(void)volume;
#endif
}

KX_FluidWrapper::~KX_FluidWrapper()
{
#ifdef WITH_PYTHON
	Py_XDECREF(m_volume);
#endif
}

#ifdef WITH_PYTHON

PyTypeObject KX_FluidWrapper::Type = {
	PyVarObject_HEAD_INIT(NULL, 0)
	"KX_FluidWrapper",
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

PyMethodDef KX_FluidWrapper::Methods[] = {
	KX_PYMETHODTABLE_O(KX_FluidWrapper, submerged),
	{NULL, NULL}  /* Sentinel */
};

PyAttributeDef KX_FluidWrapper::Attributes[] = {
	KX_PYATTRIBUTE_RO_FUNCTION("volume", KX_FluidWrapper, pyattr_get_volume),
	KX_PYATTRIBUTE_RO_FUNCTION("type", KX_FluidWrapper, pyattr_get_type),
	KX_PYATTRIBUTE_RO_FUNCTION("density", KX_FluidWrapper, pyattr_get_density),
	KX_PYATTRIBUTE_RO_FUNCTION("drag", KX_FluidWrapper, pyattr_get_drag),
	KX_PYATTRIBUTE_RW_FUNCTION("current", KX_FluidWrapper, pyattr_get_current, pyattr_set_current),
	KX_PYATTRIBUTE_RO_FUNCTION("splashes", KX_FluidWrapper, pyattr_get_splashes),
	KX_PYATTRIBUTE_RO_FUNCTION("objects", KX_FluidWrapper, pyattr_get_objects),
	{NULL}  /* Sentinel */
};

bool KX_FluidWrapper::Info(PHY_FluidInfo &info, PHY_IPhysicsEnvironment **r_env, PHY_IPhysicsController **r_ctrl,
                           const char *what)
{
	KX_GameObject *ob = m_volume ? (KX_GameObject *)BGE_PROXY_REF(m_volume) : NULL;
	PHY_IPhysicsEnvironment *env = (ob && ob->GetScene()) ? ob->GetScene()->GetPhysicsEnvironment() : NULL;
	if (env && ob->GetPhysicsController() && env->GetFluid(ob->GetPhysicsController(), &info)) {
		if (r_env) {
			*r_env = env;
		}
		if (r_ctrl) {
			*r_ctrl = ob->GetPhysicsController();
		}
		return true;
	}
	PyErr_Format(PyExc_RuntimeError, "KX_FluidWrapper.%s: the fluid volume is gone (its object is not in the game)",
	             what);
	return false;
}

KX_PYMETHODDEF_DOC_O(KX_FluidWrapper, submerged,
                     "submerged(ob): how much of the object is under the volume's surface, 0 to 1")
{
	KX_GameObject *ob;
	if (!ConvertPythonToGameObject(KX_GetActiveScene()->GetLogicManager(), value, &ob, false,
	                               "KX_FluidWrapper.submerged(ob)"))
	{
		return NULL;
	}
	PHY_FluidInfo info;
	PHY_IPhysicsEnvironment *env;
	PHY_IPhysicsController *ctrl;
	if (!Info(info, &env, &ctrl, "submerged")) {
		return NULL;
	}
	if (!ob->GetPhysicsController()) {
		return PyFloat_FromDouble(0.0);
	}
	return PyFloat_FromDouble(env->GetSubmerged(ctrl, ob->GetPhysicsController()));
}

#define GET_INFO(what) \
	KX_FluidWrapper *self = static_cast<KX_FluidWrapper *>(self_v); \
	PHY_FluidInfo info; \
	if (!self->Info(info, NULL, NULL, what)) { \
		return NULL; \
	} (void)0

PyObject *KX_FluidWrapper::pyattr_get_volume(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("volume");
	KX_GameObject *ob = (KX_GameObject *)BGE_PROXY_REF(self->m_volume);
	return ob->GetProxy();
}

PyObject *KX_FluidWrapper::pyattr_get_type(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("type");
	return PyUnicode_FromString(info.type == 1 ? "LAVA" : "WATER");
}

PyObject *KX_FluidWrapper::pyattr_get_density(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("density");
	return PyFloat_FromDouble(info.density);
}

PyObject *KX_FluidWrapper::pyattr_get_drag(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("drag");
	return PyFloat_FromDouble(info.drag);
}

PyObject *KX_FluidWrapper::pyattr_get_current(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("current");
	return PyObjectFrom(info.current);
}

int KX_FluidWrapper::pyattr_set_current(void *self_v, const KX_PYATTRIBUTE_DEF *, PyObject *value)
{
	KX_FluidWrapper *self = static_cast<KX_FluidWrapper *>(self_v);
	MT_Vector3 current;
	if (!PyVecTo(value, current)) {
		return PY_SET_ATTR_FAIL;
	}
	PHY_FluidInfo info;
	PHY_IPhysicsEnvironment *env;
	PHY_IPhysicsController *ctrl;
	if (!self->Info(info, &env, &ctrl, "current")) {
		return PY_SET_ATTR_FAIL;
	}
	env->SetFluidCurrent(ctrl, current);
	return PY_SET_ATTR_SUCCESS;
}

PyObject *KX_FluidWrapper::pyattr_get_splashes(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("splashes");
	return PyBool_FromLong(info.splashes);
}

PyObject *KX_FluidWrapper::pyattr_get_objects(void *self_v, const KX_PYATTRIBUTE_DEF *)
{
	GET_INFO("objects");
	PyObject *list = PyList_New(0);
	for (PHY_IPhysicsController *c : info.inside) {
		KX_GameObject *ob = KX_GameObject::GetClientObject((KX_ClientObjectInfo *)c->GetNewClientInfo());
		if (ob) {
			PyObject *p = ob->GetProxy();
			PyList_Append(list, p);
			Py_DECREF(p);
		}
	}
	return list;
}

#endif  /* WITH_PYTHON */
