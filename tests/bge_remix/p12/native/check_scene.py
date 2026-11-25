"""BGE-Remix P12 round 6: a scene written as File > Export > Universal Scene
Description writes it (bge_remix_usd_text.py, the exporter's own writer),
read back the way File > Import reads it (p12_usd_check --scene) and
checked; another tool's file and one with what the import does not take
(usd_files.py) read the same way. No Blender: the OpenUSD check on GitHub.

  python check_scene.py write <folder>
      exchange.usda (and its pictures), other_tool.usda, unsupported.usda
  python check_scene.py check <folder>
      the reads in <folder>: exchange.json, exchange_c.json (exchange.usdc,
      converted), other_tool.json, unsupported.json; (round 7)
      physics.json, physics_other.json; (round 8) character.json,
      character_c.json (character.usdc, converted), character_other.json,
      and OpenUSD's own skinning: character_skin.json (/Character/Rig/Body/
      BodyMesh at frame 12), character_other_skin.json (/World/Character/
      Body at frame 15)

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


def physics_scene():
    """(round 7) the exchange scene with physics as the export writes it:
    the table a 12 kg body (a box shape) with its legs as its compound
    pieces (convex hulls, 1 kg each); the box Static (a triangle mesh, its
    materials' friction); the sphere a 3 kg body (a sphere shape) hung from
    the world by a Ball joint, the root of an articulation fixed to the
    world; joints of every kind; gravity 9.81, PhysX on the CPU"""
    sc = the_scene()
    obs = sc["objects"]
    idx = {ob["name"]: i for i, ob in enumerate(obs)}

    def ours(kind, **kw):
        return [("custom string", "bgeRemix:physicsType", kind)] + \
            [("custom float", "bgeRemix:" + k, v) for k, v in sorted(kw.items())]

    sc["materials"][1]["physics"] = {"static_friction": 0.7, "dynamic_friction": 0.7, "restitution": 0.1}
    sc["materials"][2]["physics"] = {"static_friction": 0.4, "dynamic_friction": 0.4, "restitution": 0.6}
    t = idx["Table"]
    obs[t]["physics"] = {"apis": ["PhysicsRigidBodyAPI", "PhysicsMassAPI"],
                         "attrs": [("float", "physics:mass", 12.0)] + ours("RIGID_BODY", mass=12.0),
                         "collider": {"kind": "cube", "half": (0.6, 0.4, 0.025), "center": (0, 0, 0), "material": 1},
                         "joints": []}
    for name in ("Leg", "Leg.002", "Leg.003", "Leg.004"):
        obs[idx[name]]["physics"] = {"apis": [], "attrs": ours("RIGID_BODY", mass=1.0),
                                     "collider": {"kind": "mesh", "approximation": "convexHull", "material": 1,
                                                  "mass": 1.0}}
    b = idx["Box"]
    obs[b]["physics"] = {"apis": [], "attrs": ours("STATIC"),
                         "collider": {"kind": "mesh", "approximation": "none", "material": 2}}
    s = idx["Sphere"]
    q = (1.0, 0.0, 0.0, 0.0)
    obs[s]["physics"] = {
        "apis": ["PhysicsRigidBodyAPI", "PhysicsMassAPI"],
        "attrs": [("float", "physics:mass", 3.0), ("rel", "bgeRemix:idprop:bge_destructible_of", t)] +
        ours("RIGID_BODY", mass=3.0),
        "collider": {"kind": "sphere", "radius": 0.5, "center": (0, 0, 0), "material": 0},
        "joints": [
            {"prim": "PhysicsSphericalJoint", "name": "Hang", "body0": s, "body1": None,
             "attrs": [("point3f", "physics:localPos0", (0.0, 0.0, 0.5)), ("quatf", "physics:localRot0", q),
                       ("point3f", "physics:localPos1", (2.0, -1.0, 1.5)), ("quatf", "physics:localRot1", q),
                       ("uniform token", "physics:axis", "X")]},
            {"prim": "PhysicsSphericalJoint", "name": "Cone", "body0": s, "body1": t,
             "attrs": [("uniform token", "physics:axis", "X"), ("float", "physics:coneAngle0Limit", 30.0),
                       ("float", "physics:coneAngle1Limit", 20.0)]},
            {"prim": "PhysicsRevoluteJoint", "name": "Hinge", "body0": s, "body1": t,
             "attrs": [("uniform token", "physics:axis", "X"), ("float", "physics:lowerLimit", 0.0),
                       ("float", "physics:upperLimit", 100.0)]},
            {"prim": "PhysicsJoint", "name": "Slider", "body0": s, "body1": t,
             "apis": ["PhysicsLimitAPI:transX", "PhysicsLimitAPI:rotX"],
             "attrs": [("float", "limit:transX:physics:low", -0.2), ("float", "limit:transX:physics:high", 0.4),
                       ("float", "limit:rotX:physics:low", 0.0), ("float", "limit:rotX:physics:high", 0.0)]},
            {"prim": "PhysicsFixedJoint", "name": "FixedBase", "body0": None, "body1": s,
             "apis": ["PhysicsArticulationRootAPI"],
             "attrs": [("point3f", "physics:localPos0", (2.0, -1.0, 1.0)), ("quatf", "physics:localRot0", q),
                       ("custom bool", "bgeRemix:articulationBase", True)]}]}
    sc["physics_scene"] = {"attrs": [("vector3f", "physics:gravityDirection", (0.0, 0.0, -1.0)),
                                     ("float", "physics:gravityMagnitude", 9.81),
                                     ("custom string", "bgeRemix:engine", "PHYSX_CPU")]}
    return sc


# -- round 8: a character ------------------------------------------------------

def _rot_x(deg):
    import math
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]


# bone: parent, bind (in the armature's space, USD rows: Blender's
# matrix_local), length
CHAR_BONES = [("Root", None, uf.m_mul(_rot_x(-90.0), move(0.0, 0.0, 1.0)), 0.3),
              ("Spine", 0, uf.m_mul(_rot_x(-90.0), move(0.0, 0.0, 1.3)), 0.4),
              ("Arm.L", 1, uf.m_mul(uf.m_rotate("Z", -90.0), move(0.1, 0.0, 1.6)), 0.5)]
CHAR_ARM = move(1.0, 2.0, 0.0)
CHAR_BODY = move(0.0, 0.0, 0.05)  # the body object, relative to the armature


def _local(tr, q, sc):
    """(translation, w x y z, scale) as USD rows: S R T"""
    w, x, y, z = q
    R = [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y), 0,
         2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x), 0,
         2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y), 0, 0, 0, 0, 1]
    S = [sc[0], 0, 0, 0, 0, sc[1], 0, 0, 0, 0, sc[2], 0, 0, 0, 0, 1]
    return uf.m_mul(uf.m_mul(S, R), move(*tr))


def _pose(f):
    """each bone's (translation, rotation, scale) relative to its parent's
    at frame f (Walk)"""
    import math
    out = []
    for i, (_n, parent, bind, _l) in enumerate(CHAR_BONES):
        rest = bind if parent is None else uf.m_mul(bind, uf.m_inverse(CHAR_BONES[parent][2]))
        a = math.radians(20.0 * math.sin(f / 4.0) * (i + 1))
        turn = (math.cos(a / 2), math.sin(a / 2), 0.0, 0.0)  # about the bone's own X
        L = uf.m_mul(_local((0, 0, 0), turn, (1, 1, 1)), rest)
        tr = (L[12], L[13] + (0.02 * f if i == 0 else 0.0), L[14])
        out.append((tr, uf.quat_of(L), (1.0, 1.0, 1.0)))
    return out


def character_scene():
    """an armature Rig (3 bones, its Walk bound, Wave as well), a body
    skinned to it (two bones a vertex), a cube hung from its Arm.L bone"""
    tokens = ["Root", "Root/Spine", "Root/Spine/Arm_L"]
    bind = [b[2] for b in CHAR_BONES]
    rest = [bind[0]] + [uf.m_mul(b[2], uf.m_inverse(CHAR_BONES[b[1]][2])) for b in CHAR_BONES[1:]]
    walk = [(float(f), [p[0] for p in _pose(f)], [p[1] for p in _pose(f)], [p[2] for p in _pose(f)])
            for f in (1, 6, 12, 18, 24)]
    wave = [(float(f), [p[0] for p in _pose(f * 2)], [p[1] for p in _pose(f * 2)], [p[2] for p in _pose(f * 2)])
            for f in (1, 12)]
    pts, counts, idx = uf.box(0.4, 0.4, 1.0)
    pts = [(x, y, z + 1.4) for x, y, z in pts]
    indices, weights = [], []
    for x, y, z in pts:
        lo = z < 1.4
        indices += [0, 1] if lo else [1, 2]
        weights += [0.75, 0.25] if lo else [0.6, 0.4]
    body = {"name": "BodyMesh", "points": pts, "counts": counts, "indices": idx, "normals": None, "uvs": None,
            "double_sided": False, "material": None,
            "skin": {"armature": 0, "element_size": 2, "indices": indices, "weights": weights,
                     "geom_bind": CHAR_BODY, "method": "classicLinear"}}
    a = {"name": "Rig", "kind": "ARMATURE", "parent": -1, "matrix": CHAR_ARM,
         "skeleton": {"name": "RigData", "joints": tokens, "bind": bind, "rest": rest, "animation": 0,
                      "attrs": [("custom string[]", "bgeRemix:boneNames", [b[0] for b in CHAR_BONES]),
                                ("custom float[]", "bgeRemix:boneLengths", [b[3] for b in CHAR_BONES]),
                                ("custom int[]", "bgeRemix:boneConnect", [0, 1, 0])]},
         "animations": [{"name": "Walk", "joints": tokens, "samples": walk,
                         "attrs": [("custom string", "bgeRemix:action", "Walk")]},
                        {"name": "Wave", "joints": tokens, "samples": wave,
                         "attrs": [("custom string", "bgeRemix:action", "Wave")]}],
         "attrs": [("custom double", "bgeRemix:frame", 1.0)]}
    return {"root": "Character", "materials": [], "time": {"start": 1.0, "end": 24.0, "fps": 24.0},
            "objects": [a,
                        {"name": "Body", "kind": "MESH", "parent": 0, "matrix": CHAR_BODY, "mesh": body},
                        {"name": "Hat", "kind": "MESH", "parent": 0, "matrix": move(0.3, 0.0, 1.9),
                         "mesh": mesh("HatMesh", (0.1, 0.1, 0.1)),
                         "attrs": [("custom string", "bgeRemix:parentBone", "Arm.L")]}]}


def character_skinned(f):
    """the body at frame f in the world as Blender deforms it: the armature
    A, its pose P_i and rest B_i, the body object O: A * sum(w P B^-1) *
    A^-1 * O (here as USD rows)"""
    sc = character_scene()
    walk = sc["objects"][0]["animations"][0]["samples"]
    sample = [s for s in walk if s[0] == f][0]
    J = []
    for i, (_n, parent, _b, _l) in enumerate(CHAR_BONES):
        L = _local(sample[1][i], sample[2][i], sample[3][i])
        J.append(L if parent is None else uf.m_mul(L, J[parent]))
    skin = sc["objects"][1]["mesh"]["skin"]
    O = uf.m_mul(CHAR_BODY, CHAR_ARM)  # the body's world
    G = uf.m_mul(O, uf.m_inverse(CHAR_ARM))
    out = []
    for v, p in enumerate(sc["objects"][1]["mesh"]["points"]):
        q = uf.m_point(G, p)
        acc = [0.0, 0.0, 0.0]
        for k in range(2):
            j, w = skin["indices"][v * 2 + k], skin["weights"][v * 2 + k]
            r = uf.m_point(uf.m_mul(uf.m_inverse(CHAR_BONES[j][2]), J[j]), q)
            acc = [a + w * b for a, b in zip(acc, r)]
        out.append(uf.m_point(CHAR_ARM, acc))
    return out


def character_other_skinned(f):
    """another tool's body at frame f in its own space, skinned by hand
    (USD's rule: rest points * geomBind * sum(w bind^-1 joint) * the
    skeleton's world)"""
    names, bind, rest = uf.character_binds()
    anim, _w = uf.character_frame(f)
    local = dict(rest)
    for (name, _a, _m), (tr, q, sc) in zip(uf.CHARACTER_ANIMATED, anim):
        local[name] = _local(tr, q, sc)
    J = {}
    for name, parent, _p, _t in uf.CHARACTER_JOINTS:
        J[name] = local[name] if parent is None else uf.m_mul(local[name], J[parent])
    pts, _c, _i, joints, weights = uf.character_mesh()
    out = []
    for v, p in enumerate(pts):
        q = uf.m_point(uf.GEOM_BIND, p)
        acc = [0.0, 0.0, 0.0]
        for k in range(4):
            n = names[joints[v * 4 + k]]
            r = uf.m_point(uf.m_mul(uf.m_inverse(bind[n]), J[n]), q)
            acc = [a + weights[v * 4 + k] * b for a, b in zip(acc, r)]
        out.append(uf.m_point(uf.CHARACTER_ROOT, acc))
    return out


def write(folder):
    os.makedirs(os.path.join(folder, "textures"), exist_ok=True)
    uf.png(os.path.join(folder, "textures", "gold.png"), 4, 4, lambda x, y: (255, 200, 80, 255))
    with open(os.path.join(folder, "exchange.usda"), "w") as f:
        f.write(ut.scene_text(the_scene()))
    uf.other_tool(folder)
    uf.unsupported(os.path.join(folder))
    with open(os.path.join(folder, "physics.usda"), "w") as f:
        f.write(ut.scene_text(physics_scene()))
    uf.physics_other(folder)
    with open(os.path.join(folder, "character.usda"), "w") as f:
        f.write(ut.scene_text(character_scene()))
    uf.character_other(folder)
    print("written: exchange.usda, other_tool.usda, unsupported.usda, physics.usda, physics_other.usda, "
          "character.usda, character_other.usda in %s" % folder)
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

    p = load("physics.json")
    result("(round 7) the physics scene read back as written, by OpenUSD's physics reader too",
           ut.check_read(physics_scene(), p))
    ph = p.get("physics") or {}
    bad = []
    custom = ph.get("custom") or {}
    sphere = [k for k in custom if k.endswith("/Sphere")]
    if not sphere or custom[sphere[0]].get("idprop:bge_destructible_of") != ["/Exchange_Room/Furniture/Table"]:
        bad.append("our attributes on the sphere: %s" % (custom.get(sphere[0]) if sphere else sorted(custom)[:5]))
    if not [o for o in ut.objects_from_read(p) if o["name"] == "Sphere"]:
        bad.append("the sphere's collider shape came in as an object of its own")
    if [n for n in p.get("nodes") or () if n["name"] == ut.COLLIDER_NAME]:
        bad.append("a collider shape read as a node")
    if p.get("report"):
        bad.append("reported: %r" % p.get("report"))
    result("(round 7) our attributes read, collider shapes not made objects", bad)

    o = load("physics_other.json")
    ph = o.get("physics") or {}
    bad = []
    if "error" in o:
        bad.append(o["error"])
    else:
        want = uf.PHYSICS_OTHER
        bodies = sorted(b["path"] for b in ph.get("bodies") or ())
        if bodies != sorted(want["bodies"]):
            bad.append("bodies %s, not %s" % (bodies, sorted(want["bodies"])))
        kinds = sorted((j["path"].rsplit("/", 1)[-1], j["kind"]) for j in ph.get("joints") or ())
        if kinds != sorted(want["joints"].items()):
            bad.append("joints %s, not %s" % (kinds, sorted(want["joints"].items())))
        shapes = sorted((sh["path"].rsplit("/", 1)[-1], sh["kind"], sh.get("approximation", ""))
                        for sh in ph.get("shapes") or ())
        if shapes != sorted(want["shapes"]):
            bad.append("shapes %s, not %s" % (shapes, sorted(want["shapes"])))
        roots = [r for a in ph.get("articulations") or () for r in a["roots"]]
        if not roots:
            bad.append("no articulation found")
        if not ph.get("groups"):
            bad.append("no collision group found")
        dens = [b.get("density") for b in ph.get("bodies") or () if b["path"].endswith("/Crate")]
        if len(dens) != 1 or dens[0] is None or abs(dens[0] - want["crate_density"]) > 1e-9:
            bad.append("the crate's density %s, not %s" % (dens, want["crate_density"]))
    result("(round 7) another tool's physics file read by OpenUSD's physics reader", bad)

    # round 8: skeletons
    ch = load("character.json")
    result("(round 8) the character read back as written, by OpenUSD's skeleton reader too",
           ut.check_read(character_scene(), ch))
    cc = load("character_c.json")
    same = []
    if "error" in ch or "error" in cc:
        same.append("not read")
    elif json.dumps(ch.get("skeletons"), sort_keys=True) != json.dumps(cc.get("skeletons"), sort_keys=True):
        same.append("its skeletons differ")
    result("(round 8) the character's .usdc reads the same", same)
    bad = []
    custom = (ch.get("physics") or {}).get("custom") or {}
    sk = custom.get("/Character/Rig/Skeleton") or {}
    if sk.get("boneNames") != ["Root", "Spine", "Arm.L"] or sk.get("boneConnect") != [0, 1, 0] or \
            [round(x, 6) for x in sk.get("boneLengths") or ()] != [0.3, 0.4, 0.5]:
        bad.append("our bone attributes: %s" % sk)
    if (custom.get("/Character/Rig/Hat") or {}).get("parentBone") != "Arm.L":
        bad.append("the hat's bone: %s" % custom.get("/Character/Rig/Hat"))
    if (custom.get("/Character/Rig/Walk") or {}).get("action") != "Walk":
        bad.append("Walk's name: %s" % custom.get("/Character/Rig/Walk"))
    objs = ut.objects_from_read(ch) if "error" not in ch else []
    kinds = [(o["name"], o["kind"], o["parent"]) for o in objs]
    if kinds != [("Rig", "ARMATURE", -1), ("Body", "MESH", 0), ("Hat", "MESH", 0)]:
        bad.append("objects %s" % kinds)
    result("(round 8) our bone attributes, the armature an object with its body and hat under it", bad)
    sk = load("character_skin.json")
    want = character_skinned(12.0)
    got = sk.get("points") or []
    bad = []
    if sk.get("count") != len(want):
        bad.append("%s points skinned, %d in the body" % (sk.get("count"), len(want)))
    else:
        d = max(abs(a - b) for i, p in enumerate(want) for a, b in zip(p, got[i * 3:i * 3 + 3]))
        if d > 1e-5:
            bad.append("%.3g m off Blender's way" % d)
    result("(round 8) OpenUSD skins the body at frame 12 as Blender does", bad)

    o = load("character_other.json")
    bad = []
    if "error" in o:
        bad.append(o["error"])
    else:
        sk = o.get("skeletons") or {}
        s0 = (sk.get("skeletons") or [{}])[0]
        if len(sk.get("skeletons") or ()) != 1 or not s0.get("valid") or len(s0.get("joints") or ()) != 7:
            bad.append("the skeleton: %s" % {k: s0.get(k) for k in ("path", "valid", "problem", "joints")})
        if s0.get("animation") != "/World/Character/Skel/Anim":
            bad.append("its animation %s" % s0.get("animation"))
        sn = (sk.get("skinned") or [{}])[0]
        if sn.get("path") != "/World/Character/Body" or sn.get("element_size") != 4 or not sn.get("blend_shapes"):
            bad.append("the body: %s" % {k: sn.get(k) for k in ("path", "element_size", "blend_shapes")})
        an = (sk.get("animations") or [{}])[0]
        if len(an.get("times") or ()) != 30 or an.get("blend_shapes") != ["Smile"]:
            bad.append("the animation: %d samples, blend shapes %s" % (len(an.get("times") or ()),
                                                                       an.get("blend_shapes")))
        t = sk.get("time") or {}
        if (t.get("start"), t.get("end"), t.get("fps"), t.get("authored")) != (1, 30, 30, True):
            bad.append("frames %s" % t)
        objs = [(x["name"], x["kind"], x["parent"]) for x in ut.objects_from_read(o)]
        if objs != [("World", "XFORM", -1), ("Character", "ARMATURE", 0), ("Body", "MESH", 1)]:
            bad.append("objects %s" % objs)
    result("(round 8) another tool's character read by OpenUSD's skeleton reader", bad)
    sk = load("character_other_skin.json")
    want = character_other_skinned(15)
    got = sk.get("points") or []
    bad = []
    if sk.get("count") != len(want):
        bad.append("%s points skinned, %d in the body" % (sk.get("count"), len(want)))
    else:
        d = max(abs(a - b) for i, p in enumerate(want) for a, b in zip(p, got[i * 3:i * 3 + 3]))
        if d > 1e-3:  # centimetres: 0.01 mm
            bad.append("%.3g cm off the hand skinning" % d)
    result("(round 8) OpenUSD skins another tool's body at frame 15 as worked out by hand", bad)
    print("%d failed" % failed)
    return failed


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "write":
        sys.exit(write(sys.argv[2]))
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        sys.exit(check(sys.argv[2]))
    print(__doc__)
    sys.exit(2)
