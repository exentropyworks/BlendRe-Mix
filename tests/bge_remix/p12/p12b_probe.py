"""BGE-Remix P12 Part B: run inside our Blender (background) by p12b_tests.py.

argv (after --):
  exchange <out.json> <folder>
      (round 6, T12.d1, T12.d2) the exchange room made by script, written
      out as it is (want), exported with File > Export > Universal Scene
      Description as <folder>/exchange.usda and exchange.usdc; each file
      read with the bridge's OpenUSD (as the import reads it) and imported
      with File > Import into a file emptied of the room; what came in
      written out (got_usda, got_usdc).
  other <out.json> <folder>
      (T12.d3) another tool's file (usd_files.other_tool: centimetres, Y up,
      instanced) imported; what came in written out.
  unsupported <out.json> <folder>
      (T12.d4) a file with a custom shader, curves and a point instancer
      (usd_files.unsupported) imported; what came in and the report.
  physics <out.json> <folder>
      (round 7, T12.e1, T12.e2) the physics room made by script (want: its
      physics as Blender has it), exported as physics.usda and physics.usdc,
      each read with the bridge's OpenUSD (its physics, as OpenUSD's own
      physics reader gives it, against what the room holds: standard) and
      imported into an emptied file (got_usda, got_usdc). For T12.e3 the
      room and the .usda imported are saved to play (<folder>/room.blend,
      <folder>/imported.blend), each with a script that writes where its
      bodies are at tic 120.
  physics_other <out.json> <folder>
      (T12.e4) another tool's physics file (usd_files.physics_other)
      imported; its physics written out.
  character <out.json> <folder>
      (round 8, T12.f1, T12.f2) the character made by script (want: its
      bones, skin, both actions frame by frame, its body deformed at frames
      1, 12 and 24, its ragdoll), exported as character.usda and
      character.usdc; each read with the bridge's OpenUSD (its skeletons as
      OpenUSD's skeleton reader gives them; OpenUSD's own skinning of the
      body at frame 12 against Blender's) and imported into an emptied file
      (got_usda, got_usdc). For T12.f4 the character and the .usda imported
      are saved to play (<folder>/character.blend, imported.blend; the
      ragdoll's capsules taken out), Walk played by an Action actuator, with
      a script that writes every bone's pose at tics 30 and 60.
  character_other <out.json> <folder>
      (T12.f3) another tool's character (usd_files.character_other)
      imported; its bones, and its body deformed at frames 1, 15 and 30
      against OpenUSD's own skinning of the file.
  usd_view <out.json> <folder>
      (T12.f5) for the Remix View: the physics room saved as it is
      (room.blend), exported as physics.usda and imported (imported.blend),
      and another tool's physics file imported (other.blend), each with its
      3D view a Remix View in Check mode.

The physics room (PhysX on the CPU, gravity 9.81, metres):
  Floor      Static, Box bounds, 12 x 12 x 0.2 m (FloorRubber: friction 0.8,
             bounce 0.1); Ramp: Static, a triangle mesh wedge at x 4
  CrateA     Rigid Body, Box, 5 kg, 0.5 m, 1 m up; CrateB 20 kg, 0.8 m
  Ball       Rigid Body, Sphere (radius 0.25), 1 kg, bounce 0.9, 2 m up
  Rock       Rigid Body, Convex Hull, 3 kg; Capsule: Capsule bounds, lying
             on the ramp's top; Barrel: Dynamic, Cylinder, damping 0.3 and
             0.4; Trigger: Static, Ghost, Box
  Flap       a plate on a Hinge to Post (Static), its axis along Y at its
             edge, 0..100 degrees, its linked collision off: it falls open
  Link1-3    a chain along X, Ball joints, Link1 the root of an
             articulation Fixed to the World: Link2 and Link3 swing down
  LampShade  on a Cone Twist joint to Hook (Static): twist 20, swings 60
  Drawer     a Generic 6DOF slider to the world along Z (-0.3..0 m), the
             rest locked: it drops 0.3 m
  Wall       a destructible of six pieces (Strength 50, Anchored)
  Pool       a water fluid volume (current 0.5 m/s along X)

The character (round 8; PhysX on the CPU, 24 frames a second):
  Rig        an armature at (0.5, 0, 0), turned 20 degrees about Z: 12
             bones, Hips (1 m up), Spine, Neck, Head (connected, up the
             middle), UpperArm and ForeArm left and right (the arms rolled
             30 degrees), Thigh and Shin left and right
    Body     a mesh of boxes along the bones (three rings of four vertices
             each), skinned by an Armature modifier: one bone on a vertex
             in the middle of a bone, two at its ends, three at the middle
             of the spine
  Walk       frames 1 to 24 (a linear key every frame): legs and arms
             swing, the shins bend, the spine twists, the hips bob; the
             armature's own action
  Wave       frames 1 to 12: the right arm up and waving, the head scaled
             1.25 from frame 7 (a constant key)
  capsules   a ragdoll made from it by Make Ragdoll (P11)

The exchange room (metres, Z up):
  Furniture        an empty at (1, 2, 0)
    Table          a 1.2 x 0.8 x 0.05 m table top, 0.75 m up (RTX Remix
                   material Wood: brown, roughness 0.6)
      Leg, Leg.001, Leg.002, Leg.003   its four legs (0.05 x 0.05 x 0.7 m)
  Floor            a 6 x 6 m plane (Classic material FloorGrey)
  Sphere           a UV sphere, 1 m across, at (2, -1, 1): RTX Remix material
                   Gold (a picture, metallic 1, roughness 0.25)
  Cube             a 1 m cube at (-2, 2, 0.5) with a Subdivision modifier
                   (level 1): Classic material Classic Blue (hardness 50)
  Box              a 1 m box at (-2, -1, 0.5), turned 30 degrees: its top and
                   sides material BoxRed, its bottom BoxBlue (Classic); vertex
                   colours
  Point            a point lamp 3 m up
  Spot             a spot (60 degrees, blend 0.2) at (3, 3, 4) looking down
  Sun              a sun turned 45 degrees
  Area             a 1 x 0.5 m area lamp at (0, 3, 2.5)
  Camera           35 mm lens, 32 mm sensor, at (0, -8, 2) looking at the room
"""

import json
import math
import os
import shutil
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import usd_files as uf  # noqa: E402

NODE_INPUTS = ("Albedo", "Opacity", "Roughness", "Metallic", "Emissive Color", "Emissive Intensity", "IOR")
GOLD = (255, 200, 80, 255)


def mat_list(m):
    return [list(row) for row in m]


def value(sock):
    v = sock.default_value
    try:
        return list(v)
    except TypeError:
        return float(v)


# -- the exchange room -------------------------------------------------------

def _uvs(me):
    """UVs from the vertices' x and y (a plain projection)"""
    me.uv_textures.new("UVMap")
    uv = me.uv_layers[0].data
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        uv[loop.index].uv = (co.x * 0.5 + 0.5, co.y * 0.5 + 0.5)


def _mesh(name, make):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    make(bm)
    bm.to_mesh(me)
    bm.free()
    _uvs(me)
    return me


