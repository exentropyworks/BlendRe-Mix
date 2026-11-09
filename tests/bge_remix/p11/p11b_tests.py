"""BGE-Remix p11b: the tests of P11 Part B step 1 (B1, articulations). The
scenes: p11b_scenes.py.

normal(args, out, scenes, E, tests, sheets)   no RTX card needed
  T11.b1  the heavy chain: PhysX's articulation (CPU and GPU) keeps every
          joint's gap under 1 mm with a 100 kg ball on 1 kg links
  T11.b2  the ragdoll down the stairs: let go, the capsules one articulation,
          its joints together and within their limits, falling down the steps
          with the bones on them; put back, on the bones again
  T11.b3  the door: pushed by a box to its 90 degree limit and no further;
          then turned by its hinge at 1 radian a second to its other limit
  T11.b4  the two-joint arm: driven to three pairs of angles in turn, each
          within 0.5 degrees
  T11.b5  the rope bridge: its loop and its joint to the still post left
          ordinary, the rest one articulation, holding a box sent across
  T11.b6  the engines compared: the heavy chain's gaps in PhysX (articulation,
          CPU and GPU; ordinary joints), Bullet and stock 2.79b (numbers;
          each runs the file)
  T11.b7  the Remix View: the bridge's joints in Ayhan's colours and their
          warnings, Bullet's note; the door's hinge live in Run: White at
          rest, Green moving, Yellow at its limit, Blue driven
  T11.b8  the crash check: links removed and added, joints added and
          removed, the ragdoll turned on and off ten times, the root removed
rtx(...)   nothing in this step
"""

import os
import shutil

import run_p2 as p2
import run_p8 as p8

FIXED = ["-g", "fixedtime", "=", "1"]      # one 1/60 s physics step per frame
NO_REMIX = ["-g", "remix", "=", "0"]
HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "p11b_view_probe.py")

GAP_ART = 0.001      # an articulation's joints: under 1 mm
GAP_ORDINARY = 0.02  # an ordinary joint beside one (the bridge): under 2 cm
FOLLOW = 0.01        # a bone on its capsule: within 1 cm
ANGLE = 0.5          # degrees


def _blend(scenes, name):
    return os.path.join(scenes, name + ".blend")


def _run(build, out, tag, blend, frames):
    res = os.path.join(out, tag + "_p11.json")
    if os.path.isfile(res):
        os.remove(res)
    e = {"BGE_REMIX_P11_OUT": res, "BGE_REMIX_P2_FRAMES": str(frames)}
    r = p2.player(build, out, tag, blend, e, size=(640, 360), args=FIXED + NO_REMIX)
    got = p2.read_json(res) or {}
    ran = r["exit"] == 0 and not r["traceback_in_output"] and bool(got)
    return ran, got, r


def _test(c, d=None):
    return {"ok": bool(c) and all(c.values()), "checks": c, "detail": d or {}}


def _mm(v):
    return None if v is None else round(v * 1000.0, 3)


def _max(d):
    return max(d.values()) if d else None


# ---------------------------------------------------------------------------

