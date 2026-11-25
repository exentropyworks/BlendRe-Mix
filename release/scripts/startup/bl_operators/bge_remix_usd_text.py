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
                                camera a Camera, each with its transform;
                                (round 8) an armature a SkelRoot with its
                                Skeleton and a SkelAnimation for each
                                action under it, a skinned mesh bound to it

Names Blender has that USD does not take (Leg.001) are kept as the prims'
displayName. Matrices are USD's: row vectors, the translation in the last
row.
"""

try:
    from .bge_remix_mod_text import INPUT_TYPES, Out, ident, num, value, vec, matrix, _array
except ImportError:  # outside Blender (the native checks)
    from bge_remix_mod_text import INPUT_TYPES, Out, ident, num, value, vec, matrix, _array

ROOT_KINDS = ("XFORM", "MESH", "LIGHT", "CAMERA", "ARMATURE")
CREATOR = "BGE-Remix"
# the reader's node kinds (bge_remix_usd.h BRU_NODE_*)
NODE_KINDS = {0: "XFORM", 1: "MESH", 2: "LIGHT", 3: "CAMERA", 4: "ARMATURE"}
SKELETON_NAME = "Skeleton"

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
    phys = mt.get("physics")
    out.open('def Material "%s"' % prim, _meta(mt["name"], prim, [_apis(["PhysicsMaterialAPI"])] if phys else None))
    out("token outputs:surface.connect = <%s/PreviewSurface.outputs:surface>" % path)
    if phys:
        # (round 7) its friction and bounce (Blender's material physics)
        out("float physics:staticFriction = %s" % num(phys["static_friction"]))
        out("float physics:dynamicFriction = %s" % num(phys["dynamic_friction"]))
        out("float physics:restitution = %s" % num(phys["restitution"]))
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


def write_mesh(out, prim, m, looks, collider=None):
    """m: name, points, counts, indices; normals, uvs, colors per corner (or
    None); opacities; double_sided; material (an index into looks, or None);
    subsets [{name, faces, material}]. collider (round 7): the mesh is its
    object's collision shape ({approximation, material, mass})"""
    bind = m.get("material") is not None
    apis = ["MaterialBindingAPI"] if bind or (collider and collider.get("material") is not None) else []
    if collider:
        apis += ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]
        if collider.get("mass") is not None:
            apis.append("PhysicsMassAPI")
    skin = m.get("skin")
    if skin:
        apis.append("SkelBindingAPI")
    out.open('def Mesh "%s"' % prim, _meta(m.get("name"), prim, [_apis(apis)] if apis else None))
    if skin:
        # (round 8) bound to its skeleton: each vertex's joints and weights
        out("rel skel:skeleton = <%s>" % skin["skeleton_path"])
        out('uniform token skel:skinningMethod = "%s"' % skin.get("method", "classicLinear"))
        out("matrix4d primvars:skel:geomBindTransform = " + matrix(skin["geom_bind"]))
        n = skin["element_size"]
        out("int[] primvars:skel:jointIndices = %s (\n    elementSize = %d\n    interpolation = \"vertex\"\n)" %
            (_array("int", skin["indices"], 32), n))
        out("float[] primvars:skel:jointWeights = %s (\n    elementSize = %d\n    interpolation = \"vertex\"\n)" %
            (_array("float", skin["weights"], 16), n))
    if collider:
        _collider_attrs(out, collider, looks)
        out('uniform token physics:approximation = "%s"' % collider["approximation"])
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


# ---------------------------------------------------------------------------
# physics (round 7): UsdPhysics, and our own attributes (bgeRemix:*)

def _apis(names):
    return "prepend apiSchemas = [%s]" % ", ".join('"%s"' % n for n in names)


