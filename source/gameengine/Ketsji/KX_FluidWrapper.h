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

/** \file KX_FluidWrapper.h
 *  \ingroup ketsji
 *
 * BGE-Remix P11 (B3): bge.constraints.getFluid(ob), a fluid volume (Make
 * Fluid Volume; water or lava under PhysX) for Python. It holds the
 * volume's object.
 */

#ifndef __KX_FLUIDWRAPPER_H__
#define __KX_FLUIDWRAPPER_H__

#include "EXP_Value.h"

class KX_GameObject;
class PHY_IPhysicsEnvironment;
class PHY_IPhysicsController;
struct PHY_FluidInfo;

class KX_FluidWrapper : public PyObjectPlus
{
	Py_Header
public:
	KX_FluidWrapper(KX_GameObject *volume);
	virtual ~KX_FluidWrapper();

#ifdef WITH_PYTHON
	KX_PYMETHOD_DOC_O(KX_FluidWrapper, submerged);
	static PyObject *pyattr_get_volume(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_type(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_density(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_drag(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_current(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static int pyattr_set_current(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef, PyObject *value);
	static PyObject *pyattr_get_splashes(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_objects(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
#endif

private:
#ifdef WITH_PYTHON
	/* the volume now (false and a Python error: gone) */
	bool Info(PHY_FluidInfo &info, PHY_IPhysicsEnvironment **r_env, PHY_IPhysicsController **r_ctrl, const char *what);
	PyObject *m_volume;  /* the volume's proxy (its object NULL once freed) */
#endif
};

#endif  /* __KX_FLUIDWRAPPER_H__ */
