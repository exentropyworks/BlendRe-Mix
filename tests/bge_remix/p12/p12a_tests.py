"""BGE-Remix P12 Part A: Remix modding, the tests (run by run_p12.py).

The captures are written here by capture_writer.py (no game, no Remix); our
Blender imports them (p12a_probe.py, background) and what came in is set
against what was written.

normal(...)
  T12.a1  the bridge's OpenUSD on this PC: round 1's self-test, from this
          build (bge_remix_usd.dll loaded, a stage written and read back)
  T12.a2  the room comes in: counts exact; parts of the same shape on one
          mesh (the box drawn twice); every place within 0.1 mm; every
          material value; the textures decoded to PNGs (the uncompressed one
          and the BC1 one, pixel for pixel) with their DDS kept; the lamps as
          lamps that give Remix the same lights; the camera; every hash
  T12.a3  the same room written Y up in centimetres comes in at the same
          places, within 0.1 mm
  T12.a4  broken captures: a missing texture (the material comes in without
          it, named), a mesh file cut short (the sphere left out, named), a
          USD file that is not a capture (a message); no crash
  T12.a5  the imported room plays (the fake runtime): Remix gets its
          materials and lights as the capture had them
rtx(...)
  S12.a1  the room and the imported room in Remix, a picture pair

BGE_REMIX_P12A_ONLY (comma separated: selftest, room, units, broken, plays)
runs only those (a fix round's reruns).
"""

import json
import math
import os
import shutil
import sys

import run_p2 as p2
import run_p8 as p8
import run_p9 as r9

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_writer as cw  # noqa: E402

PROBE = os.path.join(HERE, "p12a_probe.py")
PLACE_TOL = 1e-4      # 0.1 mm
VALUE_TOL = 1e-4


def _test(c, d=None):
    return {"ok": all(c.values()) and bool(c), "checks": c, "detail": d}


def _only():
    return [t.strip() for t in os.environ.get("BGE_REMIX_P12A_ONLY", "").split(",") if t.strip()]


def linear(c):
    c = min(max(float(c), 0.0), 1.0)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def blender(args, out, tag, argv, timeout=600):
    """our Blender, background, running the probe; its JSON and log text"""
    res = argv[2]
    if os.path.isfile(res):
        os.remove(res)
    code, text, _ = p2.run([p2.exe(args.ours, "blender"), "--background", "--factory-startup", "--python", PROBE,
                            "--"] + argv, p2.base_env(out, tag), os.path.join(out, tag + ".log"), timeout=timeout)
    got = p2.read_json(res) or {}
    got["exit"] = code
    got["log"] = [l for l in (text or "").splitlines() if l.startswith("BGE-Remix capture import: ")]
    return got


def write(out, kind):
    folder = os.path.join(out, "capture_" + kind)
    shutil.rmtree(folder, ignore_errors=True)
    cw.main([folder, kind])
    with open(os.path.join(folder, "expected.json")) as f:
        return json.load(f)


def import_capture(args, out, tag, path, save=None):
    res = os.path.join(out, tag + "_probe.json")
    argv = ["import", path, res] + ([save] if save else [])
    return blender(args, out, tag, argv)


def mdiff(a, b):
    """the largest differences of two 4 x 4 matrices: (place, the rest)"""
    if not a or not b:
        return (1e9, 1e9)
    place = max(abs(a[r][3] - b[r][3]) for r in range(3))
    rest = max(abs(a[r][c] - b[r][c]) for r in range(3) for c in range(3))
    return place, rest


def near(a, b, tol=VALUE_TOL):
    try:
        if isinstance(a, (list, tuple)):
            return len(a) >= len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def pixels_match(got, want, tol=1):
    if not got or len(got) < len(want):
        return False
    return all(all(abs(g[k] - w[k]) <= tol for k in range(4)) for g, w in zip(got, want))


def node_expect(key):
    """the RTX Remix node's values for a capture material"""
    names = {"diffuse_color_constant": "Albedo", "reflection_roughness_constant": "Roughness",
             "metallic_constant": "Metallic", "emissive_color_constant": "Emissive Color",
             "emissive_intensity": "Emissive Intensity", "ior_constant": "IOR",
             "transmittance_color": "Transmittance", "transmittance_measurement_distance": "Transmittance Distance"}
    srgb = ("diffuse_color_constant", "emissive_color_constant", "transmittance_color")
    want = {}
    for name, (kind, v) in cw.MATERIALS[key]["inputs"].items():
        if name in names:
            want[names[name]] = [linear(c) for c in v] if name in srgb else (list(v) if kind == "color3f" else v)
    return want


