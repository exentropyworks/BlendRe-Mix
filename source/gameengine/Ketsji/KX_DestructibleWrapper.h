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

/** \file KX_DestructibleWrapper.h
 *  \ingroup ketsji
 *
 * BGE-Remix P11 (B2): bge.constraints.getDestructible(ob), a destructible
 * (Make Destructible; broken by NVIDIA Blast under PhysX) for Python. It
 * holds its pieces' objects: the destructible is found again from any of
 * them still in the game.
 */

#ifndef __KX_DESTRUCTIBLEWRAPPER_H__
#define __KX_DESTRUCTIBLEWRAPPER_H__

#include <vector>

#include "EXP_Value.h"

class KX_GameObject;
class PHY_IPhysicsEnvironment;
class PHY_IPhysicsController;
struct PHY_DestructibleInfo;

class KX_DestructibleWrapper : public PyObjectPlus
{
	Py_Header

public:
	KX_DestructibleWrapper(const std::vector<KX_GameObject *> &pieces);
	virtual ~KX_DestructibleWrapper();

#ifdef WITH_PYTHON
	KX_PYMETHOD_DOC(KX_DestructibleWrapper, damage);

	static PyObject *pyattr_get_root(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_pieces(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_broken_off(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_groups(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_broken(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_bonds(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_bonds_broken(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_anchored(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static PyObject *pyattr_get_strength(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef);
	static int pyattr_set_strength(void *self_v, const KX_PYATTRIBUTE_DEF *attrdef, PyObject *value);
#endif

private:
#ifdef WITH_PYTHON
	/* the destructible now, from a piece still in the game (false and a Python error: gone) */
	bool Info(PHY_DestructibleInfo &info, PHY_IPhysicsEnvironment **r_env, PHY_IPhysicsController **r_piece,
	          const char *what);

	std::vector<PyObject *> m_pieces;  /* the pieces' proxies (their objects NULL once freed) */
#endif
};

#endif  /* __KX_DESTRUCTIBLEWRAPPER_H__ */