def _box(name, sx, sy, sz):
    from mathutils import Matrix

    def make(bm):
        import bmesh
        # (2.79's mathutils has no Matrix.Diagonal)
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix(((sx, 0.0, 0.0, 0.0), (0.0, sy, 0.0, 0.0),
                                                           (0.0, 0.0, sz, 0.0), (0.0, 0.0, 0.0, 1.0))))
    return _mesh(name, make)


def _object(scene, name, data, loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), parent=None):
    ob = bpy.data.objects.new(name, data)
    scene.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    if parent is not None:
        ob.parent = parent
    return ob


def _remix(name, albedo, roughness, metallic, image=None):
    from bl_operators.bge_remix_material import make_remix_material
    mat = bpy.data.materials.new(name)
    node = make_remix_material(mat)
    node.inputs["Albedo"].default_value = tuple(albedo) + (1.0,)
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metallic
    node.inputs["Emissive Intensity"].default_value = 0.0
    if image is not None:
        nt = mat.node_tree
        geo = nt.nodes.new("ShaderNodeGeometry")
        tex = bpy.data.textures.new(name + "_albedo", 'IMAGE')
        tex.image = image
        tn = nt.nodes.new("ShaderNodeTexture")
        tn.texture = tex
        nt.links.new(geo.outputs["UV"], tn.inputs["Vector"])
        nt.links.new(tn.outputs["Color"], node.inputs["Albedo"])
    return mat


def _classic(name, colour, hardness=50):
    mat = bpy.data.materials.new(name)
    # a Classic material (round 6 fix 2): a new one starts as P8's physical
    # material (material.c BKE_material_physical_init)
    mat["bge_physical"] = 0
    mat.diffuse_color = colour
    mat.diffuse_intensity = 0.8
    mat.specular_intensity = 0.5
    mat.specular_hardness = hardness
    return mat


def make_room(folder):
    import bmesh
    from mathutils import Vector
    scene = bpy.data.scenes.new("Exchange Room")
    src = os.path.join(folder, "source_pictures")
    os.makedirs(src, exist_ok=True)
    # (Blender's first pixel, the bottom left, is gold)
    uf.png(os.path.join(src, "gold.png"), 8, 8,
           lambda x, y: GOLD if (x // 2 + (7 - y) // 2) % 2 == 0 else (230, 170, 60, 255))
    gold_image = bpy.data.images.load(os.path.join(src, "gold.png"))

    wood = _remix("Wood", (0.30, 0.16, 0.07), 0.6, 0.0)
    gold = _remix("Gold", (1.0, 0.766, 0.336), 0.25, 1.0, gold_image)
    grey = _classic("FloorGrey", (0.5, 0.5, 0.5), 20)
    blue = _classic("Classic Blue", (0.2, 0.4, 0.9), 50)
    red_box = _classic("BoxRed", (0.9, 0.1, 0.1))
    blue_box = _classic("BoxBlue", (0.1, 0.1, 0.9))

    furniture = _object(scene, "Furniture", None, (1.0, 2.0, 0.0))
    top = _box("TableTop", 1.2, 0.8, 0.05)
    top.materials.append(wood)
    table = _object(scene, "Table", top, (0.0, 0.0, 0.75), parent=furniture)
    leg_mesh = _box("LegMesh", 0.05, 0.05, 0.7)
    leg_mesh.materials.append(wood)
    for i, (x, y) in enumerate(((-0.55, -0.35), (0.55, -0.35), (-0.55, 0.35), (0.55, 0.35))):
        # each its own mesh (a linked copy would share one)
        me = leg_mesh if i == 0 else leg_mesh.copy()
        _object(scene, "Leg" if i == 0 else "Leg.%03d" % i, me, (x, y, -0.375), parent=table)

    def plane(bm):
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3.0)
    floor_me = _mesh("FloorMesh", plane)
    floor_me.materials.append(grey)
    _object(scene, "Floor", floor_me)

    def sphere(bm):
        bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, diameter=0.5)
    sphere_me = _mesh("SphereMesh", sphere)
    for p in sphere_me.polygons:
        p.use_smooth = True
    sphere_me.materials.append(gold)
    _object(scene, "Sphere", sphere_me, (2.0, -1.0, 1.0))

    cube_me = _box("CubeMesh", 1.0, 1.0, 1.0)
    cube_me.materials.append(blue)
    cube = _object(scene, "Cube", cube_me, (-2.0, 2.0, 0.5))
    mod = cube.modifiers.new("Subdivision", 'SUBSURF')
    mod.levels = mod.render_levels = 1

    box_me = _box("BoxMesh", 1.0, 1.0, 1.0)
    box_me.materials.append(red_box)
    box_me.materials.append(blue_box)
    for p in box_me.polygons:
        p.material_index = 1 if p.normal.z < -0.5 else 0
    col = box_me.vertex_colors.new("Col")
    for loop in box_me.loops:
        co = box_me.vertices[loop.vertex_index].co
        col.data[loop.index].color = (co.x + 0.5, co.y + 0.5, co.z + 0.5)
    _object(scene, "Box", box_me, (-2.0, -1.0, 0.5), (0.0, 0.0, 30.0))

    point = bpy.data.lamps.new("Point", 'POINT')
    point.energy = 2.0
    point.distance = 10.0
    point.shadow_soft_size = 0.1
    point.color = (1.0, 0.9, 0.8)
    _object(scene, "Point", point, (0.0, 0.0, 3.0))
    spot = bpy.data.lamps.new("Spot", 'SPOT')
    spot.energy = 3.0
    spot.distance = 8.0
    spot.spot_size = math.radians(60.0)
    spot.spot_blend = 0.2
    spot.shadow_soft_size = 0.05
    _object(scene, "Spot", spot, (3.0, 3.0, 4.0), (20.0, 0.0, 45.0))
    sun = bpy.data.lamps.new("Sun", 'SUN')
    sun.energy = 1.5
    _object(scene, "Sun", sun, (0.0, 0.0, 10.0), (45.0, 0.0, 30.0))
    area = bpy.data.lamps.new("Area", 'AREA')
    area.shape = 'RECTANGLE'
    area.size, area.size_y = 1.0, 0.5
    area.energy = 4.0
    area.distance = 5.0
    _object(scene, "Area", area, (0.0, 3.0, 2.5), (180.0, 0.0, 0.0))
    cd = bpy.data.cameras.new("Camera")
    cd.lens = 35.0
    cd.sensor_width = 32.0
    cd.sensor_fit = 'HORIZONTAL'
    cd.clip_start, cd.clip_end = 0.1, 100.0
    cam = _object(scene, "Camera", cd, (0.0, -8.0, 2.0))
    cam.rotation_euler = (Vector((0.0, 0.0, 0.5)) - Vector((0.0, -8.0, 2.0))).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    scene.update()
    return scene


# -- what a scene holds ------------------------------------------------------

