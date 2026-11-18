# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

"""BGE-Remix P12 round 3: an RTX Remix mod as USD text (mod.usda).

Plain Python, no Blender: bge_remix_mod.py gathers what changed in the
scene into the plain dicts below and this writes them; the tests and the
OpenUSD check on GitHub use it the same way.

The layout is what Remix's mod reader takes (dxvk-remix
src/dxvk/rtx_render/rtx_mod_usd.cpp):

  /RootNode                     the default prim
    Looks/mat_<H>               a material replacement: Material, its child
                                Shader (AperturePBR) and inputs:*
    BGE_Remix_Looks/<name>      materials only the added meshes use (bound)
    meshes/mesh_<H>             a mesh replacement, drawn wherever the game
                                draws mesh H: its Mesh and light children,
                                placed in the mesh's own space;
                                preserveOriginalDrawCall 0 hides the game's
                                own mesh, 1 keeps it
    lights/light_<H>            a light replacement, with its transform

Everything is in the capture's units and axes. Matrices are USD's: row
vectors, the translation in the last row.
"""

import re

LAYER_TYPE = "replacement"

# the types of AperturePBR's inputs as Remix reads them (rtx_material_data.h:
# float, Vector3 -> color3f / float3, Vector2 -> float2, bool, uint8_t and
# its enums -> uchar); Remix reads the values unchecked, so the types must
# be these
INPUT_TYPES = {}
for _n in ("anisotropy", "emissive_intensity", "opacity_constant", "reflection_roughness_constant",
           "metallic_constant", "thin_film_thickness_constant", "displace_in", "displace_out",
           "subsurface_measurement_distance", "subsurface_volumetric_anisotropy", "subsurface_radius_scale",
           "subsurface_max_sample_radius", "dlss_control_mask_intensity", "dlss_control_mask_tone_strength",
           "dlss_control_mask_structural_strength", "texture_scroll_rate", "texture_scroll_angle",
           "texture_rotation", "ior_constant", "transmittance_measurement_distance", "thin_wall_thickness",
           "rotation_speed"):
    INPUT_TYPES[_n] = "float"
for _n in ("diffuse_color_constant", "emissive_color_constant", "subsurface_transmittance_color",
           "subsurface_single_scattering_albedo", "transmittance_color"):
    INPUT_TYPES[_n] = "color3f"
INPUT_TYPES["subsurface_radius"] = "float3"
for _n in ("texture_scale", "texture_offset"):
    INPUT_TYPES[_n] = "float2"
for _n in ("enable_emission", "enable_thin_film", "thin_film_thickness_from_albedo_alpha", "use_legacy_alpha_state",
           "blend_enabled", "inverted_blend", "subsurface_diffusion_profile", "enable_dlss_control_mask",
           "thin_walled", "use_diffuse_layer", "ignore_material", "preload_textures"):
    INPUT_TYPES[_n] = "bool"
for _n in ("sprite_sheet_rows", "sprite_sheet_cols", "sprite_sheet_fps", "alpha_test_reference_value",
           "filter_mode", "wrap_mode_u", "wrap_mode_v", "portal_index", "blend_type", "alpha_test_type"):
    INPUT_TYPES[_n] = "uchar"
for _n in ("diffuse_texture", "normalmap_texture", "tangent_texture", "height_texture", "reflectionroughness_texture",
           "metallic_texture", "emissive_mask_texture", "subsurface_transmittance_texture",
           "subsurface_thickness_texture", "subsurface_single_scattering_texture", "subsurface_radius_texture",
           "secondary_texture", "transmittance_texture"):
    INPUT_TYPES[_n] = "asset"
del _n

# Remix's blend and alpha test values (surface_shared.h)
BLEND_ALPHA = 0
BLEND_EMISSIVE = 6
ALPHA_TEST_GREATER = 4
ALPHA_TEST_ALWAYS = 7


def ident(name, used=None):
    """a USD prim name from any name (letters, digits, _; not a digit
    first), made unique among used when given"""
    s = re.sub(r"[^A-Za-z0-9_]", "_", name or "") or "_"
    if s[0].isdigit():
        s = "_" + s
    if used is not None:
        base, n = s, 1
        while s in used:
            n += 1
            s = "%s_%d" % (base, n)
        used.add(s)
    return s


def num(x):
    return "%.9g" % float(x)


def vec(v):
    return "(" + ", ".join(num(x) for x in v) + ")"


def value(kind, v):
    """a value as USD text, by its USD type"""
    if kind in ("float", "double"):
        return num(v)
    if kind in ("int", "uchar", "uint"):
        return str(int(round(float(v))))
    if kind == "bool":
        return "1" if v else "0"
    if kind in ("color3f", "float3", "float2", "vector3f", "point3f", "normal3f", "texCoord2f"):
        return vec(v)
    if kind == "asset":
        return "@" + str(v) + "@"
    if kind in ("token", "string"):
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
    raise ValueError("no USD text for a " + kind)


