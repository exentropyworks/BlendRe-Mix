"""BGE-Remix P12 round 2: the test captures, written in RTX Remix's layout.

No game is used: this script writes, as text USD files, what Remix 1.6's
capture exporter (dxvk-remix src/lssusd/game_exporter.cpp) would write for
the room of the P12 tests:

  <folder>/capture_<name>.usda          the stage: /RootNode (default prim),
                                        lightspeed_layer_type "capture"
  <folder>/meshes//mesh_<H>.usda        one file a mesh (Remix writes the
                                        double slash too): /mesh_<H> an Xform,
                                        its child "mesh" the triangles, normals
                                        and st per vertex; bound to its
                                        material through /Looks
  <folder>/materials/mat_<H>.usda       /Looks/mat_<H> and its Shader, an
                                        AperturePBR MDL
  <folder>/materials/AperturePBR_*.mdl  (placeholders: Remix writes its own)
  <folder>/lights//light_<H>.usda       a sphere light a file
  <folder>/textures/<H>.dds             a material's albedo, named by its hash

In the stage, /RootNode/meshes/mesh_<H> references its file (invisible: a
prototype), /RootNode/Looks/mat_<H> its material file, each
/RootNode/instances/inst_<H>_<n> references its mesh internally with its
transform (xformOp:transform) and material, /RootNode/lights/light_<H> its
file, /RootNode/cameras/Camera the camera.

Parts of the same shape share one mesh (Remix hashes the shape, not the
place): the walls, the floor, the ceiling, the box (drawn twice), the Brick
wall and the glass pane are all one unit cube.

Plain Python (3.5 and later), no Blender: Blender's own Python (the test
scenes), GitHub's (the OpenUSD check) and any other run it.

  python capture_writer.py <folder> [room | room_cm_yup | broken]
writes that capture and <folder>/expected.json: every object, mesh,
material, lamp and the camera as the importer must bring them in (metres,
Z up, Blender's matrices).
"""

import json
import math
import os
import struct
import sys

# ---------------------------------------------------------------------------
# the room (metres, Z up): what make_scenes_p12 builds in Blender, and what
# the capture holds

CUBE = "1A2B3C4D5E6F7001"
SPHERE = "1A2B3C4D5E6F7002"
MAT = {"Room": "2B3C4D5E6F700101", "Box": "2B3C4D5E6F700102", "Sphere": "2B3C4D5E6F700103",
       "Brick": "2B3C4D5E6F700104", "Glass": "2B3C4D5E6F700105"}
LIGHT_A = "3C4D5E6F70010201"
LIGHT_B = "3C4D5E6F70010202"

# name, mesh, size (x, y, z), location, rotation about Z (degrees), material
PARTS = [
    ("Floor", CUBE, (4.0, 6.0, 0.2), (0.0, 0.0, -0.1), 0.0, "Room"),
    ("Ceiling", CUBE, (4.0, 6.0, 0.2), (0.0, 0.0, 3.1), 0.0, "Room"),
    ("WallN", CUBE, (4.0, 0.2, 3.0), (0.0, 3.1, 1.5), 0.0, "Room"),
    ("WallS", CUBE, (4.0, 0.2, 3.0), (0.0, -3.1, 1.5), 0.0, "Room"),
    ("WallE", CUBE, (0.2, 6.0, 3.0), (2.1, 0.0, 1.5), 0.0, "Room"),
    ("WallW", CUBE, (0.2, 6.0, 3.0), (-2.1, 0.0, 1.5), 0.0, "Room"),
    ("Box", CUBE, (0.6, 0.6, 0.6), (-0.9, 1.0, 0.3), 0.0, "Box"),
    ("Box2", CUBE, (0.6, 0.6, 0.6), (-1.2, -0.6, 0.3), 30.0, "Box"),
    ("Sphere", SPHERE, (0.7, 0.7, 0.7), (0.8, 1.2, 0.35), 0.0, "Sphere"),
    ("BrickWall", CUBE, (2.0, 0.25, 1.2), (0.0, 2.4, 0.6), 0.0, "Brick"),
    ("GlassPane", CUBE, (1.2, 0.02, 1.0), (0.0, 0.2, 0.9), 0.0, "Glass"),
]

