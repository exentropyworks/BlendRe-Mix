"""BGE-Remix P12 Part A: Remix modding, the tests (run by run_p12.py).

The captures are written here by capture_writer.py (no game, no Remix); our
Blender imports them (p12a_probe.py, background) and what came in is set
against what was written.

normal(...)
  T12.a1  the bridge's OpenUSD on this PC: round 1's self-test, from this
          build (bge_remix_usd.dll loaded, a stage written and read back)
  T12.a2  the room comes in: counts exact; parts of the same shape on one
          mesh (the box drawn twice), each object's material its own;
          every place within 0.1 mm; every
          material value; the textures decoded to PNGs (the uncompressed one
          and the BC1 one, pixel for pixel) with their DDS kept; the lamps as
          lamps that give Remix the same lights; the camera; every hash
  T12.a3  the same room written Y up in centimetres comes in at the same
          places, within 0.1 mm
  T12.a4  broken captures: a missing texture (the material comes in without
          it, named), a mesh file cut short (the sphere left out, named), a
          USD file that is not a capture (a message); no crash
  T12.a5  the imported room plays (the fake runtime): Remix gets its
          materials and lights as the capture had them; every object its
          own material on the one shared mesh (the game converts a shared
          mesh once for each set of materials)
  T12.a6  (round 3) the mod: the room imported, then edited by script (the
          sphere's mesh a bevelled box, its material gold, a lamp and a
          small cube parented to it, a wall moved), File > Export > RTX Remix
          Mod, the mod read back with our OpenUSD: the sphere's mesh replaced
          (the game's own switched off) by the box in the capture's units,
          the gold at the sphere's material hash, the lamp and the cube under
          the sphere's mesh hash placed relative to it, nothing else in the
          mod, the moved wall named in the report
  T12.a7  the same edits on the Y-up centimetre capture: the mod in
          centimetres, Y up, with the same shapes and places
  T12.a8  edge cases: nothing changed says so and writes nothing; a scene
          not from a capture is refused with a message; a painted texture
          is written as DDS and reads back
  T12.b1  (round 4) the asset for the Remix Toolkit: the room's box and
          sphere (its material gold) exported: the FBX holds the two meshes
          (vertices, size, read back with Blender's FBX importer); each
          material's pictures as named PNGs: the box's picture as it was,
          one-colour roughness and metallic pictures of the right grey, the
          gold's albedo; the read-me names both materials and their pictures
  T12.b2  what an asset leaves out: a lamp and an Empty in the selection are
          named in the report; nothing selected gives a message
  T12.c1  (round 5) the Remix View's Remix layer of a capture scene: the
          room imported and edited (round 3's edits, a small cube with a
          Classic material under the box, a cone on its own), its Remix View
          built in a window: every imported object, material and lamp shows
          its capture hash and what the mod does with it; the added ones
          "added to mesh ..."; three notes (the moved wall, the cone not
          parented, the Classic material left out) and no other; the room as
          it came in: every hash, nothing replaced, no notes
  T12.c2  the view and the export agree: the same scene exported as a mod;
          what the view says is replaced or added is what the mod holds, and
          the view's notes are the export's report, line for line
rtx(...)
  S12.a1  the room and the imported room in Remix, a picture pair
  S12.b1  the blend check: an orange quad with Add blending over a dark wall
          brightens the wall behind it, in the game's OpenGL and in Remix
          (Remix getting blend type 8 would darken it: an engine problem)

BGE_REMIX_P12A_ONLY (comma separated: selftest, room, units, broken, plays,
mod, modunits, modedges, asset, assetedges, view; for the RTX run: room,
blend)
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
    got["log"] = [l for l in (text or "").splitlines()
                  if l.startswith(("BGE-Remix capture import: ", "BGE-Remix mod export: "))]
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
    c["every object on its mesh, its own material on the object, with its hash%s" % (
        "" if not wrong else ": " + ", ".join(wrong[:4]))] = not wrong
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
        bool(S.get("camera")) and S.get("camera") == cam.get("name") and near(cam.get("lens"), E["camera"]["focal_length"]) and \
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
    c["a mesh file cut short: the rest came in (%s meshes, %s objects; want 1, 10)" % (
        n.get("meshes"), n.get("objects"))] = \
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
    textured = [m for m in mats if (m.get("albedo_tex") or "-") != "-"]
    c["all five materials sent, the box's and the brick's with their pictures (%d, %d with a picture)" % (
        len(set(m.get("hash") for m in mats)), len(textured))] = \
        len(set(m.get("hash") for m in mats)) >= 5 and len(set(m.get("hash") for m in textured)) >= 2
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


# ---------------------------------------------------------------------------
# round 3: File > Export > RTX Remix Mod

def srgb(c):
    c = min(max(float(c), 0.0), 1.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def k_matrix(mpu, z_up):
    """K: the capture's space into Blender's (the import's)"""
    S = [[mpu, 0.0, 0.0, 0.0], [0.0, mpu, 0.0, 0.0], [0.0, 0.0, mpu, 0.0], [0.0, 0.0, 0.0, 1.0]]
    if z_up:
        return S
    R = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
    return cw.mat_mul(R, S)


def from_usd(u):
    """USD's 16 numbers (rows) as a 4 x 4 (column vectors)"""
    return [[float(u[c * 4 + r]) for c in range(4)] for r in range(4)] if u and len(u) == 16 else None


def box_bounds(half, Kinv):
    """a box of half sizes in Blender's space, in the capture's: [min, max]"""
    pts = [[sx * half[0], sy * half[1], sz * half[2]] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    q = [[sum(Kinv[r][c] * p[c] for c in range(3)) for r in range(3)] for p in pts]
    return [[min(p[i] for p in q) for i in range(3)], [max(p[i] for p in q) for i in range(3)]]


def export_mod(args, out, tag, capture, edits, extra=()):
    res = os.path.join(out, tag + "_probe.json")
    folder = os.path.join(out, tag + "_mod")
    return blender(args, out, tag, ["export", capture, res, folder, edits] + list(extra))


def _prims(got):
    return {p["path"]: p for p in ((got.get("dump") or {}).get("prims") or ())}


def _attr(prims, path, name):
    return ((prims.get(path) or {}).get("attrs") or {}).get(name) or {}


def _bounds_near(got, want, tol):
    try:
        return all(abs(float(got[i][k]) - want[i][k]) <= tol for i in range(2) for k in range(3))
    except (TypeError, IndexError, KeyError, ValueError):
        return False


def check_mod(got, E, mpu, z_up):
    """the room's mod (the round 3 edits) read back: (checks, detail)"""
    c = {}
    ed = got.get("edits") or {}
    dump = got.get("dump") or {}
    prims = _prims(got)
    last = got.get("last") or {}
    K = k_matrix(mpu, z_up)
    Kinv = cw.mat_inv_affine(K)
    Sinv = [[1.0 / mpu, 0, 0, 0], [0, 1.0 / mpu, 0, 0], [0, 0, 1.0 / mpu, 0], [0, 0, 0, 1.0]]
    tol = PLACE_TOL / mpu   # 0.1 mm in the capture's units
    c["exported (%s), mod.usda written" % got.get("result")] = got.get("result") == ["FINISHED"] and \
        bool(last.get("path"))
    c["read back with our OpenUSD, no complaint (%s)" % "; ".join(dump.get("errors") or [])[:120]] = \
        bool(got.get("dump_ok")) and dump.get("ok") is True and not dump.get("errors")
    c["a Remix replacement layer, its default prim RootNode, in the capture's units (%s m, %s up)" % (
        dump.get("meters_per_unit"), dump.get("up_axis"))] = \
        (dump.get("custom_layer_data") or {}).get("lightspeed_layer_type") == "replacement" and \
        dump.get("default_prim") == "RootNode" and near(dump.get("meters_per_unit"), mpu, 1e-9) and \
        dump.get("up_axis") == ("Z" if z_up else "Y")
    # the sphere's mesh replaced by the box
    base = "/RootNode/meshes/mesh_" + cw.SPHERE
    box = ed.get("box") or {}
    pts = _attr(prims, base + "/replacement", "points").get("value") or {}
    counts = _attr(prims, base + "/replacement", "faceVertexCounts").get("value") or {}
    st = _attr(prims, base + "/replacement", "primvars:st").get("value") or {}
    want_b = box_bounds(box.get("half") or [0, 0, 0], Kinv)
    c["the sphere's mesh replaced, the game's own switched off (preserveOriginalDrawCall %s)" % (
        _attr(prims, base, "preserveOriginalDrawCall").get("value"),)] = \
        _attr(prims, base, "preserveOriginalDrawCall").get("value") == 0 and \
        (prims.get(base + "/replacement") or {}).get("type") == "Mesh"
    c["  by the bevelled box: %s points, %s faces, %s UVs (want %s, %s, %s)" % (
        pts.get("count"), counts.get("count"), st.get("count"), box.get("vertices"), box.get("polygons"),
        box.get("loops"))] = \
        bool(box) and (pts.get("count"), counts.get("count"), st.get("count")) == \
        (box.get("vertices"), box.get("polygons"), box.get("loops"))
    c["  in the capture's units and axes (bounds %s, want %s)" % (
        pts.get("bounds"), [[round(x, 3) for x in r] for r in want_b])] = _bounds_near(pts.get("bounds"), want_b, tol)
    # the gold
    shader = "/RootNode/Looks/mat_%s/Shader" % cw.MAT["Sphere"]
    gold = ed.get("gold") or {}
    alb = _attr(prims, shader, "inputs:diffuse_color_constant")
    want_alb = [srgb(x) for x in gold.get("albedo") or [0, 0, 0]]
    c["the gold at the sphere's material hash: albedo %s (sRGB, want %s), metal, roughness 0.25, no glow" % (
        alb.get("value"), [round(x, 4) for x in want_alb])] = \
        alb.get("type") == "color3f" and near(alb.get("value"), want_alb, 1e-3) and \
        near(_attr(prims, shader, "inputs:metallic_constant").get("value"), 1.0) and \
        near(_attr(prims, shader, "inputs:reflection_roughness_constant").get("value"), 0.25) and \
        _attr(prims, shader, "inputs:enable_emission").get("value") is False and \
        (_attr(prims, shader, "info:mdl:sourceAsset").get("value") or {}).get("asset") == "AperturePBR_Opacity.mdl"
    # the lamp and the cube under the sphere's mesh, placed relative to it
    M = ed.get("sphere_matrix")

    def placed(name, world):
        T = from_usd((prims.get(base + "/" + name) or {}).get("local_to_world"))
        if not T or not M or not world:
            return (1e9, 1e9)
        # a mesh's place: M K T K^-1; a lamp's (USD's rule: its axes turn
        # with the space, round 6 fix 1): M K T S^-1
        last = Sinv if name == lamp.get("name") else Kinv
        return mdiff(cw.mat_mul(cw.mat_mul(cw.mat_mul(M, K), T), last), world)
    lamp, cube = ed.get("lamp") or {}, ed.get("cube") or {}
    lp = _prims_type(prims, base + "/" + str(lamp.get("name")))
    lplace = placed(lamp.get("name"), lamp.get("world"))
    inten = _attr(prims, base + "/" + str(lamp.get("name")), "inputs:intensity").get("value")
    rad = _attr(prims, base + "/" + str(lamp.get("name")), "inputs:radius").get("value")
    want_i = (lamp.get("energy") or 0) * (lamp.get("distance") or 0) ** 2 / max(lamp.get("radius") or 1, 1e-9) ** 2
    c["the lamp under the sphere's mesh: a %s, where it was put (%.6f m, turn %.6f), intensity %s, radius %s "
      "(want %.1f, %s)" % (lp, lplace[0], lplace[1], inten, rad, want_i, (lamp.get("radius") or 0) / mpu)] = \
        lp == "SphereLight" and lplace[0] <= PLACE_TOL and lplace[1] <= PLACE_TOL and \
        near(inten, want_i, want_i * 1e-3) and near(rad, (lamp.get("radius") or 0) / mpu, 1e-4 / mpu)
    cplace = placed(cube.get("name"), cube.get("world"))
    cpath = base + "/" + str(cube.get("name"))
    cpts = _attr(prims, cpath, "points").get("value") or {}
    h = cube.get("half") or 0.0
    rel = ((prims.get(cpath) or {}).get("rels") or {}).get("material:binding")
    red = "/RootNode/BGE_Remix_Looks/" + str(cube.get("material"))
    c["the small cube under it: where it was put (%.6f m, turn %.6f), its size (bounds %s)" % (
        cplace[0], cplace[1], cpts.get("bounds"))] = \
        _prims_type(prims, cpath) == "Mesh" and cplace[0] <= PLACE_TOL and cplace[1] <= PLACE_TOL and \
        _bounds_near(cpts.get("bounds"), box_bounds([h, h, h], Kinv), tol)
    c["  bound to its own material in the mod (%s), red" % rel] = rel == [red] and \
        near(_attr(prims, red + "/Shader", "inputs:diffuse_color_constant").get("value"), [1.0, 0.0, 0.0], 1e-4)
    # nothing else
    want = {"/RootNode", "/RootNode/Looks", "/RootNode/Looks/mat_" + cw.MAT["Sphere"], shader,
            "/RootNode/BGE_Remix_Looks", red, red + "/Shader", "/RootNode/meshes", base, base + "/replacement",
            cpath, base + "/" + str(lamp.get("name"))}
    extra = sorted(set(p for p in prims if p.startswith("/RootNode")) - want)
    missing = sorted(want - set(prims))
    c["nothing else in the mod%s%s" % (": " + ", ".join(extra[:4]) if extra else "",
                                       "; missing " + ", ".join(missing[:4]) if missing else "")] = \
        bool(prims) and not extra and not missing
    rep = last.get("report") or []
    wall = ed.get("wall") or "?"
    c["the report names the moved wall (%s), and nothing else (%d note(s))" % (wall, len(rep))] = \
        len(rep) == 1 and wall in rep[0] and "moved" in rep[0]
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    d = {"report": rep, "counts": last.get("counts"), "error": got.get("error"), "traceback": got.get("traceback"),
         "prims": sorted(prims), "edits": ed}
    return c, d


def _prims_type(prims, path):
    return (prims.get(path) or {}).get("type")


def _places(E):
    by = {o["part"]: o["name"] for o in E["objects"]}
    return [by["Sphere"], by["WallE"]]


def t_mod(args, out, tests):
    name = "T12.a6 The mod: edits to the room go out as a Remix mod"
    E = write(out, "room")
    got = export_mod(args, out, "p12a_mod", E["path"], "room", _places(E))
    c, d = check_mod(got, E, 1.0, True)
    tests[name] = _test(c, d)


def t_mod_units(args, out, tests):
    name = "T12.a7 The mod of a Y-up centimetre capture: centimetres, Y up"
    E = write(out, "room_cm_yup")
    got = export_mod(args, out, "p12a_mod_cm_yup", E["path"], "room", _places(E))
    c, d = check_mod(got, E, 0.01, False)
    tests[name] = _test(c, d)


def t_mod_edges(args, out, tests):
    name = "T12.a8 The mod's edge cases"
    E = write(out, "room")
    c, d, runs = {}, {}, []
    g = export_mod(args, out, "p12a_mod_none", E["path"], "none")
    runs.append(g)
    last = g.get("last") or {}
    c["nothing changed: it says so (%s) and writes nothing" % (g.get("log") or ["-"])[-1:]] = \
        g.get("result") == ["FINISHED"] and not last.get("path") and not g.get("folder_exists") and \
        any("nothing changed" in l for l in g.get("log") or [])
    c["  no note: every fingerprint as it came in (%d note(s))" % len(last.get("report") or [])] = \
        not last.get("report")
    d["nothing_changed"] = {"report": last.get("report"), "log": g.get("log"), "traceback": g.get("traceback")}
    g = export_mod(args, out, "p12a_mod_plain", E["path"], "plain")
    runs.append(g)
    c["a scene not from a capture: refused with a message (%s)" % (g.get("error") or "")[:90]] = \
        g.get("result") == ["CANCELLED"] and "did not come from an RTX Remix capture" in (g.get("error") or "") and \
        not g.get("folder_exists")
    d["plain"] = g.get("error")
    g = export_mod(args, out, "p12a_mod_texture", E["path"], "texture")
    runs.append(g)
    prims = _prims(g)
    shader = "/RootNode/Looks/mat_%s/Shader" % cw.MAT["Box"]
    tex = (_attr(prims, shader, "inputs:diffuse_texture").get("value") or {})
    files = g.get("textures") or {}
    one = list(files.values())[0] if len(files) == 1 else {}
    size = one.get("size") or [0, 0]

    def row_is(row, colour):
        return bool(row) and all(all(abs(p[k] - colour[k]) <= 12 for k in range(3)) for p in row)
    c["a painted texture: the box's material replaced, its picture a DDS in the mod (%s)" % tex.get("asset")] = \
        g.get("result") == ["FINISHED"] and bool(tex.get("resolved")) and \
        str(tex.get("asset", "")).startswith("./textures/") and str(tex.get("asset", "")).endswith(".dds") and \
        len(files) == 1 and bool(one.get("ok"))
    c["  it reads back as painted, the right way up (%s: top red, bottom blue)" % (size,)] = \
        size == (g.get("edits") or {}).get("size") and row_is(one.get("top"), (255, 0, 0)) and \
        row_is(one.get("bottom"), (0, 0, 255))
    others = sorted(p for p in prims if p.startswith("/RootNode/") and not p.startswith("/RootNode/Looks"))
    c["  nothing else in the mod%s" % (": " + ", ".join(others[:4]) if others else "")] = bool(prims) and not others
    d["texture"] = {"files": {k: {x: v.get(x) for x in ("ok", "error", "size")} for k, v in files.items()},
                    "report": (g.get("last") or {}).get("report"), "error": g.get("error"),
                    "traceback": g.get("traceback")}
    c["no crash"] = all(x.get("exit") == 0 and "traceback" not in x for x in runs)
    tests[name] = _test(c, d)


# ---------------------------------------------------------------------------
# round 4: File > Export > RTX Remix Asset (for the Toolkit)

def export_asset(args, out, tag, capture, case, E):
    res = os.path.join(out, tag + "_probe.json")
    folder = os.path.join(out, tag + "_asset")
    by = {o["part"]: o["name"] for o in E["objects"]}
    return blender(args, out, tag, ["asset", capture, res, folder, case, by["Box"], by["Sphere"],
                                    "light_" + cw.LIGHT_A])


def _grey(px, v, tol=2):
    return bool(px) and all(abs(px[k] - v) <= tol for k in range(3))


def t_asset(args, out, tests):
    name = "T12.b1 The asset for the Remix Toolkit"
    E = write(out, "room")
    got = export_asset(args, out, "p12a_asset", E["path"], "room", E)
    c = {}
    last = got.get("last") or {}
    want = got.get("want") or {}
    files = got.get("files") or []
    pics = got.get("pictures") or {}
    asset = last.get("name") or "?"
    c["exported (%s): %s" % (got.get("result"), ", ".join(files))] = got.get("result") == ["FINISHED"] and \
        (asset + ".fbx") in files and (asset + "_readme.txt") in files
    fbx = got.get("fbx") or {}
    meshes = [v for v in fbx.values() if v.get("type") == 'MESH']

    def found(w):
        return any(m.get("vertices") == w.get("vertices") and near(m.get("dimensions"), w.get("dimensions"), 1e-3)
                   for m in meshes)
    b, sp = want.get("box") or {}, want.get("sphere") or {}
    c["the FBX holds the two meshes (%s), the box's %s and the sphere's %s vertices at their sizes" % (
        len(meshes), b.get("vertices"), sp.get("vertices"))] = \
        len(meshes) == 2 and bool(b) and bool(sp) and found(b) and found(sp)
    bm, sm = b.get("material", "?"), sp.get("material", "?")
    T = E["textures"]
    alb = pics.get(bm + "_albedo.png") or {}
    c["the box's albedo: its picture as it was (%s)" % (alb.get("size"),)] = \
        alb.get("size") == [T["size"], T["size"]] and pixels_match(alb.get("top"), T["rgba"])
    rough = (pics.get(bm + "_roughness.png") or {}).get("centre")
    metal = (pics.get(bm + "_metallic.png") or {}).get("centre")
    c["the box's roughness 0.55 and metallic 0 as one-colour pictures (%s, %s; want 140, 0)" % (
        rough and rough[0], metal and metal[0])] = _grey(rough, 140) and _grey(metal, 0)
    gold = (pics.get(sm + "_albedo.png") or {}).get("centre")
    want_gold = [int(round(srgb(x) * 255.0)) for x in (1.0, 0.766, 0.336)]
    grough = (pics.get(sm + "_roughness.png") or {}).get("centre")
    gmetal = (pics.get(sm + "_metallic.png") or {}).get("centre")
    c["the gold: albedo %s (sRGB, want %s), roughness %s (want 64), metallic %s (want 255)" % (
        gold and gold[:3], want_gold, grough and grough[0], gmetal and gmetal[0])] = \
        bool(gold) and all(abs(gold[k] - want_gold[k]) <= 2 for k in range(3)) and _grey(grough, 64) and \
        _grey(gmetal, 255)
    extra = sorted(p for p in pics if p not in (bm + "_albedo.png", bm + "_roughness.png", bm + "_metallic.png",
                                                sm + "_albedo.png", sm + "_roughness.png", sm + "_metallic.png"))
    c["no other pictures (no glow: no emissive one)%s" % (": " + ", ".join(extra) if extra else "")] = \
        len(pics) == 6 and not extra
    readme = got.get("readme") or ""
    c["the read-me names both materials, their pictures and the Toolkit's types"] = \
        all(x in readme for x in (bm, sm, bm + "_albedo.png", sm + "_metallic.png", "Normal - OpenGL",
                                  "type: Roughness"))
    c["nothing left out (%d note(s))" % len(last.get("report") or [])] = not last.get("report")
    c["no crash"] = got.get("exit") == 0 and "traceback" not in got
    tests[name] = _test(c, {"files": files, "pictures": {k: v.get("centre") for k, v in pics.items()},
                            "fbx": fbx, "want": want, "report": last.get("report"), "error": got.get("error"),
                            "fbx_error": got.get("fbx_error"), "traceback": got.get("traceback")})


def t_asset_edges(args, out, tests):
    name = "T12.b2 What an asset leaves out"
    E = write(out, "room")
    c, runs = {}, []
    g = export_asset(args, out, "p12a_asset_leftout", E["path"], "leftout", E)
    runs.append(g)
    rep = (g.get("last") or {}).get("report") or []
    want = g.get("want") or {}
    c["a lamp and an Empty selected: the box exported (%s)" % g.get("result")] = \
        g.get("result") == ["FINISHED"] and ((g.get("last") or {}).get("counts") or {}).get("meshes") == 1
    c["  the report names the lamp and the Empty (%d note(s))" % len(rep)] = \
        any(want.get("lamp", "?") in l and "lamp" in l for l in rep) and \
        any(want.get("empty", "?") in l and "empty" in l for l in rep) and len(rep) == 2
    g2 = export_asset(args, out, "p12a_asset_nothing", E["path"], "nothing", E)
    runs.append(g2)
    c["nothing selected: refused with a message (%s)" % (g2.get("error") or "")[:90]] = \
        g2.get("result") == ["CANCELLED"] and "no mesh is selected" in (g2.get("error") or "") and \
        not g2.get("folder_exists")
    c["no crash"] = all(x.get("exit") == 0 and "traceback" not in x for x in runs)
    tests[name] = _test(c, {"report": rep, "error": g2.get("error"), "tracebacks": [x.get("traceback") for x in runs]})


# ---------------------------------------------------------------------------
# round 5: the Remix View of a capture scene

VIEW_PROBE = os.path.join(HERE, "p12a_view_probe.py")


def view_run(args, out, tag, blend, layer=None):
    """our Blender with its window on blend: the Remix layer (or, round 8,
    another one), built"""
    res = os.path.join(out, tag + "_view.json")
    if os.path.isfile(res):
        os.remove(res)
    e = p2.base_env(out, tag)
    e.update(p8.GL_ENV)
    e["BGE_REMIX_P12V_OUT"] = res
    if layer:
        e["BGE_REMIX_P12V_LAYER"] = layer
    code, text, secs = p2.run([p2.exe(args.ours, "blender"), "--disable-crash-handler"] + p8.WINDOW +
                              [blend, "--python", VIEW_PROBE], e, os.path.join(out, tag + ".log"), timeout=600,
                              cwd=out)
    r = p2.read_json(res) or {}
    r.update({"exit": code, "seconds": round(secs, 1)})
    r["ran"] = code == 0 and bool(r.get("finished"))
    if not r["ran"]:
        r["console tail"] = (text or "").splitlines()[-25:]
    return r


def view_file(args, out, tag, E, case):
    blend = os.path.join(out, tag + ".blend")
    if os.path.isfile(blend):
        os.remove(blend)
    by = {o["part"]: o["name"] for o in E["objects"]}
    res = os.path.join(out, tag + "_probe.json")
    got = blender(args, out, tag + "_make", ["viewfile", E["path"], res, blend, case, by["Sphere"], by["WallE"],
                                             by["Box"]])
    return got, (blend if os.path.isfile(blend) else None)


def _infos(view):
    """element kind -> owner -> [info lines] (the Remix layer)"""
    out = {}
    for e in ((view.get("steps") or {}).get("build") or {}).get("elements") or []:
        out.setdefault(e.get("kind"), {}).setdefault(e.get("owner"), []).append(e.get("info") or "")
    return out


def _mod_notes(view):
    return [w for w in ((view.get("steps") or {}).get("build") or {}).get("warnings") or []
            if (w.get("code") or "").startswith("RMX_MOD_")]


def t_view(args, out, tests):
    name = "T12.c1 The Remix View of a capture scene"
    name2 = "T12.c2 The Remix View and the mod export agree"
    E = write(out, "room")
    c, d = {}, {}
    got, blend = view_file(args, out, "p12a_view_room", E, "room")
    ed = got.get("edits") or {}
    c["the edited room imported, exported and saved with a Remix View (%s screen(s))" % got.get("screens")] = \
        bool(blend) and bool(got.get("screens")) and "traceback" not in got
    view = view_run(args, out, "p12a_view_room_run", blend) if blend else {}
    infos = _infos(view)
    meshes, mats, lights = infos.get("remix:MESH") or {}, infos.get("remix:MATERIAL") or {}, \
        infos.get("remix:LIGHT") or {}
    c["the Remix View was built in the window"] = bool(view.get("ran")) and bool(meshes)
    by = {o["part"]: o for o in E["objects"]}

    def says(table, owner, text):
        return any(text in line for line in table.get(owner) or [])
    sphere, box = by["Sphere"], by["Box"]
    c["the sphere's mesh: its hash, the mod replaces it"] = \
        says(meshes, sphere["name"], "capture mesh %s: the mod replaces it" % cw.SPHERE)
    c["the box's mesh: its hash, the mod adds 1 object to it (the Classic cube)"] = \
        says(meshes, box["name"], "capture mesh %s: the mod adds 1 object to it" % cw.CUBE)
    own = [o for o in E["objects"] if o["part"] not in ("Sphere", "Box")]
    bad = [o["part"] for o in own if not says(meshes, o["name"], "capture mesh %s: the game's own" % o["mesh"])]
    c["every other place: its hash, the game's own%s" % (": not " + ", ".join(bad) if bad else "")] = not bad
    gold = "mat_" + cw.MAT["Sphere"]
    c["the gold material: its hash, the mod replaces it"] = \
        says(mats, sphere["name"], "capture material %s: the mod replaces it" % cw.MAT["Sphere"])
    c["the room's material: its hash, the game's own"] = \
        says(mats, by["WallN"]["name"], "capture material %s: the game's own" % cw.MAT["Room"])
    lamp, cube, classic = ed.get("lamp") or {}, ed.get("cube") or {}, ed.get("classic") or {}
    c["the lamp and the two small cubes: added to their meshes by the mod"] = \
        says(lights, lamp.get("name"), "added to mesh %s by the mod" % cw.SPHERE) and \
        says(meshes, cube.get("name"), "added to mesh %s by the mod" % cw.SPHERE) and \
        says(meshes, classic.get("name"), "added to mesh %s by the mod" % cw.CUBE)
    c["the capture's lamps: their hashes, the game's own"] = all(
        says(lights, "light_" + l["hash"], "capture light %s: the game's own" % l["hash"]) for l in E["lamps"])
    notes = _mod_notes(view)
    texts = sorted(n["text"] for n in notes)
    want = {"moved": ed.get("wall"), "parented": ed.get("cone"), "not an RTX Remix material": classic.get("material")}
    found = {k: any(k in t and str(v) in t for t in texts) for k, v in want.items()}
    c["three notes: the moved wall, the cone not parented, the Classic material (%d note(s))" % len(notes)] = \
        len(notes) == 3 and all(found.values())
    d["room"] = {"notes": texts, "meshes": meshes, "materials": mats, "lights": lights, "edits": ed,
                 "errors": view.get("errors"), "console tail": view.get("console tail")}
    # T12.c2: the same scene's export
    c2 = {}
    rep = sorted((got.get("export") or {}).get("report") or [])
    c2["the scene exported (%s)" % got.get("export_result")] = got.get("export_result") == ["FINISHED"]
    c2["the view's notes are the export's report, line for line (%d, %d)" % (len(texts), len(rep))] = \
        bool(texts) and texts == rep
    prims = {p["path"]: p.get("type") for p in ((got.get("dump") or {}).get("prims") or [])}
    added = {"/RootNode/meshes/mesh_%s/%s" % (cw.SPHERE, lamp.get("name")): "SphereLight",
             "/RootNode/meshes/mesh_%s/%s" % (cw.SPHERE, cube.get("name")): "Mesh",
             "/RootNode/meshes/mesh_%s/%s" % (cw.CUBE, classic.get("name")): "Mesh",
             "/RootNode/meshes/mesh_%s/replacement" % cw.SPHERE: "Mesh",
             "/RootNode/Looks/%s" % gold: "Material"}
    missing = [p for p, t in added.items() if prims.get(p) != t]
    replaced = sorted(p for p in prims if p.endswith("/replacement"))
    c2["what the view says is replaced or added is in the mod%s" % (
        ": missing " + ", ".join(missing) if missing else "")] = bool(prims) and not missing
    c2["  and nothing else is replaced (%s)" % ", ".join(replaced)] = \
        replaced == ["/RootNode/meshes/mesh_%s/replacement" % cw.SPHERE] and \
        sorted(p for p in prims if p.startswith("/RootNode/Looks/") and p.count("/") == 3) == ["/RootNode/Looks/" + gold]
    c2["no crash"] = got.get("exit") == 0 and "traceback" not in got
    # the room as it came in
    got0, blend0 = view_file(args, out, "p12a_view_none", E, "none")
    view0 = view_run(args, out, "p12a_view_none_run", blend0) if blend0 else {}
    infos0 = _infos(view0)
    m0 = infos0.get("remix:MESH") or {}
    bad0 = [o["part"] for o in E["objects"] if not says(m0, o["name"], "capture mesh %s: the game's own" % o["mesh"])]
    notes0 = _mod_notes(view0)
    c["the room as it came in: every hash, nothing replaced%s" % (": not " + ", ".join(bad0) if bad0 else "")] = \
        bool(view0.get("ran")) and not bad0 and \
        not any("the mod replaces" in l for owner in (infos0.get("remix:MATERIAL") or {}).values() for l in owner)
    c["  no notes (%d)" % len(notes0)] = bool(view0.get("ran")) and not notes0
    c["no crash"] = got.get("exit") == 0 and bool(view.get("ran")) and got0.get("exit") == 0 and \
        bool(view0.get("ran"))
    d["none"] = {"notes": [n["text"] for n in notes0], "errors": view0.get("errors"),
                 "console tail": view0.get("console tail")}
    tests[name] = _test(c, d)
    tests[name2] = _test(c2, {"view": texts, "export": rep, "prims": sorted(prims), "error": got.get("export_error")})


def normal(args, out, scenes, E, tests, sheets):
    only = _only()
    for key, fn in (("selftest", t_selftest), ("room", t_room), ("units", t_units), ("broken", t_broken),
                    ("plays", t_plays), ("mod", t_mod), ("modunits", t_mod_units), ("modedges", t_mod_edges),
                    ("asset", t_asset), ("assetedges", t_asset_edges), ("view", t_view)):
        if not only or key in only:
            try:
                fn(args, out, tests)
            except Exception:
                import traceback
                tests["%s ran" % key] = _test({"ran without an error": False}, traceback.format_exc())


def rtx(args, out, scenes, E, tests, sheets, report):
    only = _only()
    for key, fn in (("room", rtx_room), ("blend", rtx_blend)):
        if not only or key in only:
            try:
                fn(args, out, scenes, E, tests, sheets, report)
            except Exception:
                import traceback
                tests["%s (RTX) ran" % key] = _test({"ran without an error": False}, traceback.format_exc())


def rtx_blend(args, out, scenes, E, tests, sheets, report):
    name = "S12.b1 The blend check: Add blending in the game and in Remix"
    B = (E.get("p12a") or {}).get("blend")
    if not B:
        tests[name] = _test({"the scenes were made": False}, (E.get("failed") or {}).get("p12a_blend"))
        return
    shot = {"BGE_REMIX_P2_SHOT_FRAME": "300"}
    gl = p8.play(args.ours, out, "p12a_blend_gl", os.path.join(scenes, B["files"]["gl"]), shot, frames=p8.REMIX_FRAMES)
    rx = p8.play(args.ours, out, "p12a_blend_remix", os.path.join(scenes, B["files"]["remix"]), p8.REMIX_ENV,
                 frames=p8.REMIX_FRAMES, gl_debug=False)
    c, d = {}, {}
    for tag, r, label in (("gl", gl, "the game's OpenGL"), ("remix", rx, "Remix")):
        a = p8.picture(r.get("screenshot"))
        means = {}
        if a is not None:
            for k, rect in B["rects"].items():
                means[k] = round(float(p8.crop(a, rect).reshape(-1, 3).mean()), 1)
        d[tag] = means
        c["%s drew it" % label] = r.get("exit") == 0 and a is not None
        c["%s: the wall behind the Add quad is brighter than the bare wall (%s against %s)" % (
            label, means.get("add"), means.get("wall"))] = \
            bool(means) and means.get("add", 0.0) > means.get("wall", 0.0) + 5.0
    sheet = os.path.join(out, "sheet_p12a_blend.png")
    p2.contact_sheet([("the game's OpenGL (left Add, right Alpha 50%)", gl.get("screenshot")),
                      ("RTX Remix", rx.get("screenshot"))], sheet)
    sheets["p12a_blend"] = sheet if os.path.isfile(sheet) else None
    tests[name] = _test(c, d)
    report += ["", "S12.b1: Add blending, the game's OpenGL beside Remix: %s (mean brightness: %s)" % (sheet, d)]


def rtx_room(args, out, scenes, E, tests, sheets, report):
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
