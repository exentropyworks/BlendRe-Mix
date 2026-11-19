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

"""BGE-Remix P12 round 6: a scene as USD text, for File > Export >
Universal Scene Description, and the scene the import's reader gives
turned into objects.

Plain Python, no Blender: bge_remix_usd.py gathers the scene into the plain
dicts below and this writes them; the tests and the OpenUSD check on GitHub
use it the same way.

The layout (metres, Z up, as Blender's):

  /<Scene>                      the default prim, a Scope (not an object)
    Looks/<material>            a Material: its universal surface a
                                UsdPreviewSurface (any tool reads it), with
                                UsdUVTexture shaders for its pictures; an
                                RTX Remix material also its mdl surface,
                                Remix's AperturePBR ("Shader")
    <object>                    an Xform with the object's transform
                                relative to its parent, its children under
                                it; a mesh object's mesh its child Mesh
                                (named after the mesh), split by material
                                into GeomSubsets; a lamp a UsdLux light, a
                                camera a Camera, each with its transform

Names Blender has that USD does not take (Leg.001) are kept as the prims'
displayName. Matrices are USD's: row vectors, the translation in the last
row.
"""

try:
    from .bge_remix_mod_text import INPUT_TYPES, Out, ident, num, value, vec, matrix, _array
except ImportError:  # outside Blender (the native checks)
    from bge_remix_mod_text import INPUT_TYPES, Out, ident, num, value, vec, matrix, _array

ROOT_KINDS = ("XFORM", "MESH", "LIGHT", "CAMERA")
CREATOR = "BGE-Remix"
# the reader's node kinds (bge_remix_usd.h BRU_NODE_*)
NODE_KINDS = {0: "XFORM", 1: "MESH", 2: "LIGHT", 3: "CAMERA"}

# UsdPreviewSurface's inputs and their USD types
PREVIEW_TYPES = {
    "diffuseColor": "color3f", "emissiveColor": "color3f", "specularColor": "color3f",
    "useSpecularWorkflow": "int", "metallic": "float", "roughness": "float", "clearcoat": "float",
    "clearcoatRoughness": "float", "opacity": "float", "opacityThreshold": "float", "ior": "float",
    "normal": "normal3f", "displacement": "float", "occlusion": "float",
}
# the outputs of a UsdUVTexture each preview input reads
TEXTURE_OUTPUT_TYPES = {"rgb": "float3", "r": "float", "g": "float", "b": "float", "a": "float"}


def _meta(name, prim_name, extra=None):
    meta = list(extra or ())
    if name and name != prim_name:
        meta.append("displayName = " + value("string", name))
    return meta or None


def _transform(out, m):
    if m is not None:
        out("matrix4d xformOp:transform = " + matrix(m))
        out('uniform token[] xformOpOrder = ["xformOp:transform"]')