def dump(scene):
    from bl_operators import bge_remix_usd
    from bl_operators.bge_remix_material import remix_node
    d = {"name": scene.name, "camera": scene.camera.name if scene.camera else None, "objects": {}, "meshes": {},
         "materials": {}}
    for ob in scene.objects:
        o = {"type": ob.type, "parent": ob.parent.name if ob.parent else None, "matrix": mat_list(ob.matrix_world),
             "data": ob.data.name if ob.data else None, "hide": ob.hide}
        if ob.type == 'MESH':
            o["slots"] = [s.material.name if s.material else None for s in ob.material_slots]
            o["users"] = ob.data.users
            try:
                me = ob.to_mesh(scene, True, 'RENDER')
            except RuntimeError:
                me = None
            if me is not None:
                uv = me.uv_layers.active
                col = me.vertex_colors.get("Col") or me.vertex_colors.active
                slots = o["slots"]
                pts = [ob.matrix_world * v.co for v in me.vertices]
                o["world_size"] = [max(p[k] for p in pts) - min(p[k] for p in pts) if pts else 0.0
                                   for k in range(3)]
                o["mesh"] = {"vertices": len(me.vertices), "polygons": len(me.polygons), "loops": len(me.loops),
                             "uv": [list(uv.data[i].uv) for i in range(min(8, len(me.loops)))] if uv else None,
                             "colors": [list(col.data[i].color) for i in range(min(8, len(me.loops)))] if col
                             else None,
                             # each face's material, by name
                             "face_materials": [slots[p.material_index] if p.material_index < len(slots) else None
                                                for p in me.polygons]}
                bpy.data.meshes.remove(me)
            for s in ob.material_slots:
                ma = s.material
                if ma is None or ma.name in d["materials"]:
                    continue
                node = remix_node(ma) if ma.use_nodes else None
                m = {"remix": node is not None, "diffuse": list(ma.diffuse_color),
                     "diffuse_intensity": ma.diffuse_intensity, "hardness": ma.specular_hardness}
                if node is not None:
                    m["remix_type"] = node.remix_type
                    m["blend"] = node.blend
                    m["values"] = {n: value(node.inputs[n]) for n in NODE_INPUTS if n in node.inputs}
                    m["linked"] = {}
                    for inp in node.inputs:
                        if inp.is_linked:
                            tex = getattr(inp.links[0].from_node, "texture", None)
                            ima = getattr(tex, "image", None) if tex else None
                            m["linked"][inp.name] = {"image": ima.name if ima else None,
                                                    "file": bpy.path.abspath(ima.filepath) if ima else None,
                                                    "size": list(ima.size) if ima else None,
                                                    "pixel": [int(round(c * 255.0)) for c in ima.pixels[:4]]
                                                    if ima and ima.size[0] else None}
                    m["marks"] = sorted(k for k in ma.keys() if k.startswith("bge_remix_capture"))
                d["materials"][ma.name] = m
        elif ob.type == 'LAMP':
            o["light"] = bge_remix_usd.light_of(scene, ob)
            o["lamp"] = {"type": ob.data.type}
        elif ob.type == 'CAMERA':
            cd = ob.data
            o["camera"] = {"lens": cd.lens, "sensor_width": cd.sensor_width, "clip": [cd.clip_start, cd.clip_end],
                           "type": cd.type}
        d["objects"][ob.name] = o
    return d


def clear():
    """a file holding nothing but an empty scene"""
    keep = bpy.data.scenes.new("Empty")
    for sc in list(bpy.data.scenes):
        if sc != keep:
            bpy.data.scenes.remove(sc, do_unlink=True)
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.lamps, bpy.data.cameras,
                 bpy.data.textures, bpy.data.images, bpy.data.armatures, bpy.data.actions):
        for x in list(coll):
            try:
                coll.remove(x, do_unlink=True)
            except (RuntimeError, ReferenceError):
                pass
    return keep


def import_file(path):
    from bl_operators import bge_remix_usd
    keep = clear()
    r = {}
    try:
        ret = bpy.ops.import_scene.bge_remix_usd({"scene": keep}, filepath=path)
        r["result"] = sorted(ret)
    except RuntimeError as e:
        r["result"] = ["CANCELLED"]
        r["error"] = str(e)
    last = bge_remix_usd.LAST
    r["report"] = list(last.get("report") or [])
    r["counts"] = dict(last.get("counts") or {})
    name = last.get("scene")
    if name and name in bpy.data.scenes:
        r["scene"] = dump(bpy.data.scenes[name])
    return r


def _read(path):
    """the file as the import's reader gives it (bytes left out)"""
    import _bge_remix
    try:
        data = _bge_remix.usd_read(path)
    except RuntimeError as e:
        return {"error": str(e)}
    for m in data["meshes"]:
        for k in ("points", "face_sizes", "corners_data", "normals", "uvs", "colors"):
            v = m.get(k)
            m[k] = None if v is None else {"bytes": len(v), "hash": hash(v)}
    return data


def exchange(argv, out):
    from bl_operators import bge_remix_usd
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    # the startup file's own Camera, Cube and Lamp go first (round 6 fix 2:
    # the room's camera came out as Camera.001)
    clear()
    scene = make_room(folder)
    out["want"] = dump(scene)
    for ext in ("usda", "usdc"):
        path = os.path.join(folder, "exchange." + ext)
        try:
            ret = bpy.ops.export_scene.bge_remix_usd({"scene": scene}, filepath=path)
            out["export_" + ext] = {"result": sorted(ret)}
        except RuntimeError as e:
            out["export_" + ext] = {"result": ["CANCELLED"], "error": str(e)}
        last = bge_remix_usd.LAST
        out["export_" + ext].update({"report": list(last.get("report") or []), "counts": last.get("counts"),
                                     "pictures": last.get("pictures"), "error_text": last.get("error"),
                                     "exists": os.path.isfile(path)})
        out["read_" + ext] = _read(path)
    out["files"] = sorted(os.listdir(folder))
    out["textures"] = sorted(os.listdir(os.path.join(folder, "textures"))) \
        if os.path.isdir(os.path.join(folder, "textures")) else []
    # what the room's own files had, before they are read again
    out["got_usda"] = import_file(os.path.join(folder, "exchange.usda"))
    out["got_usdc"] = import_file(os.path.join(folder, "exchange.usdc"))


def other(argv, out):
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    path = uf.other_tool(folder)
    out["got"] = import_file(path)


def unsupported(argv, out):
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    path = uf.unsupported(folder)
    out["got"] = import_file(path)



# -- round 7: the physics room ------------------------------------------------

for _phase in ("p9", "p6", "p3", "p2"):
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), _phase))

MOVING = ("CrateA", "CrateB", "Ball", "Rock", "Capsule", "Barrel", "Flap", "Link2", "Link3", "LampShade",
          "Drawer")
PLAY_TIC = 120
PLAY_SCRIPT = """import json, os
import bge
scene = bge.logic.getCurrentScene()
st = bge.logic.globalDict.setdefault("p12e", {"tic": 0})
st["tic"] += 1
if st["tic"] == TIC:
    out = {}
    for name in NAMES:
        ob = scene.objects.get(name)
        if ob is not None:
            out[name] = {"pos": list(ob.worldPosition), "rot": [list(r) for r in ob.worldOrientation]}
    path = os.environ.get("BGE_REMIX_P12_OUT")
    if path:
        with open(path, "w") as f:
            json.dump({"tic": st["tic"], "bodies": out}, f)
"""


def _wedge(name, w, d, h):
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((-w / 2, -d / 2, 0), (w / 2, -d / 2, 0), (w / 2, d / 2, 0), (-w / 2, d / 2, 0),
                                   (-w / 2, -d / 2, h), (-w / 2, d / 2, h))]
    for f in ((0, 3, 2, 1), (0, 1, 4), (3, 5, 2), (0, 4, 5, 3), (1, 2, 5, 4)):
        bm.faces.new([v[i] for i in f])
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


