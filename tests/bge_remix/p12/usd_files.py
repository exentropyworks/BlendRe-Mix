"""BGE-Remix P12 round 6: USD files written by script the way other tools
write them, for File > Import > Universal Scene Description (T12.d3, T12.d4)
and the native check (native/check_scene.py). Plain Python, no Blender.

other_tool(folder): other_tool.usda and prop.usda, in centimetres and Y up
(a Maya-like file):

  /World                         an Xform
    Shelf                        an Xform: moved, turned 90 degrees about Y
      Board                      an Xform, its child Mesh BoardShape: a
                                 120 x 4 x 40 cm board, UVs stored with
                                 indices, bound to Looks/Wood
      Pot_1, Pot_2               instances (instanceable) of prop.usda's
                                 /Pot: a 10 cm box PotShape; Pot_2 half as
                                 big again
    Bulb                         a sphere light 2.5 m up
    camera1                      an Xform, its child Camera cameraShape1
    Looks/Wood                   a UsdPreviewSurface: its diffuseColor a
                                 picture (textures/wood.png), roughness 0.7

unsupported(folder): unsupported.usda (metres, Z up): a floor and a box
(meshes, which come in), the floor bound to a material whose only shader is
a custom one; a BasisCurves "Hair"; a PointInstancer "Rocks" with a
prototype mesh under it.

character_other(folder) (round 8, T12.f3): character_other.usda, a
character the way Maya writes one: centimetres, Y up, 30 frames a second
(frames 1 to 30, a sample every frame):

  /World/Character               a SkelRoot, moved (50, 0, -20) cm
    Skel                         a Skeleton of 7 joints with no length,
                                 each one's X along its limb (Maya's): root
                                 (hips, 1 m up), spine, chest, arm_l,
                                 hand_l, leg_l, foot_l; bound to Anim
      Anim                       a SkelAnimation of 4 of them, in an order of
                                 its own (root bobs 3 cm, the spine bends
                                 15 degrees, the arm swings 40, the leg 25),
                                 and the blend shape Smile's weight
    Body                         a Mesh of six boxes along the limbs, every
                                 vertex on 4 joints, its geometry bind
                                 transform 2 cm up; a blend shape Smile
"""

import math
import os
import struct
import zlib


def png(path, w, h, pixel):
    """an RGBA PNG; pixel(x, y) (y from the top) -> (r, g, b, a) 0..255"""
    rows = b""
    for y in range(h):
        rows += b"\x00" + b"".join(struct.pack("BBBB", *pixel(x, y)) for x in range(w))

    def chunk(kind, data):
        c = struct.pack(">I", len(data)) + kind + data
        return c + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


# -- 4x4 matrices as USD has them (rows; the translation last) ----------------

def m_mul(a, b):
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def m_translate(x, y, z):
    return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]


def m_scale(s):
    return [s, 0, 0, 0, 0, s, 0, 0, 0, 0, s, 0, 0, 0, 0, 1]


def m_rotate_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    # row vectors: p' = p M (USD's rotateY)
    return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]


def to_blender(p, meters_per_unit, z_up):
    """a point in a file's space in Blender's (metres, Z up)"""
    x, y, z = (c * meters_per_unit for c in p)
    return (x, y, z) if z_up else (x, -z, y)


