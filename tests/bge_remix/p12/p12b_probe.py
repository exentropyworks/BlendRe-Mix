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
                 bpy.data.textures, bpy.data.images):
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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode = argv[0]
    out = {"mode": mode}
    path = argv[1] if len(argv) > 1 else os.path.join(os.getcwd(), "p12b_probe.json")
    try:
        {"exchange": exchange, "other": other, "unsupported": unsupported}[mode](argv, out)
    except Exception:
        out["traceback"] = traceback.format_exc()
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("BGE-Remix: wrote", path)


main()