def write_preview_material(out, path, prim, mt):
    """at path (<scope>/<prim>); mt: name, preview {inputs [(name, value)],
    textures {input: {file, output, raw, normal}}}, aperture (or None:
    write_material's mdl, inputs, textures)"""
    out.open('def Material "%s"' % prim, _meta(mt["name"], prim))
    out("token outputs:surface.connect = <%s/PreviewSurface.outputs:surface>" % path)
    ap = mt.get("aperture")
    if ap:
        out("token outputs:mdl:surface.connect = <%s/Shader.outputs:out>" % path)
    pv = mt["preview"]
    textures = pv.get("textures") or {}
    out.open('def Shader "PreviewSurface"')
    out('uniform token info:id = "UsdPreviewSurface"')
    for iname, v in pv.get("inputs") or ():
        if iname in textures:
            continue
        kind = PREVIEW_TYPES[iname]
        out("%s inputs:%s = %s" % (kind, iname, value(kind, v)))
    for iname in sorted(textures):
        t = textures[iname]
        out("%s inputs:%s.connect = <%s/%s.outputs:%s>" % (PREVIEW_TYPES[iname], iname, path, "tex_" + iname,
                                                          t["output"]))
    out("token outputs:surface")
    out.close()
    if textures:
        out.open('def Shader "st_reader"')
        out('uniform token info:id = "UsdPrimvarReader_float2"')
        out('string inputs:varname = "st"')
        out("float2 outputs:result")
        out.close()
    for iname in sorted(textures):
        t = textures[iname]
        out.open('def Shader "%s"' % ("tex_" + iname))
        out('uniform token info:id = "UsdUVTexture"')
        out("asset inputs:file = @%s@" % t["file"])
        out('token inputs:sourceColorSpace = "%s"' % ("raw" if t.get("raw") else "sRGB"))
        out("float2 inputs:st.connect = <%s/st_reader.outputs:result>" % path)
        out('token inputs:wrapS = "repeat"')
        out('token inputs:wrapT = "repeat"')
        if t.get("normal"):
            out("float4 inputs:scale = (2, 2, 2, 1)")
            out("float4 inputs:bias = (-1, -1, -1, 0)")
        out("%s outputs:%s" % (TEXTURE_OUTPUT_TYPES[t["output"]], t["output"]))
        out.close()
    if ap:
        out.open('def Shader "Shader"')
        out('uniform token info:implementationSource = "sourceAsset"')
        out("uniform asset info:mdl:sourceAsset = @%s.mdl@" % ap["mdl"])
        out('uniform token info:mdl:sourceAsset:subIdentifier = "%s"' % ap["mdl"])
        for kind, iname, v in ap["inputs"]:
            kind = kind or INPUT_TYPES[iname]
            out("%s inputs:%s = %s" % (kind, iname, value(kind, v)))
        for iname in sorted(ap.get("textures") or {}):
            out("asset inputs:%s = @%s@" % (iname, ap["textures"][iname]))
        out("token outputs:out")
        out.close()
    out.close()


def write_mesh(out, prim, m, looks):
    """m: name, points, counts, indices; normals, uvs, colors per corner (or
    None); opacities; double_sided; material (an index into looks, or None);
    subsets [{name, faces, material}]"""
    bind = m.get("material") is not None
    out.open('def Mesh "%s"' % prim, _meta(m.get("name"), prim, ['prepend apiSchemas = ["MaterialBindingAPI"]']
                                           if bind else None))
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
    if bind:
        out("rel material:binding = <%s>" % looks[m["material"]])
    if m.get("subsets"):
        out('uniform token subsetFamily:materialBind:familyType = "partition"')
    for s in m.get("subsets") or ():
        sb = s.get("material") is not None
        out.open('def GeomSubset "%s"' % s["name"], ['prepend apiSchemas = ["MaterialBindingAPI"]'] if sb else None)
        out('uniform token elementType = "face"')
        out('uniform token familyName = "materialBind"')
        out("int[] indices = " + _array("int", s["faces"], 32))
        if sb:
            out("rel material:binding = <%s>" % looks[s["material"]])
        out.close()
    out.close()


def write_light_attrs(out, l):
    for kind, aname, v in l["attrs"]:
        out("%s inputs:%s = %s" % (kind, aname, value(kind, v)))


def write_camera_attrs(out, c):
    out("float focalLength = %s" % num(c["focal_length"]))
    out("float horizontalAperture = %s" % num(c["horizontal_aperture"]))
    out("float verticalAperture = %s" % num(c["vertical_aperture"]))
    out("float2 clippingRange = %s" % vec(c["clipping"]))
    out('token projection = "%s"' % ("perspective" if c.get("perspective", True) else "orthographic"))


def prim_names(scene):
    """each object's and material's prim name, unique among its siblings"""
    used = {}
    names = []
    for ob in scene["objects"]:
        names.append(ident(ob["name"], used.setdefault(ob["parent"], set())))
    looks = set()
    mats = [ident(mt["name"], looks) for mt in scene["materials"]]
    return names, mats