def box(sx, sy, sz):
    """a box centred on its origin: points, counts, indices"""
    pts = [(x * sx / 2.0, y * sy / 2.0, z * sz / 2.0) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return pts, [4] * 6, [i for q in quads for i in q]


def _f(v):
    return "%.9g" % v


def _v(t):
    return "(" + ", ".join(_f(c) for c in t) + ")"


def _mesh_text(name, size, indent, uv_indexed, binding=None):
    pts, counts, idx = box(*size)
    pad = " " * indent
    meta = '(\n%s    prepend apiSchemas = ["MaterialBindingAPI"]\n%s)\n' % (pad, pad) if binding else "\n"
    t = '%sdef Mesh "%s" %s%s{\n' % (pad, name, meta, pad)
    t += '%s    uniform token subdivisionScheme = "none"\n' % pad
    t += "%s    int[] faceVertexCounts = [%s]\n" % (pad, ", ".join(str(c) for c in counts))
    t += "%s    int[] faceVertexIndices = [%s]\n" % (pad, ", ".join(str(i) for i in idx))
    t += "%s    point3f[] points = [%s]\n" % (pad, ", ".join(_v(p) for p in pts))
    if uv_indexed:
        # four UVs, each face's corners through them (as Maya writes them)
        t += '%s    texCoord2f[] primvars:st = [(0, 0), (1, 0), (1, 1), (0, 1)] (\n' % pad
        t += '%s        interpolation = "faceVarying"\n%s    )\n' % (pad, pad)
        t += "%s    int[] primvars:st:indices = [%s]\n" % (pad, ", ".join(["0, 1, 2, 3"] * 6))
    if binding:
        t += "%s    rel material:binding = <%s>\n" % (pad, binding)
    t += "%s}\n" % pad
    return t


# the other tool's file: its objects' places in its own space, its picture
SHELF = m_mul(m_rotate_y(90.0), m_translate(100.0, 0.0, -50.0))
BOARD = m_mul(m_translate(0.0, 80.0, 0.0), SHELF)
POT_1 = m_mul(m_translate(-30.0, 84.0, 0.0), SHELF)
POT_2 = m_mul(m_mul(m_scale(1.5), m_translate(30.0, 84.0, 0.0)), SHELF)
BULB = m_translate(0.0, 250.0, 0.0)
CAMERA = m_translate(0.0, 150.0, 600.0)
WOOD = (200, 140, 80, 255)

# what the import must make of it: object, kind, parent, place (metres, Z up)
OTHER_TOOL_OBJECTS = [
    ("World", "XFORM", None, (0.0, 0.0, 0.0)),
    ("Shelf", "XFORM", "World", to_blender(SHELF[12:15], 0.01, False)),
    ("Board", "MESH", "Shelf", to_blender(BOARD[12:15], 0.01, False)),
    ("Pot_1", "MESH", "Shelf", to_blender(POT_1[12:15], 0.01, False)),
    ("Pot_2", "MESH", "Shelf", to_blender(POT_2[12:15], 0.01, False)),
    ("Bulb", "LIGHT", "World", to_blender(BULB[12:15], 0.01, False)),
    ("camera1", "CAMERA", "World", to_blender(CAMERA[12:15], 0.01, False)),
]


def other_tool(folder):
    """writes other_tool.usda, prop.usda and textures/wood.png into folder;
    returns other_tool.usda's path"""
    os.makedirs(os.path.join(folder, "textures"), exist_ok=True)
    png(os.path.join(folder, "textures", "wood.png"), 8, 8,
        lambda x, y: WOOD if (x + y) % 2 == 0 else (150, 100, 60, 255))
    prop = '#usda 1.0\n(\n    defaultPrim = "Pot"\n    metersPerUnit = 0.01\n    upAxis = "Y"\n)\n\n'
    prop += 'def Xform "Pot"\n{\n' + _mesh_text("PotShape", (10.0, 10.0, 10.0), 4, False) + "}\n"
    with open(os.path.join(folder, "prop.usda"), "w") as f:
        f.write(prop)

    def xf(m):
        return "        matrix4d xformOp:transform = ( %s )\n        uniform token[] xformOpOrder = " \
               "[\"xformOp:transform\"]\n" % ", ".join(_v(m[r * 4:r * 4 + 4]) for r in range(4))

    t = '#usda 1.0\n(\n    defaultPrim = "World"\n    metersPerUnit = 0.01\n    upAxis = "Y"\n)\n\n'
    t += 'def Xform "World"\n{\n'
    t += '    def Xform "Shelf"\n    {\n'
    t += '        double3 xformOp:translate = (100, 0, -50)\n        float xformOp:rotateY = 90\n'
    t += '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateY"]\n'
    t += '        def Xform "Board"\n        {\n            double3 xformOp:translate = (0, 80, 0)\n'
    t += '            uniform token[] xformOpOrder = ["xformOp:translate"]\n'
    t += _mesh_text("BoardShape", (120.0, 4.0, 40.0), 12, True, "/World/Looks/Wood")
    t += "        }\n"
    for name, loc, scale in (("Pot_1", (-30, 84, 0), None), ("Pot_2", (30, 84, 0), 1.5)):
        t += '        def Xform "%s" (\n            instanceable = true\n            prepend references = ' \
             '@./prop.usda@</Pot>\n        )\n        {\n' % name
        t += "            double3 xformOp:translate = %s\n" % _v(loc)
        if scale:
            t += "            float3 xformOp:scale = (%s, %s, %s)\n" % (scale, scale, scale)
            t += '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]\n'
        else:
            t += '            uniform token[] xformOpOrder = ["xformOp:translate"]\n'
        t += "        }\n"
    t += "    }\n"
    t += '    def SphereLight "Bulb"\n    {\n        float inputs:intensity = 5000\n        float inputs:radius = 5\n'
    t += '        color3f inputs:color = (1, 0.9, 0.8)\n'
    t += '        double3 xformOp:translate = (0, 250, 0)\n        uniform token[] xformOpOrder = ["xformOp:translate"]\n'
    t += "    }\n"
    t += '    def Xform "camera1"\n    {\n        double3 xformOp:translate = (0, 150, 600)\n'
    t += '        uniform token[] xformOpOrder = ["xformOp:translate"]\n'
    t += '        def Camera "cameraShape1"\n        {\n            float focalLength = 35\n'
    t += '            float horizontalAperture = 36\n            float verticalAperture = 24\n'
    t += '            float2 clippingRange = (1, 10000)\n        }\n    }\n'
    t += '    def Scope "Looks"\n    {\n        def Material "Wood"\n        {\n'
    t += '            token outputs:surface.connect = </World/Looks/Wood/surf.outputs:surface>\n'
    t += '            def Shader "surf"\n            {\n                uniform token info:id = "UsdPreviewSurface"\n'
    t += '                color3f inputs:diffuseColor.connect = </World/Looks/Wood/wood_tex.outputs:rgb>\n'
    t += '                float inputs:roughness = 0.7\n                token outputs:surface\n            }\n'
    t += '            def Shader "uv"\n            {\n                uniform token info:id = "UsdPrimvarReader_float2"\n'
    t += '                string inputs:varname = "st"\n                float2 outputs:result\n            }\n'
    t += '            def Shader "wood_tex"\n            {\n                uniform token info:id = "UsdUVTexture"\n'
    t += '                asset inputs:file = @./textures/wood.png@\n'
    t += '                float2 inputs:st.connect = </World/Looks/Wood/uv.outputs:result>\n'
    t += '                float3 outputs:rgb\n            }\n        }\n    }\n'
    t += "}\n"
    path = os.path.join(folder, "other_tool.usda")
    with open(path, "w") as f:
        f.write(t)
    return path


# what the import must name, and what must come in
UNSUPPORTED_REPORT = ("MyStudio_Toon", "/Root/Hair: a BasisCurves", "/Root/Rocks: a point instancer")
UNSUPPORTED_MESHES = ("Floor", "Box")


def unsupported(folder):
    os.makedirs(folder, exist_ok=True)
    t = '#usda 1.0\n(\n    defaultPrim = "Root"\n    metersPerUnit = 1\n    upAxis = "Z"\n)\n\n'
    t += 'def Xform "Root"\n{\n'
    t += _mesh_text("Floor", (4.0, 4.0, 0.1), 4, False, "/Root/Looks/Custom")
    t += '    def Xform "Lift"\n    {\n        double3 xformOp:translate = (0, 0, 1)\n'
    t += '        uniform token[] xformOpOrder = ["xformOp:translate"]\n'
    t += _mesh_text("Box", (0.5, 0.5, 0.5), 8, False)
    t += "    }\n"
    t += '    def BasisCurves "Hair"\n    {\n        uniform token type = "linear"\n        int[] curveVertexCounts = [3]\n'
    t += '        point3f[] points = [(0, 0, 0), (0, 0, 1), (0, 1, 1)]\n    }\n'
    t += '    def PointInstancer "Rocks"\n    {\n        rel prototypes = </Root/Rocks/Prototypes/Rock>\n'
    t += '        int[] protoIndices = [0, 0]\n        point3f[] positions = [(1, 1, 0), (2, 1, 0)]\n'
    t += '        def Scope "Prototypes"\n        {\n'
    t += _mesh_text("Rock", (0.2, 0.2, 0.2), 12, False)
    t += "        }\n    }\n"
    t += '    def Scope "Looks"\n    {\n        def Material "Custom"\n        {\n'
    t += '            token outputs:surface.connect = </Root/Looks/Custom/Toon.outputs:surface>\n'
    t += '            def Shader "Toon"\n            {\n                uniform token info:id = "MyStudio_Toon"\n'
    t += '                color3f inputs:paint = (1, 0, 0)\n                token outputs:surface\n            }\n'
    t += "        }\n    }\n}\n"
    path = os.path.join(folder, "unsupported.usda")
    with open(path, "w") as f:
        f.write(t)
    return path


# ---------------------------------------------------------------------------
# (round 7) another tool's physics: physics_other(folder) writes
# physics_other.usda the way Omniverse and Isaac Sim write them (centimetres,
# Y up, kilograms):
#
#   /World/physicsScene     gravity 981 cm/s² down (-Y)
#   /World/Floor            a 400 x 10 x 400 cm Mesh, only a collider
#                           (a triangle mesh), its physics material Rubber
#                           (friction 0.9 / 0.8, bounce 0.3)
#   /World/Crate            a body with only a density (0.0005 kg/cm³: 500
#                           kg/m³, so 32 kg for its 40 cm cube), its mesh a
#                           convex decomposition, 30 cm up
#   /World/Lamp             a 1 kg body welded to the crate (a fixed joint)
#   /World/Robot            the articulation root (on the Xform above it)
#     Base                  10 kg, fixed to the world (BaseFixed)
#     Link1, Link2, Gripper 2, 1 and 0.5 kg; Shoulder (revolute about Y, the
#                           up axis: -90..90), Elbow (revolute about Z:
#                           -45..120), Slide (prismatic along X: 0..10 cm)
#   /World/Rope             a distance joint (crate to gripper): not taken
#   /World/Debris           a collision group (the crate): not taken

def _phys_mesh(name, size, indent, apis, approximation, extra=""):
    pts, counts, idx = box(*size)
    pad = " " * indent
    t = '%sdef Mesh "%s" (\n%s    prepend apiSchemas = [%s]\n%s)\n%s{\n' % (
        pad, name, pad, ", ".join('"%s"' % a for a in apis), pad, pad)
    t += "%s    int[] faceVertexCounts = [%s]\n" % (pad, ", ".join(str(c) for c in counts))
    t += "%s    int[] faceVertexIndices = [%s]\n" % (pad, ", ".join(str(i) for i in idx))
    t += "%s    point3f[] points = [%s]\n" % (pad, ", ".join(_v(p) for p in pts))
    t += '%s    uniform token physics:approximation = "%s"\n' % (pad, approximation)
    t += extra
    t += "%s}\n" % pad
    return t


def _body(name, loc, mass, size, indent=4, density=None, approximation="convexHull"):
    pad = " " * indent
    t = '%sdef Xform "%s" (\n%s    prepend apiSchemas = ["PhysicsRigidBodyAPI", "PhysicsMassAPI"]\n%s)\n%s{\n' % (
        pad, name, pad, pad, pad)
    if mass is not None:
        t += "%s    float physics:mass = %s\n" % (pad, _f(mass))
    if density is not None:
        t += "%s    float physics:density = %s\n" % (pad, _f(density))
    t += "%s    double3 xformOp:translate = %s\n" % (pad, _v(loc))
    t += '%s    uniform token[] xformOpOrder = ["xformOp:translate"]\n' % pad
    t += _phys_mesh(name + "Mesh", size, indent + 4, ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"],
                    approximation)
    return t + "%s}\n" % pad


ROBOT = {"Base": ((100.0, 10.0, 0.0), 10.0, (20.0, 20.0, 20.0)),
         "Link1": ((100.0, 35.0, 0.0), 2.0, (8.0, 30.0, 8.0)),
         "Link2": ((100.0, 65.0, 0.0), 1.0, (6.0, 30.0, 6.0)),
         "Gripper": ((100.0, 85.0, 0.0), 0.5, (10.0, 10.0, 10.0))}


def _joint(kind, name, b0, b1, p0, p1, extra=""):
    t = '        def %s "%s"\n        {\n' % (kind, name)
    if b0:
        t += "            rel physics:body0 = <%s>\n" % b0
    if b1:
        t += "            rel physics:body1 = <%s>\n" % b1
    t += "            point3f physics:localPos0 = %s\n" % _v(p0)
    t += "            point3f physics:localPos1 = %s\n" % _v(p1)
    t += "            quatf physics:localRot0 = (1, 0, 0, 0)\n            quatf physics:localRot1 = (1, 0, 0, 0)\n"
    return t + extra + "        }\n"


def physics_other(folder):
    os.makedirs(folder, exist_ok=True)
    R = "/World/Robot/"
    t = '#usda 1.0\n(\n    defaultPrim = "World"\n    metersPerUnit = 0.01\n    kilogramsPerUnit = 1\n' \
        '    upAxis = "Y"\n)\n\n'
    t += 'def Xform "World"\n{\n'
    t += '    def PhysicsScene "physicsScene"\n    {\n        vector3f physics:gravityDirection = (0, -1, 0)\n' \
         '        float physics:gravityMagnitude = 981\n    }\n'
    t += '    def Material "Rubber" (\n        prepend apiSchemas = ["PhysicsMaterialAPI"]\n    )\n    {\n' \
         '        float physics:staticFriction = 0.9\n        float physics:dynamicFriction = 0.8\n' \
         '        float physics:restitution = 0.3\n    }\n'
    t += '    def Xform "Floor"\n    {\n        double3 xformOp:translate = (0, -5, 0)\n' \
         '        uniform token[] xformOpOrder = ["xformOp:translate"]\n'
    t += _phys_mesh("FloorMesh", (400.0, 10.0, 400.0), 8,
                    ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI", "MaterialBindingAPI"], "none",
                    "            rel material:binding:physics = </World/Rubber>\n")
    t += "    }\n"
    t += _body("Crate", (0.0, 30.0, 0.0), None, (40.0, 40.0, 40.0), density=0.0005,
               approximation="convexDecomposition")
    t += _body("Lamp", (0.0, 60.0, 0.0), 1.0, (10.0, 10.0, 10.0))
    t += '    def Xform "Robot" (\n        prepend apiSchemas = ["PhysicsArticulationRootAPI"]\n    )\n    {\n'
    for name, (loc, mass, size) in sorted(ROBOT.items()):
        t += _body(name, loc, mass, size, indent=8)
    t += _joint("PhysicsFixedJoint", "BaseFixed", None, R + "Base", ROBOT["Base"][0], (0, 0, 0))
    t += _joint("PhysicsRevoluteJoint", "Shoulder", R + "Base", R + "Link1", (0, 10, 0), (0, -15, 0),
                '            uniform token physics:axis = "Y"\n            float physics:lowerLimit = -90\n'
                '            float physics:upperLimit = 90\n')
    t += _joint("PhysicsRevoluteJoint", "Elbow", R + "Link1", R + "Link2", (0, 15, 0), (0, -15, 0),
                '            uniform token physics:axis = "Z"\n            float physics:lowerLimit = -45\n'
                '            float physics:upperLimit = 120\n')
    t += _joint("PhysicsPrismaticJoint", "Slide", R + "Link2", R + "Gripper", (0, 15, 0), (0, -5, 0),
                '            uniform token physics:axis = "X"\n            float physics:lowerLimit = 0\n'
                '            float physics:upperLimit = 10\n')
    t += "    }\n"
    t += _joint("PhysicsFixedJoint", "LampWeld", "/World/Crate", "/World/Lamp", (0, 20, 0), (0, -10, 0)) \
        .replace("        ", "    ", 1)
    t += _joint("PhysicsDistanceJoint", "Rope", "/World/Crate", R + "Gripper", (0, 0, 0), (0, 0, 0),
                "            float physics:minDistance = 0\n            float physics:maxDistance = 50\n") \
        .replace("        ", "    ", 1)
    t += '    def PhysicsCollisionGroup "Debris" (\n        prepend apiSchemas = ["CollectionAPI:colliders"]\n' \
         '    )\n    {\n        rel collection:colliders:includes = </World/Crate>\n    }\n'
    t += "}\n"
    path = os.path.join(folder, "physics_other.usda")
    with open(path, "w") as f:
        f.write(t)
    return path


PHYSICS_OTHER = {
    "bodies": ["/World/Crate", "/World/Lamp"] + ["/World/Robot/" + n for n in ROBOT],
    "joints": {"BaseFixed": "fixed", "Shoulder": "revolute", "Elbow": "revolute", "Slide": "prismatic",
               "LampWeld": "fixed", "Rope": "distance"},
    "shapes": [("FloorMesh", "mesh", "none"), ("CrateMesh", "mesh", "convexDecomposition"),
               ("LampMesh", "mesh", "convexHull")] + [(n + "Mesh", "mesh", "convexHull") for n in ROBOT],
    "crate_density": 0.0005,
    # what the import must make of it (metres, Z up; kg)
    "objects": {"Floor": ('STATIC', 'TRIANGLE_MESH', None), "Crate": ('RIGID_BODY', 'CONVEX_HULL', 32.0),
                "Lamp": ('RIGID_BODY', 'CONVEX_HULL', 1.0), "Base": ('RIGID_BODY', 'CONVEX_HULL', 10.0),
                "Link1": ('RIGID_BODY', 'CONVEX_HULL', 2.0), "Link2": ('RIGID_BODY', 'CONVEX_HULL', 1.0),
                "Gripper": ('RIGID_BODY', 'CONVEX_HULL', 0.5)},
    # joint: owner, target, kind, axis in the world, pivot in the world, limits (radians or metres)
    "constraints": {
        "Shoulder": ("Base", "Link1", 'HINGE', (0.0, 0.0, 1.0), to_blender((100.0, 20.0, 0.0), 0.01, False),
                     ("x", -90.0, 90.0)),
        "Elbow": ("Link1", "Link2", 'HINGE', (0.0, -1.0, 0.0), to_blender((100.0, 50.0, 0.0), 0.01, False),
                  ("x", -45.0, 120.0)),
        "Slide": ("Link2", "Gripper", 'GENERIC_6_DOF', (1.0, 0.0, 0.0),
                  to_blender((100.0, 80.0, 0.0), 0.01, False), ("lx", 0.0, 0.1)),
        "LampWeld": ("Crate", "Lamp", 'GENERIC_6_DOF', None, to_blender((0.0, 50.0, 0.0), 0.01, False), None)},
    "report": ("Rope", "distance joint", "Debris", "convexDecomposition"),
    "gravity": 9.81,
}


# ---------------------------------------------------------------------------
# round 8: another tool's character (Maya's way)

def m_inverse(m):
    """the inverse of a 4 x 4 (USD rows)"""
    a = [list(m[r * 4:r * 4 + 4]) + [1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    for c in range(4):
        p = max(range(c, 4), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        d = a[c][c]
        a[c] = [x / d for x in a[c]]
        for r in range(4):
            if r != c:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[r][4 + c] for r in range(4) for c in range(4)]


def m_rotate(axis, deg):
    """row vectors: p' = p M, a turn of deg about the X, Y or Z axis"""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == "X":
        return [1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]
    if axis == "Y":
        return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]
    return [c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def m_point(m, p):
    return tuple(sum(p[k] * m[k * 4 + c] for k in range(3)) + m[12 + c] for c in range(3))


def quat_of(m):
    """the turn of a rows matrix as a quaternion (w, x, y, z)"""
    # the column form R = M^T
    R = [[m[c * 4 + r] for c in range(3)] for r in range(3)]
    tr = R[0][0] + R[1][1] + R[2][2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = (0.25 * s, (R[2][1] - R[1][2]) / s, (R[0][2] - R[2][0]) / s, (R[1][0] - R[0][1]) / s)
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        s = math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2]) * 2.0
        q = ((R[2][1] - R[1][2]) / s, 0.25 * s, (R[0][1] + R[1][0]) / s, (R[0][2] + R[2][0]) / s)
    elif R[1][1] > R[2][2]:
        s = math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2]) * 2.0
        q = ((R[0][2] - R[2][0]) / s, (R[0][1] + R[1][0]) / s, 0.25 * s, (R[1][2] + R[2][1]) / s)
    else:
        s = math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1]) * 2.0
        q = ((R[1][0] - R[0][1]) / s, (R[0][2] + R[2][0]) / s, (R[1][2] + R[2][1]) / s, 0.25 * s)
    return q if q[0] >= 0.0 else tuple(-x for x in q)