def t_chain(args, out, scenes, P, tests):
    S = P.get("chain")
    n1, n6 = "T11.b1 The heavy chain holds together (articulation)", "T11.b6 The engines compared (the heavy chain)"
    if not S:
        tests[n1] = tests[n6] = _test({"the scenes were made": False})
        return
    runs = {}
    for key, name in sorted(S["files"].items()):
        runs[key] = _run(args.ours, out, name, _blend(scenes, name), S["tics"] + 5)
    if getattr(args, "official", None):
        runs["stock_2.79b"] = _run(args.official, out, "p11b_chain_stock", _blend(scenes, S["files"]["bullet"]),
                                   S["tics"] + 5)
    c, d = {}, {}
    for key in S["articulated"]:
        ran, got, _r = runs.get(key, (False, {}, None))
        art = got.get("articulation") or {}
        gaps = got.get("max_gap") or {}
        c["%s: ran" % key] = ran
        c["%s: one articulation of %d links, fixed to the world" % (key, S["links"])] = \
            art.get("links") == S["links"] and art.get("fixed") is True
        c["%s: every joint's gap under %.0f mm all the way (largest %s mm)" % (key, GAP_ART * 1000, _mm(_max(gaps)))] = \
            len(gaps) == S["joints"] and all(v < GAP_ART for v in gaps.values())
        d[key] = {"largest gap mm": _mm(_max(gaps)), "articulation": art, "weight at the end": got.get("weight")}
    tests[n1] = _test(c, d)

    c, d, table = {}, {}, []
    for key in sorted(runs):
        ran, got, r = runs[key]
        gaps = got.get("max_gap") or {}
        c["%s: runs the file" % key] = ran
        d[key] = {"largest gap mm": _mm(_max(gaps)), "all gaps added mm": _mm(got.get("max_total")),
                  "the ball's last joint mm": _mm(gaps.get("JWeight")), "exit": r["exit"] if r else None}
        table.append("  %-18s largest gap %s mm, all gaps added %s mm" %
                     (key, _mm(_max(gaps)), _mm(got.get("max_total"))))
    d["table"] = table
    tests[n6] = _test(c, d)


def t_ragdoll(args, out, scenes, P, tests):
    S = P.get("ragdoll")
    name = "T11.b2 The ragdoll down the stairs"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    c, d = {}, {}
    for key, fname in sorted(S["files"].items()):
        made = (S.get("made") or {}).get(key) or {}
        c["%s: Make Ragdoll gave %d capsules and %d joints" % (key, S["bones"], S["bones"] - 1)] = \
            made.get("capsules") == S["bones"] and made.get("joints") == S["bones"] - 1
        ran, got, _r = _run(args.ours, out, fname, _blend(scenes, fname), S["tics"])
        c["%s: ran" % key] = ran
        c["%s: getArticulation(armature) found the ragdoll, on its bones at the start" % key] = \
            got.get("ragdoll_found") is True and got.get("ragdoll_at_start") is False
        c["%s: the ragdoll let go and put back" % key] = got.get("on") is True and got.get("off") is True
        gaps = got.get("max_gap") or {}
        follow = got.get("follow_max")
        c["%s: each bone on its capsule while on (within %.0f cm; %s mm)" % (key, FOLLOW * 100, _mm(follow))] = \
            follow is not None and follow < FOLLOW
        start = (got.get("start") or {})
        hips = got.get("hips_on")
        c["%s: off, the capsules back on the bones (%s mm, and still %s mm later)" %
          (key, _mm(got.get("back_303")), _mm(got.get("back_340")))] = \
            got.get("back_303") is not None and got["back_303"] < FOLLOW and \
            got.get("back_340") is not None and got["back_340"] < FOLLOW and got.get("ragdoll_now_340") is False
        if key.startswith("physx"):
            art = got.get("articulation") or {}
            c["%s: on, the capsules one articulation of %d links (free)" % (key, S["bones"])] = \
                art.get("links") == S["bones"] and art.get("fixed") is False
            c["%s: its joints' gaps under %.0f mm (largest %s mm)" % (key, GAP_ART * 1000, _mm(_max(gaps)))] = \
                bool(gaps) and all(v < GAP_ART for v in gaps.values())
            lim = got.get("limits") or {}
            c["%s: every joint within its limits (twist %s of %d, swing %s of %d degrees)" %
              (key, _r1(lim.get("twist")), S["twist"], _r1(lim.get("swing")), S["swing"])] = \
                bool(lim) and lim["twist"] <= S["twist"] + 1.0 and lim["swing"] <= S["swing"] + 1.0
            c["%s: it went down the stairs (the hips at x %.2f, past the platform's edge 0.6)" %
              (key, hips[0] if hips else -9)] = bool(hips) and hips[0] > 0.8
        d[key] = {"largest gap mm": _mm(_max(gaps)), "bone on capsule mm": _mm(follow), "hips at the end": hips,
                  "head at the end": got.get("head_on"), "follow log": got.get("follow"),
                  "errors": [got.get(k) for k in ("on_error", "off_error") if got.get(k)],
                  "capsules": len(start)}
    tests[name] = _test(c, d)


