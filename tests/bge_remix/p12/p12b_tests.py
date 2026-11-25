"""BGE-Remix P12 Part B: USD exchange with other tools (run_p12.py's track
p12b). Round 6: File > Export and File > Import > Universal Scene
Description, scenes by script only (p12b_probe.py says what is in them).

T12.d1  The exchange room, out and back: the room exported as .usda and
        imported into an emptied file: every object back with its name,
        parent and place (0.1 mm); each mesh with its counts, UVs, colours
        and the split between its two materials; the RTX Remix materials'
        values and picture back, the Classic ones as their preview surface;
        each lamp the same Remix light, the camera its lens.
T12.d2  Checked by the standard: OpenUSD finds a UsdPreviewSurface for
        every material and AperturePBR for the RTX Remix ones; the file
        opens with no complaint; the .usdc reads the same as the .usda, and
        imports the same.
T12.d3  Another tool's file (usd_files.py: centimetres, Y up, nested
        transforms, an instanced reference, UVs with indices, a picture, a
        light, a camera) comes in upright and to scale (0.1 mm, in metres),
        the instances sharing one mesh.
T12.d4  What is not imported (a custom shader, curves, a point instancer)
        is named in the report, the rest comes in, nothing crashes.

Round 7 (physics; p12b_probe.py's physics room):
T12.e1  The physics room, out and back: every object's physics (its kind,
        mass, bounds, margin, damping, Ghost, compound, locks, material
        friction and bounce, articulation root, P11's destructible and fluid
        settings) and every joint (its kind, target, pivot and axis within
        0.1 mm and 0.01 degrees, limits, linked collision) back as they
        were; the world's gravity and engine.
T12.e2  Checked by the standard: OpenUSD's own physics reader finds the
        room's bodies, shapes (their kinds), joints (their kinds), physics
        materials, articulation root and gravity, with no complaint; the
        .usdc reads the same, and imports the same.
T12.e3  It plays the same: the room and the room imported each run 2 s
        (PhysX on the CPU, one step a frame): every moving body ends within
        1 cm and 1 degree of where the room's did.
T12.e4  Another tool's physics file (usd_files.physics_other: centimetres,
        Y up): its bodies, masses (one from its density), shapes, joints
        (their axes and pivots in the world, their limits) and the robot
        arm's articulation fixed to the world come in; the distance joint,
        the collision group and the convex decomposition are named.

Round 8 (armatures; p12b_probe.py's character):
T12.f1  The character, out and back: every bone back with its name, parent,
        head, tail and roll (0.1 mm, 0.01 degrees); every vertex with its
        groups and weights; both actions, every bone's pose the same at
        every frame; the body deformed the same at frames 1, 12 and 24
        (0.1 mm); the ragdoll's capsules back on their bones, with their
        physics and joints.
T12.f2  Checked by the standard: OpenUSD's own skeleton reader finds the
        skeleton valid (its joints and their order), the body bound to it,
        the animation's frames; OpenUSD's own skinning of the body at frame
        12 within 1 mm of Blender's; the .usdc reads the same.
T12.f3  Another tool's character (usd_files.character_other: Maya's way, Y
        up, centimetres, 30 frames a second, joints with no length, 4 bones
        a vertex, a blend shape) comes in upright and to scale, the bones
        reaching to their children; at frames 1, 15 and 30 its deformed
        body within 1 mm of OpenUSD's own skinning; the blend shape named.
T12.f4  It plays the same: the character and the character imported each
        play Walk in the game for 1 s (an Action actuator): every bone at
        tics 30 and 60 within 0.1 mm and 0.01 degrees of the original's.
T12.f5  The Remix View marks what came from USD (a window run, the physics
        layer): the physics room imported and another tool's physics file:
        every body and joint says it came from USD (each body its place in
        the file), the other tool's crate shows its note (its convex
        decomposition came in as a Convex Hull); the room made in Blender
        has no such mark.

BGE_REMIX_P12B_ONLY (comma separated: exchange, other, unsupported, physics,
play, physicsother, character, characterother, characterplay, usdview; d1
and d2 come from exchange, e1 and e2 from physics, f1 and f2 from
character; e3 needs physics run first in the same run, f4 character) runs
only those (a fix round's reruns). No RTX run this round.
"""

import math
import os
import sys

import run_p2 as p2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import usd_files as uf  # noqa: E402

PROBE = os.path.join(HERE, "p12b_probe.py")
PLACE_TOL = 1e-4      # 0.1 mm
VALUE_TOL = 1e-4


def _test(c, d=None):
    return {"ok": all(c.values()) and bool(c), "checks": c, "detail": d}


def _only():
    return [t.strip() for t in os.environ.get("BGE_REMIX_P12B_ONLY", "").split(",") if t.strip()]


def blender(args, out, tag, argv, timeout=900):
    res = argv[1]
    if os.path.isfile(res):
        os.remove(res)
    code, text, _ = p2.run([p2.exe(args.ours, "blender"), "--background", "--factory-startup", "--python", PROBE,
                            "--"] + argv, p2.base_env(out, tag), os.path.join(out, tag + ".log"), timeout=timeout)
    got = p2.read_json(res) or {}
    got["exit"] = code
    return got


def near(a, b, tol=VALUE_TOL):
    if a is None or b is None:
        return False
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(near(x, y, tol) for x, y in zip(a, b))
    return abs(float(a) - float(b)) <= tol


def mdiff(a, b):
    """the largest differences of two 4 x 4 matrices: (place, turn)"""
    if not a or not b:
        return 1e9, 1e9
    place = max(abs(a[r][3] - b[r][3]) for r in range(3))
    turn = max(abs(a[r][c] - b[r][c]) for r in range(3) for c in range(3))
    return place, turn


