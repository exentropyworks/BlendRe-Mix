"""BGE-Remix p11d: the tests of P11 Part B step 3 (B3, game fluids). The
scenes: p11d_scenes.py.

normal(args, out, scenes, E, tests, sheets)   no RTX card needed
  T11.d1  the pool: a 300 kg box floats a third under (within 2 cm), a
          2000 kg one rests on the bottom; the volume's settings and the
          objects in it from Python
  T11.d2  the drop: a light ball dropped in slows sharply, never reaches the
          bottom, comes to rest at the surface; one splash where it went in
          (any more only from bobbing back, far smaller)
  T11.d3  the river: a raft drifts 3 to 5 m downstream in 5 s, hardly
          sideways
  T11.d4  lava against water: the 1500 kg box sinks in water, floats in lava
          (about 0.48 m deep); let go 1 m down, lava pushes the box up
          harder; thrown in, it stops sooner in lava
  T11.d5  the plank: stood on end, it turns and lies flat
  T11.d6  Make Fluid Volume: its settings, a static Ghost with Convex Hull
          bounds, the Water preset (a flipbook, a UV map made) on a mesh
          without a material, a material of its own kept, the Physics tab's
          Type setting density and drag, made again
  T11.d7  the Lava preset: made by Make Fluid Volume, its glow wired, a
          flipbook; in the fake runtime its material a sprite sheet with
          an emissive picture
  T11.d8  Bullet and stock 2.79b: the pool plays and things fall through
  T11.d9  the Remix View: the volumes' info, outlines and the river's
          arrows; Bullet's note; Run in Ayhan's colours (the pool White
          empty, Blue at a splash, Green in use; the ball Green floating,
          the box Yellow sinking)
  T11.d10 the splash to Remix (the fake runtime): sent as GPU particles
  T11.d11 the crash check: a floating box ended, the pool ended, its volume
          asked for after, a box added after
rtx(...)
  S11.d1  the drop in Remix (numbers only)

BGE_REMIX_P11D_ONLY (comma separated: pool, drop, river, versus, plank,
make, lava, engines, view, remix, crash) runs only those (a fix round's
reruns).
"""

import os
import re
import shutil

import run_p2 as p2
import run_p8 as p8
import run_p9 as r9

FIXED = ["-g", "fixedtime", "=", "1"]      # one 1/60 s physics step per frame
NO_REMIX = ["-g", "remix", "=", "0"]
SPLASH = re.compile(r"BGE-Remix splash: (\w+) at (\S+) (\S+) (\S+), size (\S+), speed (\S+), time (\S+)")


def _blend(scenes, name):
    return os.path.join(scenes, name + ".blend")


def _run(build, out, tag, blend, frames, env=None):
    res = os.path.join(out, tag + "_p11.json")
    if os.path.isfile(res):
        os.remove(res)
    e = {"BGE_REMIX_P11_OUT": res, "BGE_REMIX_P2_FRAMES": str(frames), "BGE_REMIX_SPLASH_LOG": "1"}
    e.update(env or {})
    r = p2.player(build, out, tag, blend, e, size=(640, 360), args=FIXED + NO_REMIX)
    got = p2.read_json(res) or {}
    ran = r["exit"] == 0 and not r["traceback_in_output"] and bool(got)
    return ran, got, r