def make_physics_room(folder):
    import bmesh
    import make_scenes_p6 as m6
    scene = m6.base("P12 Physics")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    scene.game_settings.physics_gravity = 9.81
    rubber = m6.material("FloorRubber", (0.4, 0.4, 0.42), friction=0.8, bounce=0.1)
    grey = m6.material("Grey", (0.6, 0.6, 0.6))
    bouncy = m6.material("BallBounce", (0.8, 0.2, 0.2), friction=0.5, bounce=0.9)
    m6.box(scene, "Floor", (12.0, 12.0, 0.2), (0.0, 0.0, -0.1), rubber, physics='STATIC')
    ramp = bpy.data.objects.new("Ramp", _wedge("RampMesh", 2.0, 1.0, 1.0))
    ramp.data.materials.append(grey)
    scene.objects.link(ramp)
    ramp.location = (4.0, 0.0, 0.0)
    ramp.game.physics_type = 'STATIC'
    ramp.game.use_collision_bounds = False
    m6.box(scene, "CrateA", 0.5, (-3.0, -2.0, 1.0), grey, mass=5.0)
    m6.box(scene, "CrateB", 0.8, (-1.5, -2.0, 1.5), grey, mass=20.0)
    m6.ball(scene, "Ball", 0.25, (0.0, -3.0, 2.0), bouncy, mass=1.0)
    rock_me = bpy.data.meshes.new("RockMesh")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, diameter=0.3)
    for i, vert in enumerate(bm.verts):
        vert.co *= 1.0 + 0.15 * ((i * 37) % 5) / 4.0
    bm.to_mesh(rock_me)
    bm.free()
    rock_me.materials.append(grey)
    rock = bpy.data.objects.new("Rock", rock_me)
    scene.objects.link(rock)
    rock.location = (1.5, -2.0, 1.0)
    rock.game.physics_type = 'RIGID_BODY'
    rock.game.use_collision_bounds = True
    rock.game.collision_bounds_type = 'CONVEX_HULL'
    rock.game.mass = 3.0

    def cylinder(name, r, depth):
        me = bpy.data.meshes.new(name + "Mesh")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=16, diameter1=r, diameter2=r, depth=depth)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(grey)
        ob = bpy.data.objects.new(name, me)
        scene.objects.link(ob)
        return ob
    cap = cylinder("Capsule", 0.15, 0.6)
    cap.location = (3.6, 0.0, 1.25)
    cap.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    cap.game.physics_type = 'RIGID_BODY'
    cap.game.use_collision_bounds = True
    cap.game.collision_bounds_type = 'CAPSULE'
    cap.game.mass = 2.0
    barrel = cylinder("Barrel", 0.3, 0.8)
    barrel.location = (-3.0, 1.0, 1.0)
    barrel.game.physics_type = 'DYNAMIC'
    barrel.game.use_collision_bounds = True
    barrel.game.collision_bounds_type = 'CYLINDER'
    barrel.game.mass = 8.0
    barrel.game.damping = 0.3
    barrel.game.rotation_damping = 0.4
    trig = m6.box(scene, "Trigger", 1.0, (0.0, 2.0, 0.5), grey, physics='STATIC')
    trig.game.use_ghost = True
    # the flap on its post
    post = m6.box(scene, "Post", (0.1, 0.1, 2.0), (3.0, 3.0, 1.0), grey, physics='STATIC')
    flap = m6.box(scene, "Flap", (1.0, 0.6, 0.05), (3.55, 3.0, 1.95), grey, mass=2.0)
    c = m6.joint(flap, post, 'HINGE', pivot=(-0.5, 0.0, 0.0), axis=(0.0, 0.0, math.radians(90.0)))
    c.name = "FlapHinge"
    c.use_angular_limit_x = True
    c.limit_angle_min_x, c.limit_angle_max_x = 0.0, math.radians(100.0)
    c.use_linked_collision = True
    # the chain
    links = []
    for k in range(3):
        links.append(m6.box(scene, "Link%d" % (k + 1), (0.4, 0.1, 0.1), (-2.8 + 0.4 * k, 3.0, 3.0), grey,
                            mass=1.0))
    links[0].bge_articulation = 'FIXED'
    for k in (1, 2):
        c = m6.joint(links[k], links[k - 1], 'BALL', pivot=(-0.5, 0.0, 0.0))
        c.name = "ChainBall%d" % k
        c.use_linked_collision = True
    # the lamp on its cone twist joint
    hook = m6.box(scene, "Hook", 0.1, (0.0, 4.0, 3.0), grey, physics='STATIC')
    shade = m6.box(scene, "LampShade", (0.2, 0.2, 0.3), (0.4, 4.0, 3.0), grey, mass=1.5)
    c = m6.joint(shade, hook, 'CONE_TWIST', pivot=(-2.0, 0.0, 0.0))
    c.name = "LampCone"
    for a, v in (("x", 20.0), ("y", 60.0), ("z", 60.0)):
        setattr(c, "use_angular_limit_" + a, True)
        setattr(c, "limit_angle_min_" + a, -math.radians(v))
        setattr(c, "limit_angle_max_" + a, math.radians(v))
    c.use_linked_collision = True
    # the drawer on its slider (to the world, along Z)
    drawer = m6.box(scene, "Drawer", (0.6, 0.8, 0.2), (-1.0, 4.0, 2.0), grey, mass=1.0)
    c = m6.joint(drawer, None, 'GENERIC_6_DOF', axis=(0.0, math.radians(-90.0), 0.0))
    c.name = "DrawerSlide"
    c.use_limit_x, c.limit_min_x, c.limit_max_x = True, -0.3, 0.0
    for a in "yz":
        setattr(c, "use_limit_" + a, True)
        setattr(c, "limit_min_" + a, 0.0)
        setattr(c, "limit_max_" + a, 0.0)
    for a in "xyz":
        setattr(c, "use_angular_limit_" + a, True)
        setattr(c, "limit_angle_min_" + a, 0.0)
        setattr(c, "limit_angle_max_" + a, 0.0)
    # P11: the destructible wall, the pool
    wall = m6.box(scene, "Wall", (2.0, 0.3, 1.0), (2.0, -4.5, 0.5), grey, physics='STATIC')
    for o in scene.objects:
        o.select = o == wall
    scene.objects.active = wall
    ret = bpy.ops.object.bge_remix_make_destructible(pieces=6, seed=1, strength=50.0, anchored=True)
    if 'FINISHED' not in ret:
        raise RuntimeError("Make Destructible: %s" % ret)
    pool = m6.box(scene, "Pool", (2.0, 2.0, 1.0), (-4.0, -4.0, 0.5), grey, physics='STATIC')
    for o in scene.objects:
        o.select = o == pool
    scene.objects.active = pool
    ret = bpy.ops.object.bge_remix_make_fluid_volume(fluid_type='WATER', current=(0.5, 0.0, 0.0))
    if 'FINISHED' not in ret:
        raise RuntimeError("Make Fluid Volume: %s" % ret)
    import make_scenes_p2 as p2
    p2.camera(scene, (0.0, -12.0, 5.0), (0.0, 0.0, 1.0), lens=24.0)
    scene.update()
    return scene