def rel_near(a, b, tol=1e-3):
    if isinstance(a, (list, tuple)):
        return isinstance(b, (list, tuple)) and len(a) == len(b) and all(rel_near(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return a == b


TYPES = {"XFORM": "EMPTY", "MESH": "MESH", "LIGHT": "LAMP", "CAMERA": "CAMERA"}


def hardness_to_roughness(har):
    return (2.0 / (max(har, 1.0) + 2.0)) ** 0.25


def check_room(c, want, got, label):
    """the room as it went out (want) against what came in (got: the
    import's result)"""
    scene = got.get("scene") or {}
    W, G = want.get("objects") or {}, scene.get("objects") or {}
    c["%s: imported (%s), %d objects (want %d)" % (label, got.get("result"), len(G), len(W))] = \
        got.get("result") == ["FINISHED"] and len(G) == len(W) and len(W) > 0
    missing = sorted(n for n in W if n not in G)
    c["%s: every object back by its name%s" % (label, ": missing " + ", ".join(missing) if missing else "")] = \
        not missing
    wrong = []
    for n, w in sorted(W.items()):
        g = G.get(n)
        if g is None:
            continue
        place, turn = mdiff(w["matrix"], g["matrix"])
        if g["type"] != w["type"] or g["parent"] != w["parent"] or place > PLACE_TOL or turn > 1e-4:
            wrong.append("%s (%s under %s, %.2g m / %.2g off)" % (n, g["type"], g["parent"], place, turn))
    c["%s: each a %s, under its parent, in its place within 0.1 mm%s" % (
        label, "/".join(sorted(set(w["type"] for w in W.values()))), ": " + "; ".join(wrong) if wrong else "")] = \
        not wrong and not missing
    # meshes
    bad = []
    for n, w in sorted(W.items()):
        g = G.get(n) or {}
        if w["type"] != 'MESH':
            continue
        wm, gm = w.get("mesh") or {}, g.get("mesh") or {}
        counts = [(wm.get(k), gm.get(k)) for k in ("vertices", "polygons", "loops")]
        if any(a != b for a, b in counts):
            bad.append("%s counts %s" % (n, counts))
        if not near(wm.get("uv"), gm.get("uv"), 1e-5):
            bad.append("%s UVs" % n)
        if wm.get("colors") and not near(wm.get("colors"), gm.get("colors"), 1.5 / 255.0):
            bad.append("%s colours %s / %s" % (n, wm.get("colors", [])[:2], (gm.get("colors") or [])[:2]))
        if wm.get("face_materials") != gm.get("face_materials"):
            bad.append("%s face materials %s / %s" % (n, wm.get("face_materials"), gm.get("face_materials")))
    c["%s: each mesh (modifiers applied) with its counts, UVs, colours and its faces' materials%s" % (
        label, ": " + "; ".join(bad) if bad else "")] = not bad and not missing
    box = (G.get("Box") or {}).get("mesh") or {}
    fm = box.get("face_materials") or []
    c["%s: the box split between BoxRed (%d faces) and BoxBlue (%d)" % (
        label, fm.count("BoxRed"), fm.count("BoxBlue"))] = fm.count("BoxRed") == 5 and fm.count("BoxBlue") == 1
    # materials
    WM, GM = want.get("materials") or {}, scene.get("materials") or {}
    bad = []
    for name in ("Gold", "Wood"):
        w, g = WM.get(name) or {}, GM.get(name) or {}
        for k in ("Albedo", "Roughness", "Metallic", "Opacity", "Emissive Intensity"):
            wv, gv = (w.get("values") or {}).get(k), (g.get("values") or {}).get(k)
            if isinstance(wv, list):
                wv, gv = wv[:3], (gv or [])[:3]
            if not near(wv, gv, 1e-4):
                bad.append("%s %s %s / %s" % (name, k, wv, gv))
        if not g.get("remix") or g.get("blend") != w.get("blend") or g.get("marks"):
            bad.append("%s: remix %s, blend %s, marks %s" % (name, g.get("remix"), g.get("blend"), g.get("marks")))
    gl = ((GM.get("Gold") or {}).get("linked") or {}).get("Albedo") or {}
    pic = gl.get("pixel")
    c["%s: the RTX Remix materials' values exact%s" % (label, ": " + "; ".join(bad) if bad else "")] = \
        not bad and "Gold" in GM and "Wood" in GM
    c["%s: Gold's picture back on its Albedo (%s, %s, first pixel %s)" % (
        label, gl.get("file") and os.path.basename(gl.get("file")), gl.get("size"), pic)] = \
        bool(gl.get("file")) and gl.get("size") == [8, 8] and bool(pic) and \
        all(abs(pic[k] - [255, 200, 80, 255][k]) <= 1 for k in range(4)) and \
        os.path.basename(os.path.dirname(gl.get("file") or "")) == "textures"
    bad = []
    for name in ("FloorGrey", "Classic Blue", "BoxRed", "BoxBlue"):
        w, g = WM.get(name) or {}, GM.get(name) or {}
        if not w:
            bad.append("%s not in the room" % name)
            continue
        alb = [x * w["diffuse_intensity"] for x in w["diffuse"]]
        gv = g.get("values") or {}
        if not g.get("remix") or not near(alb, (gv.get("Albedo") or [])[:3], 1e-4) or \
                not near(hardness_to_roughness(w["hardness"]), gv.get("Roughness"), 1e-4):
            bad.append("%s: %s / albedo %s roughness %s" % (name, g.get("remix"), gv.get("Albedo"),
                                                            gv.get("Roughness")))
    c["%s: the Classic materials as their preview surface (colour times intensity, roughness from hardness)%s" % (
        label, ": " + "; ".join(bad) if bad else "")] = not bad
    # lamps and the camera
    bad = []
    for n, w in sorted(W.items()):
        if w["type"] != 'LAMP':
            continue
        g = G.get(n) or {}
        wl, gl = w.get("light") or {}, g.get("light") or {}
        if not wl or wl.get("type") != gl.get("type") or \
                not all(rel_near(v, (gl.get("attrs") or {}).get(k)) for k, v in (wl.get("attrs") or {}).items()):
            bad.append("%s: %s / %s" % (n, wl, gl))
    c["%s: each lamp gives the same Remix light (point, spot, sun, area)%s" % (
        label, ": " + "; ".join(bad) if bad else "")] = not bad and \
        sum(1 for w in W.values() if w["type"] == 'LAMP') == 4
    wc, gc = (W.get("Camera") or {}).get("camera") or {}, (G.get("Camera") or {}).get("camera") or {}
    c["%s: the camera's lens %s, sensor %s, clipping %s" % (label, gc.get("lens"), gc.get("sensor_width"),
                                                          gc.get("clip"))] = \
        bool(wc) and near(wc.get("lens"), gc.get("lens")) and near(wc.get("sensor_width"), gc.get("sensor_width")) \
        and near(wc.get("clip"), gc.get("clip"), 1e-5) and scene.get("camera") == "Camera"
    c["%s: nothing reported (%d note(s))" % (label, len(got.get("report") or []))] = not got.get("report")


def t_exchange(args, out, tests):
    folder = os.path.join(out, "p12b_exchange")
    got = blender(args, out, "p12b_exchange", ["exchange", os.path.join(out, "p12b_exchange_probe.json"), folder])
    want = got.get("want") or {}
    ea, ec = got.get("export_usda") or {}, got.get("export_usdc") or {}

    c = {}
    counts = ea.get("counts") or {}
    c["exported as .usda (%s; %s objects, %s meshes, %s materials, %s lamps, %s cameras, %s pictures)" % (
        ea.get("result"), counts.get("objects"), counts.get("meshes"), counts.get("materials"), counts.get("lamps"),
        counts.get("cameras"), counts.get("pictures"))] = \
        ea.get("result") == ["FINISHED"] and ea.get("exists") and counts.get("objects") == 15 and \
        counts.get("meshes") == 9 and counts.get("materials") == 6 and counts.get("lamps") == 4 and \
        counts.get("cameras") == 1
    c["the picture copied beside it (%s)" % ", ".join(got.get("textures") or [])] = \
        "gold.png" in (got.get("textures") or [])
    c["nothing left out by the export (%d note(s))" % len(ea.get("report") or [])] = not ea.get("report")
    check_room(c, want, got.get("got_usda") or {}, ".usda")
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.d1 The exchange room, out and back"] = _test(c, {
        "export": ea, "report": (got.get("got_usda") or {}).get("report"),
        "error": (got.get("got_usda") or {}).get("error"), "traceback": got.get("traceback")})

    c = {}
    ra, rc = got.get("read_usda") or {}, got.get("read_usdc") or {}
    mats = ra.get("materials") or []
    c["the .usda opens with no complaint (OpenUSD: %s, report %r)" % (ra.get("usd_errors"), ra.get("report"))] = \
        "error" not in ra and ra.get("usd_errors") == 0 and not ra.get("report")
    no_preview = [m["name"] for m in mats if not m.get("preview")]
    c["OpenUSD finds a UsdPreviewSurface for every material (%d)%s" % (
        len(mats), ": not for " + ", ".join(no_preview) if no_preview else "")] = len(mats) == 6 and not no_preview
    ap = sorted(m["name"] for m in mats if m.get("aperture"))
    c["and AperturePBR for the RTX Remix ones only (%s)" % ", ".join(ap)] = ap == ["Gold", "Wood"]
    c["exported as .usdc (%s)" % ec.get("result")] = ec.get("result") == ["FINISHED"] and ec.get("exists") and \
        not ec.get("report")
    differ = [k for k in ("meters_per_unit", "z_up", "default_prim", "nodes", "meshes", "materials", "lights",
                          "cameras", "report", "usd_errors") if ra.get(k) != rc.get(k)]
    c["the .usdc reads the same as the .usda%s" % (": its %s differ" % ", ".join(differ) if differ else "")] = \
        "error" not in rc and not differ and bool(ra)
    check_room(c, want, got.get("got_usdc") or {}, ".usdc imported")
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.d2 Checked by the standard"] = _test(c, {
        "usda_report": ra.get("report"), "usdc_error": rc.get("error"), "export_usdc": ec,
        "traceback": got.get("traceback")})