def check_room(got, E, mpu, z_up):
    """the imported room against what the writer wrote: (checks, detail)"""
    S = got.get("scene") or {}
    objs, meshes, mats, imgs, lamps = (S.get(k) or {} for k in ("objects", "meshes", "materials", "images", "lamps"))
    c = {}
    c["it came in as a new scene (%s)" % got.get("result")] = got.get("result") == ["FINISHED"] and bool(S)
    n = S.get("counts") or {}
    c["counts: %s meshes, %s objects, %s materials, %s lamps, camera %s (want 2, 11, 5, 2, 1)" % (
        n.get("meshes"), n.get("objects"), n.get("materials"), n.get("lamps"), n.get("camera"))] = \
        (n.get("meshes"), n.get("objects"), n.get("materials"), n.get("lamps"), n.get("camera")) == (2, 11, 5, 2, 1)
    # places, shared meshes, materials, hashes
    worst_place, worst_rest, wrong = 0.0, 0.0, []
    for o in E["objects"]:
        g = objs.get(o["name"])
        if not g:
            wrong.append(o["name"] + " missing")
            continue
        place, rest = mdiff(g.get("matrix"), o["matrix"])
        worst_place, worst_rest = max(worst_place, place), max(worst_rest, rest)
        if g.get("data") != "mesh_" + o["mesh"]:
            wrong.append("%s on %s" % (o["name"], g.get("data")))
        if g.get("material") != "mat_" + o["material"] or g.get("material_link") != 'OBJECT':
            wrong.append("%s material %s (%s)" % (o["name"], g.get("material"), g.get("material_link")))
        if g.get("hash") != o["mesh"] or g.get("mesh_hash") != o["mesh"]:
            wrong.append("%s hash %s %s" % (o["name"], g.get("hash"), g.get("mesh_hash")))
    c["every place within 0.1 mm (worst %.6f m, turn and size %.6f)" % (worst_place, worst_rest)] = \
        worst_place <= PLACE_TOL and worst_rest <= PLACE_TOL
    c["every object on its mesh and material, with its hash%s" % ("" if not wrong else ": " + ", ".join(wrong[:4]))] = \
        not wrong
    cube = meshes.get("mesh_" + cw.CUBE) or {}
    sphere = meshes.get("mesh_" + cw.SPHERE) or {}
    ec, es = E["meshes"][cw.CUBE], E["meshes"][cw.SPHERE]
    c["parts of one shape share a mesh: the cube under %s objects, the box twice (want 10)" % cube.get("users")] = \
        cube.get("users") == 10
    c["the cube: %s vertices, %s faces, UVs and normals (want %d, %d)" % (
        cube.get("vertices"), cube.get("polygons"), ec["vertices"], ec["triangles"])] = \
        (cube.get("vertices"), cube.get("polygons")) == (ec["vertices"], ec["triangles"]) and \
        bool(cube.get("uv")) and bool(cube.get("custom_normals")) and cube.get("hash") == cw.CUBE
    c["the sphere: %s vertices, %s faces (want %d, %d)" % (
        sphere.get("vertices"), sphere.get("polygons"), es["vertices"], es["triangles"])] = \
        (sphere.get("vertices"), sphere.get("polygons")) == (es["vertices"], es["triangles"]) and \
        bool(sphere.get("uv")) and sphere.get("hash") == cw.SPHERE
    # materials
    bad = []
    for key, h in cw.MAT.items():
        m = mats.get("mat_" + h) or {}
        if not m.get("remix") or m.get("hash") != h:
            bad.append("%s not an RTX Remix material with its hash" % key)
            continue
        want_type = 'TRANSLUCENT' if cw.MATERIALS[key]["mdl"] == "AperturePBR_Translucent" else 'OPAQUE'
        if m.get("remix_type") != want_type:
            bad.append("%s %s" % (key, m.get("remix_type")))
        for sock, v in node_expect(key).items():
            if not near((m.get("values") or {}).get(sock), v):
                bad.append("%s %s %s (want %s)" % (key, sock, (m.get("values") or {}).get(sock), v))
        kept = m.get("kept") or {}
        if not all(k in kept for k in cw.SAMPLER):
            bad.append("%s kept %s" % (key, sorted(kept)))
        tex = cw.MATERIALS[key].get("texture")
        link = (m.get("linked") or {}).get("Albedo") or {}
        if tex and not (link.get("image") and (link.get("dds") or "").endswith(h + ".dds")):
            bad.append("%s texture %s" % (key, link))
    c["every material's values as written%s" % ("" if not bad else ": " + "; ".join(bad[:4]))] = not bad
    box_img = imgs.get(cw.MAT["Box"] + ".dds.png") or {}
    brick_img = imgs.get(cw.MAT["Brick"] + ".dds.png") or {}
    T = E["textures"]
    c["the uncompressed texture decoded pixel for pixel (%s)" % box_img.get("size")] = \
        box_img.get("size") == [T["size"], T["size"]] and pixels_match(box_img.get("top"), T["rgba"])
    c["the BC1 texture decoded pixel for pixel (%s)" % brick_img.get("size")] = \
        brick_img.get("size") == [T["size"], T["size"]] and pixels_match(brick_img.get("top"), T["bc1"])
    # lamps: the lights Remix gets back (remix_light.cc): sphere radiance
    # E D^2 / r^2 (physical) or E D / r^2 (Classic spot), D = 1
    lbad = []
    for el in E["lamps"]:
        g = lamps.get("light_" + el["hash"]) or {}
        if not g:
            lbad.append(el["name"] + " missing")
            continue
        spot = el["cone"] is not None
        if g.get("type") != ('SPOT' if spot else 'POINT') or g.get("hash") != el["hash"]:
            lbad.append("%s %s" % (el["name"], g.get("type")))
        r = g.get("soft") or 0.0
        radiance = (g.get("energy") or 0.0) / (r * r) if r > 0 else 0.0
        if not near(radiance, el["intensity"], el["intensity"] * 1e-3) or not near(r, el["radius"]):
            lbad.append("%s gives %.2f at radius %.3f (want %.2f, %.3f)" % (el["name"], radiance, r, el["intensity"],
                                                                         el["radius"]))
        if g.get("physical") != (0.0 if spot else 1.0) or not near(g.get("color"), el["colour"]):
            lbad.append("%s physical %s colour %s" % (el["name"], g.get("physical"), g.get("color")))
        place, rest = mdiff(g.get("matrix"), el["matrix"])
        if place > PLACE_TOL or rest > PLACE_TOL:
            lbad.append("%s place %.6f turn %.6f" % (el["name"], place, rest))
        if spot:
            half = math.radians(el["cone"])
            if not near(g.get("spot_size"), 2.0 * half) or \
                    not near(g.get("spot_blend"), el["softness"] / (1.0 - math.cos(half))):
                lbad.append("%s cone %s blend %s" % (el["name"], g.get("spot_size"), g.get("spot_blend")))
    c["the lamps give Remix the capture's lights%s" % ("" if not lbad else ": " + "; ".join(lbad[:3]))] = not lbad
    cam = S.get("camera_data") or {}
    place, rest = mdiff(cam.get("matrix"), E["camera"]["matrix"])
    c["the camera: lens %s, sensor %s, place %.6f, turn %.6f" % (cam.get("lens"), cam.get("sensor_width"), place,
                                                                 rest)] = \
        S.get("camera") == "Camera" and near(cam.get("lens"), E["camera"]["focal_length"]) and \
        near(cam.get("sensor_width"), E["camera"]["horizontal_aperture"]) and place <= PLACE_TOL and rest <= PLACE_TOL
    cap = S.get("capture") or {}
    c["the capture's units and up axis kept with the scene (%s m a unit, Z up %s)" % (
        cap.get("meters_per_unit"), cap.get("z_up"))] = \
        near(cap.get("meters_per_unit"), mpu, 1e-9) and cap.get("z_up") == (1 if z_up else 0) and \
        bool(cap.get("path")) and S.get("pipeline") == 1
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    d = {"counts": n, "log": got.get("log"), "error": got.get("error"), "traceback": got.get("traceback"),
         "materials": {k: {x: v.get(x) for x in ("remix_type", "values", "kept")} for k, v in mats.items()},
         "lamps": lamps, "camera": cam, "capture": cap}
    return c, d


