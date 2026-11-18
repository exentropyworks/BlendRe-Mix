"""BGE-Remix P12 Part A: run inside our Blender (background) by p12a_tests.py.

argv (after --):
  selftest <folder> <out.json>
      the bridge's OpenUSD self-test (_bge_remix.usd_selftest)
  import <capture> <out.json> [<save.blend>]
      File > Import > RTX Remix Capture (the operator), then what came in
      written out: the scene's marks, objects, meshes, materials (their RTX
      Remix node's values, textures and kept inputs), images (the decoded
      textures' top rows), lamps and camera. With save.blend: the imported
      scene alone saved to play (with Remix on, a probe and the room's
      world).
  export <capture> <out.json> <mod folder> <edits> [<sphere place> <wall place>]
      (round 3) the capture imported, edited by script, then File > Export >
      RTX Remix Mod (the operator) into <mod folder>; written out: the
      result, the export's report and counts, the mod read back with the
      bridge's OpenUSD (its stage dump), what the edits were, and the DDS
      textures written decoded (their top and bottom rows). edits:
        room     the sphere's mesh a bevelled box, its material gold, a lamp
                 and a small cube parented to it, a wall moved
        none     nothing changed
        texture  the box's picture painted (top half red, bottom half blue)
        plain    no import: a scene of its own, not from a capture
"""

import json
import math
import os
import shutil
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "p2"))
sys.path.insert(0, HERE)

NODE_INPUTS = ("Albedo", "Opacity", "Roughness", "Metallic", "Emissive Color", "Emissive Intensity", "IOR",
               "Transmittance", "Transmittance Distance", "Anisotropy", "Thin Film")


def mat_list(m):
    return [list(row) for row in m]


def value(sock):
    v = sock.default_value
    try:
        return list(v)
    except TypeError:
        return float(v)


def top_rows(ima, rows=2):
    """the image's top rows (Blender keeps rows from the bottom), 0..255"""
    w, h = ima.size
    px = list(ima.pixels)
    out = []
    for r in range(rows):
        y = h - 1 - r
        for x in range(w):
            i = (y * w + x) * 4
            out.append([int(round(c * 255.0)) for c in px[i:i + 4]])
    return out


def as_dict(prop):
    """an ID property group (or nothing) as a plain dict"""
    if prop is None:
        return {}
    return prop.to_dict() if hasattr(prop, "to_dict") else dict(prop)


def dump_scene(scene):
    d = {"name": scene.name, "capture": as_dict(scene.get("bge_remix_capture")),
         "counts": as_dict(scene.get("bge_remix_capture_counts")),
         "pipeline": scene.get("bge_remix_pipeline"),
         "camera": scene.camera.name if scene.camera else None, "objects": {}, "meshes": {}, "materials": {},
         "images": {}, "lamps": {}}
    for ob in scene.objects:
        o = {"type": ob.type, "data": ob.data.name if ob.data else None, "matrix": mat_list(ob.matrix_world),
             "hash": ob.get("bge_remix_capture_hash"), "mesh_hash": ob.get("bge_remix_capture_mesh"),
             "hide": ob.hide}
        if ob.type == 'MESH' and ob.material_slots:
            s = ob.material_slots[0]
            o["material"] = s.material.name if s.material else None
            o["material_link"] = s.link
        d["objects"][ob.name] = o
        if ob.type == 'MESH' and ob.data.name not in d["meshes"]:
            me = ob.data
            d["meshes"][me.name] = {"vertices": len(me.vertices), "polygons": len(me.polygons),
                                   "loops": len(me.loops), "uv": len(me.uv_layers) > 0,
                                   "custom_normals": bool(me.has_custom_normals),
                                   "hash": me.get("bge_remix_capture_hash"), "users": me.users}
        if ob.type == 'MESH':
            for s in ob.material_slots:
                ma = s.material
                if ma is None or ma.name in d["materials"]:
                    continue
                node = next((n for n in ma.node_tree.nodes if n.bl_idname == "ShaderNodeRemixMaterial"), None) \
                    if ma.node_tree else None
                m = {"hash": ma.get("bge_remix_capture_hash"), "mdl": ma.get("bge_remix_capture_mdl"),
                     "kept": as_dict(ma.get("bge_remix_capture_inputs")), "remix": node is not None}
                if node:
                    m["remix_type"] = node.remix_type
                    m["blend"] = node.blend
                    m["thin_walled"] = node.use_thin_walled
                    m["values"] = {n: value(node.inputs[n]) for n in NODE_INPUTS if n in node.inputs}
                    m["linked"] = {}
                    for inp in node.inputs:
                        if inp.is_linked:
                            src = inp.links[0].from_node
                            tex = getattr(src, "texture", None)
                            ima = getattr(tex, "image", None) if tex else None
                            m["linked"][inp.name] = {"node": src.bl_idname,
                                                    "image": ima.name if ima else None,
                                                    "dds": tex.get("bge_remix_capture_dds") if tex else None}
                            if ima and ima.name not in d["images"]:
                                d["images"][ima.name] = {"file": bpy.path.abspath(ima.filepath),
                                                         "size": list(ima.size), "top": top_rows(ima),
                                                         "dds": ima.get("bge_remix_capture_dds")}
                d["materials"][ma.name] = m
        if ob.type == 'LAMP':
            la = ob.data
            d["lamps"][ob.name] = {"type": la.type, "energy": la.energy, "color": list(la.color),
                                   "distance": la.distance, "soft": la.shadow_soft_size,
                                   "spot_size": getattr(la, "spot_size", None),
                                   "spot_blend": getattr(la, "spot_blend", None),
                                   "physical": la.get("bge_physical"), "hash": la.get("bge_remix_capture_hash"),
                                   "matrix": mat_list(ob.matrix_world)}
        if ob.type == 'CAMERA':
            cd = ob.data
            d["camera_data"] = {"name": ob.name, "lens": cd.lens, "sensor_width": cd.sensor_width, "sensor_fit": cd.sensor_fit,
                                "clip": [cd.clip_start, cd.clip_end], "matrix": mat_list(ob.matrix_world)}
    return d