def t_other(args, out, tests):
    folder = os.path.join(out, "p12b_other")
    got = blender(args, out, "p12b_other", ["other", os.path.join(out, "p12b_other_probe.json"), folder])
    r = got.get("got") or {}
    G = (r.get("scene") or {}).get("objects") or {}
    c = {}
    c["imported (%s), %d objects" % (r.get("result"), len(G))] = r.get("result") == ["FINISHED"] and \
        len(G) == len(uf.OTHER_TOOL_OBJECTS)
    bad = []
    for name, kind, parent, place in uf.OTHER_TOOL_OBJECTS:
        g = G.get(name)
        if g is None:
            bad.append("%s missing" % name)
            continue
        loc = [g["matrix"][k][3] for k in range(3)]
        if g["type"] != TYPES[kind] or g["parent"] != parent or not near(loc, place, PLACE_TOL):
            bad.append("%s: a %s under %s at %s (want a %s under %s at %s)" % (
                name, g["type"], g["parent"], [round(x, 5) for x in loc], TYPES[kind], parent,
                [round(x, 5) for x in place]))
    c["every object, its kind and parent, in metres, Z up, within 0.1 mm%s" % (
        ": " + "; ".join(bad) if bad else "")] = not bad
    board = G.get("Board") or {}
    size = board.get("world_size")
    c["the board upright and to scale: %s m (want 0.4 x 1.2 x 0.04)" % (size and [round(x, 4) for x in size])] = \
        near(size, [0.4, 1.2, 0.04], 1e-4)
    p1, p2_ = G.get("Pot_1") or {}, G.get("Pot_2") or {}
    c["the two pots share one mesh (%s, %s; %s users)" % (p1.get("data"), p2_.get("data"), p1.get("users"))] = \
        bool(p1.get("data")) and p1.get("data") == p2_.get("data") and p1.get("users") == 2
    s2 = p2_.get("world_size")
    c["the second pot half as big again: %s m (want 0.15)" % (s2 and [round(x, 4) for x in s2])] = \
        near(s2, [0.15, 0.15, 0.15], 1e-4)
    uv = (board.get("mesh") or {}).get("uv")
    c["the board's UVs through their indices: %s" % (uv and uv[:4])] = \
        near(uv and uv[:4], [[0, 0], [1, 0], [1, 1], [0, 1]], 1e-6)
    M = (r.get("scene") or {}).get("materials") or {}
    wood = M.get("Wood") or {}
    lk = (wood.get("linked") or {}).get("Albedo") or {}
    c["the preview surface as an RTX Remix material: roughness %s, its picture %s" % (
        (wood.get("values") or {}).get("Roughness"), lk.get("file") and os.path.basename(lk["file"]))] = \
        bool(wood.get("remix")) and near((wood.get("values") or {}).get("Roughness"), 0.7) and \
        bool(lk.get("file")) and os.path.basename(lk["file"]) == "wood.png" and lk.get("size") == [8, 8]
    bulb, cam = G.get("Bulb") or {}, G.get("camera1") or {}
    c["the light a lamp (%s), the camera its 35 mm lens and 36 mm sensor (%s)" % (
        (bulb.get("lamp") or {}).get("type"), cam.get("camera"))] = \
        (bulb.get("lamp") or {}).get("type") == 'POINT' and \
        near((cam.get("camera") or {}).get("lens"), 35.0) and \
        near((cam.get("camera") or {}).get("sensor_width"), 36.0)
    c["nothing reported (%d note(s))" % len(r.get("report") or [])] = not r.get("report")
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.d3 Another tool's file"] = _test(c, {"report": r.get("report"), "error": r.get("error"),
                                                     "objects": {k: v.get("matrix") for k, v in G.items()},
                                                     "traceback": got.get("traceback")})


def t_unsupported(args, out, tests):
    folder = os.path.join(out, "p12b_unsupported")
    got = blender(args, out, "p12b_unsupported", ["unsupported", os.path.join(out, "p12b_unsup_probe.json"),
                                                  folder])
    r = got.get("got") or {}
    report = "\n".join(r.get("report") or [])
    G = (r.get("scene") or {}).get("objects") or {}
    c = {}
    c["imported (%s)" % r.get("result")] = r.get("result") == ["FINISHED"]
    for want in uf.UNSUPPORTED_REPORT:
        c["the report names %r" % want] = want in report
    meshes = sorted(n for n, g in G.items() if g["type"] == 'MESH')
    c["the rest came in: the floor and the box (%s)" % ", ".join(meshes)] = meshes == ["Floor", "Lift"] and \
        (G.get("Lift") or {}).get("data") == "Box"
    custom = ((r.get("scene") or {}).get("materials") or {}).get("Custom") or {}
    c["the custom shader's material comes in plain (an RTX Remix material: %s)" % custom.get("remix")] = \
        bool(custom.get("remix"))
    c["nothing else (no Rock, no Hair: %s)" % ", ".join(sorted(G))] = "Rock" not in G and "Hair" not in G and \
        "Rocks" not in G
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.d4 What is not imported"] = _test(c, {"report": r.get("report"), "error": r.get("error"),
                                                      "traceback": got.get("traceback")})


# ---------------------------------------------------------------------------
# round 7: physics

ANGLE_TOL = math.radians(0.01)
ANGLE_FIELDS = ("axis_x", "axis_y", "axis_z", "limit_angle_min_x", "limit_angle_min_y", "limit_angle_min_z",
                "limit_angle_max_x", "limit_angle_max_y", "limit_angle_max_z")


def _same(a, b, tol=1e-4):
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or a is None:
        return a == b
    if isinstance(a, (list, tuple)):
        return isinstance(b, (list, tuple)) and len(a) == len(b) and all(_same(x, y, tol) for x, y in zip(a, b))
    try:
        return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)))
    except (TypeError, ValueError):
        return a == b