def _splashes(out, tag):
    try:
        with open(os.path.join(out, tag + ".log"), errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    return [{"type": m[0], "at": [float(m[1]), float(m[2]), float(m[3])], "size": float(m[4]),
             "speed": float(m[5]), "time": float(m[6])} for m in SPLASH.findall(text)]


def _test(c, d=None):
    return {"ok": bool(c) and all(c.values()), "checks": c, "detail": d or {}}


def _r(v, n=3):
    return None if v is None else round(v, n)


def _only():
    return [x.strip() for x in os.environ.get("BGE_REMIX_P11D_ONLY", "").split(",") if x.strip()]


def t_pool(args, out, scenes, P, tests):
    S = P.get("pool")
    name = "T11.d1 The pool: a light box floats, a heavy one sinks"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["files"]["physx_cpu"], _blend(scenes, S["files"]["physx_cpu"]),
                       S["tics"] + 5)
    light, heavy, fl = got.get("Light") or {}, got.get("Heavy") or {}, got.get("fluid") or {}
    depth = (S["surface"] - (light["z"] - 0.5)) if "z" in light else None
    c = {"ran": ran,
         "the 300 kg box floats %.2f m deep (%s m)" % (S["light_depth"], _r(depth)):
             depth is not None and abs(depth - S["light_depth"]) < 0.02,
         "and is at rest (%s m/s)" % _r(light.get("speed")): light.get("speed") is not None and light["speed"] < 0.03,
         "the 2000 kg box rests on the bottom (z %s)" % _r(heavy.get("z")):
             heavy.get("z") is not None and abs(heavy["z"] - S["heavy_z"]) < 0.02,
         "submerged: %s of the light box under" % _r(got.get("submerged_light")):
             got.get("submerged_light") is not None and abs(got["submerged_light"] - S["light_depth"]) < 0.02,
         "the volume from Python: water, 1000 kg/m3, drag 3, no current (%s)" % fl:
             fl.get("type") == "WATER" and abs((fl.get("density") or 0) - 1000.0) < 1e-3 and
             abs((fl.get("drag") or 0) - 3.0) < 1e-3 and fl.get("current") == [0.0, 0.0, 0.0] and
             fl.get("splashes") is True and fl.get("volume") == "Pool",
         "the objects in it: both boxes (%s)" % got.get("objects"): got.get("objects") == ["Heavy", "Light"],
         "the floor is no fluid": got.get("floor_is_fluid") is False}
    tests[name] = _test(c, {k: got.get(k) for k in ("Light", "Heavy", "fluid", "submerged_light", "objects")})


def t_drop(args, out, scenes, P, tests):
    S = P.get("drop")
    name = "T11.d2 The drop: slowed by the water, at rest at the surface, one splash"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    tag = S["files"]["physx_cpu"]
    ran, got, r = _run(args.ours, out, tag, _blend(scenes, tag), S["tics"] + 5)
    z, speed = got.get("z") or [], got.get("speed") or []
    rad, top = S["radius"], S["surface"]
    entered = next((i for i, h in enumerate(z) if h - rad < top), None)
    c, d = {"ran": ran}, {}
    if entered is not None and entered + 15 < len(speed):
        inside = speed[entered]
        after = speed[entered + 15]
        low = min(z[entered:])
        c["it went in fast (%.2f m/s)" % inside] = inside > 6.0
        c["it slowed sharply (%.2f m/s a quarter second in)" % after] = after < 0.5 * inside
        c["it never reached the bottom (lowest z %.2f)" % low] = low > rad + 0.05
        d.update({"in at tic": entered + 1, "speed in": _r(inside, 2), "a quarter second in": _r(after, 2)})
    else:
        c["it went in"] = False
    if z:
        depth = top - (z[-1] - rad)
        c["at rest at the surface (%.3f m under, %.3f m/s)" % (depth, speed[-1])] = \
            speed[-1] < 0.05 and 0.0 < depth < 2 * rad
    sp = _splashes(out, tag)
    first = sp[0] if sp else None
    c["one splash where it went in (%d; the rest from bobbing back, far smaller)" % len(sp)] = bool(sp) and \
        all(s["speed"] < 0.5 * first["speed"] for s in sp[1:])
    if first:
        c["on the surface over the ball (%s)" % first["at"]] = abs(first["at"][2] - top) < 1e-3 and \
            abs(first["at"][0] - S["at"][0]) < 0.05 and abs(first["at"][1] - S["at"][1]) < 0.05
        c["water, the ball's size, how fast it went in (%s, %.2f m, %.2f m/s)" % (
            first["type"], first["size"], first["speed"])] = first["type"] == "water" and \
            abs(first["size"] - 2 * rad) < 0.06 and first["speed"] > 6.0
    d["splashes"] = sp
    tests[name] = _test(c, d)