def _attrs(out, attrs, obj_paths=None):
    """(type, name, value): a type starting "custom " or "uniform " as it is;
    a "rel" names an object (its index)"""
    for kind, name, v in attrs or ():
        base = kind.split(" ")[-1]
        if base == "rel":
            out("custom rel %s = <%s>" % (name, obj_paths[v]))
        elif base.endswith("[]"):
            out("%s %s = %s" % (kind, name, _array(base[:-2], list(v), 8)))
        elif base == "quatf":
            out("%s %s = %s" % (kind, name, vec(v)))
        else:
            out("%s %s = %s" % (kind, name, value(base, v)))


def _collider_attrs(out, c, looks):
    if c.get("material") is not None:
        out("rel material:binding:physics = <%s>" % looks[c["material"]])
    if c.get("mass") is not None:
        out("float physics:mass = %s" % num(c["mass"]))


COLLIDER_PRIMS = {"cube": "Cube", "sphere": "Sphere", "capsule": "Capsule", "cylinder": "Cylinder", "cone": "Cone"}
COLLIDER_NAME = "BGE_Collider"


def write_collider(out, c, looks):
    """an object's collision shape that is not its mesh: an invisible Cube,
    Sphere, Capsule, Cylinder or Cone ({kind, center, half (cube), radius,
    height, axis, material, mass})"""
    apis = ["PhysicsCollisionAPI"] + (["MaterialBindingAPI"] if c.get("material") is not None else []) + \
        (["PhysicsMassAPI"] if c.get("mass") is not None else [])
    out.open('def %s "%s"' % (COLLIDER_PRIMS[c["kind"]], COLLIDER_NAME), [_apis(apis)])
    out('uniform token purpose = "guide"')
    _collider_attrs(out, c, looks)
    if c["kind"] == "cube":
        out("double size = 2")
    elif c["kind"] == "sphere":
        out("double radius = %s" % num(c["radius"]))
    else:
        out("double radius = %s" % num(c["radius"]))
        out("double height = %s" % num(c["height"]))
        out('uniform token axis = "%s"' % c.get("axis", "Z"))
    ops = ['"xformOp:translate"']
    out("double3 xformOp:translate = %s" % vec(c.get("center") or (0.0, 0.0, 0.0)))
    if c["kind"] == "cube":
        out("float3 xformOp:scale = %s" % vec(c["half"]))
        ops.append('"xformOp:scale"')
    out("uniform token[] xformOpOrder = [%s]" % ", ".join(ops))
    out.close()


def _samples(out, kind, name, samples, per_line=4):
    """samples: [(time, [values])]"""
    out("%s %s.timeSamples = {" % (kind, name))
    base = kind.rstrip("[]")
    for t, vals in samples:
        out("    %s: %s," % (num(t), _array(base, vals, per_line)))
    out("}")


def write_skeleton(out, sk, anim_paths):
    """sk: name (the armature's), joints (path tokens), bind (in the
    skeleton's space), rest (local; 16 each), attrs (ours), animation (the
    index of the one bound, or None)"""
    out.open('def Skeleton "%s"' % SKELETON_NAME, _meta(sk.get("name"), SKELETON_NAME, [_apis(["SkelBindingAPI"])]))
    out("uniform token[] joints = " + _array("token", sk["joints"], 4))
    out("uniform matrix4d[] bindTransforms = [%s]" % ",\n    ".join(matrix(m) for m in sk["bind"]))
    out("uniform matrix4d[] restTransforms = [%s]" % ",\n    ".join(matrix(m) for m in sk["rest"]))
    if sk.get("animation") is not None:
        out("rel skel:animationSource = <%s>" % anim_paths[sk["animation"]])
    _attrs(out, sk.get("attrs"))
    out.close()


def write_animation(out, prim, a):
    """a: name (the action's), joints, samples [(time, translations
    [(x, y, z)], rotations [(w, x, y, z)], scales [(x, y, z)])], attrs
    (ours)"""
    out.open('def SkelAnimation "%s"' % prim, _meta(a["name"], prim))
    out("uniform token[] joints = " + _array("token", a["joints"], 4))
    _samples(out, "float3[]", "translations", [(t, tr) for t, tr, _r, _s in a["samples"]])
    _samples(out, "quatf[]", "rotations", [(t, ro) for t, _t, ro, _s in a["samples"]])
    _samples(out, "half3[]", "scales", [(t, sc) for t, _t, _r, sc in a["samples"]])
    _attrs(out, a.get("attrs"))
    out.close()