def physics_diff(want, got):
    """the objects and joints whose physics differ: lines"""
    bad = []
    W, G = want.get("objects") or {}, got.get("objects") or {}
    for name, w in sorted(W.items()):
        g = G.get(name)
        if g is None:
            bad.append("%s missing" % name)
            continue
        for k, v in sorted(w["game"].items()):
            if not _same(v, g["game"].get(k)):
                bad.append("%s %s %s / %s" % (name, k, v, g["game"].get(k)))
        for k in ("articulation", "friction", "elasticity", "parent"):
            if not _same(w.get(k), g.get(k)):
                bad.append("%s %s %s / %s" % (name, k, w.get(k), g.get(k)))
        if w.get("idprops") != g.get("idprops"):
            bad.append("%s ID properties %s / %s" % (name, w.get("idprops"), g.get("idprops")))
        gj = {j["name"]: j for j in g.get("joints") or ()}
        for j in w.get("joints") or ():
            h = gj.get(j["name"])
            if h is None:
                bad.append("%s: joint %s missing (has %s)" % (name, j["name"], sorted(gj)))
                continue
            for k, v in sorted(j.items()):
                if k in ("world_axis", "world_pivot"):
                    continue
                tol = ANGLE_TOL if k in ANGLE_FIELDS else 1e-4
                if not _same(v, h.get(k), tol):
                    bad.append("%s/%s %s %s / %s" % (name, j["name"], k, v, h.get(k)))
        if len(gj) != len(w.get("joints") or ()):
            bad.append("%s: %d joints, %d were" % (name, len(gj), len(w.get("joints") or ())))
    extra = sorted(set(G) - set(W))
    if extra:
        bad.append("more objects: %s" % ", ".join(extra))
    for k in ("engine", "device", "gravity"):
        if not _same(want.get(k), got.get(k)):
            bad.append("the world's %s %s / %s" % (k, want.get(k), got.get(k)))
    return bad


def _lines(bad, n=6):
    return ": " + "; ".join(bad[:n]) + (" (and %d more)" % (len(bad) - n) if len(bad) > n else "") if bad else ""


def t_physics(args, out, tests):
    folder = os.path.join(out, "p12b_physics")
    got = blender(args, out, "p12b_physics", ["physics", os.path.join(out, "p12b_physics_probe.json"), folder],
                  timeout=1800)
    out_state["physics_folder"] = folder if got.get("moving") else None
    out_state["moving"] = got.get("moving") or []
    want = got.get("want") or {}
    ea, ec = got.get("export_usda") or {}, got.get("export_usdc") or {}
    ga, gc = got.get("got_usda") or {}, got.get("got_usdc") or {}
    c = {}
    counts = ea.get("counts") or {}
    c["exported as .usda (%s; %s objects)" % (ea.get("result"), counts.get("objects"))] = \
        ea.get("result") == ["FINISHED"] and bool(ea.get("exists"))
    rep = [l for l in (ea.get("report") or []) if "hidden layers" not in l]
    c["nothing left out but the destructible's kept original (on layer 20)%s" % _lines(rep)] = not rep
    c["imported (%s, %d note(s)%s)" % (ga.get("result"), len(ga.get("report") or []),
                                      _lines(ga.get("report") or [], 3))] = \
        ga.get("result") == ["FINISHED"] and not ga.get("report")
    W = want.get("objects") or {}
    bodies = sorted(n for n, w in W.items() if w["game"]["physics_type"] in ('RIGID_BODY', 'DYNAMIC'))
    bad = physics_diff(want, ga.get("physics") or {})
    c["every object's physics and every joint back as they were (%d objects, %d bodies, %d joints)%s" % (
        len(W), len(bodies), sum(len(w.get("joints") or ()) for w in W.values()), _lines(bad))] = \
        not bad and len(W) > 20
    G = (ga.get("physics") or {}).get("objects") or {}
    wall = [n for n, w in W.items() if (w.get("idprops") or {}).get("bge_destructible")]
    pool = [n for n, w in W.items() if (w.get("idprops") or {}).get("bge_fluid")]
    c["the destructible (%s: Strength %s, Anchored %s) and its %d pieces, the pool (%s) come back" % (
        wall, wall and (G.get(wall[0]) or {}).get("idprops", {}).get("bge_destructible_strength"),
        wall and (G.get(wall[0]) or {}).get("idprops", {}).get("bge_destructible_anchored"),
        sum(1 for g in G.values() if (g.get("idprops") or {}).get("bge_destructible_of")), pool)] = \
        len(wall) == 1 and len(pool) == 1 and \
        sum(1 for g in G.values() if (g.get("idprops") or {}).get("bge_destructible_of")) >= 5
    c["the world: %s %s, gravity %s" % ((ga.get("physics") or {}).get("engine"),
                                        (ga.get("physics") or {}).get("device"),
                                        (ga.get("physics") or {}).get("gravity"))] = \
        (ga.get("physics") or {}).get("engine") == 'PHYSX' and \
        _same((ga.get("physics") or {}).get("gravity"), 9.81)
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.e1 The physics room, out and back"] = _test(c, {"export": ea, "import_report": ga.get("report"),
                                                            "diff": bad, "traceback": got.get("traceback")})

    c = {}
    E = got.get("standard_want") or {}
    for ext in ("usda", "usdc"):
        S = got.get("standard_" + ext) or {}
        c["%s: OpenUSD's physics reader read it (%s), no complaint (%s, %r)" % (
            ext, S.get("read"), S.get("usd_errors"), S.get("report"))] = \
            bool(S.get("read")) and S.get("usd_errors") == 0 and not S.get("report")
        c["%s: the bodies %s" % (ext, ", ".join(S.get("bodies") or []))] = S.get("bodies") == sorted(E.get("bodies") or [])
        diff = sorted(k for k in set(E.get("shapes") or {}) | set(S.get("shapes") or {})
                      if (E.get("shapes") or {}).get(k) != (S.get("shapes") or {}).get(k))
        c["%s: every collider and its shape's kind (%d)%s" % (ext, len(S.get("shapes") or {}), _lines(
            ["%s %s/%s" % (k, (E.get("shapes") or {}).get(k), (S.get("shapes") or {}).get(k)) for k in diff]))] = \
            not diff and bool(E.get("shapes"))
        diff = sorted(k for k in set(E.get("joints") or {}) | set(S.get("joints") or {})
                      if (E.get("joints") or {}).get(k) != (S.get("joints") or {}).get(k))
        c["%s: every joint and its kind (%s)%s" % (ext, ", ".join("%s %s" % kv for kv in sorted(
            (S.get("joints") or {}).items())), _lines(diff))] = not diff and bool(E.get("joints"))
        fr = [k for k, v in (E.get("frictions") or {}).items() if not _same(v, (S.get("frictions") or {}).get(k))]
        c["%s: the physics materials (friction, bounce)%s" % (ext, _lines(fr))] = not fr
        c["%s: the articulation root (%s, want %s), gravity %s" % (ext, S.get("roots"), E.get("roots"),
                                                                 S.get("gravity"))] = \
            S.get("roots") == E.get("roots") and _same(S.get("gravity"), E.get("gravity"))
    c["the .usdc's physics reads the same as the .usda's"] = \
        bool(got.get("physics_json_usda")) and got.get("physics_json_usda") == got.get("physics_json_usdc")
    bad = physics_diff(want, gc.get("physics") or {})
    c["the .usdc imports the same (%s)%s" % (gc.get("result"), _lines(bad))] = \
        gc.get("result") == ["FINISHED"] and not bad and not gc.get("report")
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.e2 Checked by the standard (physics)"] = _test(c, {"want": E, "usda": got.get("standard_usda"),
                                                                "export_usdc": ec})