def matrix(m):
    """16 numbers (USD's rows) as a matrix4d"""
    rows = [m[r * 4:r * 4 + 4] for r in range(4)]
    return "( " + ", ".join(vec(r) for r in rows) + " )"


def _array(kind, items, per_line=8):
    if not items:
        return "[]"
    text = [value(kind, x) for x in items]
    lines = [", ".join(text[i:i + per_line]) for i in range(0, len(text), per_line)]
    return "[" + (",\n" if len(lines) > 1 else "").join(lines) + "]"


class Out:
    """indented lines"""

    def __init__(self):
        self.lines = []
        self.depth = 0

    def __call__(self, text=""):
        pad = "    " * self.depth
        for line in text.split("\n"):
            self.lines.append(pad + line if line else "")

    def open(self, head, meta=None):
        self(head + ((" (\n    " + "\n    ".join(meta) + "\n)") if meta else ""))
        self("{")
        self.depth += 1

    def close(self):
        self.depth -= 1
        self("}")

    def text(self):
        return "\n".join(self.lines) + "\n"


def _transform(out, m):
    if m is not None:
        out("matrix4d xformOp:transform = " + matrix(m))
        out('uniform token[] xformOpOrder = ["xformOp:transform"]')


def write_material(out, scope, name, mt):
    """at <scope>/<name>; mt: mdl (AperturePBR_Opacity or AperturePBR_Translucent), inputs [(type,
    name, value)] (type None: by INPUT_TYPES), textures {input: path}"""
    out.open('def Material "%s"' % name)
    out("token outputs:mdl:surface.connect = <%s/%s/Shader.outputs:out>" % (scope, name))
    out.open('def Shader "Shader"')
    out('uniform token info:implementationSource = "sourceAsset"')
    out("uniform asset info:mdl:sourceAsset = @%s.mdl@" % mt["mdl"])
    out('uniform token info:mdl:sourceAsset:subIdentifier = "%s"' % mt["mdl"])
    for kind, iname, v in mt["inputs"]:
        kind = kind or INPUT_TYPES[iname]
        out("%s inputs:%s = %s" % (kind, iname, value(kind, v)))
    for iname in sorted(mt.get("textures", {})):
        out("asset inputs:%s = @%s@" % (iname, mt["textures"][iname]))
    out("token outputs:out")
    out.close()
    out.close()


def write_mesh(out, name, m):
    """m: points [(x, y, z)], counts, indices; normals, uvs, colors per
    corner (or None); opacities per corner (or None); double_sided; matrix
    (or None); binding (a material path or None); subsets [{name, faces,
    binding}]"""
    meta = ['prepend apiSchemas = ["MaterialBindingAPI"]'] if m.get("binding") else None
    out.open('def Mesh "%s"' % name, meta)
    out("uniform bool doubleSided = %s" % value("bool", m.get("double_sided")))
    out('uniform token orientation = "rightHanded"')
    out('uniform token subdivisionScheme = "none"')
    out("int[] faceVertexCounts = " + _array("int", m["counts"], 32))
    out("int[] faceVertexIndices = " + _array("int", m["indices"], 32))
    out("point3f[] points = " + _array("point3f", m["points"], 4))
    if m.get("normals"):
        out("normal3f[] primvars:normals = %s (\n    interpolation = \"faceVarying\"\n)" %
            _array("normal3f", m["normals"], 4))
    if m.get("uvs"):
        out("texCoord2f[] primvars:st = %s (\n    interpolation = \"faceVarying\"\n)" %
            _array("texCoord2f", m["uvs"], 6))
    if m.get("colors"):
        out("color3f[] primvars:displayColor = %s (\n    interpolation = \"faceVarying\"\n)" %
            _array("color3f", m["colors"], 4))
    if m.get("opacities"):
        out("float[] primvars:displayOpacity = %s (\n    interpolation = \"faceVarying\"\n)" %
            _array("float", m["opacities"], 12))
    if m.get("binding"):
        out("rel material:binding = <%s>" % m["binding"])
    _transform(out, m.get("matrix"))
    for s in m.get("subsets") or ():
        meta = ['prepend apiSchemas = ["MaterialBindingAPI"]'] if s.get("binding") else None
        out.open('def GeomSubset "%s"' % s["name"], meta)
        out('uniform token elementType = "face"')
        out('uniform token familyName = "materialBind"')
        out("int[] indices = " + _array("int", s["faces"], 32))
        if s.get("binding"):
            out("rel material:binding = <%s>" % s["binding"])
        out.close()
    out.close()


LIGHT_TYPES = ("SphereLight", "DiskLight", "RectLight", "DistantLight", "CylinderLight")


def write_light(out, name, l):
    """l: type (LIGHT_TYPES), attrs [(type, name, value)] (names without
    inputs:), shaped (the cone attrs, ShapingAPI), matrix"""
    if l["type"] not in LIGHT_TYPES:
        raise ValueError("no Remix light " + l["type"])
    meta = ['prepend apiSchemas = ["ShapingAPI"]'] if l.get("shaped") else None
    out.open('def %s "%s"' % (l["type"], name), meta)
    for kind, aname, v in l["attrs"]:
        out("%s inputs:%s = %s" % (kind, aname, value(kind, v)))
    _transform(out, l.get("matrix"))
    out.close()