# the materials' AperturePBR inputs (as the Remix Toolkit would leave them:
# Remix's own capture writes the albedo texture and opacity; the constants
# are what an edited capture holds)
MATERIALS = {
    "Room": {"mdl": "AperturePBR_Opacity", "inputs": {
        "diffuse_color_constant": ("color3f", (0.6, 0.6, 0.58)),
        "reflection_roughness_constant": ("float", 0.8),
        "metallic_constant": ("float", 0.0)}},
    "Box": {"mdl": "AperturePBR_Opacity", "texture": "rgba", "inputs": {
        "reflection_roughness_constant": ("float", 0.55),
        "metallic_constant": ("float", 0.0)}},
    "Sphere": {"mdl": "AperturePBR_Opacity", "inputs": {
        "diffuse_color_constant": ("color3f", (0.3, 0.5, 0.8)),
        "reflection_roughness_constant": ("float", 0.2),
        "metallic_constant": ("float", 1.0),
        "emissive_color_constant": ("color3f", (0.2, 0.4, 1.0)),
        "emissive_intensity": ("float", 0.5),
        "enable_emission": ("bool", True)}},
    "Brick": {"mdl": "AperturePBR_Opacity", "texture": "bc1", "inputs": {
        "reflection_roughness_constant": ("float", 0.9)}},
    "Glass": {"mdl": "AperturePBR_Translucent", "inputs": {
        "ior_constant": ("float", 1.5),
        "transmittance_color": ("color3f", (0.9, 0.95, 1.0)),
        "transmittance_measurement_distance": ("float", 0.5),
        "thin_walled": ("bool", False)}},
}
# Remix's own sampler attributes (game_exporter.cpp writes them unprefixed)
SAMPLER = {"filter_mode": 1, "wrap_mode_u": 0, "wrap_mode_v": 0}

# lamps: name, hash, location, radius, colour, intensity, cone (degrees
# from the axis, None: all round), softness, aimed at
LAMPS = [
    ("LampA", LIGHT_A, (-1.2, -1.0, 2.6), 0.1, (1.0, 1.0, 1.0), 300.0, None, 0.0, None),
    ("LampB", LIGHT_B, (1.2, 1.5, 2.6), 0.1, (1.0, 0.85, 0.7), 500.0, 40.0, 0.1, (1.2, 1.5, 0.0)),
]
CAMERA = {"location": (1.6, -2.7, 1.7), "target": (-0.1, 1.2, 0.7), "focal_length": 22.0,
          "horizontal_aperture": 32.0, "vertical_aperture": 18.0, "near": 0.1, "far": 100.0}

TEXTURE_SIZE = 64


# ---------------------------------------------------------------------------
# small maths (row-major 4x4 lists, column vectors: Blender's convention)

def mat_identity():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def mat_trs(loc, rot_z_deg, size):
    c, s = math.cos(math.radians(rot_z_deg)), math.sin(math.radians(rot_z_deg))
    return [[c * size[0], -s * size[1], 0.0, loc[0]],
            [s * size[0], c * size[1], 0.0, loc[1]],
            [0.0, 0.0, size[2], loc[2]],
            [0.0, 0.0, 0.0, 1.0]]


def mat_inv_affine(m):
    """the inverse of an affine 4x4 (3x3 by cofactors)"""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0]) +
           a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    inv = [[0.0] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            r = [x for x in range(3) if x != j]
            c = [x for x in range(3) if x != i]
            minor = a[r[0]][c[0]] * a[r[1]][c[1]] - a[r[0]][c[1]] * a[r[1]][c[0]]
            inv[i][j] = ((-1) ** (i + j)) * minor / det
    t = [m[0][3], m[1][3], m[2][3]]
    out = [inv[i] + [-sum(inv[i][k] * t[k] for k in range(3))] for i in range(3)]
    return out + [[0.0, 0.0, 0.0, 1.0]]


def look_at(loc, target, forward_neg_z=True):
    """an object at loc whose -Z points at target, its Y up as far as it goes"""
    f = [target[i] - loc[i] for i in range(3)]
    n = math.sqrt(sum(x * x for x in f))
    f = [x / n for x in f]
    z = [-x for x in f]                       # its +Z points away
    up = [0.0, 0.0, 1.0]
    if abs(sum(up[i] * z[i] for i in range(3))) > 0.999:
        up = [0.0, 1.0, 0.0]
    x = [up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0]]
    n = math.sqrt(sum(v * v for v in x))
    x = [v / n for v in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    return [[x[0], y[0], z[0], loc[0]], [x[1], y[1], z[1], loc[1]], [x[2], y[2], z[2], loc[2]], [0, 0, 0, 1.0]]


def apply(m, p):
    return [sum(m[i][k] * p[k] for k in range(3)) + m[i][3] for i in range(3)]


def apply_dir(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


# ---------------------------------------------------------------------------
# the shapes, as a D3D game draws them: triangles, every vertex with its own
# normal and UV (the cube's faces each with the whole texture)

def cube_mesh():
    faces = [((0, 0, -1), [(-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1)]),
             ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
             ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
             ((0, 1, 0), [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)]),
             ((-1, 0, 0), [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)]),
             ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)])]
    uv = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    points, normals, uvs, tris = [], [], [], []
    for n, quad in faces:
        base = len(points)
        for k, c in enumerate(quad):
            points.append(tuple(0.5 * x for x in c))
            normals.append(n)
            uvs.append(uv[k])
        tris += [base, base + 1, base + 2, base, base + 2, base + 3]
    return {"points": points, "normals": normals, "uvs": uvs, "indices": tris}