FIXED = ["-g", "fixedtime", "=", "1"]
NO_REMIX = ["-g", "remix", "=", "0"]
out_state = {}


def _play(args, out, tag, blend):
    res = os.path.join(out, tag + "_bodies.json")
    if os.path.isfile(res):
        os.remove(res)
    r = p2.player(args.ours, out, tag, blend, {"BGE_REMIX_P12_OUT": res, "BGE_REMIX_P2_FRAMES": "150"},
                  size=(640, 360), args=FIXED + NO_REMIX)
    return p2.read_json(res) or {}, r


def t_play(args, out, tests):
    folder = out_state.get("physics_folder") or os.path.join(out, "p12b_physics")
    names = out_state.get("moving") or []
    a, ra = _play(args, out, "p12b_play_room", os.path.join(folder, "room.blend"))
    b, rb = _play(args, out, "p12b_play_imported", os.path.join(folder, "imported.blend"))
    c = {}
    A, B = a.get("bodies") or {}, b.get("bodies") or {}
    c["both played to tic %s / %s (%d / %d bodies)" % (a.get("tic"), b.get("tic"), len(A), len(B))] = \
        bool(A) and len(A) == len(B) and (not names or len(A) == len(names))
    bad, worst_p, worst_r = [], 0.0, 0.0
    for name, x in sorted(A.items()):
        y = B.get(name)
        if y is None:
            bad.append("%s missing" % name)
            continue
        dp = math.sqrt(sum((p - q) ** 2 for p, q in zip(x["pos"], y["pos"])))
        # the angle between the two turns
        R = [[sum(x["rot"][k][i] * y["rot"][k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        cos = max(-1.0, min(1.0, (R[0][0] + R[1][1] + R[2][2] - 1.0) * 0.5))
        dr = math.degrees(math.acos(cos))
        worst_p, worst_r = max(worst_p, dp), max(worst_r, dr)
        if dp > 0.01 or dr > 1.0:
            bad.append("%s %.3f m, %.2f deg" % (name, dp, dr))
    moved = [n for n, x in A.items() if n in ("Flap", "Link3", "Drawer")]
    c["every body where the room's was (worst %.4f m, %.3f degrees)%s" % (worst_p, worst_r, _lines(bad))] = \
        not bad and bool(A)
    c["the flap, the chain's end and the drawer moved (%s)" % ", ".join(moved)] = len(moved) == 3
    c["no crash"] = ra["exit"] == 0 and rb["exit"] == 0 and not ra["traceback_in_output"] and \
        not rb["traceback_in_output"]
    tests["T12.e3 It plays the same"] = _test(c, {"room": A, "imported": B})


def t_physics_other(args, out, tests):
    folder = os.path.join(out, "p12b_physics_other")
    got = blender(args, out, "p12b_physics_other",
                  ["physics_other", os.path.join(out, "p12b_physics_other_probe.json"), folder])
    r = got.get("got") or {}
    P = r.get("physics") or {}
    G = P.get("objects") or {}
    want = uf.PHYSICS_OTHER
    c = {}
    c["imported (%s)" % r.get("result")] = r.get("result") == ["FINISHED"]
    bad = []
    for name, (kind, bounds, mass) in sorted(want["objects"].items()):
        g = (G.get(name) or {}).get("game") or {}
        if g.get("physics_type") != kind or (bounds and g.get("collision_bounds_type") != bounds) or \
                (mass is not None and not _same(g.get("mass"), mass, 1e-3)):
            bad.append("%s: %s %s %s kg (want %s %s %s)" % (name, g.get("physics_type"), g.get("collision_bounds_type"),
                                                          g.get("mass"), kind, bounds, mass))
    c["the bodies, their shapes and masses (the crate's 32 kg from its density)%s" % _lines(bad)] = not bad
    joints = {}
    for name, g in G.items():
        for j in g.get("joints") or ():
            joints[j["name"]] = (name, j)
    bad = []
    for name, (owner, target, kind, axis, pivot, limit) in sorted(want["constraints"].items()):
        o, j = joints.get(name, (None, None))
        if j is None:
            bad.append("%s missing" % name)
            continue
        if o != owner or j.get("target") != target or j.get("pivot_type") != kind:
            bad.append("%s: %s to %s, a %s" % (name, o, j.get("target"), j.get("pivot_type")))
        if axis is not None and abs(abs(sum(a * b for a, b in zip(axis, j.get("world_axis") or (0, 0, 0)))) - 1.0) > 1e-4:
            bad.append("%s: its axis %s (want +-%s)" % (name, [round(x, 4) for x in j.get("world_axis") or ()], axis))
        if not _same(pivot, j.get("world_pivot"), 1e-4):
            bad.append("%s: its pivot %s (want %s)" % (name, [round(x, 4) for x in j.get("world_pivot") or ()], pivot))
        if limit is not None:
            ax, lo, hi = limit
            if ax == "x":
                ok = j.get("use_angular_limit_x") and _same(j.get("limit_angle_min_x"), math.radians(lo)) and \
                    _same(j.get("limit_angle_max_x"), math.radians(hi))
            else:
                ok = j.get("use_limit_x") and _same(j.get("limit_min_x"), lo) and _same(j.get("limit_max_x"), hi)
            if not ok:
                bad.append("%s: its limits %s" % (name, {k: v for k, v in j.items() if "limit" in k and v}))
    c["the joints: who to whom, their kinds, axes and pivots in the world, limits%s" % _lines(bad)] = not bad
    c["the robot arm an articulation Fixed to the World on its base (%s)" % (G.get("Base") or {}).get("articulation")] = \
        (G.get("Base") or {}).get("articulation") == 'FIXED' and "BaseFixed" not in joints
    report = "\n".join(r.get("report") or [])
    for w in want["report"]:
        c["the report names %r" % w] = w in report
    c["the world: %s, gravity %s (want 9.81)" % (P.get("engine"), P.get("gravity"))] = \
        P.get("engine") == 'PHYSX' and _same(P.get("gravity"), want["gravity"])
    floor = G.get("Floor") or {}
    c["the floor's physics material: friction %s, bounce %s (want 0.8, 0.3)" % (floor.get("friction"),
                                                                              floor.get("elasticity"))] = \
        _same(floor.get("friction"), 0.8) and _same(floor.get("elasticity"), 0.3)
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.e4 Another tool's physics file"] = _test(c, {"report": r.get("report"), "error": r.get("error"),
                                                          "traceback": got.get("traceback")})


# ---------------------------------------------------------------------------
# round 8: armatures

def turn_deg(a, b):
    """the angle (degrees) between the turns of two 4 x 4 (or 3 x 3)
    matrices, their scale taken out"""
    def cols(m):
        c = [[m[r][k] for r in range(3)] for k in range(3)]
        return [[x / max(math.sqrt(sum(y * y for y in v)), 1e-12) for x in v] for v in c]
    A, B = cols(a), cols(b)
    tr = sum(sum(A[k][r] * B[k][r] for r in range(3)) for k in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1.0) * 0.5))))