# joint: parent, its place in the skeleton (cm), its X's turn about Z
# (degrees: 90 up, -90 down, 0 along +X)
CHARACTER_JOINTS = [
    ("root", None, (0.0, 100.0, 0.0), 90.0),
    ("root/spine", "root", (0.0, 130.0, 0.0), 90.0),
    ("root/spine/chest", "root/spine", (0.0, 160.0, 0.0), 90.0),
    ("root/spine/chest/arm_l", "root/spine/chest", (20.0, 150.0, 0.0), 0.0),
    ("root/spine/chest/arm_l/hand_l", "root/spine/chest/arm_l", (50.0, 150.0, 0.0), 0.0),
    ("root/leg_l", "root", (10.0, 95.0, 0.0), -90.0),
    ("root/leg_l/foot_l", "root/leg_l", (10.0, 10.0, 0.0), -90.0),
]
# the animated joints (an order of their own): the axis each turns about
# (its own), the most it turns
CHARACTER_ANIMATED = [("root/leg_l", "Z", 25.0), ("root", None, 0.0), ("root/spine/chest/arm_l", "Y", 40.0),
                      ("root/spine", "Z", 15.0)]
CHARACTER_ROOT = m_translate(50.0, 0.0, -20.0)
CHARACTER_SEGMENTS = [("root", "root/spine"), ("root/spine", "root/spine/chest"),
                      ("root/spine/chest/arm_l", "root/spine/chest/arm_l/hand_l"), ("root", "root/leg_l"),
                      ("root/leg_l", "root/leg_l/foot_l"), ("root/spine/chest", "root/spine/chest/arm_l")]