def t_selftest(args, out, tests):
    name = "T12.a1 The bridge's OpenUSD on this PC"
    res = os.path.join(out, "p12a_selftest.json")
    got = blender(args, out, "p12a_selftest", ["selftest", os.path.join(out, "usd_selftest"), res])
    lines = (got.get("report") or "").splitlines()
    c = {"OpenUSD %s started in our Blender" % got.get("version"): got.get("version") == "25.11",
         "every self-test check passed (%d)" % len(lines): got.get("failed") == 0 and len(lines) >= 30,
         "no crash": got.get("exit") == 0}
    tests[name] = _test(c, {"report": lines, "traceback": got.get("traceback")})


def t_room(args, out, tests):
    name = "T12.a2 The room comes in"
    E = write(out, "room")
    got = import_capture(args, out, "p12a_room", E["path"])
    c, d = check_room(got, E, 1.0, True)
    tests[name] = _test(c, d)


def t_units(args, out, tests):
    name = "T12.a3 Y up in centimetres comes in at the same places"
    E = write(out, "room_cm_yup")
    got = import_capture(args, out, "p12a_cm_yup", E["path"])
    c, d = check_room(got, E, 0.01, False)
    tests[name] = _test(c, d)


def t_broken(args, out, tests):
    name = "T12.a4 Broken captures: reported by name, no crash"
    E = write(out, "broken")
    P = E["paths"]
    c, d, runs = {}, {}, []
    g = import_capture(args, out, "p12a_missing", P["missing_texture"])
    runs.append(g)
    S = g.get("scene") or {}
    box = (S.get("materials") or {}).get("mat_" + cw.MAT["Box"]) or {}
    said = [l for l in g.get("log") or [] if cw.MAT["Box"] + ".dds" in l and "missing" in l]
    c["a missing texture: it came in"] = g.get("result") == ["FINISHED"] and (S.get("counts") or {}).get("objects") == 11
    c["  the Box material came in without it"] = bool(box) and "Albedo" not in (box.get("linked") or {})
    c["  and the report names it"] = bool(said)
    d["missing_texture"] = g.get("log")
    g = import_capture(args, out, "p12a_cut", P["cut_mesh"])
    runs.append(g)
    S = g.get("scene") or {}
    n = S.get("counts") or {}
    said = [l for l in g.get("log") or [] if "mesh_" + cw.SPHERE in l]
    c["a mesh file cut short: the rest came in (%s meshes, %s objects; want 1, 10)" % (n.get("meshes"),
                                                                                     n.get("objects"))] = \
        g.get("result") == ["FINISHED"] and (n.get("meshes"), n.get("objects")) == (1, 10)
    c["  and the report names the sphere's mesh"] = bool(said)
    d["cut_mesh"] = g.get("log")
    g = import_capture(args, out, "p12a_plain", P["not_a_capture"])
    runs.append(g)
    c["a USD file that is no capture: refused with a message (%s)" % (g.get("error") or "")[:90]] = \
        g.get("result") == ["CANCELLED"] and "not an RTX Remix capture" in (g.get("error") or "") and \
        not g.get("scene")
    c["no crash"] = all(x.get("exit") == 0 and "traceback" not in x for x in runs)
    d["not_a_capture"] = g.get("error")
    tests[name] = _test(c, d)


