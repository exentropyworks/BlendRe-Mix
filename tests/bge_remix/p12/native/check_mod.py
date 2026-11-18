"""BGE-Remix P12 round 3: a small RTX Remix mod written as File > Export > RTX
Remix Mod writes it (bge_remix_mod_text.py, the exporter's own writer), then
read back through the bridge's OpenUSD (p12_usd_check --dump) and checked.
No Blender: the OpenUSD check on GitHub.

  python check_mod.py write <folder>              <folder>/mod.usda, a texture
  python check_mod.py check <folder> <dump.json>  the dump against what was written

The mod: the room's sphere mesh replaced (the game's switched off) by a box,
a lamp and a small cube added to it (the cube bound to a mod material), the
sphere's material replaced (gold, a texture), a lamp replaced; in
centimetres, Y up (a game's units).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "release", "scripts", "startup", "bl_operators"))
sys.path.insert(0, os.path.dirname(HERE))
import bge_remix_mod_text as mt  # noqa: E402
import capture_writer as cw  # noqa: E402

BOX = [(x, y, z) for x in (-50.0, 50.0) for y in (-20.0, 20.0) for z in (-30.0, 30.0)]
QUADS = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
MOVE = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 10.0, 20.0, 30.0, 1.0]


def the_mod():
    corners = [i for q in QUADS for i in q]
    box = {"points": BOX, "counts": [4] * len(QUADS), "indices": corners,
           "normals": [(0.0, 0.0, 1.0)] * len(corners), "uvs": [(0.5, 0.5)] * len(corners), "double_sided": False}
    small = dict(box, points=[(x / 10.0, y / 10.0, z / 10.0) for x, y, z in BOX], matrix=MOVE,
                 binding="/RootNode/BGE_Remix_Looks/Red")
    return {
        "meters_per_unit": 0.01, "z_up": 0,
        "looks": {"mat_" + cw.MAT["Sphere"]: {
            "mdl": "AperturePBR_Opacity",
            "inputs": [(None, "diffuse_color_constant", (1.0, 0.766, 0.336)), (None, "metallic_constant", 1.0),
                       (None, "reflection_roughness_constant", 0.25), (None, "enable_emission", False),
                       (None, "blend_type", mt.BLEND_ALPHA), (None, "alpha_test_type", mt.ALPHA_TEST_ALWAYS),
                       (None, "filter_mode", 1)],
            "textures": {"diffuse_texture": "./textures/gold.dds"}}},
        "local_looks": {"Red": {"mdl": "AperturePBR_Opacity", "inputs": [(None, "diffuse_color_constant",
                                                                          (1.0, 0.0, 0.0))]}},
        "meshes": {"mesh_" + cw.SPHERE: {
            "preserve": 0, "meshes": {"replacement": box, "SmallCube": small},
            "lights": {"Lamp": {"type": "SphereLight", "shaped": False, "matrix": MOVE,
                                "attrs": [("color3f", "color", (1.0, 1.0, 1.0)), ("float", "intensity", 800.0),
                                          ("float", "radius", 5.0)]}}}},
        "lights": {"light_" + cw.LIGHT_B: {
            "type": "SphereLight", "shaped": True, "matrix": MOVE,
            "attrs": [("color3f", "color", (1.0, 0.5, 0.25)), ("float", "intensity", 300.0),
                      ("float", "radius", 10.0), ("float", "shaping:cone:angle", 30.0),
                      ("float", "shaping:cone:softness", 0.05)]}},
    }


def write(folder):
    os.makedirs(os.path.join(folder, "textures"), exist_ok=True)
    with open(os.path.join(folder, "mod.usda"), "w", newline="\n") as f:
        f.write(mt.mod_text(the_mod()))
    # (any file: the check is that the mod finds it)
    with open(os.path.join(folder, "textures", "gold.dds"), "wb") as f:
        f.write(b"DDS ")
    print("wrote", os.path.join(folder, "mod.usda"))
    return 0


def check(folder, dump_path):
    with open(dump_path) as f:
        dump = json.load(f)
    mod = the_mod()
    bad = mt.check_dump(mod, dump)
    prims = {p["path"]: p for p in dump.get("prims") or ()}

    def attr(path, name):
        return ((prims.get(path) or {}).get("attrs") or {}).get(name) or {}

    sphere = "/RootNode/meshes/mesh_" + cw.SPHERE
    a = attr(sphere, "preserveOriginalDrawCall")
    if a.get("value") != 0:
        bad.append("the sphere's own mesh is not switched off (%s)" % a)
    pts = attr(sphere + "/replacement", "points").get("value") or {}
    if pts.get("count") != 8 or pts.get("bounds") != [[-50, -20, -30], [50, 20, 30]]:
        bad.append("the box's points: %s" % pts)
    shader = "/RootNode/Looks/mat_%s/Shader" % cw.MAT["Sphere"]
    for name, kind in (("inputs:diffuse_color_constant", "color3f"), ("inputs:metallic_constant", "float"),
                       ("inputs:enable_emission", "bool"), ("inputs:blend_type", "uchar"),
                       ("inputs:filter_mode", "uchar")):
        if attr(shader, name).get("type") != kind:
            bad.append("%s is a %s, not a %s" % (name, attr(shader, name).get("type"), kind))
    rel = ((prims.get(sphere + "/SmallCube") or {}).get("rels") or {}).get("material:binding")
    if rel != ["/RootNode/BGE_Remix_Looks/Red"]:
        bad.append("the small cube is bound to %s" % rel)
    lt = (prims.get(sphere + "/Lamp") or {}).get("local_to_world")
    if lt != MOVE:
        bad.append("the lamp's transform is %s" % lt)
    for p in prims:
        if p.startswith("/RootNode/") and p not in mt.expected_prims(mod) and \
                p not in ("/RootNode/Looks", "/RootNode/BGE_Remix_Looks", "/RootNode/meshes", "/RootNode/lights"):
            bad.append("%s was not written" % p)
    for line in bad:
        print("FAIL  " + line)
    print("ok    the mod read back as written" if not bad else "%d problem(s)" % len(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "write":
        sys.exit(write(sys.argv[2]))
    if len(sys.argv) >= 4 and sys.argv[1] == "check":
        sys.exit(check(sys.argv[2], sys.argv[3]))
    print(__doc__)
    sys.exit(2)