def animation_paths(scene, obj_paths, names):
    """each armature's animations' prim paths: {object index: [paths]}"""
    out = {}
    for i, ob in enumerate(scene["objects"]):
        if ob["kind"] != "ARMATURE":
            continue
        used = set(names[j] for j, o in enumerate(scene["objects"]) if o["parent"] == i) | {SKELETON_NAME}
        out[i] = [obj_paths[i] + "/" + ident(a["name"], used) for a in ob.get("animations") or ()]
    return out


def skeleton_path(obj_paths, i):
    return obj_paths[i] + "/" + SKELETON_NAME


JOINT_PREFIX = "BGE_Joint_"


def write_joint(out, j, obj_paths):
    """j: prim (PhysicsRevoluteJoint, PhysicsSphericalJoint,
    PhysicsPrismaticJoint, PhysicsFixedJoint, PhysicsJoint), name, apis,
    body0 / body1 (object indices, None: the world), attrs"""
    out.open('def %s "%s"' % (j["prim"], JOINT_PREFIX + ident(j["name"])), [_apis(j["apis"])] if j.get("apis")
             else None)
    for key in ("body0", "body1"):
        if j.get(key) is not None:
            out("rel physics:%s = <%s>" % (key, obj_paths[j[key]]))
    _attrs(out, j["attrs"], obj_paths)
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
    for i, ob in enumerate(scene["objects"]):
        names.append(ident(ob["name"], used.setdefault(ob["parent"], set())))
        if ob["kind"] == "ARMATURE":
            used[i] = {SKELETON_NAME}  # (round 8) its Skeleton's name
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
    anims = animation_paths(scene, obj_paths, names)
    root = ident(scene["root"])
    out = Out()
    out("#usda 1.0")
    out("(")
    out("    customLayerData = {")
    out('        string creator = "%s"' % CREATOR)
    out("    }")
    out('    defaultPrim = "%s"' % root)
    t = scene.get("time")
    if t:
        # (round 8) the frames the animations cover, and their rate
        out("    endTimeCode = %s" % num(t["end"]))
        out("    framesPerSecond = %s" % num(t["fps"]))
    out("    metersPerUnit = 1")
    if t:
        out("    startTimeCode = %s" % num(t["start"]))
        out("    timeCodesPerSecond = %s" % num(t["fps"]))
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
        elif kind == "ARMATURE":
            # (round 8) a SkelRoot: its Skeleton, animations and what it
            # moves under it
            phys = ob.get("physics") or {}
            out.open('def SkelRoot "%s"' % prim, _meta(ob["name"], prim, [_apis(phys["apis"])] if phys.get("apis")
                                                     else None))
        else:
            phys = ob.get("physics") or {}
            out.open('def Xform "%s"' % prim, _meta(ob["name"], prim, [_apis(phys["apis"])] if phys.get("apis")
                                                  else None))
        phys = ob.get("physics") or {}
        if not ob.get("visible", True):
            out('token visibility = "invisible"')
        _transform(out, ob["matrix"])
        _attrs(out, phys.get("attrs"), obj_paths)
        _attrs(out, ob.get("attrs"), obj_paths)
        collider = phys.get("collider")
        if kind == "ARMATURE":
            write_skeleton(out, ob["skeleton"], anims[i])
            for a, path in zip(ob.get("animations") or (), anims[i]):
                write_animation(out, path.rsplit("/", 1)[1], a)
        if kind == "MESH":
            m = ob["mesh"]
            if m.get("skin"):
                m = dict(m, skin=dict(m["skin"], skeleton_path=skeleton_path(obj_paths, m["skin"]["armature"])))
            write_mesh(out, mesh_paths[i].rsplit("/", 1)[1], m, looks,
                       collider if collider and collider["kind"] == "mesh" else None)
        if collider and collider["kind"] != "mesh":
            write_collider(out, collider, looks)
        for j in phys.get("joints") or ():
            write_joint(out, j, obj_paths)
        for c in children.get(i, ()):
            write_object(c)
        out.close()

    ps = scene.get("physics_scene")
    if ps:
        out.open('def PhysicsScene "physicsScene"')
        _attrs(out, ps["attrs"])
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
    and lamps and cameras are objects of their own.

    (round 8) An Xform with one Skeleton under it (a SkelRoot, as every tool
    writes one) is an armature, in the skeleton's place, with what else is
    under it hanging from it; a Skeleton on its own is an armature too."""
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
        skels = [c for c in k if NODE_KINDS.get(nodes[c]["kind"]) == "ARMATURE"]
        if len(skels) == 1:
            # (round 8) an Xform (a SkelRoot) with one Skeleton: the armature,
            # in the skeleton's place, whatever else hangs from it
            taken[skels[0]] = i
            continue
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
    def data_name(ob):
        if ob["kind"] == "MESH":
            return ob["mesh"].get("name") or "mesh"
        if ob["kind"] == "ARMATURE":
            return ob["skeleton"].get("name") or SKELETON_NAME
        return ob["name"]

    return [{"name": ob["name"], "kind": ob["kind"], "parent": ob["parent"], "world": world[i],
             "data_name": data_name(ob)} for i, ob in enumerate(scene["objects"])]


def _flat(v):
    """a read array: a list (the native check's JSON) or bytes of float32
    (_bge_remix.usd_read's)"""
    if isinstance(v, (bytes, bytearray)):
        from array import array
        a = array("f")
        a.frombytes(bytes(v))
        return a.tolist()
    return list(v or ())


def written_order(scene):
    """the scene with its objects in the order scene_text writes them (each
    object, then what hangs from it), parents renumbered: the order the
    reader gives them back"""
    children = {}
    for i, ob in enumerate(scene["objects"]):
        children.setdefault(ob["parent"], []).append(i)
    order = []

    def walk(i):
        order.append(i)
        for c in children.get(i, ()):
            walk(c)

    for i in children.get(-1, ()):
        walk(i)
    new = {old: n for n, old in enumerate(order)}
    objects = []
    def renumber(attrs):
        return [(k, n, new[v] if k.split(" ")[-1] == "rel" else v) for k, n, v in attrs or ()]

    for i in order:
        ob = dict(scene["objects"][i])
        ob["parent"] = new[ob["parent"]] if ob["parent"] >= 0 else -1
        phys = ob.get("physics")
        if phys:
            # (round 7) the objects its joints and attributes name
            phys = dict(phys, attrs=renumber(phys.get("attrs")))
            phys["joints"] = [dict(j, attrs=renumber(j.get("attrs")),
                                   body0=new[j["body0"]] if j.get("body0") is not None else None,
                                   body1=new[j["body1"]] if j.get("body1") is not None else None)
                              for j in phys.get("joints") or ()]
            ob["physics"] = phys
        if ob.get("attrs"):
            ob["attrs"] = renumber(ob["attrs"])
        skin = (ob.get("mesh") or {}).get("skin")
        if skin:
            # (round 8) the armature it is bound to
            ob["mesh"] = dict(ob["mesh"], skin=dict(skin, armature=new[skin["armature"]]))
        objects.append(ob)
    return dict(scene, objects=objects)


def check_read(scene, read, tol=1e-6):
    """what is wrong with a scene this wrote, as the reader read it back: a
    list of lines, empty when it is as written"""
    # (round 6 fix 2: compared in the order written, not the order gathered)
    scene = written_order(scene)
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
    # (round 7) the physics, as OpenUSD's physics reader reads it
    phys = read.get("physics")
    if isinstance(phys, str):
        import json
        try:
            phys = json.loads(phys)
        except ValueError:
            phys = None
    bad += check_physics(scene, phys)
    # (round 8) the skeletons, as OpenUSD's skeleton reader reads them
    skel = read.get("skeletons")
    if isinstance(skel, str):
        import json
        try:
            skel = json.loads(skel)
        except ValueError:
            skel = None
    bad += check_skeletons(scene, skel)
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


JOINT_KINDS = {"PhysicsRevoluteJoint": "revolute", "PhysicsSphericalJoint": "spherical",
               "PhysicsPrismaticJoint": "prismatic", "PhysicsFixedJoint": "fixed", "PhysicsJoint": "d6"}


def _near(a, b, tol=1e-5):
    if isinstance(a, (list, tuple)):
        return isinstance(b, (list, tuple)) and len(a) == len(b) and all(_near(x, y, tol) for x, y in zip(a, b))
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)))
    except (TypeError, ValueError):
        return False