def paths(scene):
    """every object's prim path, its mesh's (or None), every material's"""
    root = "/" + ident(scene["root"])
    names, mats = prim_names(scene)
    obj = []
    for i, ob in enumerate(scene["objects"]):
        parent = root if ob["parent"] < 0 else obj[ob["parent"]]
        obj.append(parent + "/" + names[i])
    mesh = []
    for i, ob in enumerate(scene["objects"]):
        if ob["kind"] == "MESH":
            used = set(names[j] for j, o in enumerate(scene["objects"]) if o["parent"] == i)
            mesh.append(obj[i] + "/" + ident(ob["mesh"].get("name") or "mesh", used))
        else:
            mesh.append(None)
    return obj, mesh, [root + "/Looks/" + m for m in mats]


def scene_text(scene):
    """scene: root (its name), objects [{name, kind (ROOT_KINDS), parent
    (an earlier object's index, -1: none), matrix (16, local to the
    parent), visible, mesh / light (write_light's) / camera}], materials
    [{name, preview, aperture}]; the .usda text. Objects come parents first."""
    obj_paths, mesh_paths, looks = paths(scene)
    names, mats = prim_names(scene)
    root = ident(scene["root"])
    out = Out()
    out("#usda 1.0")
    out("(")
    out("    customLayerData = {")
    out('        string creator = "%s"' % CREATOR)
    out("    }")
    out('    defaultPrim = "%s"' % root)
    out("    metersPerUnit = 1")
    out('    upAxis = "Z"')
    out(")")
    out()
    out.open('def Scope "%s"' % root, _meta(scene["root"], root))
    if scene["materials"]:
        out.open('def Scope "Looks"')
        for i, mt in enumerate(scene["materials"]):
            write_preview_material(out, looks[i], mats[i], mt)
        out.close()
    children = {}
    for i, ob in enumerate(scene["objects"]):
        children.setdefault(ob["parent"], []).append(i)

    def write_object(i):
        ob = scene["objects"][i]
        prim = names[i]
        kind = ob["kind"]
        if kind == "LIGHT":
            l = ob["light"]
            out.open('def %s "%s"' % (l["type"], prim),
                     _meta(ob["name"], prim, ['prepend apiSchemas = ["ShapingAPI"]'] if l.get("shaped") else None))
            write_light_attrs(out, l)
        elif kind == "CAMERA":
            out.open('def Camera "%s"' % prim, _meta(ob["name"], prim))
            write_camera_attrs(out, ob["camera"])
        else:
            out.open('def Xform "%s"' % prim, _meta(ob["name"], prim))
        if not ob.get("visible", True):
            out('token visibility = "invisible"')
        _transform(out, ob["matrix"])
        if kind == "MESH":
            write_mesh(out, mesh_paths[i].rsplit("/", 1)[1], ob["mesh"], looks)
        for c in children.get(i, ()):
            write_object(c)
        out.close()

    for i in children.get(-1, ()):
        write_object(i)
    out.close()
    return out.text()


# ---------------------------------------------------------------------------
# reading: what the import's reader gives (bge_remix_usd.h bru_scene_api, as
# _bge_remix.usd_read's dict) turned into objects

def mat_mul(a, b):
    """USD rows: a then b"""
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


IDENTITY = [1.0 if r == c else 0.0 for r in range(4) for c in range(4)]