def save_to_play(scene, path):
    import make_scenes_p2 as p2
    for win in bpy.context.window_manager.windows:
        win.screen.scene = scene
    for sc in list(bpy.data.scenes):
        if sc != scene:
            bpy.data.scenes.remove(sc, do_unlink=True)
    scene["bge_remix"] = 1
    scene.game_settings.material_mode = 'GLSL'
    scene.game_settings.fps = 60
    p2.world(scene, (0.05, 0.05, 0.06))
    p2.add_probe(scene)
    scene.update()
    bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, compress=False)


def _parent(ob, parent, world):
    """ob under parent, at world (Blender's matrices)"""
    from mathutils import Matrix
    ob.parent = parent
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.matrix_basis = parent.matrix_world.inverted() * world


def edit_room(scene, sphere_place, wall_place):
    """the round 3 edits; what they were (Blender's space)"""
    import bmesh
    from mathutils import Matrix
    from bl_operators.bge_remix_material import make_remix_material, remix_node
    places = {ob.get("bge_remix_capture_place"): ob for ob in scene.objects}
    sphere, wall = places[sphere_place], places[wall_place]
    info = {"sphere_matrix": mat_list(sphere.matrix_world)}
    # the sphere's mesh: a bevelled box, 1 x 0.6 x 0.4, its UVs from its
    # place (x, y)
    me = sphere.data
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(1.0, 0.6, 0.4), verts=bm.verts[:])
    bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:], offset=0.05, segments=2, vertex_only=False)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for l in f.loops:
            l[uv].uv = (l.vert.co.x + 0.5, l.vert.co.y / 0.6 + 0.5)
    bm.to_mesh(me)
    bm.free()
    me.update()
    info["box"] = {"vertices": len(me.vertices), "polygons": len(me.polygons), "loops": len(me.loops),
                   "half": [0.5, 0.3, 0.2]}
    # its material: gold
    mat = sphere.material_slots[0].material
    node = remix_node(mat)
    node.inputs["Albedo"].default_value = (1.0, 0.766, 0.336, 1.0)
    node.inputs["Metallic"].default_value = 1.0
    node.inputs["Roughness"].default_value = 0.25
    node.inputs["Emissive Intensity"].default_value = 0.0
    info["gold"] = {"material": mat.name, "albedo": [1.0, 0.766, 0.336], "metallic": 1.0, "roughness": 0.25}
    # a lamp and a small cube (its own red material) under the sphere
    la = bpy.data.lamps.new("ModLamp", 'POINT')
    la.energy = 2.0
    la.distance = 1.0
    la.shadow_soft_size = 0.05
    la["bge_physical"] = 1.0
    lamp = bpy.data.objects.new("ModLamp", la)
    scene.objects.link(lamp)
    cme = bpy.data.meshes.new("ModCube")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.1)
    bm.to_mesh(cme)
    bm.free()
    red = bpy.data.materials.new("BGE_Red")
    rnode = make_remix_material(red)
    rnode.inputs["Albedo"].default_value = (1.0, 0.0, 0.0, 1.0)
    cme.materials.append(red)
    cube = bpy.data.objects.new("ModCube", cme)
    scene.objects.link(cube)
    lamp_world = Matrix.Translation((0.8, 1.2, 1.0))
    cube_world = Matrix.Translation((0.8, 1.2, 0.85)) * Matrix.Rotation(math.radians(30.0), 4, 'Z')
    _parent(lamp, sphere, lamp_world)
    _parent(cube, sphere, cube_world)
    # a wall moved (a mod cannot carry it)
    wall.location.x += 0.5
    scene.update()
    info["lamp"] = {"name": lamp.name, "world": mat_list(lamp.matrix_world), "energy": 2.0, "distance": 1.0,
                    "radius": 0.05}
    info["cube"] = {"name": cube.name, "world": mat_list(cube.matrix_world), "material": red.name,
                    "vertices": len(cme.vertices), "half": 0.05}
    info["wall"] = wall.name
    return info