def expected_physics(scene):
    """what OpenUSD's physics reader must find in a scene this wrote (round
    7): {bodies {path: mass}, shapes {path: (kind, body)}, joints {path:
    (kind, rel0, rel1)}, materials {path: (static, dynamic, restitution)},
    roots [paths], gravity}"""
    obj_paths, mesh_paths, looks = paths(scene)
    bodies, shapes, joints, materials, roots = {}, {}, {}, {}, []
    is_body = {}
    for i, ob in enumerate(scene["objects"]):
        phys = ob.get("physics") or {}
        if "PhysicsRigidBodyAPI" in (phys.get("apis") or ()):
            mass = None
            for kind, name, v in phys.get("attrs") or ():
                if name == "physics:mass":
                    mass = v
            bodies[obj_paths[i]] = mass
            is_body[i] = True
        if "PhysicsArticulationRootAPI" in (phys.get("apis") or ()):
            roots.append(obj_paths[i])
    for i, ob in enumerate(scene["objects"]):
        phys = ob.get("physics") or {}
        c = phys.get("collider")
        if c:
            k = i
            while k >= 0 and not is_body.get(k):
                k = scene["objects"][k]["parent"]
            body = obj_paths[k] if k >= 0 else ""
            path = mesh_paths[i] if c["kind"] == "mesh" else obj_paths[i] + "/" + COLLIDER_NAME
            shapes[path] = (c["kind"], body)
        for j in phys.get("joints") or ():
            path = obj_paths[i] + "/" + JOINT_PREFIX + ident(j["name"])
            joints[path] = (JOINT_KINDS[j["prim"]], obj_paths[j["body0"]] if j.get("body0") is not None else "",
                            obj_paths[j["body1"]] if j.get("body1") is not None else "")
            if "PhysicsArticulationRootAPI" in (j.get("apis") or ()):
                roots.append(path)
    for i, mt in enumerate(scene["materials"]):
        p = mt.get("physics")
        if p:
            materials[looks[i]] = (p["static_friction"], p["dynamic_friction"], p["restitution"])
    gravity = None
    for kind, name, v in (scene.get("physics_scene") or {}).get("attrs") or ():
        if name == "physics:gravityMagnitude":
            gravity = v
    return {"bodies": bodies, "shapes": shapes, "joints": joints, "materials": materials, "roots": roots,
            "gravity": gravity}