def sphere_mesh(segments=16, rings=8):
    """a unit-diameter UV sphere"""
    points, normals, uvs, tris = [], [], [], []
    for r in range(rings + 1):
        v = r / float(rings)
        theta = math.pi * v
        for s in range(segments + 1):
            u = s / float(segments)
            phi = 2.0 * math.pi * u
            n = (math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), -math.cos(theta))
            points.append(tuple(0.5 * x for x in n))
            normals.append(n)
            uvs.append((u, v))
    row = segments + 1
    for r in range(rings):
        for s in range(segments):
            a, b = r * row + s, r * row + s + 1
            c, d = (r + 1) * row + s + 1, (r + 1) * row + s
            if r > 0:
                tris += [a, b, c]
            if r < rings - 1:
                tris += [a, c, d]
    return {"points": points, "normals": normals, "uvs": uvs, "indices": tris}


# ---------------------------------------------------------------------------
# the textures (rows from the top, as DDS files are)

def texture_rgba():
    """the Box's: a 64 x 64 pattern of 8-pixel squares, each its own colour"""
    px = []
    for y in range(TEXTURE_SIZE):
        for x in range(TEXTURE_SIZE):
            cx, cy = x // 8, y // 8
            px.append((40 + cx * 25, 200 - cy * 20, 120 + ((cx + cy) % 2) * 100, 255))
    return px


def brick_colour(bx, by):
    """the Brick wall's 4 x 4 blocks: brick red, a mortar line every 4th row
    and, shifted every other course, every 8th column"""
    if by % 4 == 3:
        return (180, 175, 165)
    shift = 4 if (by // 4) % 2 else 0
    if (bx + shift) % 8 == 7:
        return (180, 175, 165)
    return (150 + (bx * 7) % 40, 50 + (by * 5) % 20, 35)


def to565(c):
    r, g, b = c[0] * 31 // 255, c[1] * 63 // 255, c[2] * 31 // 255
    return (r << 11) | (g << 5) | b


def from565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


def dds_header(width, height, fourcc=None):
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | (0x80000 if fourcc else 0x8)
    pitch = (max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8) if fourcc else width * 4
    if fourcc:
        pf = struct.pack("<II4sIIIII", 32, 0x4, fourcc, 0, 0, 0, 0, 0)
    else:
        pf = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32, 0x000000ff, 0x0000ff00, 0x00ff0000, 0xff000000)
    head = struct.pack("<IIIIIII", 124, flags, height, width, pitch, 0, 1) + b"\0" * 44 + pf
    head += struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    return b"DDS " + head


def write_dds_rgba(path, px):
    with open(path, "wb") as f:
        f.write(dds_header(TEXTURE_SIZE, TEXTURE_SIZE))
        f.write(b"".join(struct.pack("<BBBB", *p) for p in px))