GAME = ("physics_type", "mass", "use_collision_bounds", "collision_bounds_type", "collision_margin", "radius",
        "damping", "rotation_damping", "velocity_min", "velocity_max", "use_ghost", "use_collision_compound",
        "lock_location_x", "lock_location_y", "lock_location_z", "lock_rotation_x", "lock_rotation_y",
        "lock_rotation_z")
JOINT = ("pivot_type", "pivot_x", "pivot_y", "pivot_z", "axis_x", "axis_y", "axis_z", "use_linked_collision",
         "use_limit_x", "use_limit_y", "use_limit_z", "use_angular_limit_x", "use_angular_limit_y",
         "use_angular_limit_z", "limit_min_x", "limit_min_y", "limit_min_z", "limit_max_x", "limit_max_y",
         "limit_max_z", "limit_angle_min_x", "limit_angle_min_y", "limit_angle_min_z", "limit_angle_max_x",
         "limit_angle_max_y", "limit_angle_max_z")
IDPROPS = ("bge_destructible", "bge_fluid", "bge_ragdoll")


def _plain(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if hasattr(v, "to_list"):
        return v.to_list()
    try:
        return [_plain(x) for x in v]
    except TypeError:
        return str(v)


def _on_visible_layer(scene, ob):
    """its base on one of the scene's visible layers (what the game plays)"""
    for b in scene.object_bases:
        if b.object == ob:
            return any(x and y for x, y in zip(b.layers, scene.layers))
    return False


def physics_dump(scene):
    from mathutils import Euler, Vector
    gs = scene.game_settings
    d = {"engine": gs.physics_engine, "device": getattr(gs, "physx_device", None), "gravity": gs.physics_gravity,
         "objects": {}}
    for ob in scene.objects:
        if not _on_visible_layer(scene, ob):
            continue
        o = {"type": ob.type, "parent": ob.parent.name if ob.parent else None,
             "matrix": [list(r) for r in ob.matrix_world],
             "game": {k: _plain(getattr(ob.game, k)) for k in GAME},
             "articulation": getattr(ob, "bge_articulation", None),
             "idprops": {k: _plain(ob[k]) for k in ob.keys() if k.startswith(IDPROPS)}}
        mats = [s.material for s in ob.material_slots if s.material is not None]
        if mats:
            o["friction"] = mats[0].physics.friction
            o["elasticity"] = mats[0].physics.elasticity
        o["joints"] = []
        for c in ob.constraints:
            if c.type != 'RIGID_BODY_JOINT':
                continue
            j = {k: _plain(getattr(c, k)) for k in JOINT}
            j["name"] = c.name
            j["target"] = c.target.name if c.target else None
            W = ob.matrix_world
            frame = W.to_3x3().normalized() * Euler((c.axis_x, c.axis_y, c.axis_z), 'XYZ').to_matrix()
            j["world_axis"] = list(frame.col[0])
            j["world_pivot"] = list(W * Vector((c.pivot_x, c.pivot_y, c.pivot_z)))
            o["joints"].append(j)
        if ob.type == 'MESH':
            o["volume"] = None
        d["objects"][ob.name] = o
    return d


def standard_expect(scene):
    """what OpenUSD's physics reader must find for the room (from Blender's
    settings, not from the export): bodies, shapes and their kinds, joints
    and their kinds, physics materials, articulation roots, gravity"""
    kinds = {'BOX': "cube", 'SPHERE': "sphere", 'CAPSULE': "capsule", 'CYLINDER': "cylinder", 'CONE': "cone",
             'CONVEX_HULL': "mesh", 'TRIANGLE_MESH': "mesh"}
    joints = {'BALL': "spherical", 'CONE_TWIST': "spherical", 'HINGE': "revolute", 'GENERIC_6_DOF': "d6"}
    E = {"bodies": [], "shapes": {}, "joints": {}, "frictions": {}, "roots": 0, "gravity": scene.game_settings.physics_gravity}
    for ob in scene.objects:
        if not _on_visible_layer(scene, ob) or ob.type != 'MESH':
            continue
        g = ob.game
        if g.physics_type not in ('STATIC', 'RIGID_BODY', 'DYNAMIC'):
            continue
        piece = g.use_collision_compound and ob.parent is not None and ob.parent.game.use_collision_compound
        if g.physics_type in ('RIGID_BODY', 'DYNAMIC') and not piece:
            E["bodies"].append(ob.name)
        bounds = g.collision_bounds_type if g.use_collision_bounds else \
            ('SPHERE' if g.physics_type != 'STATIC' else 'TRIANGLE_MESH')
        E["shapes"][ob.name] = kinds[bounds]
        mats = [s.material for s in ob.material_slots if s.material is not None]
        if mats:
            E["frictions"][ob.name] = [mats[0].physics.friction, mats[0].physics.elasticity]
        for c in ob.constraints:
            if c.type == 'RIGID_BODY_JOINT':
                E["joints"][c.name] = joints[c.pivot_type]
        if getattr(ob, "bge_articulation", 'NONE') == 'FIXED':
            E["joints"]["FixedBase"] = "fixed"
            E["roots"] += 1
        elif getattr(ob, "bge_articulation", 'NONE') == 'FREE':
            E["roots"] += 1
    return E


def standard_got(read):
    """what OpenUSD's physics reader found, by object name"""
    import json as _json
    from bl_operators import bge_remix_usd_text as ut
    phys = _json.loads(read.get("physics") or "{}") if isinstance(read.get("physics"), str) else {}
    # every prim of an object (its Xform, its mesh) by the object's name
    names = {}
    nodes = read.get("nodes") or ()
    for o in ut.objects_from_read(read):
        for k in (o["node"], o["data_node"]):
            names[nodes[k]["path"]] = o["name"]

    def owner(path):
        while path and path != "/":
            if path in names:
                return names[path]
            path = path.rsplit("/", 1)[0]
        return None
    mats = {m["path"]: m for m in phys.get("materials") or ()}
    out = {"read": phys.get("read"), "bodies": sorted(owner(b["path"]) for b in phys.get("bodies") or ()),
           "shapes": {}, "joints": {}, "frictions": {}, "roots": 0,
           "gravity": ((phys.get("scenes") or [{}])[0]).get("gravity_magnitude")}
    for sh in phys.get("shapes") or ():
        # a mesh shape's prim is the mesh: its object is the Xform above it
        out["shapes"][owner(sh["path"])] = sh["kind"]
        for m in sh.get("materials") or ():
            pm = mats.get(m)
            if pm:
                out["frictions"][owner(sh["path"])] = [pm["dynamic_friction"], pm["restitution"]]
    for j in phys.get("joints") or ():
        name = (phys.get("custom", {}).get(j["path"]) or {}).get("name") or j["path"].rsplit("/", 1)[-1]
        out["joints"][name.replace("BGE_Joint_", "")] = j["kind"]
    out["roots"] = sum(len(a.get("roots") or ()) for a in phys.get("articulations") or ())
    return out


def save_to_play(scene, path, names):
    import make_scenes_p2 as p2
    import make_scenes_p9 as m9
    for sc in list(bpy.data.scenes):
        if sc != scene:
            bpy.data.scenes.remove(sc, do_unlink=True)
    m9.logic(scene, "P12ePlay", PLAY_SCRIPT.replace("TIC", str(PLAY_TIC)).replace("NAMES", repr(list(names))))
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, compress=False)