def check_physics(scene, phys):
    """what is wrong with a scene's physics as OpenUSD's physics reader read
    it back (the read's physics, as a dict): a list of lines"""
    if not isinstance(phys, dict):
        return ["no physics read"]
    E = expected_physics(scene)
    bad = []
    if not phys.get("read"):
        bad.append("OpenUSD's physics reader did not read it")
    got_bodies = {b["path"]: b for b in phys.get("bodies") or ()}
    if sorted(got_bodies) != sorted(E["bodies"]):
        bad.append("bodies %s read, %s written" % (sorted(got_bodies), sorted(E["bodies"])))
    for path, mass in E["bodies"].items():
        b = got_bodies.get(path)
        if b is not None and mass is not None and not _near(b.get("mass"), mass):
            bad.append("%s: mass %s read, %s written" % (path, b.get("mass"), mass))
    got_shapes = {s["path"]: (s["kind"], s["body"]) for s in phys.get("shapes") or ()}
    if got_shapes != E["shapes"]:
        miss = sorted(set(E["shapes"].items()) - set(got_shapes.items()))
        more = sorted(set(got_shapes.items()) - set(E["shapes"].items()))
        bad.append("shapes: missing %s, more %s" % (miss[:4], more[:4]))
    got_joints = {j["path"]: (j["kind"], j["rel0"], j["rel1"]) for j in phys.get("joints") or ()}
    if got_joints != E["joints"]:
        miss = sorted(set(E["joints"].items()) - set(got_joints.items()))
        more = sorted(set(got_joints.items()) - set(E["joints"].items()))
        bad.append("joints: missing %s, more %s" % (miss[:4], more[:4]))
    got_mats = {m["path"]: (m["static_friction"], m["dynamic_friction"], m["restitution"])
                for m in phys.get("materials") or ()}
    for path, want in E["materials"].items():
        if not _near(list(got_mats.get(path) or ()), list(want)):
            bad.append("physics material %s: %s read, %s written" % (path, got_mats.get(path), want))
    roots = set(r for a in phys.get("articulations") or () for r in a.get("roots") or ())
    for r in E["roots"]:
        if r not in roots:
            bad.append("articulation root %s not found (%s)" % (r, sorted(roots)))
    if E["gravity"] is not None:
        sc = (phys.get("scenes") or [{}])[0]
        if not _near(sc.get("gravity_magnitude"), E["gravity"]):
            bad.append("gravity %s read, %s written" % (sc.get("gravity_magnitude"), E["gravity"]))
    return bad