def write_dds_bc1(path):
    """BC1 (DXT1): each 4 x 4 block one colour, as decoded exactly"""
    n = TEXTURE_SIZE // 4
    blocks = []
    for by in range(n):
        for bx in range(n):
            c = to565(brick_colour(bx, by))
            # colour0 > colour1 (four-colour blocks), every pixel colour0
            c0, c1 = (c, c - 1) if c > 0 else (1, 0)
            blocks.append(struct.pack("<HHI", c0, c1, 0) if c > 0 else struct.pack("<HHI", 0, 0, 0))
    with open(path, "wb") as f:
        f.write(dds_header(TEXTURE_SIZE, TEXTURE_SIZE, b"DXT1"))
        f.write(b"".join(blocks))


def bc1_pixels():
    """what the BC1 texture decodes to (rows from the top)"""
    px = []
    for y in range(TEXTURE_SIZE):
        for x in range(TEXTURE_SIZE):
            px.append(from565(to565(brick_colour(x // 4, y // 4))) + (255,))
    return px


# ---------------------------------------------------------------------------
# writing USD text

def fmt(v):
    return "%.9g" % v


def tup(t):
    return "(" + ", ".join(fmt(x) for x in t) + ")"


def matrix_usda(m):
    """a Blender matrix (column vectors) as USD's matrix4d (row vectors: the
    translation in the last row)"""
    rows = [[m[j][i] for j in range(4)] for i in range(4)]
    return "( " + ", ".join(tup(r) for r in rows) + " )"


def layer_head(meters_per_unit, z_up, extra=""):
    return ('#usda 1.0\n(\n%s    metersPerUnit = %s\n    timeCodesPerSecond = 60\n    upAxis = "%s"\n)\n\n' %
            (extra, fmt(meters_per_unit), "Z" if z_up else "Y"))


class Space:
    """the capture's own space: units (metres per unit) and up axis. K maps
    Blender's metres, Z up, into it (points: K p; matrices: K M K^-1)"""

    def __init__(self, meters_per_unit, z_up):
        self.mpu = meters_per_unit
        self.z_up = z_up
        s = 1.0 / meters_per_unit
        if z_up:
            self.K = [[s, 0, 0, 0], [0, s, 0, 0], [0, 0, s, 0], [0, 0, 0, 1.0]]
        else:
            # Z up to Y up: (x, y, z) -> (x, z, -y)
            self.K = [[s, 0, 0, 0], [0, 0, s, 0], [0, -s, 0, 0], [0, 0, 0, 1.0]]
        self.Kinv = mat_inv_affine(self.K)

    def point(self, p):
        return apply(self.K, p)

    def direction(self, v):
        d = apply_dir(self.K, v)
        n = math.sqrt(sum(x * x for x in d))
        return [x / n for x in d]

    def matrix(self, m):
        return mat_mul(mat_mul(self.K, m), self.Kinv)


def write_mesh(folder, h, mesh, mat_hash, sp):
    pts = [sp.point(p) for p in mesh["points"]]
    nrm = [sp.direction(n) for n in mesh["normals"]]
    tris = mesh["indices"]
    # (Remix flips v: 1 - v of the game's; ours are Blender's already)
    text = layer_head(sp.mpu, sp.z_up, '    defaultPrim = "mesh_%s"\n' % h)
    text += 'def Xform "mesh_%s" (\n    prepend apiSchemas = ["MaterialBindingAPI"]\n)\n{\n' % h
    text += '    rel material:binding = </Looks/mat_%s>\n' % mat_hash
    text += '    token visibility = "inherited"\n\n'
    text += '    def Mesh "mesh"\n    {\n'
    text += '        uniform bool doubleSided = 0\n'
    text += '        int[] faceVertexCounts = [%s]\n' % ", ".join("3" for _ in range(len(tris) // 3))
    text += '        int[] faceVertexIndices = [%s]\n' % ", ".join(str(i) for i in tris)
    text += '        normal3f[] normals = [%s]\n' % ", ".join(tup(n) for n in nrm)
    text += '        uniform token orientation = "rightHanded"\n'
    text += '        point3f[] points = [%s]\n' % ", ".join(tup(p) for p in pts)
    text += '        texCoord2f[] primvars:st = [%s] (\n            interpolation = "vertex"\n        )\n' % \
        ", ".join(tup(u) for u in mesh["uvs"])
    text += '        uniform token subdivisionScheme = "none"\n'
    text += '        token visibility = "inherited"\n'
    text += '        matrix4d xformOp:transform = ( (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1) )\n'
    text += '        uniform token[] xformOpOrder = ["xformOp:transform"]\n'
    text += '    }\n}\n\n'
    text += 'def Scope "Looks"\n{\n    def Material "mat_%s" (\n' % mat_hash
    text += '        prepend references = @../materials/mat_%s.usda@</Looks/mat_%s>\n    )\n    {\n    }\n}\n' % \
        (mat_hash, mat_hash)
    os.makedirs(os.path.join(folder, "meshes"), exist_ok=True)
    with open(os.path.join(folder, "meshes", "mesh_%s.usda" % h), "w") as f:
        f.write(text)


def usd_value(kind, v):
    if kind == "bool":
        return "1" if v else "0"
    if kind in ("color3f", "float3"):
        return tup(v)
    return fmt(v)


def write_material(folder, key, sp):
    h = MAT[key]
    m = MATERIALS[key]
    mdl = m["mdl"]
    text = layer_head(sp.mpu, sp.z_up, '    defaultPrim = "Looks"\n')
    text += 'def Scope "Looks"\n{\n    def Material "mat_%s"\n    {\n' % h
    text += '        token outputs:mdl:surface.connect = </Looks/mat_%s/Shader.outputs:out>\n\n' % h
    text += '        def Shader "Shader" (\n            kind = "Material"\n        )\n        {\n'
    text += '            uniform token info:implementationSource = "sourceAsset"\n'
    text += '            uniform asset info:mdl:sourceAsset = @./%s.mdl@\n' % mdl
    text += '            uniform token info:mdl:sourceAsset:subIdentifier = "%s"\n' % mdl
    if m.get("texture"):
        text += '            asset inputs:diffuse_texture = @../textures/%s.dds@ (\n' % h
        text += '                colorSpace = "auto"\n            )\n'
    for name, (kind, v) in sorted(m["inputs"].items()):
        text += '            %s inputs:%s = %s\n' % (kind, name, usd_value(kind, v))
    text += '            uniform bool enable_opacity = 0\n'
    for name, v in sorted(SAMPLER.items()):
        text += '            uniform uint %s = %d\n' % (name, v)
    text += '            token outputs:out\n        }\n    }\n}\n'
    os.makedirs(os.path.join(folder, "materials"), exist_ok=True)
    with open(os.path.join(folder, "materials", "mat_%s.usda" % h), "w") as f:
        f.write(text)
    os.makedirs(os.path.join(folder, "textures"), exist_ok=True)
    if m.get("texture") == "rgba":
        write_dds_rgba(os.path.join(folder, "textures", h + ".dds"), texture_rgba())
    elif m.get("texture") == "bc1":
        write_dds_bc1(os.path.join(folder, "textures", h + ".dds"))


def lamp_matrix(lamp):
    name, h, loc, radius, colour, intensity, cone, soft, aim = lamp
    if aim is None:
        return mat_trs(loc, 0.0, (1.0, 1.0, 1.0))
    return look_at(loc, aim)


def write_light(folder, lamp, sp):
    name, h, loc, radius, colour, intensity, cone, soft, aim = lamp
    text = layer_head(sp.mpu, sp.z_up, '    defaultPrim = "light_%s"\n' % h)
    shaping = ' (\n    prepend apiSchemas = ["ShapingAPI"]\n)' if cone is not None else ""
    text += 'def SphereLight "light_%s"%s\n{\n' % (h, shaping)
    text += '    color3f inputs:color = %s\n' % tup(colour)
    text += '    float inputs:intensity = %s\n' % fmt(intensity)
    text += '    float inputs:radius = %s\n' % fmt(radius / sp.mpu)
    if cone is not None:
        text += '    float inputs:shaping:cone:angle = %s\n' % fmt(cone)
        text += '    float inputs:shaping:cone:softness = %s\n' % fmt(soft)
        text += '    float inputs:shaping:focus = 0\n'
    else:
        text += '    float inputs:shaping:cone:angle = 180\n'
    text += '    matrix4d xformOp:transform = %s\n' % matrix_usda(sp.matrix(lamp_matrix(lamp)))
    text += '    uniform token[] xformOpOrder = ["xformOp:transform"]\n}\n'
    os.makedirs(os.path.join(folder, "lights"), exist_ok=True)
    with open(os.path.join(folder, "lights", "light_%s.usda" % h), "w") as f:
        f.write(text)


def camera_matrix():
    return look_at(CAMERA["location"], CAMERA["target"])


def write_capture(folder, name, meters_per_unit=1.0, z_up=True, parts=None, skip_textures=(), cut_mesh=None):
    sp = Space(meters_per_unit, z_up)
    parts = PARTS if parts is None else parts
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.join(folder, "materials"), exist_ok=True)
    for mdl in ("AperturePBR_Opacity", "AperturePBR_Translucent"):
        with open(os.path.join(folder, "materials", mdl + ".mdl"), "w") as f:
            f.write("// placeholder: the capture's copy of Remix's %s.mdl\n" % mdl)
    meshes = {CUBE: cube_mesh(), SPHERE: sphere_mesh()}
    first_mat = {}
    for p in parts:
        first_mat.setdefault(p[1], MAT[p[5]])
    for h, mesh in meshes.items():
        if h in first_mat:
            write_mesh(folder, h, mesh, first_mat[h], sp)
    for key in MATERIALS:
        write_material(folder, key, sp)
    for key in skip_textures:
        path = os.path.join(folder, "textures", MAT[key] + ".dds")
        if os.path.isfile(path):
            os.remove(path)
    for lamp in LAMPS:
        write_light(folder, lamp, sp)
    if cut_mesh:
        path = os.path.join(folder, "meshes", "mesh_%s.usda" % cut_mesh)
        with open(path) as f:
            text = f.read()
        with open(path, "w") as f:
            f.write(text[:len(text) // 2])

    extra = ('    customLayerData = {\n'
             '        dictionary cameraSettings = {\n            string boundCamera = "/RootNode/cameras/Camera"\n        }\n'
             '        string lightspeed_exe_name = "bge_remix_tests.exe"\n'
             '        string lightspeed_game_icon = "bge_remix_tests.exe_icon.bmp"\n'
             '        string lightspeed_game_name = "BGE-Remix P12 test room"\n'
             '        string lightspeed_geometry_hash_rules = "positions,indices,geometrydescriptor"\n'
             '        string lightspeed_layer_type = "capture"\n'
             '    }\n    defaultPrim = "RootNode"\n    endTimeCode = 0\n    startTimeCode = 0\n')
    text = layer_head(meters_per_unit, z_up, extra)
    text += 'def "RootNode"\n{\n'
    text += '    def "meshes"\n    {\n'
    for h in sorted(meshes):
        if h not in first_mat:
            continue
        text += '        def Xform "mesh_%s" (\n' % h
        text += '            prepend apiSchemas = ["MaterialBindingAPI"]\n'
        text += '            prepend references = @./meshes//mesh_%s.usda@</mesh_%s>\n        )\n        {\n' % (h, h)
        text += '            rel material:binding = </RootNode/Looks/mat_%s>\n' % first_mat[h]
        text += '            token visibility = "invisible"\n        }\n'
    text += '    }\n\n    def "Looks"\n    {\n'
    for key in sorted(MAT):
        h = MAT[key]
        text += '        def Material "mat_%s" (\n' % h
        text += '            prepend references = @./materials/mat_%s.usda@</Looks/mat_%s>\n        )\n        {\n        }\n' % \
            (h, h)
    text += '    }\n\n    def Xform "instances"\n    {\n'
    count = {}
    for p in parts:
        pname, mh, size, loc, rot, mkey = p
        n = count.get(mh, 0)
        count[mh] = n + 1
        text += '        def Xform "inst_%s_%d" (\n' % (mh, n)
        text += '            prepend apiSchemas = ["MaterialBindingAPI"]\n'
        text += '            prepend references = </RootNode/meshes/mesh_%s>\n        )\n        {\n' % mh
        text += '            rel material:binding = </RootNode/Looks/mat_%s>\n' % MAT[mkey]
        text += '            token visibility = "inherited"\n'
        text += '            matrix4d xformOp:transform = %s\n' % matrix_usda(sp.matrix(mat_trs(loc, rot, size)))
        text += '            uniform token[] xformOpOrder = ["xformOp:transform"]\n        }\n'
    text += '    }\n\n    def Xform "lights"\n    {\n'
    for lamp in LAMPS:
        text += '        def SphereLight "light_%s" (\n' % lamp[1]
        text += '            prepend references = @./lights//light_%s.usda@\n        )\n        {\n        }\n' % lamp[1]
    text += '    }\n\n    def Xform "cameras"\n    {\n'
    cam_sp = sp.matrix(camera_matrix())
    text += '        def Camera "Camera"\n        {\n'
    text += '            float2 clippingRange = (%s, %s)\n' % (fmt(CAMERA["near"] / meters_per_unit),
                                                             fmt(CAMERA["far"] / meters_per_unit))
    text += '            float focalLength = %s\n' % fmt(CAMERA["focal_length"])
    text += '            float horizontalAperture = %s\n' % fmt(CAMERA["horizontal_aperture"])
    text += '            float verticalAperture = %s\n' % fmt(CAMERA["vertical_aperture"])
    text += '            matrix4d xformOp:transform = %s\n' % matrix_usda(cam_sp)
    text += '            uniform token[] xformOpOrder = ["xformOp:transform"]\n        }\n'
    text += '    }\n}\n'
    path = os.path.join(folder, "capture_%s.usda" % name)
    with open(path, "w") as f:
        f.write(text)
    return path


def expected(parts=None):
    """what the importer must bring in (metres, Z up, Blender's matrices)"""
    parts = PARTS if parts is None else parts
    objects = []
    count = {}
    for p in parts:
        pname, mh, size, loc, rot, mkey = p
        n = count.get(mh, 0)
        count[mh] = n + 1
        objects.append({"part": pname, "name": "inst_%s_%d" % (mh, n), "mesh": mh, "material": MAT[mkey],
                        "material_key": mkey, "matrix": mat_trs(loc, rot, size)})
    materials = {}
    for key, m in MATERIALS.items():
        materials[MAT[key]] = {"key": key, "mdl": m["mdl"], "texture": m.get("texture"),
                               "inputs": {k: v for k, (kind, v) in m["inputs"].items()}}
    lamps = []
    for lamp in LAMPS:
        name, h, loc, radius, colour, intensity, cone, soft, aim = lamp
        lamps.append({"name": name, "hash": h, "matrix": lamp_matrix(lamp), "radius": radius, "colour": colour,
                      "intensity": intensity, "cone": cone, "softness": soft})
    meshes = {CUBE: cube_mesh(), SPHERE: sphere_mesh()}
    return {"objects": objects, "materials": materials, "lamps": lamps,
            "meshes": {h: {"vertices": len(m["points"]), "triangles": len(m["indices"]) // 3}
                       for h, m in meshes.items() if h in count},
            "camera": dict(CAMERA, matrix=camera_matrix()),
            "textures": {"rgba": [list(p) for p in texture_rgba()[:TEXTURE_SIZE * 2]],
                         "bc1": [list(p) for p in bc1_pixels()[:TEXTURE_SIZE * 2]], "size": TEXTURE_SIZE}}


def write_broken(folder):
    """three broken captures: a missing texture, a mesh file cut short, and
    a USD file that is no capture"""
    paths = {}
    paths["missing_texture"] = write_capture(os.path.join(folder, "missing_texture"), "missing_texture",
                                             skip_textures=("Box",))
    paths["cut_mesh"] = write_capture(os.path.join(folder, "cut_mesh"), "cut_mesh", cut_mesh=SPHERE)
    other = os.path.join(folder, "not_a_capture")
    os.makedirs(other, exist_ok=True)
    paths["not_a_capture"] = os.path.join(other, "plain.usda")
    with open(paths["not_a_capture"], "w") as f:
        f.write('#usda 1.0\n(\n    defaultPrim = "World"\n)\n\ndef Xform "World"\n{\n    def Cube "Cube"\n    {\n    }\n}\n')
    return paths


def main(argv):
    folder = argv[0]
    kind = argv[1] if len(argv) > 1 else "room"
    os.makedirs(folder, exist_ok=True)
    out = {"kind": kind}
    if kind == "room":
        out["path"] = write_capture(folder, "room")
    elif kind == "room_cm_yup":
        out["path"] = write_capture(folder, "room_cm_yup", meters_per_unit=0.01, z_up=False)
    elif kind == "broken":
        out["paths"] = write_broken(folder)
    else:
        raise SystemExit("unknown kind: " + kind)
    out.update(expected())
    with open(os.path.join(folder, "expected.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("BGE-Remix: wrote the %s capture in %s" % (kind, folder))


if __name__ == "__main__":
    main(sys.argv[1:])