def t_river(args, out, scenes, P, tests):
    S = P.get("river")
    name = "T11.d3 The river: a raft drifts with the current"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"] + 5)
    a, b = got.get("from"), got.get("to")
    dx = (b[0] - a[0]) if a and b else None
    dy = (b[1] - a[1]) if a and b else None
    c = {"ran": ran,
         "it drifted %s m downstream in %.0f s (3 to 5)" % (_r(dx, 2), S["seconds"]): dx is not None and 3.0 < dx < 5.0,
         "and %s m sideways" % _r(dy): dy is not None and abs(dy) < 0.2,
         "the current from Python (%s)" % got.get("current"): got.get("current") == [1.0, 0.0, 0.0]}
    tests[name] = _test(c, {"from": a, "to": b})


def t_versus(args, out, scenes, P, tests):
    S = P.get("versus")
    name = "T11.d4 Lava against water: lava holds things higher and stops them sooner"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    got = {}
    c = {}
    for key in ("water", "lava"):
        ran, g, r = _run(args.ours, out, S["files"][key], _blend(scenes, S["files"][key]), S["tics"] + 5)
        c["%s: ran" % key] = ran
        got[key] = g
    w, l = got["water"], got["lava"]
    lava_depth = (S["surface"] - (l["heavy_z"] - 0.5)) if l.get("heavy_z") is not None else None
    c["the 1500 kg box sinks in water (z %s)" % _r(w.get("heavy_z"))] = \
        w.get("heavy_z") is not None and abs(w["heavy_z"] - 0.5) < 0.02
    c["and floats in lava, %s m deep (%.2f)" % (_r(lava_depth), S["lava_depth"])] = \
        lava_depth is not None and abs(lava_depth - S["lava_depth"]) < 0.03
    c["let go 1 m down, lava pushes it up harder (%s against %s m/s after a step)" % (
        _r(l.get("pushed_up_speed")), _r(w.get("pushed_up_speed")))] = \
        l.get("pushed_up_speed") is not None and w.get("pushed_up_speed") is not None and \
        l["pushed_up_speed"] > w["pushed_up_speed"] > 0.0
    c["thrown in at 5 m/s, it stops sooner in lava (%s against %s m/s a second later)" % (
        _r(l.get("thrown_speed"), 2), _r(w.get("thrown_speed"), 2))] = \
        l.get("thrown_speed") is not None and w.get("thrown_speed") is not None and \
        l["thrown_speed"] < w["thrown_speed"] < 5.0
    tests[name] = _test(c, got)


def t_plank(args, out, scenes, P, tests):
    S = P.get("plank")
    name = "T11.d5 The plank: stood on end, it lies flat"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"] + 5)
    ax = got.get("length_axis")
    c = {"ran": ran,
         "its length level (%s from level)" % (_r(abs(ax[2]), 2) if ax else None): bool(ax) and abs(ax[2]) < 0.2}
    tests[name] = _test(c, got)


def t_make(args, out, scenes, P, tests):
    R = P.get("operator")
    name = "T11.d6 Make Fluid Volume: settings, Ghost, the Water preset, made again"
    if not R:
        tests[name] = _test({"the checks were made": False})
        return
    a, b, again = R.get("plain") or {}, R.get("own") or {}, R.get("again") or {}

    def ghost(s):
        return s.get("physics") == 'STATIC' and s.get("ghost") is True and s.get("bounds") == 'CONVEX_HULL'
    c = {"its settings: water, 1000 kg/m3, drag 3, no current, splashes (%s)" % a:
             a.get("bge_fluid") == 1 and a.get("type") == 0 and abs((a.get("density") or 0) - 1000.0) < 1e-3 and
             abs((a.get("drag") or 0) - 3.0) < 1e-3 and a.get("current") == [0.0, 0.0, 0.0] and
             bool(a.get("splashes")),
         "a static Ghost with Convex Hull bounds": ghost(a) and ghost(b),
         "no material: the Water preset (%s), a flipbook" % R.get("plain_preset"):
             R.get("plain_preset") == 'WATER' and R.get("plain_flipbook") == 2,
         "no UV map: one made (%s before, %s after)" % (R.get("plain_uv_before"), a.get("uv")):
             R.get("plain_uv_before") == 0 and a.get("uv") == 1,
         "its own material kept (%s), its current (%s)" % (b.get("materials"), b.get("current")):
             b.get("materials") == ["DOwn"] and b.get("current") == [0.5, 0.0, 0.0],
         "the Physics tab's Type sets density and drag: lava %s, water %s" % (
             R.get("panel_lava"), R.get("panel_water")):
             R.get("panel_lava") == [3100.0, 24.0] and R.get("panel_water") == [1000.0, 3.0],
         "made again as lava: its settings changed, its material kept (%s)" % again.get("materials"):
             again.get("type") == 1 and abs((again.get("density") or 0) - 3100.0) < 1e-3 and
             abs((again.get("drag") or 0) - 24.0) < 1e-3 and again.get("materials") == a.get("materials")}
    tests[name] = _test(c, R)


