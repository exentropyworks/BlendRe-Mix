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

/** \file usd_core.cpp
 *  \ingroup remix_bridge
 *
 * BGE-Remix P12: starting OpenUSD in bge_remix_usd.dll, and its self-test.
 */

#include "usd_core.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <mutex>

#include "pxr/pxr.h"
#include "pxr/base/plug/registry.h"
#include "pxr/base/tf/errorMark.h"
#include "pxr/base/tf/span.h"
#include "pxr/usd/sdf/fileFormat.h"
#include "pxr/usd/usd/stage.h"
#include "pxr/usd/usdGeom/mesh.h"
#include "pxr/usd/usdGeom/metrics.h"
#include "pxr/usd/usdGeom/primvarsAPI.h"
#include "pxr/usd/usdGeom/xform.h"
#include "pxr/usd/usdPhysics/collisionAPI.h"
#include "pxr/usd/usdPhysics/massAPI.h"
#include "pxr/usd/usdPhysics/meshCollisionAPI.h"
#include "pxr/usd/usdPhysics/parseDesc.h"
#include "pxr/usd/usdPhysics/parseUtils.h"
#include "pxr/usd/usdPhysics/rigidBodyAPI.h"
#include "pxr/usd/usdPhysics/scene.h"
#include "pxr/usd/usdPhysics/tokens.h"
#include "pxr/usd/usdShade/material.h"
#include "pxr/usd/usdShade/materialBindingAPI.h"
#include "pxr/usd/usdShade/shader.h"

PXR_NAMESPACE_USING_DIRECTIVE

