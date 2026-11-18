"""BGE-Remix P12 Part A: the test scenes (made by make_scenes_p12.py).

The room (P12's capture round trip), built in Blender from the same
description the capture writer writes its capture from (capture_writer.py):
floor, four walls and a ceiling, a box drawn twice (the second turned 30
degrees), a sphere, a Brick wall (its brick texture, the BC1 one the
capture has) and a glass pane (RTX Remix's translucent material), lit by a
point lamp and a spot; parts of the same shape share one mesh, as in the
capture, each with its own material on the object. All materials are RTX
Remix materials with the capture's values.
This is the room the imported one is set beside in the RTX run (S12.a1).

P12 round 4, the blend check (S12.b1): a dark grey wall lit from the front
by a sun, seen straight on by an orthographic camera, with two orange quads
in front of it: the left one Add blending, the right one Alpha blending at
half opacity. Made twice: p12_blend_gl.blend (the game's OpenGL) and
p12_blend_remix.blend (RTX Remix). Add blending must brighten the wall
behind its quad.
"""

import math
import os

import bpy

import capture_writer as cw
import make_scenes_p2 as p2
import make_scenes_p3 as p3


def linear(c):
    c = min(max(float(c), 0.0), 1.0)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def shape_mesh(name, data):
    me = bpy.data.meshes.new(name)
    pts, tris, uvs = data["points"], data["indices"], data["uvs"]
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", [c for p in pts for c in p])
    me.loops.add(len(tris))
    me.loops.foreach_set("vertex_index", tris)
    n = len(tris) // 3
    me.polygons.add(n)
    me.polygons.foreach_set("loop_start", [3 * i for i in range(n)])
    me.polygons.foreach_set("loop_total", [3] * n)
    me.update(calc_edges=True)
    me.uv_textures.new("UVMap")
    me.uv_layers[0].data.foreach_set("uv", [c for i in tris for c in uvs[i]])
    me.polygons.foreach_set("use_smooth", [True] * n)
    me.use_auto_smooth = True
    me.normals_split_custom_set([tuple(data["normals"][i]) for i in tris])
    return me


def png(folder, name, px):
    """an image of the texture's pixels (rows from the top) saved as PNG"""
    size = cw.TEXTURE_SIZE
    ima = bpy.data.images.new(name, size, size, alpha=True)
    flat = []
    for y in range(size - 1, -1, -1):  # Blender's rows start at the bottom
        for x in range(size):
            flat += [c / 255.0 for c in px[y * size + x]]
    ima.pixels = flat
    ima.filepath_raw = os.path.join(folder, name + ".png")
    ima.file_format = 'PNG'
    ima.save()
    return ima


def remix_material(key, folder):
    from bl_operators.bge_remix_material import make_remix_material, _set
    spec = cw.MATERIALS[key]
    mat = bpy.data.materials.new("P12" + key)
    node = make_remix_material(mat)
    names = {"diffuse_color_constant": "Albedo", "reflection_roughness_constant": "Roughness",
             "metallic_constant": "Metallic", "emissive_color_constant": "Emissive Color",
             "emissive_intensity": "Emissive Intensity", "ior_constant": "IOR",
             "transmittance_color": "Transmittance", "transmittance_measurement_distance": "Transmittance Distance"}
    srgb = ("diffuse_color_constant", "emissive_color_constant", "transmittance_color")
    for name, (kind, v) in spec["inputs"].items():
        if name not in names:
            continue
        if kind == "color3f":
            v = tuple(linear(c) for c in v) if name in srgb else tuple(v)
            _set(node, names[name], v + (1.0,))
        else:
            _set(node, names[name], float(v))
    if spec["mdl"] == "AperturePBR_Translucent":
        node.remix_type = 'TRANSLUCENT'
    tex_px = {"rgba": cw.texture_rgba, "bc1": cw.bc1_pixels}.get(spec.get("texture"))
    if tex_px:
        nt = mat.node_tree
        geo = nt.nodes.new("ShaderNodeGeometry")
        tex = bpy.data.textures.new("P12" + key, 'IMAGE')
        tex.image = png(folder, "p12_" + key.lower(), tex_px())
        tn = nt.nodes.new("ShaderNodeTexture")
        tn.texture = tex
        nt.links.new(geo.outputs["UV"], tn.inputs["Vector"])
        nt.links.new(tn.outputs["Color"], node.inputs["Albedo"])
    return mat


def lamp(scene, spec):
    """a lamp giving Remix the capture's light (remix_light.cc, distance 1 m)"""
    name, h, loc, radius, colour, intensity, cone, soft, aim = spec
    la = bpy.data.lamps.new(name, 'SPOT' if cone is not None else 'POINT')
    la.color = colour
    la.distance = 1.0
    la.shadow_soft_size = radius
    la.energy = intensity * radius * radius
    la["bge_physical"] = 0.0 if cone is not None else 1.0
    if cone is not None:
        half = math.radians(cone)
        la.spot_size = 2.0 * half
        la.spot_blend = soft / (1.0 - math.cos(half))
    ob = bpy.data.objects.new(name, la)
    scene.objects.link(ob)
    ob.matrix_world = matrix(cw.lamp_matrix(spec))
    return ob