def t_door(args, out, scenes, P, tests):
    S = P.get("door")
    name = "T11.b3 The door: to its limit, then turned by its hinge"
    if not S:
        tests[name] = _test({"the scene was made": False})
        return
    ran, got, _r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"])
    speeds = got.get("speeds") or []
    avg = sum(speeds) / len(speeds) if speeds else None
    art = got.get("articulation") or {}
    c = {"ran": ran,
         "an articulation of 2 links, fixed to the world": art.get("links") == 2 and art.get("fixed") is True,
         "pushed by the box, it swung open to its %.0f degree limit (%s) and no further (largest %s)" %
         (S["open"], _r1(got.get("open")), _r1(got.get("max_angle"))):
             got.get("open") is not None and abs(got["open"] - S["open"]) <= 1.0 and
             got.get("max_angle", 999) <= S["open"] + ANGLE,
         "turned by its hinge at %.1f rad/s (%s)" % (S["speed"], _r1(avg, 3)):
             avg is not None and abs(avg - S["speed"]) <= 0.1 * abs(S["speed"]),
         "closed to its other limit, %.0f degrees (%s), and no further (smallest %s)" %
         (S["shut"], _r1(got.get("closed")), _r1(got.get("min_angle"))):
             got.get("closed") is not None and abs(got["closed"] - S["shut"]) <= 1.0 and
             got.get("min_angle", -999) >= S["shut"] - ANGLE,
         "getJointPosition says what the door shows (the post against the door; within %.1f degrees: %s)" %
         (ANGLE, _r1(got.get("joint_vs_world"), 3)):
             got.get("joint_vs_world") is not None and got["joint_vs_world"] <= ANGLE}
    tests[name] = _test(c, {"angles (tic, door, joint)": got.get("angles"), "errors": [
        got.get(k) for k in ("joint_error", "motor_error") if got.get(k)]})


def _r1(v, n=1):
    return None if v is None else round(v, n)


def t_arm(args, out, scenes, P, tests):
    S = P.get("arm")
    name = "T11.b4 The two-joint arm to its angles"
    if not S:
        tests[name] = _test({"the scene was made": False})
        return
    ran, got, _r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"])
    art = got.get("articulation") or {}
    c = {"ran": ran, "an articulation of 3 links, fixed to the world": art.get("links") == 3 and art.get("fixed")}
    for k, tgt in (("hold1", S["target1"]), ("hold2", S["target2"]), ("hold3", S["target3"])):
        h = got.get(k) or {}
        w, j = h.get("world") or [99, 99], h.get("joint") or [99, 99]
        c["at %s degrees, within %.1f (off by %s and %s)" % (tuple(tgt), ANGLE, _r1(w[0], 3), _r1(w[1], 3))] = \
            max(w) <= ANGLE
        c["at %s, getJointPosition says what the arm shows (%s, %s)" % (tuple(tgt), _r1(j[0], 3), _r1(j[1], 3))] = \
            max(j) <= ANGLE
    c["the forearm's end where the angles put it (within 1 mm; %s mm)" % _mm(got.get("tip_err"))] = \
        got.get("tip_err") is not None and got["tip_err"] < 0.001
    tests[name] = _test(c, {"log (tic, upper, fore, joint upper, joint fore)": got.get("log"),
                            "errors": [got.get(k) for k in ("drive_error", "joint_error") if got.get(k)]})