def place_off(a, b):
    return max(abs(a[r][3] - b[r][3]) for r in range(3))


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def bones_diff(W, G):
    bad = []
    wb, gb = (W.get("rig") or {}).get("bones") or {}, (G.get("rig") or {}).get("bones") or {}
    for name, w in sorted(wb.items()):
        g = gb.get(name)
        if g is None:
            bad.append("%s missing" % name)
            continue
        if g["parent"] != w["parent"] or g["connect"] != w["connect"] or g["deform"] != w["deform"]:
            bad.append("%s: under %s (connected %s, deform %s), was under %s (%s, %s)" % (
                name, g["parent"], g["connect"], g["deform"], w["parent"], w["connect"], w["deform"]))
        dh, dt = dist(w["head"], g["head"]), dist(w["tail"], g["tail"])
        dr = turn_deg(w["matrix"], g["matrix"])
        if dh > PLACE_TOL or dt > PLACE_TOL or dr > 0.01:
            bad.append("%s: head %.3g m, tail %.3g m, roll %.3g deg off" % (name, dh, dt, dr))
    if sorted(gb) != sorted(wb):
        bad.append("bones %s, were %s" % (sorted(gb), sorted(wb)))
    return bad


def poses_diff(W, G):
    bad, worst = [], [0.0, 0.0]
    for act, w in sorted((W.get("actions") or {}).items()):
        g = (G.get("actions") or {}).get(act)
        if g is None:
            bad.append("action %s missing" % act)
            continue
        if sorted(g["poses"]) != sorted(w["poses"]):
            bad.append("%s: frames %s, were %s" % (act, g["range"], w["range"]))
            continue
        for f, bones in w["poses"].items():
            for b, m in bones.items():
                h = g["poses"][f].get(b)
                if h is None:
                    bad.append("%s frame %s: no %s" % (act, f, b))
                    continue
                dp, dr = place_off(m, h), turn_deg(m, h)
                ds = max(abs(math.sqrt(sum(m[r][k] ** 2 for r in range(3))) -
                             math.sqrt(sum(h[r][k] ** 2 for r in range(3)))) for k in range(3))
                worst = [max(worst[0], dp), max(worst[1], dr)]
                if dp > PLACE_TOL or dr > 0.01 or ds > 1e-4:
                    bad.append("%s frame %s %s: %.3g m, %.3g deg, scale %.3g off" % (act, f, b, dp, dr, ds))
    return bad, worst


def groups_diff(W, G):
    wg, gg = (W.get("body") or {}).get("groups") or [], (G.get("body") or {}).get("groups") or []
    if len(wg) != len(gg):
        return ["%d vertices, were %d" % (len(gg), len(wg))]
    bad = []
    for v, (a, b) in enumerate(zip(wg, gg)):
        if sorted(a) != sorted(b) or any(abs(a[k] - b[k]) > 1e-5 for k in a):
            bad.append("vertex %d: %s, was %s" % (v, b, a))
    return bad


def deformed_diff(W, G, frames, tol):
    bad, worst = [], 0.0
    for f in frames:
        a, b = (W or {}).get(str(f)) or [], (G or {}).get(str(f)) or []
        if not a or len(a) != len(b):
            bad.append("frame %s: %d vertices, %d wanted" % (f, len(b), len(a)))
            continue
        d = max(dist(p, q) for p, q in zip(a, b))
        worst = max(worst, d)
        if d > tol:
            bad.append("frame %s: %.3g m off" % (f, d))
    return bad, worst


def capsules_diff(W, G):
    bad = []
    wc, gc = W.get("capsules") or {}, G.get("capsules") or {}
    for name, w in sorted(wc.items()):
        g = gc.get(name)
        if g is None:
            bad.append("%s missing" % name)
            continue
        if (g["parent"], g["parent_type"], g["parent_bone"]) != (w["parent"], w["parent_type"], w["parent_bone"]):
            bad.append("%s: on %s %s %s, was on %s %s %s" % (name, g["parent"], g["parent_type"], g["parent_bone"],
                                                            w["parent"], w["parent_type"], w["parent_bone"]))
        if place_off(w["matrix"], g["matrix"]) > PLACE_TOL or turn_deg(w["matrix"], g["matrix"]) > 0.01:
            bad.append("%s: placed %.3g m, %.3g deg off" % (name, place_off(w["matrix"], g["matrix"]),
                                                          turn_deg(w["matrix"], g["matrix"])))
    if sorted(gc) != sorted(wc):
        bad.append("capsules %d, were %d" % (len(gc), len(wc)))
    bad += physics_diff({"objects": {n: c["physics"] for n, c in wc.items() if c.get("physics")}},
                        {"objects": {n: c["physics"] for n, c in gc.items() if c.get("physics")}})
    return bad