namespace brb {
namespace usd {

static std::mutex g_mutex;
static bool g_started = false;

const char *version()
{
	return "25.11";
}

bool started()
{
	return g_started;
}

/* OpenUSD's errors since the mark, one line each */
static std::string errors_since(const TfErrorMark &mark)
{
	std::string text;
	for (const TfError &e : mark) {
		if (!text.empty())
			text += "; ";
		text += e.GetCommentary();
	}
	return text;
}

bool start(const std::string &plugin_dir, std::string &r_error)
{
	std::lock_guard<std::mutex> lock(g_mutex);
	if (g_started)
		return true;
	/* OpenUSD stops the whole program (a fatal error) when its first file
	 * call finds no plugin descriptions: look for them first */
	const char *env = getenv("BGE_REMIX_USD_PLUGINPATH");
	bool found = env && env[0];
	for (const char *need : {"plugInfo.json", "ar/resources/plugInfo.json", "sdf/resources/plugInfo.json",
	                         "usd/resources/plugInfo.json"}) {
		std::error_code ec;
		if (plugin_dir.empty() ||
		    !std::filesystem::exists(std::filesystem::u8path(plugin_dir + "/" + need), ec)) {
			if (!found) {
				r_error = "OpenUSD's plugin descriptions were not found (" +
				          (plugin_dir.empty() ? std::string("no usd folder given") :
				                                plugin_dir + "/" + need + " is missing") +
				          ")";
				return false;
			}
			break;
		}
		found = true;
	}
	TfErrorMark mark;
	PlugRegistry &reg = PlugRegistry::GetInstance();
	if (!plugin_dir.empty()) {
		std::string dir = plugin_dir;
		if (dir.back() != '/' && dir.back() != '\\')
			dir += '/';
		reg.RegisterPlugins(dir);
	}
	const char *formats[] = {"usda", "usdc", "usd"};
	for (const char *ext : formats) {
		if (!SdfFileFormat::FindByExtension(ext)) {
			r_error = std::string("OpenUSD's ") + ext + " file format was not found (its plugins: " +
			          (plugin_dir.empty() ? std::string("not given") : plugin_dir) + ")";
			std::string more = errors_since(mark);
			if (!more.empty())
				r_error += ": " + more;
			mark.Clear();
			return false;
		}
	}
	mark.Clear();
	g_started = true;
	return true;
}

/* ------------------------------------------------------------------------- */
/* the self-test */

namespace {

struct Report {
	std::string text;
	int failed = 0;
	void check(const std::string &name, bool ok, const std::string &detail = std::string())
	{
		text += ok ? "ok    " : "FAIL  ";
		text += name;
		if (!detail.empty())
			text += " (" + detail + ")";
		text += "\n";
		if (!ok)
			failed++;
	}
};

const SdfPath kWorld("/World");
const SdfPath kBox("/World/Box");
const SdfPath kMat("/World/Looks/Brick");
const SdfPath kShader("/World/Looks/Brick/Shader");
const SdfPath kScene("/PhysicsScene");
const TfToken kMdl("mdl");
const char *kMdlFile = "AperturePBR_Opacity.mdl";
const GfVec3f kDiffuse(0.8f, 0.3f, 0.2f);
const float kRoughness = 0.6f;
const float kMass = 5.0f;

void write_stage(const UsdStageRefPtr &stage)
{
	UsdGeomSetStageUpAxis(stage, UsdGeomTokens->z);
	UsdGeomSetStageMetersPerUnit(stage, 1.0);
	UsdGeomXform world = UsdGeomXform::Define(stage, kWorld);
	stage->SetDefaultPrim(world.GetPrim());

	/* a 1 m box, its faces each with the whole texture */
	UsdGeomMesh box = UsdGeomMesh::Define(stage, kBox);
	VtVec3fArray points;
	for (int i = 0; i < 8; i++)
		points.push_back(GfVec3f((i & 1) ? 0.5f : -0.5f, (i & 2) ? 0.5f : -0.5f, (i & 4) ? 0.5f : -0.5f));
	const int faces[6][4] = {{0, 2, 3, 1}, {4, 5, 7, 6}, {0, 1, 5, 4}, {2, 6, 7, 3}, {0, 4, 6, 2}, {1, 3, 7, 5}};
	VtIntArray counts, indices;
	VtVec2fArray st;
	const GfVec2f corners[4] = {GfVec2f(0, 0), GfVec2f(1, 0), GfVec2f(1, 1), GfVec2f(0, 1)};
	for (const auto &f : faces) {
		counts.push_back(4);
		for (int k = 0; k < 4; k++) {
			indices.push_back(f[k]);
			st.push_back(corners[k]);
		}
	}
	box.CreatePointsAttr(VtValue(points));
	box.CreateFaceVertexCountsAttr(VtValue(counts));
	box.CreateFaceVertexIndicesAttr(VtValue(indices));
	box.CreateSubdivisionSchemeAttr(VtValue(UsdGeomTokens->none));
	VtVec3fArray extent(2);
	extent[0] = GfVec3f(-0.5f);
	extent[1] = GfVec3f(0.5f);
	box.CreateExtentAttr(VtValue(extent));
	UsdGeomPrimvar uv = UsdGeomPrimvarsAPI(box).CreatePrimvar(
	    TfToken("st"), SdfValueTypeNames->TexCoord2fArray, UsdGeomTokens->faceVarying);
	uv.Set(st);

	/* an RTX Remix material, as Remix's own capture writes one */
	UsdShadeMaterial mat = UsdShadeMaterial::Define(stage, kMat);
	UsdShadeShader shader = UsdShadeShader::Define(stage, kShader);
	shader.SetSourceAsset(SdfAssetPath(kMdlFile), kMdl);
	shader.SetSourceAssetSubIdentifier(TfToken("AperturePBR_Opacity"), kMdl);
	shader.CreateInput(TfToken("diffuse_color_constant"), SdfValueTypeNames->Color3f).Set(kDiffuse);
	shader.CreateInput(TfToken("reflection_roughness_constant"), SdfValueTypeNames->Float).Set(kRoughness);
	UsdShadeOutput out = shader.CreateOutput(TfToken("out"), SdfValueTypeNames->Token);
	mat.CreateSurfaceOutput(kMdl).ConnectToSource(out);
	UsdShadeMaterialBindingAPI::Apply(box.GetPrim()).Bind(mat);

	/* physics */
	UsdPhysicsScene::Define(stage, kScene);
	UsdPhysicsRigidBodyAPI::Apply(box.GetPrim());
	UsdPhysicsMassAPI::Apply(box.GetPrim()).CreateMassAttr(VtValue(kMass));
	UsdPhysicsCollisionAPI::Apply(box.GetPrim());
	UsdPhysicsMeshCollisionAPI::Apply(box.GetPrim())
	    .CreateApproximationAttr(VtValue(UsdPhysicsTokens->convexHull));
}

std::string num(double v)
{
	char buf[64];
	snprintf(buf, sizeof(buf), "%g", v);
	return buf;
}

void read_stage(const UsdStageRefPtr &stage, const std::string &tag, Report &rep)
{
	rep.check(tag + " up axis Z", UsdGeomGetStageUpAxis(stage) == UsdGeomTokens->z,
	          UsdGeomGetStageUpAxis(stage).GetString());
	rep.check(tag + " metres per unit 1", std::fabs(UsdGeomGetStageMetersPerUnit(stage) - 1.0) < 1e-9,
	          num(UsdGeomGetStageMetersPerUnit(stage)));
	rep.check(tag + " default prim /World", stage->GetDefaultPrim().GetPath() == kWorld);

	UsdGeomMesh box(stage->GetPrimAtPath(kBox));
	rep.check(tag + " box is a mesh", bool(box));
	if (!box)
		return;
	VtVec3fArray points;
	VtIntArray counts, indices;
	box.GetPointsAttr().Get(&points);
	box.GetFaceVertexCountsAttr().Get(&counts);
	box.GetFaceVertexIndicesAttr().Get(&indices);
	bool corner_ok = points.size() == 8;
	for (size_t i = 0; corner_ok && i < points.size(); i++)
		for (int a = 0; a < 3; a++)
			if (std::fabs(std::fabs(points[i][a]) - 0.5f) > 1e-6f)
				corner_ok = false;
	rep.check(tag + " box points", corner_ok, num(points.size()) + " points");
	rep.check(tag + " box faces", counts.size() == 6 && indices.size() == 24,
	          num(counts.size()) + " faces, " + num(indices.size()) + " corners");
	UsdGeomPrimvar uv = UsdGeomPrimvarsAPI(box).GetPrimvar(TfToken("st"));
	VtVec2fArray st;
	if (uv)
		uv.Get(&st);
	rep.check(tag + " box UVs", uv && st.size() == 24 && uv.GetInterpolation() == UsdGeomTokens->faceVarying,
	          num(st.size()) + " values");

	UsdShadeMaterial mat = UsdShadeMaterialBindingAPI(box.GetPrim()).ComputeBoundMaterial();
	rep.check(tag + " material bound", mat && mat.GetPath() == kMat,
	          mat ? mat.GetPath().GetString() : std::string("none"));
	if (mat) {
		UsdShadeShader shader = mat.ComputeSurfaceSource({kMdl});
		SdfAssetPath asset;
		bool src = shader && shader.GetSourceAsset(&asset, kMdl);
		rep.check(tag + " material is AperturePBR", src && asset.GetAssetPath() == kMdlFile,
		          src ? asset.GetAssetPath() : std::string("no source asset"));
		GfVec3f diffuse(0.0f);
		float rough = 0.0f;
		if (shader) {
			shader.GetInput(TfToken("diffuse_color_constant")).Get(&diffuse);
			shader.GetInput(TfToken("reflection_roughness_constant")).Get(&rough);
		}
		rep.check(tag + " material values", GfIsClose(diffuse, kDiffuse, 1e-6) && std::fabs(rough - kRoughness) < 1e-6f,
		          "colour " + num(diffuse[0]) + " " + num(diffuse[1]) + " " + num(diffuse[2]) + ", roughness " +
		              num(rough));
	}

	float mass = 0.0f;
	UsdPhysicsMassAPI mass_api(box.GetPrim());
	if (box.GetPrim().HasAPI<UsdPhysicsMassAPI>())
		mass_api.GetMassAttr().Get(&mass);
	rep.check(tag + " rigid body with mass", box.GetPrim().HasAPI<UsdPhysicsRigidBodyAPI>() &&
	                                              std::fabs(mass - kMass) < 1e-6f,
	          "mass " + num(mass));

	/* OpenUSD's own UsdPhysics reader */
	int scenes = 0, bodies = 0, shapes = 0;
	bool shape_on_box = false;
	UsdPhysicsReportFn fn = [&](UsdPhysicsObjectType type, TfSpan<const SdfPath> paths,
	                            TfSpan<const UsdPhysicsObjectDesc> descs, const VtValue &) {
		switch (type) {
			case UsdPhysicsObjectType::Scene:
				scenes += int(paths.size());
				break;
			case UsdPhysicsObjectType::RigidBody:
				bodies += int(paths.size());
				break;
			case UsdPhysicsObjectType::MeshShape:
				shapes += int(paths.size());
				for (size_t i = 0; i < descs.size(); i++) {
					const UsdPhysicsShapeDesc &d = static_cast<const UsdPhysicsShapeDesc &>(descs[i]);
					if (d.rigidBody == kBox)
						shape_on_box = true;
				}
				break;
			default:
				break;
		}
	};
	bool parsed = LoadUsdPhysicsFromRange(stage, {SdfPath::AbsoluteRootPath()}, fn, VtValue());
	rep.check(tag + " UsdPhysics reader", parsed && scenes == 1 && bodies == 1 && shapes == 1 && shape_on_box,
	          num(scenes) + " scene, " + num(bodies) + " body, " + num(shapes) + " shape" +
	              (shape_on_box ? " on the box" : ""));
}

}  // namespace

int selftest(const std::string &plugin_dir, const std::string &folder, std::string &r_report)
{
	Report rep;
	std::string err;
	bool ok = start(plugin_dir, err);
	rep.check("OpenUSD " + std::string(version()) + " started", ok, err);
	if (!ok) {
		r_report = rep.text;
		return rep.failed;
	}
	std::string dir = folder;
	if (!dir.empty() && dir.back() != '/' && dir.back() != '\\')
		dir += '/';
	const char *exts[] = {"usda", "usdc"};
	for (const char *ext : exts) {
		const std::string path = dir + "bge_remix_usd_check." + ext;
		std::remove(path.c_str());
		TfErrorMark mark;
		{
			UsdStageRefPtr stage = UsdStage::CreateNew(path);
			rep.check(std::string(ext) + " stage created", bool(stage), errors_since(mark));
			if (!stage)
				continue;
			write_stage(stage);
			stage->GetRootLayer()->Save();
		}
		{
			UsdStageRefPtr stage = UsdStage::Open(path);
			rep.check(std::string(ext) + " stage read back", bool(stage), errors_since(mark));
			if (stage)
				read_stage(stage, ext, rep);
		}
		rep.check(std::string(ext) + " no OpenUSD errors", mark.IsClean(), errors_since(mark));
		mark.Clear();
	}
	r_report = rep.text;
	return rep.failed;
}

}  // namespace usd
}  // namespace brb