GEOM_BIND = m_translate(0.0, 2.0, 0.0)


def character_binds():
    """each joint's bind transform (in the skeleton's space) and rest one
    (relative to its parent)"""
    names = [j[0] for j in CHARACTER_JOINTS]
    bind = {}
    for name, _parent, pos, turn in CHARACTER_JOINTS:
        bind[name] = m_mul(m_rotate("Z", turn), m_translate(*pos))
    rest = {}
    for name, parent, _pos, _turn in CHARACTER_JOINTS:
        rest[name] = bind[name] if parent is None else m_mul(bind[name], m_inverse(bind[parent]))
    return names, bind, rest


def character_frame(f):
    """the animated joints at frame f: [(translation, rotation w x y z,
    scale)], the blend shape's weight"""
    _names, _bind, rest = character_binds()
    phase = math.sin(2.0 * math.pi * (f - 1) / 29.0)
    out = []
    for name, axis, most in CHARACTER_ANIMATED:
        L = rest[name]
        if axis is not None:
            L = m_mul(m_rotate(axis, most * phase), L)
        t = (L[12], L[13], L[14])
        if name == "root":
            t = (t[0], t[1] + 3.0 * phase, t[2])
        out.append((t, quat_of(L), (1.0, 1.0, 1.0)))
    return out, 0.5 + 0.5 * phase