def _mock_run(args, out, tag, blend, seconds=30):
    dump, cache, adump = (os.path.join(out, tag + x) for x in ("_bakes", "_cache", "_atlas"))
    for folder in (dump, cache, adump):
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder)
    log, env = p8.mock_env(args, out, tag, cache, dump=dump)
    env["BGE_REMIX_ATLAS_DUMP"] = adump
    env["BGE_REMIX_SPLASH_LOG"] = "1"
    run = r9.pipe_play(args.ours, out, tag, blend, env, seconds=seconds)
    return run, r9.mock_lines(log)


def t_lava(args, out, scenes, P, tests):
    R, L = P.get("operator") or {}, P.get("lava")
    name = "T11.d7 The Lava preset: its glow, a flipbook (fake runtime)"
    if not L:
        tests[name] = _test({"the scenes were made": False})
        return
    glow = R.get("hot_glow") or {}
    c = {"Make Fluid Volume gave lava the Lava preset (%s)" % R.get("hot_preset"): R.get("hot_preset") == 'LAVA',
         "its glow wired into Emissive Color, intensity %s" % glow.get("intensity"):
             glow.get("wired") is True and (glow.get("intensity") or 0) > 1.0,
         "a flipbook at %s frames a second (slow)" % R.get("hot_fps"):
             R.get("hot_flipbook") == 2 and 1 <= (R.get("hot_fps") or 0) <= 4}
    if getattr(args, "mock", None):
        run, lines = _mock_run(args, out, "p11d_lava_mock", _blend(scenes, L["file"]))
        st = run.get("stats") or {}
        mats = r9.mock_materials(lines)
        sheets_sent = [m for m in mats if m.get("sprite") not in (None, "0,0,0", "1,1,0")]
        m = sheets_sent[-1] if sheets_sent else None
        want = "4,4,%d" % (L.get("fps") or 0)
        c["Remix drew it (the fake runtime)"] = bool(run.get("exit") == 0) and st.get("running") is True
        c["its material a sprite sheet: 4 x 4 at %d a second (%s)" % (L.get("fps") or 0, m and m.get("sprite"))] = \
            bool(m) and m.get("sprite") == want
        c["it glows: an emissive picture from the flipbook (%s)" % (m and m.get("emissive_tex"))] = \
            bool(m) and "_flipbook" in (m.get("emissive_tex") or "") and float(m.get("intensity") or 0) > 0.0
        d = {"material": m, "stats": {k: st.get(k) for k in ("running", "procedural_bakes", "textures_waiting")}}
    else:
        c["the fake runtime (--mock) was given"] = False
        d = {}
    tests[name] = _test(c, d)


def t_engines(args, out, scenes, P, tests):
    S = P.get("pool")
    name = "T11.d8 Bullet and stock 2.79b: the pool plays, things fall through"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    runs = {"bullet": _run(args.ours, out, S["files"]["bullet"], _blend(scenes, S["files"]["bullet"]),
                           S["tics"] + 5)}
    if getattr(args, "official", None):
        runs["stock_2.79b"] = _run(args.official, out, "p11d_pool_stock", _blend(scenes, S["files"]["bullet"]),
                                   S["tics"] + 5)
    c, d = {}, {}
    for key, (ran, got, r) in sorted(runs.items()):
        light = got.get("Light") or {}
        c["%s: runs the file" % key] = ran
        c["%s: the light box fell through to the bottom (z %s)" % (key, _r(light.get("z")))] = \
            light.get("z") is not None and abs(light["z"] - 0.5) < 0.05
        c["%s: no fluid from Python (%s)" % (key, got.get("fluid"))] = got.get("fluid") is None
        d[key] = {"Light": light, "Heavy": got.get("Heavy"), "exit": r["exit"] if r else None}
    tests[name] = _test(c, d)