def paint_box(scene, box_material_hash):
    """the box's picture painted: top half red, bottom half blue"""
    mat = next(m for m in bpy.data.materials if m.get("bge_remix_capture_hash") == box_material_hash)
    ima = None
    for n in mat.node_tree.nodes:
        tex = getattr(n, "texture", None)
        if tex is not None and getattr(tex, "image", None) is not None:
            ima = tex.image
    w, h = ima.size
    px = []
    for y in range(h):
        c = (1.0, 0.0, 0.0, 1.0) if y >= h // 2 else (0.0, 0.0, 1.0, 1.0)
        px.extend(c * w)
    ima.pixels = px
    return {"material": mat.name, "image": ima.name, "size": [w, h], "dirty": ima.is_dirty}


def decoded(folder):
    """the mod's DDS textures decoded: their top and bottom rows"""
    import _bge_remix
    out = {}
    tex = os.path.join(folder, "textures")
    for name in sorted(os.listdir(tex)) if os.path.isdir(tex) else ():
        if not name.lower().endswith(".dds"):
            continue
        png = os.path.join(folder, name + ".png")
        ok, err = _bge_remix.dds_to_png(os.path.join(tex, name), png)
        d = {"ok": ok, "error": err}
        if ok:
            ima = bpy.data.images.load(png)
            w, h = ima.size
            d["size"] = [w, h]
            d["top"] = top_rows(ima, 1)
            px = list(ima.pixels)
            d["bottom"] = [[int(round(c * 255.0)) for c in px[x * 4:x * 4 + 4]] for x in range(w)]
        out[name] = d
    return out


def export(argv, out):
    import _bge_remix
    from bl_operators import bge_remix_mod
    capture, folder, edits = argv[1], argv[3], argv[4]
    shutil.rmtree(folder, ignore_errors=True)
    if edits == "plain":
        scene = bpy.data.scenes.new("Plain")
    else:
        before = set(bpy.data.scenes.keys())
        bpy.ops.import_scene.bge_remix_capture(filepath=capture)
        scene = [bpy.data.scenes[n] for n in bpy.data.scenes.keys() if n not in before][0]
    if edits == "room":
        out["edits"] = edit_room(scene, argv[5], argv[6])
    elif edits == "texture":
        import capture_writer as cw
        out["edits"] = paint_box(scene, cw.MAT["Box"])
    try:
        ret = bpy.ops.export_scene.bge_remix_mod({"scene": scene}, directory=folder)
        out["result"] = sorted(ret)
    except RuntimeError as e:
        out["result"] = ["CANCELLED"]
        out["error"] = str(e)
    out["last"] = {"report": list(bge_remix_mod.LAST.get("report") or []), "path": bge_remix_mod.LAST.get("path"),
                   "counts": bge_remix_mod.LAST.get("counts")}
    out["folder_exists"] = os.path.isdir(folder)
    mod = os.path.join(folder, "mod.usda")
    if os.path.isfile(mod):
        dump = os.path.join(folder + "_dump.json")
        ok, err = _bge_remix.usd_dump(mod, dump)
        out["dump_ok"], out["dump_error"] = ok, err
        if ok:
            with open(dump) as f:
                out["dump"] = json.load(f)
        out["textures"] = decoded(folder)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode = argv[0]
    out = {"mode": mode}
    try:
        if mode == "export":
            path = argv[2]
            export(argv, out)
        elif mode == "selftest":
            import _bge_remix
            os.makedirs(argv[1], exist_ok=True)
            failed, report, version = _bge_remix.usd_selftest(argv[1])
            out.update({"failed": failed, "report": report, "version": version})
            path = argv[2]
        else:
            path = argv[2]
            before = set(bpy.data.scenes.keys())
            try:
                ret = bpy.ops.import_scene.bge_remix_capture(filepath=argv[1])
                out["result"] = sorted(ret)
            except RuntimeError as e:
                out["result"] = ["CANCELLED"]
                out["error"] = str(e)
            new = [bpy.data.scenes[n] for n in bpy.data.scenes.keys() if n not in before]
            if new:
                out["scene"] = dump_scene(new[0])
                if len(argv) > 3:
                    save_to_play(new[0], argv[3])
                    out["saved"] = argv[3]
    except Exception:
        out["traceback"] = traceback.format_exc()
        path = argv[2] if len(argv) > 2 else os.path.join(os.getcwd(), "p12a_probe.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("BGE-Remix: wrote", path)


main()