def character_mesh():
    """six boxes along the limbs (points in the mesh's own space: the
    geometry bind transform puts them in the skeleton's), every vertex on 4
    joints"""
    names, bind, _rest = character_binds()
    index = {n: i for i, n in enumerate(names)}
    pts, counts, idx, joints, weights = [], [], [], [], []
    to_mesh = m_inverse(GEOM_BIND)
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for a, b in CHARACTER_SEGMENTS:
        pa, pb = m_point(bind[a], (0, 0, 0)), m_point(bind[b], (0, 0, 0))
        d = [y - x for x, y in zip(pa, pb)]
        n = math.sqrt(sum(x * x for x in d))
        d = [x / n for x in d]
        side = (0.0, 0.0, 1.0)
        up = (d[1] * side[2] - d[2] * side[1], d[2] * side[0] - d[0] * side[2], d[0] * side[1] - d[1] * side[0])
        others = [index[j] for j in ("root", "root/spine/chest", "root/spine", "root/leg_l")
                  if j not in (a, b)][:2]
        first = len(pts)
        for t in (0.1, 0.9):
            centre = [x + (y - x) * t for x, y in zip(pa, pb)]
            for u in (-3.0, 3.0):
                for v in (-3.0, 3.0):
                    p = tuple(c + u * s + v * w for c, s, w in zip(centre, side, up))
                    pts.append(m_point(to_mesh, p))
                    near, far = (index[a], index[b]) if t < 0.5 else (index[b], index[a])
                    joints += [near, far] + others
                    weights += [0.6, 0.25, 0.1, 0.05] if t < 0.5 else [0.55, 0.3, 0.1, 0.05]
        for q in quads:
            counts.append(4)
            idx += [first + i for i in q]
    return pts, counts, idx, joints, weights


