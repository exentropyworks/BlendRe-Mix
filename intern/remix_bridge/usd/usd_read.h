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

/** \file usd_read.h
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: what the capture reader (usd_capture.cpp) and the scene
 * reader (usd_scene.cpp, round 6) both read: a mesh's faces with its
 * normals, UVs and colours per corner, whatever the file's interpolation
 * or indices; a shader input's value.
 */

#ifndef __USD_READ_H__
#define __USD_READ_H__

#include <functional>
#include <string>
#include <vector>

#include "pxr/pxr.h"
#include "pxr/base/gf/matrix4d.h"
#include "pxr/base/tf/errorMark.h"
#include "pxr/usd/usd/attribute.h"
#include "pxr/usd/usdGeom/mesh.h"

namespace brb {
namespace usd {

struct MeshData {
	std::string name;
	std::vector<float> points, normals, uvs, colors;  /* colours: 4 a corner */
	std::vector<int> face_sizes, corners;
	std::string uv_name;  /* the UVs' primvar */
	bool double_sided = false;
};

/* the mesh's faces, normals, UVs (primvars:st; with any_uv, else the first
 * texCoord2f primvar) and colours (displayColor, displayOpacity) per
 * corner; left-handed faces turned round. False (with the reason through
 * note) when it has none or they do not agree */
bool read_mesh_data(const PXR_NS::UsdGeomMesh &mesh, double time, MeshData &m,
                    const std::function<void(const std::string &)> &note, bool any_uv = false);

struct Value {
	std::string name, text, path;
	int kind = 0;  /* BRU_VALUE_* */
	double v[4] = {0, 0, 0, 0};
	bool exists = false;
};

/* an attribute's value (numbers, vectors, tokens, assets: resolved, or
 * where it would be) */
bool read_value(const PXR_NS::UsdAttribute &attr, double time, Value &in);

void copy_matrix(const PXR_NS::GfMatrix4d &m, double r[16]);
std::string errors_since(const PXR_NS::TfErrorMark &mark);

}  // namespace usd
}  // namespace brb

#endif /* __USD_READ_H__ */