def matrix(m):
    from mathutils import Matrix
    return Matrix(m)


def make_room(folder):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = p3.base_scene()
    scene.name = "P12Room"
    scene.game_settings.fps = 60
    p2.world(scene, (0.05, 0.05, 0.06))
    meshes = {cw.CUBE: shape_mesh("P12Cube", cw.cube_mesh()), cw.SPHERE: shape_mesh("P12Sphere", cw.sphere_mesh())}
    mats = {key: remix_material(key, folder) for key in cw.MATERIALS}
    for name, mh, size, loc, rot, mkey in cw.PARTS:
        ob = bpy.data.objects.new(name, meshes[mh])
        scene.objects.link(ob)
        ob.matrix_world = matrix(cw.mat_trs(loc, rot, size))
        # the material on the object (the game converts a shared mesh once
        # for each set of materials, P12)
        if not meshes[mh].materials:
            meshes[mh].materials.append(None)
        ob.material_slots[0].link = 'OBJECT'
        ob.material_slots[0].material = mats[mkey]
    for spec in cw.LAMPS:
        lamp(scene, spec)
    cd = bpy.data.cameras.new("Camera")
    cd.sensor_fit = 'HORIZONTAL'
    cd.sensor_width = cw.CAMERA["horizontal_aperture"]
    cd.lens = cw.CAMERA["focal_length"]
    cd.clip_start, cd.clip_end = cw.CAMERA["near"], cw.CAMERA["far"]
    cam = bpy.data.objects.new("Camera", cd)
    scene.objects.link(cam)
    cam.matrix_world = matrix(cw.camera_matrix())
    scene.camera = cam
    p2.add_probe(scene)
    scene["bge_remix"] = 1
    scene.update()
    save(os.path.join(folder, "p12_room.blend"))
    return {"file": "p12_room.blend", "parts": [p[0] for p in cw.PARTS], "lamps": [l[0] for l in cw.LAMPS]}


def save(path):
    """p2.save without its Classic marks: these are RTX Remix materials and
    physical (or, the spot, Classic) lamps as made here"""
    for sc in bpy.data.scenes:
        sc["bge_remix_pipeline"] = 1
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, compress=False)
    print("BGE-Remix: wrote", path)


# the blend check: where things are in the 960 x 540 picture (left, top,
# right, bottom), the camera showing 4 m across
BLEND_RECTS = {"add": [200, 230, 280, 310], "alpha": [680, 230, 760, 310], "wall": [440, 450, 520, 510]}
ORANGE = (1.0, 0.4, 0.05)


def make_blend(folder):
    from bl_operators.bge_remix_material import make_remix_material, _set
    from mathutils import Euler
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = p3.base_scene()
    scene.name = "P12Blend"
    scene.game_settings.fps = 60
    p2.world(scene, (0.02, 0.02, 0.02))

    def material(name, rgb, blend, opacity=1.0):
        mat = bpy.data.materials.new(name)
        node = make_remix_material(mat)
        _set(node, "Albedo", tuple(rgb) + (1.0,))
        _set(node, "Roughness", 0.8)
        _set(node, "Opacity", opacity)
        node.blend = blend
        return mat
    wall = material("P12BlendWall", (0.18, 0.18, 0.18), 'OPAQUE')
    p2.plane(scene, "Wall", 6.0, (0.0, 1.0, 0.0), (math.radians(90.0), 0.0, 0.0), wall)
    p2.plane(scene, "AddQuad", 1.0, (-1.0, 0.5, 0.0), (math.radians(90.0), 0.0, 0.0),
             material("P12BlendAdd", ORANGE, 'ADDITIVE'))
    p2.plane(scene, "AlphaQuad", 1.0, (1.0, 0.5, 0.0), (math.radians(90.0), 0.0, 0.0),
             material("P12BlendAlpha", ORANGE, 'BLENDED', 0.5))
    sun = bpy.data.lamps.new("Sun", 'SUN')
    sun.energy = 1.0
    sob = bpy.data.objects.new("Sun", sun)
    scene.objects.link(sob)
    sob.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0))  # shining along +Y, at the wall
    cd = bpy.data.cameras.new("Camera")
    cd.type = 'ORTHO'
    cd.ortho_scale = 4.0
    cam = bpy.data.objects.new("Camera", cd)
    scene.objects.link(cam)
    cam.location = (0.0, -5.0, 0.0)
    cam.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0))
    scene.camera = cam
    p2.add_probe(scene)
    files = {}
    for key, remix in (("gl", 0), ("remix", 1)):
        scene["bge_remix"] = remix
        scene.update()
        files[key] = "p12_blend_%s.blend" % key
        save(os.path.join(folder, files[key]))
    return {"files": files, "rects": BLEND_RECTS, "orange": list(ORANGE)}


def make(folder, E):
    E["p12a"] = {"room": make_room(folder)}
    try:
        E["p12a"]["blend"] = make_blend(folder)
    except Exception:
        import traceback
        E["failed"]["p12a_blend"] = traceback.format_exc()