def _rows(m):
    return "( " + ", ".join(_v(m[r * 4:r * 4 + 4]) for r in range(4)) + " )"


def character_other(folder):
    os.makedirs(folder, exist_ok=True)
    names, bind, rest = character_binds()
    pts, counts, idx, joints, weights = character_mesh()
    t = '#usda 1.0\n(\n    defaultPrim = "World"\n    endTimeCode = 30\n    framesPerSecond = 30\n' \
        '    metersPerUnit = 0.01\n    startTimeCode = 1\n    timeCodesPerSecond = 30\n    upAxis = "Y"\n)\n\n'
    t += 'def Xform "World"\n{\n'
    t += '    def SkelRoot "Character"\n    {\n'
    t += "        matrix4d xformOp:transform = %s\n" % _rows(CHARACTER_ROOT)
    t += '        uniform token[] xformOpOrder = ["xformOp:transform"]\n'
    t += '        def Skeleton "Skel" (\n            prepend apiSchemas = ["SkelBindingAPI"]\n        )\n        {\n'
    t += "            uniform token[] joints = [%s]\n" % ", ".join('"%s"' % n for n in names)
    t += "            uniform matrix4d[] bindTransforms = [%s]\n" % ", ".join(_rows(bind[n]) for n in names)
    t += "            uniform matrix4d[] restTransforms = [%s]\n" % ", ".join(_rows(rest[n]) for n in names)
    t += "            rel skel:animationSource = </World/Character/Skel/Anim>\n"
    t += '            def SkelAnimation "Anim"\n            {\n'
    t += "                uniform token[] joints = [%s]\n" % ", ".join('"%s"' % a[0] for a in CHARACTER_ANIMATED)
    t += '                uniform token[] blendShapes = ["Smile"]\n'
    frames = range(1, 31)
    samples = {f: character_frame(f) for f in frames}
    for attr, kind, k in (("translations", "float3[]", 0), ("rotations", "quatf[]", 1), ("scales", "half3[]", 2)):
        t += "                %s %s.timeSamples = {\n" % (kind, attr)
        for f in frames:
            t += "                    %d: [%s],\n" % (f, ", ".join(_v(j[k]) for j in samples[f][0]))
        t += "                }\n"
    t += "                float[] blendShapeWeights.timeSamples = {\n"
    for f in frames:
        t += "                    %d: [%s],\n" % (f, _f(samples[f][1]))
    t += "                }\n            }\n        }\n"
    t += '        def Mesh "Body" (\n            prepend apiSchemas = ["SkelBindingAPI"]\n        )\n        {\n'
    t += '            uniform token subdivisionScheme = "none"\n'
    t += "            int[] faceVertexCounts = [%s]\n" % ", ".join(str(c) for c in counts)
    t += "            int[] faceVertexIndices = [%s]\n" % ", ".join(str(i) for i in idx)
    t += "            point3f[] points = [%s]\n" % ", ".join(_v(p) for p in pts)
    t += "            matrix4d primvars:skel:geomBindTransform = %s\n" % _rows(GEOM_BIND)
    t += "            int[] primvars:skel:jointIndices = [%s] (\n                elementSize = 4\n" \
         '                interpolation = "vertex"\n            )\n' % ", ".join(str(j) for j in joints)
    t += "            float[] primvars:skel:jointWeights = [%s] (\n                elementSize = 4\n" \
         '                interpolation = "vertex"\n            )\n' % ", ".join(_f(w) for w in weights)
    t += "            rel skel:skeleton = </World/Character/Skel>\n"
    t += '            uniform token[] skel:blendShapes = ["Smile"]\n'
    t += "            rel skel:blendShapeTargets = [</World/Character/Body/Smile>]\n"
    t += '            def BlendShape "Smile"\n            {\n'
    t += "                uniform vector3f[] offsets = [(0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 1, 0)]\n"
    t += "                uniform int[] pointIndices = [8, 9, 10, 11]\n            }\n"
    t += "        }\n    }\n}\n"
    path = os.path.join(folder, "character_other.usda")
    with open(path, "w") as f:
        f.write(t)
    return path


def character_expect():
    """what the import must make of character_other (metres, Z up): each
    bone's head and, for a bone with a child in its chain, its tail (that
    child's head)"""
    names, bind, _rest = character_binds()
    children = {}
    for name, parent, _p, _t in CHARACTER_JOINTS:
        children.setdefault(parent, []).append(name)

    def count(n):
        return sum(1 + count(c) for c in children.get(n, ()))

    heads, tails = {}, {}
    for n in names:
        p = m_point(m_mul(bind[n], CHARACTER_ROOT), (0, 0, 0))
        heads[n.rsplit("/", 1)[-1]] = to_blender(p, 0.01, False)
    for n in names:
        kids = children.get(n, ())
        if kids:
            c = max(kids, key=lambda k: (count(k), -names.index(k)))
            tails[n.rsplit("/", 1)[-1]] = heads[c.rsplit("/", 1)[-1]]
    return {"heads": heads, "tails": tails, "bones": len(names), "fps": 30, "frames": (1, 30),
            "vertices": len(character_mesh()[0]), "report": ("Smile", "blend shape")}