def t_character(args, out, tests):
    folder = os.path.join(out, "p12b_character")
    got = blender(args, out, "p12b_character", ["character", os.path.join(out, "p12b_character_probe.json"),
                                                 folder], timeout=1800)
    out_state["character_folder"] = folder if (got.get("want") or {}).get("rig") else None
    W = got.get("want") or {}
    ea, ec = got.get("export_usda") or {}, got.get("export_usdc") or {}
    ga, gc = got.get("got_usda") or {}, got.get("got_usdc") or {}
    A, C = ga.get("character") or {}, gc.get("character") or {}
    c = {}
    counts = ea.get("counts") or {}
    c["exported as .usda (%s; %s armature, %s skinned, %s animations)" % (
        ea.get("result"), counts.get("armatures"), counts.get("skinned"), counts.get("animations"))] = \
        ea.get("result") == ["FINISHED"] and bool(ea.get("exists")) and counts.get("armatures") == 1 and \
        counts.get("skinned") == 1 and counts.get("animations") == 2
    rep = [l for l in (ea.get("report") or []) if "hidden layers" not in l]
    c["nothing left out%s" % _lines(rep)] = not rep
    c["imported (%s, %d note(s)%s)" % (ga.get("result"), len(ga.get("report") or []),
                                      _lines(ga.get("report") or [], 3))] = \
        ga.get("result") == ["FINISHED"] and not ga.get("report")
    wb = (W.get("rig") or {}).get("bones") or {}
    bad = bones_diff(W, A)
    c["every bone back: name, parent, head, tail, roll (%d bones)%s" % (len(wb), _lines(bad))] = \
        not bad and len(wb) == 12
    c["the armature where it was (%.3g m, %.3g deg)" % (
        place_off((W.get("rig") or {}).get("matrix") or [[0] * 4] * 4, (A.get("rig") or {}).get("matrix") or
                  [[1e9] * 4] * 4),
        turn_deg((W.get("rig") or {}).get("matrix") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                 (A.get("rig") or {}).get("matrix") or [[1, 0, 0], [0, 1, 0], [0, 0, 1]]))] = \
        bool(A.get("rig")) and place_off(W["rig"]["matrix"], A["rig"]["matrix"]) <= PLACE_TOL and \
        turn_deg(W["rig"]["matrix"], A["rig"]["matrix"]) <= 0.01
    bad = groups_diff(W, A)
    body = A.get("body") or {}
    c["the body: every vertex's groups and weights (%d vertices)%s" % (len(body.get("groups") or ()),
                                                                     _lines(bad))] = \
        not bad and bool(body.get("groups"))
    c["the body under Rig, an Armature modifier on Rig (%s, %s)" % (body.get("parent"), body.get("modifiers"))] = \
        body.get("parent") == "Rig" and body.get("modifiers") == [["ARMATURE", "Rig"]]
    bad, worst = poses_diff(W, A)
    c["both actions, every bone's pose at every frame (worst %.3g m, %.3g deg)%s" % (worst[0], worst[1],
                                                                                   _lines(bad))] = \
        not bad and sorted(A.get("actions") or {}) == ["Walk", "Wave"]
    c["Walk the armature's action, Wave kept (%s; Wave fake user %s)" % (
        A.get("action"), ((A.get("actions") or {}).get("Wave") or {}).get("fake_user"))] = \
        A.get("action") == "Walk" and bool(((A.get("actions") or {}).get("Wave") or {}).get("fake_user"))
    c["24 frames a second, frames 1 to 24 (%s, %s)" % (A.get("fps"), A.get("frames"))] = \
        _same(A.get("fps"), 24.0) and A.get("frames") == [1, 24]
    bad, worst = deformed_diff(W.get("deformed"), A.get("deformed"), (1, 12, 24), PLACE_TOL)
    c["the body deformed the same at frames 1, 12 and 24 (worst %.3g m)%s" % (worst, _lines(bad))] = not bad
    bad = capsules_diff(W, A)
    c["the ragdoll's %d capsules back on their bones, with their physics and joints%s" % (
        len(W.get("capsules") or {}), _lines(bad))] = not bad and len(W.get("capsules") or {}) == 12
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.f1 The character, out and back"] = _test(c, {"export": ea, "import_report": ga.get("report"),
                                                         "traceback": got.get("traceback")})

    c = {}
    joints = got.get("want_joints") or []
    for ext in ("usda", "usdc"):
        S = got.get("standard_" + ext) or {}
        sk = S.get("skeletons") or {}
        skels = sk.get("skeletons") or []
        s0 = skels[0] if skels else {}
        c["%s: no complaint (%s, %r)" % (ext, S.get("usd_errors"), S.get("report"))] = \
            S.get("usd_errors") == 0 and not S.get("report") and "error" not in S
        c["%s: one skeleton, valid (%s %s), its %d joints in order" % (ext, s0.get("valid"), s0.get("problem"),
                                                                       len(s0.get("joints") or ()))] = \
            len(skels) == 1 and bool(s0.get("valid")) and s0.get("joints") == joints and len(joints) == 12
        skin = sk.get("skinned") or []
        c["%s: the body bound to it (%s)" % (ext, [x.get("path") for x in skin])] = \
            len(skin) == 1 and skin[0].get("skeleton") == s0.get("path") and bool(S.get("mesh_path"))
        anims = sorted(a["path"].rsplit("/", 1)[-1] for a in sk.get("animations") or ())
        t = sk.get("time") or {}
        c["%s: Walk bound, Wave there, frames %s to %s at %s" % (ext, t.get("start"), t.get("end"), t.get("fps"))] = \
            (s0.get("animation") or "").endswith("/Walk") and anims == ["Walk", "Wave"] and \
            bool(t.get("authored")) and _same(t.get("start"), 1) and _same(t.get("end"), 24) and \
            _same(t.get("fps"), 24)
        usd = (S.get("skinned") or {}).get("12") or []
        mine = (W.get("deformed") or {}).get("12") or []
        d = max(dist(p, q) for p, q in zip(mine, usd)) if mine and len(mine) == len(usd) else 1e9
        c["%s: OpenUSD's own skinning of the body at frame 12 within 1 mm of Blender's (%.3g m)" % (ext, d)] = \
            d <= 1e-3
    import json as _json
    c["the .usdc's skeletons read the same as the .usda's"] = \
        bool((got.get("standard_usda") or {}).get("skeletons")) and \
        _json.dumps((got.get("standard_usda") or {}).get("skeletons"), sort_keys=True) == \
        _json.dumps((got.get("standard_usdc") or {}).get("skeletons"), sort_keys=True)
    bad = bones_diff(W, C) + poses_diff(W, C)[0] + groups_diff(W, C)
    c["the .usdc imports the same (%s)%s" % (gc.get("result"), _lines(bad))] = \
        gc.get("result") == ["FINISHED"] and not bad and not gc.get("report")
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.f2 Checked by the standard (skeletons)"] = _test(c, {"usda": {k: v for k, v in (
        got.get("standard_usda") or {}).items() if k != "skinned"}, "export_usdc": ec})


def t_character_other(args, out, tests):
    folder = os.path.join(out, "p12b_character_other")
    got = blender(args, out, "p12b_character_other",
                  ["character_other", os.path.join(out, "p12b_character_other_probe.json"), folder])
    r = got.get("got") or {}
    G = r.get("character") or {}
    E = got.get("expect") or {}
    S = got.get("standard") or {}
    c = {}
    c["imported (%s)" % r.get("result")] = r.get("result") == ["FINISHED"]
    bones = G.get("bones") or {}
    c["an armature of %d bones (%s), its action Anim (%s)" % (len(bones), G.get("armatures"), G.get("action"))] = \
        len(G.get("armatures") or ()) == 1 and len(bones) == E.get("bones") and G.get("action") == "Anim"
    bad = []
    for n, h in sorted((E.get("heads") or {}).items()):
        b = bones.get(n)
        if b is None:
            bad.append("%s missing" % n)
        elif dist(b["head"], h) > PLACE_TOL:
            bad.append("%s's head at %s, not %s" % (n, [round(x, 4) for x in b["head"]], [round(x, 4) for x in h]))
    c["upright and to scale: every joint where the file has it, in metres, Z up%s" % _lines(bad)] = \
        not bad and bool(bones)
    bad = []
    for n, t in sorted((E.get("tails") or {}).items()):
        b = bones.get(n)
        if b is not None and dist(b["tail"], t) > PLACE_TOL:
            bad.append("%s reaches %s, not %s" % (n, [round(x, 4) for x in b["tail"]], [round(x, 4) for x in t]))
    c["the bones reaching to their children%s" % _lines(bad)] = not bad and bool(bones)
    body = G.get("body") or {}
    c["the body: %s vertices, %s groups, %s, under %s" % (body.get("vertices"), body.get("groups"),
                                                         body.get("modifiers"), body.get("parent"))] = \
        body.get("vertices") == E.get("vertices") and body.get("modifiers") == ["ARMATURE"] and \
        body.get("parent") in (G.get("armatures") or [None])
    c["30 frames a second, frames 1 to 30 (%s, %s)" % (G.get("fps"), G.get("frames"))] = \
        _same(G.get("fps"), 30.0) and G.get("frames") == [1, 30]
    usd = {f: [uf.to_blender(p, 0.01, False) for p in pts] for f, pts in (S.get("skinned") or {}).items()}
    bad, worst = deformed_diff(usd, G.get("deformed"), (1, 15, 30), 1e-3)
    c["at frames 1, 15 and 30 its body within 1 mm of OpenUSD's own skinning (worst %.3g m)%s" % (
        worst, _lines(bad))] = not bad and len(usd) == 3
    report = "\n".join(r.get("report") or [])
    for w in E.get("report") or ():
        c["the report names %r" % w] = w in report
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.f3 Another tool's character"] = _test(c, {"report": r.get("report"), "error": r.get("error"),
                                                       "traceback": got.get("traceback")})