# ---------------------------------------------------------------------------
# skeletons (round 8): as OpenUSD's skeleton reader reads them back

def expected_skeletons(scene):
    """what OpenUSD's skeleton reader must find in a scene this wrote:
    {skeletons {path: (joints, bind, rest, animation path)}, skinned {mesh
    path: skin}, animations {path: animation}, time}"""
    obj_paths, mesh_paths, _looks = paths(scene)
    names, _mats = prim_names(scene)
    anims = animation_paths(scene, obj_paths, names)
    skels, skinned, animations = {}, {}, {}
    for i, ob in enumerate(scene["objects"]):
        if ob["kind"] == "ARMATURE":
            sk = ob["skeleton"]
            a = sk.get("animation")
            skels[skeleton_path(obj_paths, i)] = (list(sk["joints"]), sk["bind"], sk["rest"],
                                                  anims[i][a] if a is not None else "")
            for an, path in zip(ob.get("animations") or (), anims[i]):
                animations[path] = an
        skin = (ob.get("mesh") or {}).get("skin")
        if skin:
            skinned[mesh_paths[i]] = dict(skin, skeleton_path=skeleton_path(obj_paths, skin["armature"]))
    return {"skeletons": skels, "skinned": skinned, "animations": animations, "time": scene.get("time")}


def _off(a, b):
    a, b = [float(x) for x in a], [float(x) for x in b]
    if len(a) != len(b):
        return float("inf")
    return max([abs(x - y) for x, y in zip(a, b)] or [0.0])