def _imported_blend(args, out, tag):
    E = write(out, "room")
    blend = os.path.join(out, tag + ".blend")
    if os.path.isfile(blend):
        os.remove(blend)
    got = import_capture(args, out, tag + "_import", E["path"], save=blend)
    return E, (blend if os.path.isfile(blend) else None), got


def mock_value(m, key):
    try:
        return [float(x) for x in m.get(key, "").split(",")]
    except ValueError:
        return []


def t_plays(args, out, tests):
    name = "T12.a5 The imported room plays (the fake runtime)"
    if not getattr(args, "mock", None):
        tests[name] = _test({"the fake runtime (--mock) was given": False})
        return
    E, blend, got = _imported_blend(args, out, "p12a_imported_mock")
    c = {"the imported room saved to play": bool(blend)}
    if not blend:
        tests[name] = _test(c, {"import": got.get("error"), "traceback": got.get("traceback")})
        return
    tag = "p12a_plays_mock"
    cache = os.path.join(out, tag + "_cache")
    shutil.rmtree(cache, ignore_errors=True)
    os.makedirs(cache)
    log, env = p8.mock_env(args, out, tag, cache)
    run = r9.pipe_play(args.ours, out, tag, blend, env, seconds=10)
    lines = r9.mock_lines(log)
    st = run.get("stats") or {}
    mats = r9.mock_materials(lines)
    lights = [l for l in lines if l.startswith("CreateLight ")]
    c["Remix drew it (the fake runtime)"] = run.get("exit") == 0 and st.get("running") is True

    def opaque(alb, rough, metal):
        return any(m.get("type") == "opaque" and near(mock_value(m, "albedo"), alb, 0.003) and
                   near(m.get("roughness"), rough, 0.002) and near(m.get("metallic"), metal, 0.002) for m in mats)
    room = cw.MATERIALS["Room"]["inputs"]
    sph = cw.MATERIALS["Sphere"]["inputs"]
    gl = cw.MATERIALS["Glass"]["inputs"]
    c["the room's material as the capture had it (albedo %s)" % (room["diffuse_color_constant"][1],)] = \
        opaque(room["diffuse_color_constant"][1], 0.8, 0.0)
    c["the sphere's: metal, roughness 0.2, its glow"] = opaque(sph["diffuse_color_constant"][1], 0.2, 1.0) and \
        any(near(mock_value(m, "emissive"), sph["emissive_color_constant"][1], 0.003) and
            near(m.get("intensity"), 0.5, 0.002) for m in mats)
    c["the glass: translucent, IOR 1.5, its colour and distance"] = any(
        m.get("type") == "translucent" and near(m.get("ior"), 1.5, 0.002) and
        near(mock_value(m, "transmittance"), gl["transmittance_color"][1], 0.003) and
        near(m.get("distance"), 0.5, 0.002) for m in mats)

    def light(want_pos, radiance, shaped, cone=None, soft=None):
        for l in lights:
            d = dict(p.split("=", 1) for p in l.split(" ")[1:] if "=" in p)
            if d.get("type") != "sphere":
                continue
            pos = [float(x) for x in d.get("pos", "0,0,0").split(",")]
            rad = [float(x) for x in d.get("radiance", "0,0,0").split(",")]
            if not near(pos, want_pos, 0.002) or d.get("shaped") != ("1" if shaped else "0"):
                continue
            if not all(abs(a - b) <= 0.01 * max(b, 1.0) for a, b in zip(rad, radiance)):
                continue
            if shaped and not (near(d.get("cone"), cone, 0.01) and near(d.get("softness"), soft, 0.002)):
                continue
            return True
        return False
    a, b = cw.LAMPS
    c["lamp A sent back as the capture's light: a sphere, radiance %s" % (a[5],)] = \
        light(a[2], [a[5] * x for x in a[4]], False)
    c["lamp B as the capture's spot: cone %s, softness %s" % (b[6], b[7])] = \
        light(b[2], [b[5] * x for x in b[4]], True, b[6], b[7])
    tests[name] = _test(c, {"materials": mats, "lights": lights, "stats": {k: st.get(k) for k in ("running",)}})