def physics(argv, out):
    from bl_operators import bge_remix_usd
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    scene = make_physics_room(folder)
    out["want"] = physics_dump(scene)
    out["standard_want"] = standard_expect(scene)
    for ext in ("usda", "usdc"):
        path = os.path.join(folder, "physics." + ext)
        try:
            ret = bpy.ops.export_scene.bge_remix_usd({"scene": scene}, filepath=path)
            out["export_" + ext] = {"result": sorted(ret)}
        except RuntimeError as e:
            out["export_" + ext] = {"result": ["CANCELLED"], "error": str(e)}
        last = bge_remix_usd.LAST
        out["export_" + ext].update({"report": list(last.get("report") or []), "counts": last.get("counts"),
                                     "exists": os.path.isfile(path)})
        import _bge_remix
        try:
            read = _bge_remix.usd_read(path)
            out["standard_" + ext] = standard_got(read)
            out["standard_" + ext]["usd_errors"] = read.get("usd_errors")
            out["standard_" + ext]["report"] = read.get("report")
            out["physics_json_" + ext] = read.get("physics")
        except RuntimeError as e:
            out["standard_" + ext] = {"error": str(e)}
    names = [n for n in MOVING if n in scene.objects]
    out["moving"] = names
    save_to_play(scene, os.path.join(folder, "room.blend"), names)
    for ext in ("usda", "usdc"):
        r = import_file(os.path.join(folder, "physics." + ext))
        name = (r.get("scene") or {}).get("name")
        if name and name in bpy.data.scenes:
            r["physics"] = physics_dump(bpy.data.scenes[name])
            if ext == "usda":
                save_to_play(bpy.data.scenes[name], os.path.join(folder, "imported.blend"), names)
        out["got_" + ext] = r


def physics_other(argv, out):
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    path = uf.physics_other(folder)
    r = import_file(path)
    name = (r.get("scene") or {}).get("name")
    if name and name in bpy.data.scenes:
        sc = bpy.data.scenes[name]
        r["physics"] = physics_dump(sc)
    out["got"] = r


# -- round 8: the character ----------------------------------------------------

# bone: parent, head, tail, connected, roll (degrees)
BONES = [
    ("Hips", None, (0.0, 0.0, 1.0), (0.0, 0.0, 1.1), False, 0.0),
    ("Spine", "Hips", (0.0, 0.0, 1.1), (0.0, 0.0, 1.45), True, 0.0),
    ("Neck", "Spine", (0.0, 0.0, 1.45), (0.0, 0.0, 1.55), True, 0.0),
    ("Head", "Neck", (0.0, 0.0, 1.55), (0.0, 0.0, 1.8), True, 0.0),
    ("UpperArm.L", "Spine", (0.15, 0.0, 1.42), (0.45, 0.0, 1.42), False, 30.0),
    ("ForeArm.L", "UpperArm.L", (0.45, 0.0, 1.42), (0.72, 0.0, 1.42), True, 30.0),
    ("UpperArm.R", "Spine", (-0.15, 0.0, 1.42), (-0.45, 0.0, 1.42), False, -30.0),
    ("ForeArm.R", "UpperArm.R", (-0.45, 0.0, 1.42), (-0.72, 0.0, 1.42), True, -30.0),
    ("Thigh.L", "Hips", (0.1, 0.0, 1.0), (0.1, 0.0, 0.55), False, 0.0),
    ("Shin.L", "Thigh.L", (0.1, 0.0, 0.55), (0.1, 0.0, 0.1), True, 0.0),
    ("Thigh.R", "Hips", (-0.1, 0.0, 1.0), (-0.1, 0.0, 0.55), False, 0.0),
    ("Shin.R", "Thigh.R", (-0.1, 0.0, 0.55), (-0.1, 0.0, 0.1), True, 0.0),
]
CHAIN = {"Hips": "Spine", "Spine": "Neck", "Neck": "Head", "UpperArm.L": "ForeArm.L", "UpperArm.R": "ForeArm.R",
         "Thigh.L": "Shin.L", "Thigh.R": "Shin.R"}
DEFORM_FRAMES = (1, 12, 24)
CHAR_PLAY_TICS = (30, 60)
CHAR_PLAY_SCRIPT = """import json, os
import bge
scene = bge.logic.getCurrentScene()
st = bge.logic.globalDict.setdefault("p12f", {"tic": 0, "poses": {}})
st["tic"] += 1
if st["tic"] in TICS:
    rig = scene.objects.get("Rig")
    pose = {}
    if rig is not None:
        for ch in rig.channels:
            pose[ch.name] = {"head": list(ch.pose_head), "tail": list(ch.pose_tail),
                             "matrix": [list(r) for r in ch.pose_matrix]}
        st["poses"][str(st["tic"])] = {"frame": rig.getActionFrame(0), "bones": pose}
    if st["tic"] == max(TICS):
        path = os.environ.get("BGE_REMIX_P12_OUT")
        if path:
            with open(path, "w") as f:
                json.dump({"tic": st["tic"], "poses": st["poses"]}, f)
"""


def _keys(act, bone, prop, frames_values, interpolation='LINEAR'):
    """keys on one bone's property: [(frame, (values))]"""
    width = len(frames_values[0][1])
    for i in range(width):
        fc = act.fcurves.new('pose.bones["%s"].%s' % (bone, prop), i, bone)
        for f, v in frames_values:
            kp = fc.keyframe_points.insert(f, v[i])
            kp.interpolation = interpolation
        fc.update()


