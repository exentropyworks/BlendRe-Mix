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

BGE_REMIX_P12B_ONLY (comma separated: exchange, other, unsupported; d1 and
d2 both come from exchange) runs only those (a fix round's reruns). No RTX
run this round.
"""

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


def normal(args, out, scenes, E, tests, sheets):
    only = _only()
    for key, fn in (("exchange", t_exchange), ("other", t_other), ("unsupported", t_unsupported)):
        if not only or key in only:
            try:
                fn(args, out, tests)
            except Exception:
                import traceback
                tests["%s ran" % key] = _test({"ran without an error": False}, traceback.format_exc())


def rtx(args, out, scenes, E, tests, sheets, report):
    """no RTX run this round"""
    return