def normal(args, out, scenes, E, tests, sheets):
    only = _only()
    for key, fn in (("selftest", t_selftest), ("room", t_room), ("units", t_units), ("broken", t_broken),
                    ("plays", t_plays)):
        if not only or key in only:
            try:
                fn(args, out, tests)
            except Exception:
                import traceback
                tests["%s ran" % key] = _test({"ran without an error": False}, traceback.format_exc())


def rtx(args, out, scenes, E, tests, sheets, report):
    name = "S12.a1 The room and the imported room in Remix (a picture pair)"
    P = (E.get("p12a") or {}).get("room")
    if not P:
        tests[name] = _test({"the scenes were made": False})
        return
    _E, blend, got = _imported_blend(args, out, "p12a_imported_rtx")
    env = {"RTX_ENABLE_ASYNC_COMPILATION": "0", "BGE_REMIX_P2_FROM_REMIX": "1"}
    runs = {}
    for tag, path in (("p12a_room_rtx", os.path.join(scenes, P["file"])), ("p12a_imported_rtx", blend)):
        if not path:
            runs[tag] = {}
            continue
        runs[tag] = p8.play(args.ours, out, tag, path, env, frames=200, seconds=12, gl_debug=False)
    c = {"the imported room saved to play": bool(blend)}
    for tag, label in (("p12a_room_rtx", "the room"), ("p12a_imported_rtx", "the imported room")):
        r = runs.get(tag) or {}
        st = r.get("stats") or {}
        c["%s ran with Remix drawing" % label] = r.get("exit") == 0 and st.get("running") is True and \
            bool(r.get("screenshot"))
    sheet = os.path.join(out, "sheet_p12a_room.png")
    p2.contact_sheet([("the room (made in Blender)", (runs.get("p12a_room_rtx") or {}).get("screenshot")),
                      ("the room imported from its capture", (runs.get("p12a_imported_rtx") or {}).get("screenshot"))],
                     sheet)
    sheets["p12a_room"] = sheet if os.path.isfile(sheet) else None
    tests[name] = _test(c, {"import": got.get("error"), "exits": {k: v.get("exit") for k, v in runs.items()}})
    report += ["", "S12.a1: the room and the imported room in Remix, side by side: %s" % sheet]