def t_bridge(args, out, scenes, P, tests):
    S = P.get("bridge")
    name = "T11.b5 The rope bridge with a loop"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    c, d = {}, {}
    for key, fname in sorted(S["files"].items()):
        ran, got, _r = _run(args.ours, out, fname, _blend(scenes, fname), S["tics"])
        gaps = got.get("max_gap") or {}
        c["%s: ran" % key] = ran
        drop = got.get("drop_z")
        d[key] = {"gaps mm": {k: _mm(v) for k, v in sorted(gaps.items())}, "largest speed": got.get("max_speed"),
                  "the box rests at z": drop, "plank 3 at z": got.get("mid_z"),
                  "articulation": got.get("articulation")}
        if not key.startswith("physx"):
            continue
        art = got.get("articulation") or {}
        c["%s: one articulation of %d links, 2 joints left ordinary (the loop, the still post)" % (key, S["links"])] = \
            art.get("links") == S["links"] and art.get("ordinary") == 2
        art_gaps = [gaps.get(j) for j in S["articulated"]]
        c["%s: the planks' hinges under %.0f mm (largest %s mm)" % (key, GAP_ART * 1000,
                                                                     _mm(max([g for g in art_gaps if g] or [0])))] = \
            all(g is not None and g < GAP_ART for g in art_gaps)
        ord_gaps = [gaps.get(j) for j in S["ordinary"]]
        c["%s: the loop and the post's joint hold (under %.0f cm: %s mm)" %
          (key, GAP_ORDINARY * 100, [_mm(g) for g in ord_gaps])] = \
            all(g is not None and g < GAP_ORDINARY for g in ord_gaps)
        c["%s: nothing flies apart (fastest plank %s m/s)" % (key, _r1(got.get("max_speed"), 2))] = \
            got.get("max_speed") is not None and got["max_speed"] < 20.0
        low, far = got.get("roller_min_z"), got.get("roller_max_x")
        c["%s: the bridge sags and holds the box sent across (lowest %s, to x %s)" % (key, _r1(low, 2), _r1(far, 2))] = \
            low is not None and low >= S["z"] - 0.6 and far is not None and far > -0.5
    tests[name] = _test(c, d)


def t_crash(args, out, scenes, P, tests):
    S = P.get("crash")
    name = "T11.b8 The crash check"
    if not S:
        tests[name] = _test({"the scene was made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"])
    links = got.get("links") or {}
    c = {"ran to the end (exit 0, no Python error)": ran and not got.get("errors"),
         "the ragdoll turned on and off %d times" % S["toggles"]: got.get("toggles") == S["toggles"]}
    for k, want in S["links"].items():
        c["%s: %s links (%s)" % (k, want if want is not None else "no articulation", links.get(k))] = \
            links.get(k) == want
    tests[name] = _test(c, {"links": links, "errors": got.get("errors"), "exit": r["exit"]})


# ---------------------------------------------------------------------------
# the Remix View (Blender's UI)

def view_probe(args, out, tag, blend, env):
    res = os.path.join(out, tag + "_p11b.json")
    if os.path.isfile(res):
        os.remove(res)
    folder = os.path.join(out, tag)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    e = p2.base_env(out, tag)
    e.update(p8.GL_ENV)
    e.update(env)
    e.update({"BGE_REMIX_P11B_OUT": res, "BGE_REMIX_P11B_DIR": folder})
    code, text, secs = p2.run([p2.exe(args.ours, "blender"), "--disable-crash-handler"] + p8.WINDOW +
                              [blend, "--python", PROBE], e, os.path.join(out, tag + ".log"), timeout=900, cwd=out)
    r = p2.read_json(res) or {}
    r.update({"exit": code, "seconds": round(secs, 1), "folder": folder})
    r["ran"] = code == 0 and bool(r.get("finished"))
    return r


def _find(els, owner, name, prefix):
    for e in els:
        if e["owner"] == owner and e["name"] == name and e["kind"].startswith(prefix):
            return e
    return None