def mod_text(mod):
    """mod: meters_per_unit, z_up, looks {mat_<H>: material}, local_looks
    {name: material}, meshes {mesh_<H>: {preserve, meshes {name: mesh},
    lights {name: light}}}, lights {light_<H>: light}; the mod.usda text"""
    out = Out()
    out("#usda 1.0")
    out("(")
    out("    customLayerData = {")
    out('        string lightspeed_layer_type = "%s"' % LAYER_TYPE)
    out("    }")
    out('    defaultPrim = "RootNode"')
    out("    metersPerUnit = %s" % num(mod["meters_per_unit"]))
    out('    upAxis = "%s"' % ("Z" if mod["z_up"] else "Y"))
    out(")")
    out()
    out.open('def Xform "RootNode"')
    if mod.get("looks"):
        out.open('def Scope "Looks"')
        for name in sorted(mod["looks"]):
            write_material(out, "/RootNode/Looks", name, mod["looks"][name])
        out.close()
    if mod.get("local_looks"):
        out.open('def Scope "BGE_Remix_Looks"')
        for name in sorted(mod["local_looks"]):
            write_material(out, "/RootNode/BGE_Remix_Looks", name, mod["local_looks"][name])
        out.close()
    if mod.get("meshes"):
        out.open('def Xform "meshes"')
        for name in sorted(mod["meshes"]):
            r = mod["meshes"][name]
            out.open('def Xform "%s"' % name)
            out("custom int preserveOriginalDrawCall = %d" % (1 if r.get("preserve") else 0))
            for child in sorted(r.get("meshes", {})):
                write_mesh(out, child, r["meshes"][child])
            for child in sorted(r.get("lights", {})):
                write_light(out, child, r["lights"][child])
            out.close()
        out.close()
    if mod.get("lights"):
        out.open('def Xform "lights"')
        for name in sorted(mod["lights"]):
            write_light(out, name, mod["lights"][name])
        out.close()
    out.close()
    return out.text()


def expected_prims(mod):
    """the prims the mod must hold when read back: {path: type}"""
    p = {"/RootNode": "Xform"}
    for scope, key in (("Looks", "looks"), ("BGE_Remix_Looks", "local_looks")):
        for name in mod.get(key) or {}:
            p["/RootNode/%s/%s" % (scope, name)] = "Material"
            p["/RootNode/%s/%s/Shader" % (scope, name)] = "Shader"
    for name, r in (mod.get("meshes") or {}).items():
        base = "/RootNode/meshes/" + name
        p[base] = "Xform"
        for child, m in (r.get("meshes") or {}).items():
            p[base + "/" + child] = "Mesh"
            for s in m.get("subsets") or ():
                p[base + "/" + child + "/" + s["name"]] = "GeomSubset"
        for child, l in (r.get("lights") or {}).items():
            p[base + "/" + child] = l["type"]
    for name, l in (mod.get("lights") or {}).items():
        p["/RootNode/lights/" + name] = l["type"]
    return p


def check_dump(mod, dump):
    """what is wrong with a mod read back (its stage dump as a dict): a
    list of lines, empty when it is as written"""
    bad = []
    if not dump.get("ok", False):
        return ["the mod did not open"]
    for e in dump.get("errors") or ():
        bad.append("OpenUSD: %s" % e)
    if (dump.get("custom_layer_data") or {}).get("lightspeed_layer_type") != LAYER_TYPE:
        bad.append("lightspeed_layer_type is not %r" % LAYER_TYPE)
    if dump.get("default_prim") != "RootNode":
        bad.append("the default prim is not RootNode")
    if abs(float(dump.get("meters_per_unit") or 0.0) - float(mod["meters_per_unit"])) > 1e-9:
        bad.append("metersPerUnit is %r, not %r" % (dump.get("meters_per_unit"), mod["meters_per_unit"]))
    if dump.get("up_axis") != ("Z" if mod["z_up"] else "Y"):
        bad.append("upAxis is %r" % dump.get("up_axis"))
    prims = {p["path"]: p for p in dump.get("prims") or ()}
    for path, kind in sorted(expected_prims(mod).items()):
        got = prims.get(path)
        if got is None:
            bad.append("%s is missing" % path)
        elif got.get("type") != kind:
            bad.append("%s is a %s, not a %s" % (path, got.get("type"), kind))
    # every texture is there
    for scope, key in (("Looks", "looks"), ("BGE_Remix_Looks", "local_looks")):
        for name, mt in (mod.get(key) or {}).items():
            shader = prims.get("/RootNode/%s/%s/Shader" % (scope, name)) or {}
            for iname in mt.get("textures") or {}:
                a = (shader.get("attrs") or {}).get("inputs:" + iname) or {}
                v = a.get("value") or {}
                if not isinstance(v, dict) or not v.get("resolved"):
                    bad.append("%s/%s: the texture %s is not found" % (scope, name, mt["textures"][iname]))
    return bad