def make_character(folder):
    import make_scenes_p6 as m6
    from mathutils import Quaternion, Vector
    scene = m6.base("P12 Character")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    scene.render.fps = 24
    scene.render.fps_base = 1.0
    scene.frame_start, scene.frame_end = 1, 24
    arm = bpy.data.armatures.new("RigData")
    rig = bpy.data.objects.new("Rig", arm)
    scene.objects.link(rig)
    rig.location = (0.5, 0.0, 0.0)
    rig.rotation_euler = (0.0, 0.0, math.radians(20.0))
    scene.objects.active = rig
    for o in scene.objects:
        o.select = o == rig
    scene.update()
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = {}
    for name, parent, head, tail, connect, roll in BONES:
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = head, tail
        eb.roll = math.radians(roll)
        if parent:
            eb.parent = ebs[parent]
            eb.use_connect = connect
        ebs[name] = eb
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    # the body: boxes along the bones, three rings each
    import bmesh
    bm = bmesh.new()
    weights = []
    children = {}
    for name, parent, _h, _t, _c, _r in BONES:
        children.setdefault(parent, []).append(name)
    for name, parent, head, tail, _c, _r in BONES:
        h, t = Vector(head), Vector(tail)
        d = (t - h).normalized()
        side = d.cross(Vector((0.0, 1.0, 0.0)))
        if side.length < 1e-6:
            side = d.cross(Vector((1.0, 0.0, 0.0)))
        side.normalize()
        up = d.cross(side).normalized()
        rings = []
        for k, f in enumerate((0.05, 0.5, 0.95)):
            c = h + (t - h) * f
            ring = [bm.verts.new(c + side * u * 0.04 + up * v * 0.04) for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            if k == 0:
                w = {name: 0.6, parent: 0.4} if parent else {name: 1.0}
            elif k == 1:
                w = {"Spine": 0.6, "UpperArm.L": 0.2, "UpperArm.R": 0.2} if name == "Spine" else {name: 1.0}
            else:
                w = {name: 0.7, CHAIN[name]: 0.3} if name in CHAIN else {name: 1.0}
            weights += [w] * 4
            rings.append(ring)
        for a, b in ((0, 1), (1, 2)):
            for i in range(4):
                bm.faces.new((rings[a][i], rings[a][(i + 1) % 4], rings[b][(i + 1) % 4], rings[b][i]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[2])
    me = bpy.data.meshes.new("BodyMesh")
    bm.to_mesh(me)
    bm.free()
    body = bpy.data.objects.new("Body", me)
    scene.objects.link(body)
    body.parent = rig
    body.game.physics_type = 'NO_COLLISION'
    for v, w in enumerate(weights):
        for g, x in w.items():
            vg = body.vertex_groups.get(g) or body.vertex_groups.new(g)
            vg.add([v], x, 'REPLACE')
    mod = body.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    # the actions
    # a key every frame (unit turns): the game, playing between frames, moves
    # the same through these keys as through the file's samples
    ph = {f: math.sin(2.0 * math.pi * (f - 1) / 23.0) for f in range(1, 25)}
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

    def q(axis, deg):
        return tuple(Quaternion(axis, math.radians(deg)))
    walk = bpy.data.actions.new("Walk")
    for bone, axis, most in (("Thigh.L", X, 30.0), ("Thigh.R", X, -30.0), ("UpperArm.L", X, -20.0),
                             ("UpperArm.R", X, 20.0), ("Spine", Y, 10.0)):
        _keys(walk, bone, "rotation_quaternion", [(f, q(axis, most * p)) for f, p in sorted(ph.items())])
    for bone in ("Shin.L", "Shin.R"):
        _keys(walk, bone, "rotation_quaternion", [(f, q(X, 20.0 * abs(p))) for f, p in sorted(ph.items())])
    _keys(walk, "Hips", "location", [(f, (0.0, 0.03 * abs(p), 0.0)) for f, p in sorted(ph.items())])
    wave = bpy.data.actions.new("Wave")
    wph = {1: 0.0, 4: 1.0, 7: -1.0, 10: 1.0, 12: 0.0}
    _keys(wave, "UpperArm.R", "rotation_quaternion", [(f, q(Z, -80.0 * (1.0 if f > 1 else 0.0)))
                                                      for f in sorted(wph)])
    _keys(wave, "ForeArm.R", "rotation_quaternion", [(f, q(X, 30.0 * p)) for f, p in sorted(wph.items())])
    _keys(wave, "Head", "scale", [(1, (1.0, 1.0, 1.0)), (7, (1.25, 1.25, 1.25))], 'CONSTANT')
    wave.use_fake_user = True
    rig.animation_data_create().action = walk
    # the ragdoll
    scene.objects.active = rig
    for o in scene.objects:
        o.select = o == rig
    ret = bpy.ops.object.bge_remix_make_ragdoll()
    if 'FINISHED' not in ret:
        raise RuntimeError("Make Ragdoll: %s" % ret)
    import make_scenes_p2 as p2
    p2.camera(scene, (0.0, -6.0, 1.5), (0.0, 0.0, 1.0), lens=35.0)
    scene.frame_set(1)
    scene.update()
    return scene


def _rows(m):
    return [list(r) for r in m]


def _deformed(scene, ob):
    me = ob.to_mesh(scene, True, 'RENDER')
    try:
        W = ob.matrix_world
        return [list(W * v.co) for v in me.vertices]
    finally:
        bpy.data.meshes.remove(me)


def character_dump(scene):
    """the armature's bones, the body's skin, both actions frame by frame,
    the body deformed, the ragdoll's capsules"""
    from mathutils import Matrix
    d = {"fps": scene.render.fps / scene.render.fps_base, "frames": [scene.frame_start, scene.frame_end]}
    rig = scene.objects.get("Rig")
    body = scene.objects.get("Body")
    if rig is None or rig.type != 'ARMATURE':
        d["error"] = "no armature Rig"
        return d
    d["rig"] = {"matrix": _rows(rig.matrix_world), "type": rig.type, "bones": {}}
    for b in rig.data.bones:
        d["rig"]["bones"][b.name] = {"parent": b.parent.name if b.parent else None, "head": list(b.head_local),
                                     "tail": list(b.tail_local), "matrix": _rows(b.matrix_local),
                                     "connect": b.use_connect, "deform": b.use_deform}
    ad = rig.animation_data
    current = ad.action if ad else None
    d["action"] = current.name if current else None
    d["actions"] = {}
    if body is not None:
        d["body"] = {"type": body.type, "parent": body.parent.name if body.parent else None,
                     "modifiers": [(m.type, m.object.name if getattr(m, "object", None) else None)
                                   for m in body.modifiers],
                     "groups": [{body.vertex_groups[g.group].name: g.weight for g in v.groups}
                                for v in body.data.vertices] if body.type == 'MESH' else []}
    frame = scene.frame_current
    if ad is None:
        ad = rig.animation_data_create()
    for name in ("Walk", "Wave"):
        act = bpy.data.actions.get(name)
        if act is None:
            continue
        # (from the rest pose: a bone the action has no keys for stands at rest)
        for pb in rig.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        ad.action = act
        poses = {}
        first, last = act.frame_range
        for f in range(int(first), int(last) + 1):
            scene.frame_set(f)
            poses[str(f)] = {pb.name: _rows(pb.matrix) for pb in rig.pose.bones}
            if name == "Walk" and f in DEFORM_FRAMES and body is not None:
                d.setdefault("deformed", {})[str(f)] = _deformed(scene, body)
        d["actions"][name] = {"range": [first, last], "poses": poses, "fake_user": act.use_fake_user}
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    ad.action = current
    scene.frame_set(frame)
    caps = {}
    phys = physics_dump(scene)
    for ob in scene.objects:
        if "bge_ragdoll_bone" in ob:
            caps[ob.name] = {"parent": ob.parent.name if ob.parent else None, "parent_type": ob.parent_type,
                             "parent_bone": ob.parent_bone, "matrix": _rows(ob.matrix_world),
                             "physics": phys["objects"].get(ob.name)}
    d["capsules"] = caps
    return d


def save_to_play_character(scene, path):
    import make_scenes_p2 as p2
    import make_scenes_p9 as m9
    for sc in list(bpy.data.scenes):
        if sc != scene:
            bpy.data.scenes.remove(sc, do_unlink=True)
    for ob in [o for o in scene.objects if "bge_ragdoll_bone" in o]:
        scene.objects.unlink(ob)
        bpy.data.objects.remove(ob)
    rig = scene.objects["Rig"]
    walk = bpy.data.actions["Walk"]
    scene.objects.active = rig
    bpy.ops.logic.sensor_add(type='ALWAYS', object=rig.name)
    bpy.ops.logic.controller_add(type='LOGIC_AND', object=rig.name)
    bpy.ops.logic.actuator_add(type='ACTION', object=rig.name)
    s, c, a = rig.game.sensors[-1], rig.game.controllers[-1], rig.game.actuators[-1]
    a.action = walk
    a.play_mode = 'PLAY'
    a.frame_start, a.frame_end = 1, 24
    s.link(c)
    c.link(actuator=a)
    m9.logic(scene, "P12fPlay", CHAR_PLAY_SCRIPT.replace("TICS", repr(CHAR_PLAY_TICS)))
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, compress=False)


def _usd_standard(path, mesh_name, frame):
    """the file as OpenUSD reads it: its skeletons, and OpenUSD's own
    skinning of the mesh at frame (in the file's space)"""
    import _bge_remix
    try:
        read = _bge_remix.usd_read(path)
    except RuntimeError as e:
        return {"error": str(e)}
    skel = json.loads(read.get("skeletons") or "{}")
    out = {"skeletons": skel, "usd_errors": read.get("usd_errors"), "report": read.get("report"),
           "meters_per_unit": read.get("meters_per_unit"), "z_up": read.get("z_up")}
    mesh = [s["path"] for s in skel.get("skinned") or () if s["path"].rsplit("/", 1)[-1] == mesh_name]
    out["mesh_path"] = mesh[0] if mesh else None
    out["skinned"] = {}
    if mesh:
        from array import array
        for f in (frame if isinstance(frame, (list, tuple)) else (frame,)):
            b = _bge_remix.usd_skinned_points(path, mesh[0], float(f))
            if b is not None:
                a = array("f")
                a.frombytes(bytes(b))
                v = a.tolist()
                out["skinned"][str(f)] = [v[i:i + 3] for i in range(0, len(v), 3)]
    return out


def character(argv, out):
    from bl_operators import bge_remix_usd
    from bl_operators.bge_remix_usd import SceneExport
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    scene = make_character(folder)
    out["want"] = character_dump(scene)
    rig = scene.objects["Rig"]
    bones = SceneExport.bone_order(rig.data)
    out["want_joints"] = SceneExport.joint_tokens(bones)
    for ext in ("usda", "usdc"):
        path = os.path.join(folder, "character." + ext)
        try:
            ret = bpy.ops.export_scene.bge_remix_usd({"scene": scene}, filepath=path)
            out["export_" + ext] = {"result": sorted(ret)}
        except RuntimeError as e:
            out["export_" + ext] = {"result": ["CANCELLED"], "error": str(e)}
        last = bge_remix_usd.LAST
        out["export_" + ext].update({"report": list(last.get("report") or []), "counts": last.get("counts"),
                                     "exists": os.path.isfile(path)})
        out["standard_" + ext] = _usd_standard(path, "BodyMesh", 12)
    save_to_play_character(scene, os.path.join(folder, "character.blend"))
    for ext in ("usda", "usdc"):
        r = import_file(os.path.join(folder, "character." + ext))
        name = (r.get("scene") or {}).get("name")
        if name and name in bpy.data.scenes:
            sc = bpy.data.scenes[name]
            r["character"] = character_dump(sc)
            r["marks"] = {ob.name: ob.get("bge_remix_usd_prim") for ob in sc.objects}
            if ext == "usda":
                save_to_play_character(sc, os.path.join(folder, "imported.blend"))
        out["got_" + ext] = r


def character_other(argv, out):
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    path = uf.character_other(folder)
    E = uf.character_expect()
    frames = (1, 15, 30)
    out["standard"] = _usd_standard(path, "Body", list(frames))
    r = import_file(path)
    name = (r.get("scene") or {}).get("name")
    if name and name in bpy.data.scenes:
        sc = bpy.data.scenes[name]
        arm = [o for o in sc.objects if o.type == 'ARMATURE']
        body = sc.objects.get("Body")
        d = {"armatures": [o.name for o in arm], "fps": sc.render.fps / sc.render.fps_base,
             "frames": [sc.frame_start, sc.frame_end]}
        if arm:
            a = arm[0]
            W = a.matrix_world
            d["bones"] = {b.name: {"head": list(W * b.head_local), "tail": list(W * b.tail_local),
                                   "parent": b.parent.name if b.parent else None} for b in a.data.bones}
            d["action"] = a.animation_data.action.name if a.animation_data and a.animation_data.action else None
        if body is not None:
            d["body"] = {"parent": body.parent.name if body.parent else None, "vertices": len(body.data.vertices),
                         "groups": len(body.vertex_groups),
                         "modifiers": [m.type for m in body.modifiers]}
            d["deformed"] = {}
            for f in frames:
                sc.frame_set(f)
                d["deformed"][str(f)] = _deformed(sc, body)
        r["character"] = d
    out["got"] = r
    out["expect"] = E


def remix_view_save(scene, path):
    """the scene alone, saved with its 3D view a Remix View in Check mode"""
    for win in bpy.context.window_manager.windows:
        win.screen.scene = scene
    for sc in list(bpy.data.scenes):
        if sc != scene:
            bpy.data.scenes.remove(sc, do_unlink=True)
    made = 0
    for screen in bpy.data.screens:
        screen.scene = scene
        areas = sorted((a for a in screen.areas if a.type == 'VIEW_3D'), key=lambda a: -a.width * a.height)
        for area in areas[:1]:
            space = area.spaces.active
            space.is_game_view = True
            space.game_view_mode = 'CHECK'
            made += 1
    scene.update()
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, compress=False)
    return made