def _play_character(args, out, tag, blend):
    res = os.path.join(out, tag + "_poses.json")
    if os.path.isfile(res):
        os.remove(res)
    r = p2.player(args.ours, out, tag, blend, {"BGE_REMIX_P12_OUT": res, "BGE_REMIX_P2_FRAMES": "90"},
                  size=(640, 360), args=FIXED + NO_REMIX)
    return p2.read_json(res) or {}, r


def t_character_play(args, out, tests):
    folder = out_state.get("character_folder") or os.path.join(out, "p12b_character")
    a, ra = _play_character(args, out, "p12b_play_character", os.path.join(folder, "character.blend"))
    b, rb = _play_character(args, out, "p12b_play_character_imported", os.path.join(folder, "imported.blend"))
    c = {}
    A, B = a.get("poses") or {}, b.get("poses") or {}
    c["both played to tic %s / %s (poses at %s / %s)" % (a.get("tic"), b.get("tic"), sorted(A), sorted(B))] = \
        sorted(A) == ["30", "60"] and sorted(B) == ["30", "60"]
    bad, worst = [], [0.0, 0.0]
    for tic in sorted(A):
        x, y = A[tic], B.get(tic) or {}
        for name, p in sorted((x.get("bones") or {}).items()):
            q = (y.get("bones") or {}).get(name)
            if q is None:
                bad.append("tic %s: %s missing" % (tic, name))
                continue
            dp = max(dist(p["head"], q["head"]), dist(p["tail"], q["tail"]))
            dr = turn_deg(p["matrix"], q["matrix"])
            worst = [max(worst[0], dp), max(worst[1], dr)]
            if dp > PLACE_TOL or dr > 0.01:
                bad.append("tic %s %s: %.3g m, %.3g deg" % (tic, name, dp, dr))
    frames = [(A.get(t) or {}).get("frame") for t in ("30", "60")]
    c["every bone where the original's was (worst %.3g m, %.3g deg; Walk at frames %s)%s" % (
        worst[0], worst[1], frames, _lines(bad))] = not bad and len((A.get("30") or {}).get("bones") or ()) == 12
    c["no crash"] = ra["exit"] == 0 and rb["exit"] == 0 and not ra["traceback_in_output"] and \
        not rb["traceback_in_output"]
    tests["T12.f4 It plays the same (armature)"] = _test(c, {"original": A.get("60"), "imported": B.get("60")})


def t_usd_view(args, out, tests):
    import p12a_tests as pa
    folder = os.path.join(out, "p12b_usd_view")
    got = blender(args, out, "p12b_usd_view", ["usd_view", os.path.join(out, "p12b_usd_view_probe.json"), folder],
                  timeout=1800)
    c = {}
    c["the room exported, imported, the other tool's file imported, each saved with a Remix View (%s; %s, %s)" % (
        got.get("export"), (got.get("imported") or {}).get("result"), (got.get("other") or {}).get("result"))] = \
        got.get("export") == ["FINISHED"] and (got.get("imported") or {}).get("result") == ["FINISHED"] and \
        (got.get("other") or {}).get("result") == ["FINISHED"] and bool(got.get("room_screens"))
    views = {}
    for tag in ("room", "imported", "other"):
        blend = os.path.join(folder, tag + ".blend")
        views[tag] = pa.view_run(args, out, "p12b_usd_view_" + tag, blend, layer="PHYSICS") \
            if os.path.isfile(blend) else {}
        c["%s: the Remix View built in the window (physics layer)" % tag] = bool(views[tag].get("ran"))

    def parts(view):
        b = (view.get("steps") or {}).get("build") or {}
        return b.get("elements") or [], b.get("warnings") or []

    for tag in ("imported", "other"):
        els, warns = parts(views[tag])
        marks = (got.get(tag) or {}).get("marks") or {}
        bodies = [e for e in els if (e.get("kind") or "").startswith("body:") and
                  e.get("kind") != "body:NO_COLLISION"]
        bad = []
        for e in bodies:
            prim = (marks.get(e.get("owner")) or {}).get("prim") or (marks.get(e.get("name")) or {}).get("prim")
            if not prim or ("from USD: " + prim) not in (e.get("info") or ""):
                bad.append("%s: %r" % (e.get("name"), e.get("info")))
        c["%s: every body says it came from USD, with its place in the file (%d bodies)%s" % (
            tag, len(bodies), _lines(bad, 4))] = not bad and bool(bodies)
        joints = [e for e in els if (e.get("kind") or "").startswith("joint:")]
        bad = ["%s: %r" % (e.get("name"), e.get("info")) for e in joints if "from USD" not in (e.get("info") or "")]
        c["%s: every joint says it came from USD (%d joints)%s" % (tag, len(joints), _lines(bad, 4))] = \
            not bad and bool(joints)
        eng = [e for e in els if (e.get("kind") or "").startswith("engine:")]
        c["%s: the scene says which file it came from (%r)" % (tag, eng and eng[0].get("info"))] = \
            bool(eng) and "the scene came from USD (" in (eng[0].get("info") or "")
        if tag == "other":
            notes = [w for w in warns if w.get("code") == "USD_NOTE"]
            crate = [w for w in notes if w.get("name") == "Crate" or w.get("owner") == "Crate"]
            c["other: the crate's note: its convex decomposition came in as a Convex Hull (%s)" % (
                [w.get("text") for w in crate])] = \
                any("convexDecomposition" in (w.get("text") or "") and "Convex Hull" in (w.get("text") or "")
                    for w in crate)
    els, warns = parts(views["room"])
    marked = [e.get("name") for e in els if "USD" in (e.get("info") or "")] + \
        [w.get("name") for w in warns if w.get("code") == "USD_NOTE"]
    c["the room made in Blender has no such mark (%d elements%s)" % (len(els), _lines(marked, 4))] = \
        not marked and bool(els)
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests["T12.f5 The Remix View marks what came from USD"] = _test(c, {
        "traceback": got.get("traceback"), "other_marks": (got.get("other") or {}).get("marks"),
        "views": {t: {k: v for k, v in (views[t] or {}).items() if k != "steps"} for t in views}})


def normal(args, out, scenes, E, tests, sheets):
    only = _only()
    for key, fn in (("exchange", t_exchange), ("other", t_other), ("unsupported", t_unsupported),
                    ("physics", t_physics), ("play", t_play), ("physicsother", t_physics_other),
                    ("character", t_character), ("characterother", t_character_other),
                    ("characterplay", t_character_play), ("usdview", t_usd_view)):
        if not only or key in only:
            try:
                fn(args, out, tests)
            except Exception:
                import traceback
                tests["%s ran" % key] = _test({"ran without an error": False}, traceback.format_exc())


def rtx(args, out, scenes, E, tests, sheets, report):
    """no RTX run this round"""
    return