def objects_from_read(read):
    """the objects a read scene becomes: [{name, kind, parent (an earlier
    object's index, -1), node (the node it is), data_node (the mesh, light
    or camera node: its own, or a child it took in), data_name, matrix
    (local to world), visible}].

    An Xform whose only child is a mesh, light or camera with no children
    of its own takes it in: one object, the Xform's name, the child's world
    place (how most tools write an object: Maya's camera1/cameraShape1); a
    light or camera only when it sits where its Xform is. In this export's
    own files a mesh object is an Xform with its mesh and its child objects
    under it: there the one mesh child is taken in whatever else is there,
    and lamps and cameras are objects of their own."""
    nodes = read["nodes"]
    ours = read.get("creator") == CREATOR
    kids = {}
    for i, n in enumerate(nodes):
        kids.setdefault(n["parent"], []).append(i)
    taken = {}
    for i, n in enumerate(nodes):
        if NODE_KINDS.get(n["kind"]) != "XFORM":
            continue
        k = kids.get(i, [])
        if ours:
            data = [c for c in k if NODE_KINDS.get(nodes[c]["kind"]) == "MESH"]
        else:
            data = k if len(k) == 1 and NODE_KINDS.get(nodes[k[0]]["kind"]) != "XFORM" else []
        if len(data) != 1 or kids.get(data[0]):
            continue
        c = data[0]
        if NODE_KINDS[nodes[c]["kind"]] == "MESH" or \
                max(abs(a - b) for a, b in zip(nodes[c]["matrix"], n["matrix"])) < 1e-9:
            taken[c] = i
    owner_of = {v: k for k, v in taken.items()}
    objects = []
    of_node = {}
    for i, n in enumerate(nodes):
        if i in taken:
            continue
        data = owner_of.get(i, i)
        kind = NODE_KINDS.get(nodes[data]["kind"], "XFORM")
        p = n["parent"]
        while p >= 0 and p not in of_node:
            p = nodes[p]["parent"]
        objects.append({"name": n["name"], "kind": kind, "parent": of_node[p] if p >= 0 else -1, "node": i,
                        "data_node": data, "data_name": nodes[data]["name"],
                        "matrix": list(nodes[data]["matrix"]), "visible": bool(nodes[data].get("visible", 1))})
        of_node[i] = len(objects) - 1
    return objects


def expected_objects(scene):
    """what objects_from_read must give for a scene this wrote: [{name,
    kind, parent, world}]"""
    world = []
    for ob in scene["objects"]:
        m = ob["matrix"]
        world.append(m if ob["parent"] < 0 else mat_mul(m, world[ob["parent"]]))
    return [{"name": ob["name"], "kind": ob["kind"], "parent": ob["parent"], "world": world[i],
             "data_name": (ob["mesh"].get("name") or "mesh") if ob["kind"] == "MESH" else ob["name"]}
            for i, ob in enumerate(scene["objects"])]


def _flat(v):
    """a read array: a list (the native check's JSON) or bytes of float32
    (_bge_remix.usd_read's)"""
    if isinstance(v, (bytes, bytearray)):
        from array import array
        a = array("f")
        a.frombytes(bytes(v))
        return a.tolist()
    return list(v or ())