def usd_view(argv, out):
    folder = argv[2]
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder, exist_ok=True)
    scene = make_physics_room(folder)
    path = os.path.join(folder, "physics.usda")
    try:
        out["export"] = sorted(bpy.ops.export_scene.bge_remix_usd({"scene": scene}, filepath=path))
    except RuntimeError as e:
        out["export"] = ["CANCELLED", str(e)]
    out["room_screens"] = remix_view_save(scene, os.path.join(folder, "room.blend"))
    out["room_bodies"] = sorted(n for n, o in physics_dump(scene)["objects"].items()
                                if o["game"]["physics_type"] in ('STATIC', 'RIGID_BODY', 'DYNAMIC'))
    for tag, src in (("imported", path), ("other", uf.physics_other(os.path.join(folder, "other")))):
        r = import_file(src)
        name = (r.get("scene") or {}).get("name")
        if name and name in bpy.data.scenes:
            sc = bpy.data.scenes[name]
            r["marks"] = {ob.name: {"prim": ob.get("bge_remix_usd_prim"), "notes": ob.get("bge_remix_usd_notes"),
                                    "physics": ob.game.physics_type,
                                    "joints": [c.name for c in ob.constraints if c.type == 'RIGID_BODY_JOINT']}
                          for ob in sc.objects}
            r["usd"] = dict(sc.get("bge_remix_usd") or {})
            r["screens"] = remix_view_save(sc, os.path.join(folder, tag + ".blend"))
        r.pop("scene", None)
        out[tag] = r


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode = argv[0]
    out = {"mode": mode}
    path = argv[1] if len(argv) > 1 else os.path.join(os.getcwd(), "p12b_probe.json")
    try:
        {"exchange": exchange, "other": other, "unsupported": unsupported, "physics": physics,
         "physics_other": physics_other, "character": character, "character_other": character_other,
         "usd_view": usd_view}[mode](argv, out)
    except Exception:
        out["traceback"] = traceback.format_exc()
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("BGE-Remix: wrote", path)


main()
