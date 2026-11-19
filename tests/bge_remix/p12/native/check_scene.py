"""BGE-Remix P12 round 6: a scene written as File > Export > Universal Scene
Description writes it (bge_remix_usd_text.py, the exporter's own writer),
read back the way File > Import reads it (p12_usd_check --scene) and
checked; another tool's file and one with what the import does not take
(usd_files.py) read the same way. No Blender: the OpenUSD check on GitHub.

  python check_scene.py write <folder>
      exchange.usda (and its pictures), other_tool.usda, unsupported.usda
  python check_scene.py check <folder>
      the reads in <folder>: exchange.json, exchange_c.json (exchange.usdc,
      converted), other_tool.json, unsupported.json

The exchange scene: an empty with a table under it (its top a mesh, four
legs parented to it, one named Leg.001), a two-material box with vertex
colours, a sphere with an RTX Remix material (a picture, metal,
roughness), a point lamp, a spot and a camera.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "release", "scripts", "startup", "bl_operators"))
sys.path.insert(0, os.path.dirname(HERE))
import bge_remix_usd_text as ut  # noqa: E402
import usd_files as uf  # noqa: E402


def move(x, y, z):
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, x, y, z, 1.0]


def mesh(name, size, material=None, subsets=None, colors=False):
    pts, counts, idx = uf.box(*size)
    m = {"name": name, "points": pts, "counts": counts, "indices": idx,
         "normals": [(0.0, 0.0, 1.0)] * len(idx), "uvs": [((i % 4) / 4.0, (i // 4) / 6.0) for i in range(len(idx))],
         "double_sided": False, "material": material, "subsets": subsets}
    if colors:
        m["colors"] = [((i % 3) / 2.0, 0.5, 1.0 - (i % 5) / 4.0) for i in range(len(idx))]
    return m


def the_scene():
    gold = {"name": "Gold.Remix", "preview": {
        "inputs": [("diffuseColor", (1.0, 0.766, 0.336)), ("metallic", 1.0), ("roughness", 0.25), ("opacity", 1.0)],
        "textures": {"diffuseColor": {"file": "./textures/gold.png", "output": "rgb"}}},
        "aperture": {"mdl": "AperturePBR_Opacity",
                     "inputs": [(None, "diffuse_color_constant", (1.0, 0.89, 0.62)), (None, "metallic_constant", 1.0),
                                (None, "reflection_roughness_constant", 0.25)],
                     "textures": {"diffuse_texture": "./textures/gold.png"}}}
    wood = {"name": "Wood", "preview": {"inputs": [("diffuseColor", (0.4, 0.25, 0.1)), ("roughness", 0.6)]}}
    red = {"name": "Red", "preview": {"inputs": [("diffuseColor", (0.8, 0.05, 0.05)), ("roughness", 0.5)]}}
    blue = {"name": "Blue", "preview": {"inputs": [("diffuseColor", (0.05, 0.1, 0.8)), ("roughness", 0.5)]}}
    objects = [
        {"name": "Furniture", "kind": "XFORM", "parent": -1, "matrix": move(1.0, 2.0, 0.0)},
        {"name": "Table", "kind": "MESH", "parent": 0, "matrix": move(0.0, 0.0, 0.75),
         "mesh": mesh("TableTop", (1.2, 0.8, 0.05), material=1)},
    ]
    for i, (x, y) in enumerate(((-0.55, -0.35), (0.55, -0.35), (-0.55, 0.35), (0.55, 0.35))):
        objects.append({"name": "Leg.%03d" % (i + 1) if i else "Leg", "kind": "MESH", "parent": 1,
                        "matrix": move(x, y, -0.375), "mesh": mesh("LegMesh.%d" % i, (0.05, 0.05, 0.7), material=1)})
    objects += [
        {"name": "Box", "kind": "MESH", "parent": -1, "matrix": move(-2.0, 0.0, 0.5),
         "mesh": mesh("BoxMesh", (1.0, 1.0, 1.0), colors=True,
                      subsets=[{"name": "material_0", "faces": [0, 1, 2], "material": 2},
                               {"name": "material_1", "faces": [3, 4, 5], "material": 3}])},
        {"name": "Sphere", "kind": "MESH", "parent": -1, "matrix": move(2.0, -1.0, 1.0),
         "mesh": mesh("SphereMesh", (1.0, 1.0, 1.0), material=0)},
        {"name": "Point", "kind": "LIGHT", "parent": -1, "matrix": move(0.0, 0.0, 3.0),
         "light": {"type": "SphereLight", "attrs": [("color3f", "color", (1.0, 0.9, 0.8)),
                                                   ("float", "intensity", 2500.0), ("float", "radius", 0.1)]}},
        {"name": "Spot", "kind": "LIGHT", "parent": -1, "matrix": move(3.0, 3.0, 4.0), "light": {
            "type": "SphereLight", "shaped": True,
            "attrs": [("color3f", "color", (1.0, 1.0, 1.0)), ("float", "intensity", 4000.0),
                      ("float", "radius", 0.05), ("float", "shaping:cone:angle", 30.0),
                      ("float", "shaping:cone:softness", 0.1)]}},
        {"name": "Camera", "kind": "CAMERA", "parent": -1, "matrix": move(0.0, -8.0, 2.0),
         "camera": {"focal_length": 35.0, "horizontal_aperture": 32.0, "vertical_aperture": 18.0,
                    "clipping": (0.1, 100.0)}},
    ]
    return {"root": "Exchange Room", "objects": objects, "materials": [gold, wood, red, blue]}


def write(folder):
    os.makedirs(os.path.join(folder, "textures"), exist_ok=True)
    uf.png(os.path.join(folder, "textures", "gold.png"), 4, 4, lambda x, y: (255, 200, 80, 255))
    with open(os.path.join(folder, "exchange.usda"), "w") as f:
        f.write(ut.scene_text(the_scene()))
    uf.other_tool(folder)
    uf.unsupported(os.path.join(folder))
    print("written: exchange.usda, other_tool.usda, unsupported.usda in %s" % folder)
    return 0


def check(folder):
    failed = 0

    def result(name, bad):
        nonlocal failed
        print("%s  %s" % ("ok   " if not bad else "FAIL ", name))
        for line in bad:
            print("        " + line)
        failed += 1 if bad else 0

    def load(name):
        try:
            return json.load(open(os.path.join(folder, name)))
        except (OSError, ValueError) as e:
            return {"error": "%s: %s" % (name, e)}

    scene = the_scene()
    a = load("exchange.json")
    result("exchange.usda read back as written", ut.check_read(scene, a))
    c = load("exchange_c.json")
    result("exchange.usdc (converted) read back as written", ut.check_read(scene, c))
    same = []
    if "error" in a or "error" in c:
        same.append("not read")
    else:
        for key in ("nodes", "meshes", "materials", "lights", "cameras"):
            if json.dumps(a[key], sort_keys=True) != json.dumps(c[key], sort_keys=True):
                same.append("its %s differ" % key)
    result("the .usdc reads the same as the .usda", same)

    o = load("other_tool.json")
    bad = []
    if "error" in o:
        bad.append(o["error"])
    else:
        if abs(o["meters_per_unit"] - 0.01) > 1e-12 or o["z_up"]:
            bad.append("not read as centimetres, Y up")
        if o.get("usd_errors") or o.get("report"):
            bad.append("reported: %r" % o.get("report"))
        obs = ut.objects_from_read(o)
        names = [ob["name"] for ob in obs]
        want = [w[0] for w in uf.OTHER_TOOL_OBJECTS]
        if names != want:
            bad.append("objects %s, not %s" % (names, want))
        else:
            for ob, (name, kind, parent, place) in zip(obs, uf.OTHER_TOOL_OBJECTS):
                p = obs[ob["parent"]]["name"] if ob["parent"] >= 0 else None
                if ob["kind"] != kind or p != parent:
                    bad.append("%s: a %s under %s, not a %s under %s" % (name, ob["kind"], p, kind, parent))
                got = uf.to_blender(ob["matrix"][12:15], o["meters_per_unit"], o["z_up"])
                if max(abs(x - y) for x, y in zip(got, place)) > 1e-4:
                    bad.append("%s at %s, not %s" % (name, got, place))
            pots = [o["nodes"][ob["data_node"]]["index"] for ob in obs if ob["name"].startswith("Pot_")]
            if len(pots) != 2 or pots[0] != pots[1]:
                bad.append("the pots do not share one mesh (%s)" % pots)
            board = o["nodes"][[ob for ob in obs if ob["name"] == "Board"][0]["data_node"]]
            me = o["meshes"][board["index"]]
            if not me["uvs"] or me["uvs"][0:8] != [0, 0, 1, 0, 1, 1, 0, 1]:
                bad.append("the board's indexed UVs read as %s" % (me["uvs"] or [])[0:8])
            wood = o["materials"][board["material"]] if board["material"] >= 0 else {}
            tex = (wood.get("preview_inputs") or {}).get("diffuseColor") or {}
            if not wood.get("preview") or not tex.get("exists") or tex.get("output") != "rgb":
                bad.append("the wood's picture not found (%r)" % tex)
            if len(o["lights"]) != 1 or len(o["cameras"]) != 1:
                bad.append("%d lights, %d cameras" % (len(o["lights"]), len(o["cameras"])))
    result("another tool's file (cm, Y up, instanced) read", bad)

    u = load("unsupported.json")
    bad = []
    if "error" in u:
        bad.append(u["error"])
    else:
        for want in uf.UNSUPPORTED_REPORT:
            if want not in u["report"]:
                bad.append("%r not in the report" % want)
        meshes = [ob["name"] for ob in ut.objects_from_read(u) if ob["kind"] == "MESH"]
        if sorted(meshes) != sorted(["Floor", "Lift"]):
            bad.append("meshes %s came in" % meshes)
    result("what is not imported is named; the rest read", bad)
    print("%d failed" % failed)
    return failed


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "write":
        sys.exit(write(sys.argv[2]))
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        sys.exit(check(sys.argv[2]))
    print(__doc__)
    sys.exit(2)