def check_read(scene, read, tol=1e-6):
    """what is wrong with a scene this wrote, as the reader read it back: a
    list of lines, empty when it is as written"""
    bad = []
    if "error" in read:
        return ["not read: %s" % read["error"]]
    if read.get("usd_errors"):
        bad.append("OpenUSD complained %d time(s)" % read["usd_errors"])
    if abs(float(read.get("meters_per_unit", 0.0)) - 1.0) > 1e-12 or not read.get("z_up"):
        bad.append("not in metres, Z up")
    if read.get("report"):
        for line in read["report"].strip().split("\n"):
            bad.append("reported: " + line)
    got = objects_from_read(read)
    want = expected_objects(scene)
    if len(got) != len(want):
        bad.append("%d objects read, %d written" % (len(got), len(want)))
        return bad
    for g, w in zip(got, want):
        if g["name"] != w["name"] or g["kind"] != w["kind"] or g["parent"] != w["parent"]:
            bad.append("%s (%s, under %d) read as %s (%s, under %d)" % (w["name"], w["kind"], w["parent"], g["name"],
                                                                      g["kind"], g["parent"]))
            continue
        if g["data_name"] != w["data_name"]:
            bad.append("%s: its data %s read as %s" % (w["name"], w["data_name"], g["data_name"]))
        d = max(abs(a - b) for a, b in zip(g["matrix"], w["world"]))
        if d > tol:
            bad.append("%s: placed %.3g off" % (w["name"], d))
    # meshes: counts, subsets, materials
    for g, ob in zip(got, scene["objects"]):
        if ob["kind"] != "MESH":
            continue
        node = read["nodes"][g["data_node"]]
        me = read["meshes"][node["index"]]
        m = ob["mesh"]
        if me["vertices"] != len(m["points"]) or me["faces"] != len(m["counts"]) or \
                me["corners"] != len(m["indices"]):
            bad.append("%s: %d/%d/%d vertices/faces/corners read, %d/%d/%d written" % (
                ob["name"], me["vertices"], me["faces"], me["corners"], len(m["points"]), len(m["counts"]),
                len(m["indices"])))
        for key, width in (("uvs", 2), ("colors", 3)):
            if bool(m.get(key)) != bool(me.get(key)):
                bad.append("%s: %s %s" % (ob["name"], key, "lost" if m.get(key) else "appeared"))
            elif m.get(key):
                flat = [x for v in m[key] for x in v]
                rd = _flat(me[key])
                if key == "colors":
                    rd = [c for i, c in enumerate(rd) if i % 4 < 3]
                d = max(abs(a - b) for a, b in zip(flat, rd))
                if d > tol:
                    bad.append("%s: its %s %.3g off" % (ob["name"], key, d))
        want_subsets = [(s["name"], list(s["faces"])) for s in m.get("subsets") or ()]
        got_subsets = [(s["name"], list(s["faces"])) for s in me["subsets"]]
        if want_subsets != got_subsets:
            bad.append("%s: subsets %s read as %s" % (ob["name"], want_subsets, got_subsets))
        mats = read["materials"]

        def mname(i):
            return mats[i]["name"] if i is not None and i >= 0 else None

        want_mat = scene["materials"][m["material"]]["name"] if m.get("material") is not None else None
        if mname(node["material"]) != want_mat:
            bad.append("%s: bound to %s, not %s" % (ob["name"], mname(node["material"]), want_mat))
        for s, i in zip(m.get("subsets") or (), node["subset_materials"]):
            w = scene["materials"][s["material"]]["name"] if s.get("material") is not None else None
            if mname(i) != w:
                bad.append("%s: its %s bound to %s, not %s" % (ob["name"], s["name"], mname(i), w))
    # materials: OpenUSD finds the surfaces written
    by_name = {mt["name"]: mt for mt in read["materials"]}
    for mt in scene["materials"]:
        r = by_name.get(mt["name"])
        if r is None:
            bad.append("material %s not read (not bound?)" % mt["name"])
            continue
        if not r["preview"]:
            bad.append("material %s: OpenUSD finds no UsdPreviewSurface" % mt["name"])
        if bool(mt.get("aperture")) != bool(r["aperture"]):
            bad.append("material %s: AperturePBR %s" % (mt["name"], "not found" if mt.get("aperture") else "found"))
        for iname, t in (mt["preview"].get("textures") or {}).items():
            got_in = r["preview_inputs"].get(iname)
            if not got_in or got_in.get("kind") != 6 or not got_in.get("exists") or got_in.get("output") != t["output"]:
                bad.append("material %s: its %s picture %s not found" % (mt["name"], iname, t["file"]))
        for iname, v in mt["preview"].get("inputs") or ():
            if iname in (mt["preview"].get("textures") or {}):
                continue
            got_in = r["preview_inputs"].get(iname)
            vv = list(v) if isinstance(v, (list, tuple)) else [v]
            if not got_in or max(abs(a - b) for a, b in zip(vv, got_in["v"])) > 1e-6:
                bad.append("material %s: its %s read as %s, not %s" % (mt["name"], iname,
                                                                       got_in and got_in["v"][:len(vv)], vv))
    return bad