def t_view(args, out, scenes, P, tests):
    import p11b_tests as tb
    S = P.get("view")
    name = "T11.d9 The Remix View: fluid volumes in Ayhan's colours"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    c, d = {}, {}
    m = tb.view_probe(args, out, "p11d_view_model", _blend(scenes, S["files"]["physx_cpu"]),
                      {"BGE_REMIX_P11B_PART": "model"})
    built = (m.get("steps") or {}).get("s_build") or {}
    els, shapes = built.get("elements") or [], built.get("shapes") or []
    pool = tb._find(els, S["pool"], S["pool"], "body:")
    riv = tb._find(els, S["river"], S["river"], "body:")
    c["the model was built"] = m["ran"] and bool(els)
    c["the pool: water, its density and drag, no current (%s)" % (pool and pool["info"])] = \
        bool(pool) and pool["info"].startswith("water, 1000 kg/m3, drag 3") and "no current" in pool["info"] and \
        pool["state"] == "WHITE"
    c["the river: its current (%s)" % (riv and riv["info"])] = bool(riv) and "current 1.00 m/s" in riv["info"]

    def lines(e):
        return len([s for s in shapes if e and s["a"] == e["index"] and s["type"] == "POINTS"])
    c["the pool outlined: its hull's faces (%d lines)" % lines(pool)] = lines(pool) >= 6
    c["the river: its outline and nine arrows (%d lines)" % lines(riv)] = lines(riv) >= lines(pool) + 18
    m2 = tb.view_probe(args, out, "p11d_view_bullet", _blend(scenes, S["files"]["bullet"]),
                       {"BGE_REMIX_P11B_PART": "model"})
    w2 = ((m2.get("steps") or {}).get("s_build") or {}).get("warnings") or []
    c["under Bullet: noted, floating needs PhysX"] = m2["ran"] and \
        len([w for w in w2 if w["code"] == "PHY_FLUID_ENGINE"]) == 2
    frames = sorted(int(f) for f in S["frames"])
    r = tb.view_probe(args, out, "p11d_view_run", _blend(scenes, S["files"]["physx_cpu"]),
                      {"BGE_REMIX_P11B_PART": "run", "BGE_REMIX_P11B_FRAMES": ",".join(str(f) for f in frames)})
    steps = r.get("steps") or {}
    c["Run ran"] = r["ran"]
    live = {}
    for f in frames:
        s = steps.get("s_run_%d" % f) or {}
        got = {}
        for who in ("pool", "ball", "heavy"):
            j = [l for l in s.get("live") or [] if l["owner"] == S[who] and l["kind"].startswith("body:")]
            got[who] = j[0] if j else None
        live[f] = got
        want = S["frames"][str(f)]
        st = got["pool"]["state"] if got["pool"] else None
        c["frame %d: the pool %s (%s)" % (f, want, st)] = st == want
    last = live.get(frames[-1]) or {}
    c["frame %d: the ball Green, floating (%s)" % (frames[-1], last.get("ball") and last["ball"]["state"])] = \
        bool(last.get("ball")) and last["ball"]["state"] == "GREEN"
    c["frame %d: the box Yellow, sinking (%s)" % (frames[-1], last.get("heavy") and last["heavy"]["state"])] = \
        bool(last.get("heavy")) and last["heavy"]["state"] == "YELLOW"
    d.update({"pool": pool, "river": riv, "live": live, "errors": m.get("errors"),
              "run": {k: r.get(k) for k in ("exit", "seconds", "last_step", "crash")}})
    tests[name] = _test(c, d)