def check_skeletons(scene, skel, tol=1e-5):
    """what is wrong with a scene's skeletons as OpenUSD read them back (the
    read's skeletons, as a dict): a list of lines"""
    E = expected_skeletons(scene)
    if not (E["skeletons"] or E["skinned"] or E["animations"]):
        return []
    if not isinstance(skel, dict):
        return ["no skeletons read"]
    bad = []
    got = {s["path"]: s for s in skel.get("skeletons") or ()}
    if sorted(got) != sorted(E["skeletons"]):
        bad.append("skeletons %s read, %s written" % (sorted(got), sorted(E["skeletons"])))
    for path, (joints, bind, rest, anim) in E["skeletons"].items():
        g = got.get(path)
        if g is None:
            continue
        if not g.get("valid"):
            bad.append("%s: OpenUSD finds it broken: %s" % (path, g.get("problem")))
        if list(g["joints"]) != joints:
            bad.append("%s: joints %s read, %s written" % (path, g["joints"][:4], joints[:4]))
            continue
        d = _off(g["bind"], [x for m in bind for x in m])
        if d > tol:
            bad.append("%s: its bind transforms %.3g off" % (path, d))
        d = _off(g["rest"], [x for m in rest for x in m])
        if d > tol:
            bad.append("%s: its rest transforms %.3g off" % (path, d))
        if g.get("animation", "") != anim:
            bad.append("%s: its animation %s read, %s written" % (path, g.get("animation") or "none", anim or "none"))
    got = {s["path"]: s for s in skel.get("skinned") or ()}
    if sorted(got) != sorted(E["skinned"]):
        bad.append("skinned meshes %s read, %s written" % (sorted(got), sorted(E["skinned"])))
    for path, skin in E["skinned"].items():
        g = got.get(path)
        if g is None:
            continue
        if g["skeleton"] != skin["skeleton_path"]:
            bad.append("%s: bound to %s, not %s" % (path, g["skeleton"], skin["skeleton_path"]))
        if g["interpolation"] != "vertex" or g["element_size"] != skin["element_size"]:
            bad.append("%s: %s influences, %d each, read; vertex, %d written" % (
                path, g["interpolation"], g["element_size"], skin["element_size"]))
        elif list(g["indices"]) != list(skin["indices"]) or _off(g["weights"], skin["weights"]) > tol:
            bad.append("%s: its joint influences read back otherwise" % path)
        d = _off(g["geom_bind"], skin["geom_bind"])
        if d > tol:
            bad.append("%s: its geometry bind transform %.3g off" % (path, d))
        if g["method"] != skin.get("method", "classicLinear"):
            bad.append("%s: skinned %s, not %s" % (path, g["method"], skin.get("method", "classicLinear")))
    got = {a["path"]: a for a in skel.get("animations") or ()}
    if sorted(got) != sorted(E["animations"]):
        bad.append("animations %s read, %s written" % (sorted(got), sorted(E["animations"])))
    for path, a in E["animations"].items():
        g = got.get(path)
        if g is None:
            continue
        times = [t for t, _tr, _ro, _sc in a["samples"]]
        if _off(g["times"], times) > 1e-9:
            bad.append("%s: frames %s read, %s written" % (path, g["times"][:3], times[:3]))
            continue
        worst = [0.0, 0.0, 0.0]
        for k, (_t, tr, ro, sc) in enumerate(a["samples"]):
            worst[0] = max(worst[0], _off(g["translations"][k], [x for v in tr for x in v]))
            worst[1] = max(worst[1], _off(g["rotations"][k], [x for v in ro for x in v]))
            # scales are halfs: 3 digits
            worst[2] = max(worst[2], _off(g["scales"][k], [x for v in sc for x in v]) /
                           max(1.0, max([abs(x) for v in sc for x in v] or [1.0])))
        if worst[0] > tol or worst[1] > tol or worst[2] > 1e-3:
            bad.append("%s: its samples %.3g/%.3g/%.3g off (move/turn/scale)" % (path, worst[0], worst[1], worst[2]))
    t = E["time"]
    if t:
        gt = skel.get("time") or {}
        if not gt.get("authored") or not _near(gt.get("start"), t["start"]) or not _near(gt.get("end"), t["end"]) \
                or not _near(gt.get("fps"), t["fps"]):
            bad.append("frames %s-%s at %s read, %s-%s at %s written" % (gt.get("start"), gt.get("end"), gt.get("fps"),
                                                                         t["start"], t["end"], t["fps"]))
    return bad
