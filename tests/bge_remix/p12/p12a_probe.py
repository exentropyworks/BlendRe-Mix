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
"""

import json
import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "p2"))

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


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode = argv[0]
    out = {"mode": mode}
    try:
        if mode == "selftest":
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