def t_remix(args, out, scenes, P, tests):
    S = P.get("drop")
    name = "T11.d10 The splash to Remix: GPU particles (fake runtime)"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    if not getattr(args, "mock", None):
        tests[name] = _test({"the fake runtime (--mock) was given": False})
        return
    run, lines = _mock_run(args, out, "p11d_drop_mock", _blend(scenes, S["files"]["physx_cpu_remix"]))
    st = run.get("stats") or {}
    emitters = [l for l in lines if l.startswith("Emitter ") and " hide=1 " in l]
    c = {"Remix drew the pool (the fake runtime)": bool(run.get("exit") == 0) and st.get("running") is True,
         "the splash sent to Remix (%s)" % st.get("splashes_sent"): (st.get("splashes_sent") or 0) >= 1,
         "as an emitter drawn %s frames, its ring hidden (%d)" % (st.get("splash_emitter_draws"), len(emitters)):
             (st.get("splash_emitter_draws") or 0) >= 1 and len(emitters) >= 1}
    tests[name] = _test(c, {"emitters": emitters[:3], "stats": {k: st.get(k) for k in (
        "running", "splashes_sent", "splash_emitter_draws", "gpu_emitters")}})


def t_crash(args, out, scenes, P, tests):
    S = P.get("crash")
    name = "T11.d11 The crash check"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"] + 5)
    left = got.get("left") or {}
    c = {"ran to the end": ran,
         "the volume was found": got.get("made") is True,
         "asked for after the pool was ended: gone (a RuntimeError)": got.get("gone") == "RuntimeError",
         "its current set after: gone (a RuntimeError)": got.get("set_gone") == "RuntimeError",
         "the ended box gone, the added one there (%s)" % sorted(left):
             "Box0" not in left and "Box1" in left and "Spare" in left,
         "with the pool gone, the boxes fell to the bottom (%s)" % {k: _r(v, 2) for k, v in left.items()}:
             bool(left) and all(abs(v - 0.5) < 0.05 for v in left.values()),
         "no other error (%s)" % got.get("errors"): not got.get("errors")}
    tests[name] = _test(c, {k: got.get(k) for k in ("left", "gone", "set_gone", "errors")})


def normal(args, out, scenes, E, tests, sheets):
    P = E.get("p11d") or {}
    only = _only()
    for key, fn in (("pool", t_pool), ("drop", t_drop), ("river", t_river), ("versus", t_versus),
                    ("plank", t_plank), ("make", t_make), ("lava", t_lava), ("engines", t_engines),
                    ("view", t_view), ("remix", t_remix), ("crash", t_crash)):
        if not only or key in only:
            fn(args, out, scenes, P, tests)


def rtx(args, out, scenes, E, tests, sheets, report):
    """S11.d1: the drop in Remix (numbers only)"""
    P = E.get("p11d") or {}
    S = P.get("drop")
    name = "S11.d1 The drop in Remix (numbers only)"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    tag = "p11d_drop_rtx"
    res = os.path.join(out, tag + "_p11.json")
    if os.path.isfile(res):
        os.remove(res)
    env = {"RTX_ENABLE_ASYNC_COMPILATION": "0", "BGE_REMIX_P11_OUT": res, "BGE_REMIX_P11D_WAIT_REMIX": "1",
           "BGE_REMIX_SPLASH_LOG": "1"}
    r = p8.play(args.ours, out, tag, _blend(scenes, S["files"]["physx_cpu_remix"]), env, frames=100000,
                gl_debug=False, extra=FIXED)
    got = p2.read_json(res) or {}
    st = r.get("stats") or {}
    c = {"ran with Remix drawing": bool(got) and bool(got.get("remix_drawing")),
         "the splash sent to Remix (%s)" % st.get("splashes_sent"): (st.get("splashes_sent") or 0) >= 1}
    d = {"frame_ms_median": _r(got.get("frame_ms_median"), 2), "frame_ms_p95": _r(got.get("frame_ms_p95"), 2),
         "splashes sent": st.get("splashes_sent"), "splash emitter draws": st.get("splash_emitter_draws"),
         "exit": r.get("exit")}
    tests[name] = _test(c, d)
    report += ["", "B3 the drop in Remix: frame %s ms (p95 %s), %s splash(es) sent to Remix" %
               (d["frame_ms_median"], d["frame_ms_p95"], d["splashes sent"])]