def t_view(args, out, scenes, P, tests):
    name = "T11.b7 The Remix View: joints in Ayhan's colours"
    B, D, R = P.get("bridge"), P.get("door"), P.get("ragdoll")
    if not (B and D and R):
        tests[name] = _test({"the scenes were made": False})
        return
    c, d = {}, {}
    # the bridge (PhysX): the model
    m = view_probe(args, out, "p11b_view_bridge", _blend(scenes, B["files"]["physx_cpu"]), {"BGE_REMIX_P11B_PART": "model"})
    built = (m.get("steps") or {}).get("s_build") or {}
    els, warns = built.get("elements") or [], built.get("warnings") or []
    c["the bridge's model was built"] = m["ran"] and bool(els)
    hinges = [_find(els, "Plank%d" % i, "Hinge%d" % i, "joint:") for i in range(len(B["articulated"]))]
    c["the planks' hinges: in the articulation (not Red or Black)"] = \
        all(h and h["state"] not in ("RED", "BLACK") and "articulation" in h["info"] for h in hinges)
    left = {}
    for owner, jname in (("Plank7", "ToRightPost"), ("Plank3", "Loop")):
        e = _find(els, owner, jname, "joint:")
        codes = sorted(w["code"] for w in warns if w["owner"] == owner and w["name"] == jname)
        left[jname] = {"state": e and e["state"], "warnings": codes}
        c["%s: Red, left ordinary (PHY_ART_LEFT)" % jname] = bool(e) and e["state"] == "RED" and \
            "PHY_ART_LEFT" in codes
    post = _find(els, "LeftPost", "LeftPost", "body:")
    c["the left post: the articulation's root, %d links" % B["links"]] = \
        bool(post) and post["info"].startswith("articulation root") and ("%d links" % B["links"]) in post["info"]
    d["bridge"] = {"hinges": [h and {"state": h["state"], "info": h["info"]} for h in hinges], "left ordinary": left,
                   "post": post, "errors": m.get("errors")}
    # Bullet: the root is noted
    m = view_probe(args, out, "p11b_view_ragdoll_bullet", _blend(scenes, R["files"]["bullet"]),
                   {"BGE_REMIX_P11B_PART": "model"})
    warns = ((m.get("steps") or {}).get("s_build") or {}).get("warnings") or []
    engine = [w for w in warns if w["code"] == "PHY_ART_ENGINE"]
    c["under Bullet: the ragdoll's root noted (articulations need PhysX)"] = m["ran"] and len(engine) == 1
    d["bullet"] = {"PHY_ART_ENGINE": engine, "errors": m.get("errors")}
    # the door live in Run
    frames = (10, 40, 100, 150)
    want = {10: "WHITE", 40: "GREEN", 100: "YELLOW", 150: "BLUE"}
    m = view_probe(args, out, "p11b_view_door", _blend(scenes, D["file"]),
                   {"BGE_REMIX_P11B_PART": "run", "BGE_REMIX_P11B_FRAMES": ",".join(str(f) for f in frames)})
    steps = m.get("steps") or {}
    c["the door's model was built and Run ran"] = m["ran"]
    live = {}
    for f in frames:
        s = steps.get("s_run_%d" % f) or {}
        j = [l for l in s.get("live") or [] if l["owner"] == "Door" and l["name"] == D["joint"]]
        live[f] = j[0] if j else None
        c["frame %d: the hinge %s (%s)" % (f, want[f], j[0]["state"] if j else None)] = \
            bool(j) and j[0]["state"] == want[f]
    d["door live"] = live
    d["door errors"] = m.get("errors")
    tests[name] = _test(c, d)


def normal(args, out, scenes, E, tests, sheets):
    P = E.get("p11b") or {}
    only = [x.strip() for x in os.environ.get("BGE_REMIX_P11B_ONLY", "").split(",") if x.strip()]
    for key, fn in (("chain", t_chain), ("ragdoll", t_ragdoll), ("door", t_door), ("arm", t_arm),
                    ("bridge", t_bridge), ("view", t_view), ("crash", t_crash)):
        if not only or key in only:
            fn(args, out, scenes, P, tests)


def rtx(args, out, scenes, E, tests, sheets, report):
    """(B1 has no RTX measurements)"""
    return
