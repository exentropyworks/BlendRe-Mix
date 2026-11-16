"""BGE-Remix p11c: the tests of P11 Part B step 2 (B2, destruction with NVIDIA
Blast). The scenes: p11c_scenes.py.

normal(args, out, scenes, E, tests, sheets)   no RTX card needed
  T11.c1  the wall: a 20 kg ball at 10 m/s breaks it where it lands (pieces
          broken off, its top corners still held); at 3 m/s it stays whole
  T11.c2  the pillar: an explosion at mid-height breaks it there and throws
          the pieces out; the top, held by nothing, falls; its foot stays
  T11.c3  the budget: six crates blown apart one after another, never more
          than Max Pieces (200) broken-off pieces; the oldest go first
  T11.c4  Bullet and stock 2.79b: the same wall hit at 10 m/s stays one
          whole object (each runs the file)
  T11.c5  Make Destructible: the same seed gives the same pieces, another
          seed others; the pieces' volumes add up to the cube's; made again,
          the same pieces replace the old ones; the original is kept on
          layer 20
  T11.c6  the Remix View: the wall's pieces counted, the budget's warning,
          Bullet's note; Run in Ayhan's colours: White whole, Blue damaged
          by a script, Green breaking, Yellow at the budget
  T11.c7  the crash check: pieces and the parent piece ended while broken,
          damage after, every piece ended, the destructible asked for after
rtx(...)
  S11.c1  the wall breaking in Remix (numbers only)

BGE_REMIX_P11C_ONLY (comma separated: wall, pillar, budget, engines, make,
view, crash) runs only those (a fix round's reruns).
"""

import os

import run_p2 as p2
import run_p8 as p8

FIXED = ["-g", "fixedtime", "=", "1"]      # one 1/60 s physics step per frame
NO_REMIX = ["-g", "remix", "=", "0"]
HELD = 0.002     # m: a piece still held moves less than this


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


def _r(v, n=3):
    return None if v is None else round(v, n)


def _only():
    return [x.strip() for x in os.environ.get("BGE_REMIX_P11C_ONLY", "").split(",") if x.strip()]


def t_wall(args, out, scenes, P, tests):
    S = P.get("wall")
    name = "T11.c1 The wall: a hard hit breaks it, a soft one does not"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    c, d = {}, {}
    for key in ("physx_cpu_10", "physx_cpu_3"):
        ran, got, r = _run(args.ours, out, S["files"][key], _blend(scenes, S["files"][key]), S["tics"] + 5)
        made = got.get("made") or {}
        c["%s: ran" % key] = ran
        c["%s: one destructible, its pieces and bonds found, anchored" % key] = \
            bool(made) and made.get("pieces", 0) >= S["pieces_asked"] // 2 and made.get("bonds", 0) > made.get(
                "pieces", 0) and made.get("anchored") is True
        corners = [v for v in (got.get("corner_moved") or []) if v is not None]
        if key.endswith("_10"):
            c["10 m/s: it broke (%s pieces broken off)" % got.get("broken_off")] = (got.get("broken_off") or 0) >= 1
            c["10 m/s: not all of it (%s of %s broken off)" % (got.get("broken_off"), made.get("pieces"))] = \
                (got.get("broken_off") or 0) < made.get("pieces", 0) // 2
            c["10 m/s: its top corners still held (moved %s m)" % [_r(v) for v in corners]] = \
                len(corners) == 2 and all(v < HELD for v in corners)
        else:
            c["3 m/s: it stays whole (%s groups)" % got.get("groups")] = got.get("groups") == 1 and \
                (got.get("broken_off") or 0) == 0
            moved = max((got.get("moved") or {}).values() or [None]) if got.get("moved") else None
            c["3 m/s: no piece moved (%s m)" % _r(moved)] = moved is not None and moved < HELD
        d[key] = {"made": made, "groups": got.get("groups"), "broken off": got.get("broken_off"),
                  "bonds broken": got.get("bonds_broken"), "corners moved": [_r(v) for v in corners],
                  "exit": r["exit"] if r else None}
    tests[name] = _test(c, d)


def t_pillar(args, out, scenes, P, tests):
    S = P.get("pillar")
    name = "T11.c2 The pillar: blown at mid-height, its top falls"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"] + 5)
    c = {"ran": ran,
         "the explosion hit it": got.get("hit") == 1,
         "pieces broke loose (%s)" % got.get("broken_off"): (got.get("broken_off") or 0) >= 2,
         "its top fell (%s m)" % _r(got.get("top_drop")): (got.get("top_drop") or 0.0) > 0.5,
         "its foot stays (moved %s m)" % _r(got.get("base_moved")):
             got.get("base_moved") is not None and got.get("base_moved") < HELD}
    tests[name] = _test(c, {k: got.get(k) for k in ("made", "groups", "broken_off", "top_drop", "base_moved", "hit")})


def t_budget(args, out, scenes, P, tests):
    S = P.get("budget")
    name = "T11.c3 The budget: never more than Max Pieces, the oldest go first"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"] + 5)
    per = got.get("per_crate") or []
    made = got.get("made") or []
    c = {"ran": ran,
         "six destructibles (%s pieces)" % made: len(made) == S["crates"] and all(m for m in made),
         "never more than %d broken off (at most %s)" % (S["max"], got.get("most")):
             got.get("most") is not None and 0 < got["most"] <= S["max"],
         "at the budget once they all broke (%s)" % (sum(per) if per else None): bool(per) and
             sum(per) >= S["max"] * 0.75,
         "the oldest went first: the first crate's broken-off pieces gone, the last one's left (%s)" % per:
             len(per) == S["crates"] and per[0] == 0 and per[-1] > 0}
    tests[name] = _test(c, {"most": got.get("most"), "per crate at the end": per, "made": made})


def t_engines(args, out, scenes, P, tests):
    S = P.get("wall")
    name = "T11.c4 Bullet and stock 2.79b: the wall stays whole"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    runs = {"bullet": _run(args.ours, out, S["files"]["bullet_10"], _blend(scenes, S["files"]["bullet_10"]),
                           S["tics"] + 5)}
    if getattr(args, "official", None):
        runs["stock_2.79b"] = _run(args.official, out, "p11c_wall_stock", _blend(scenes, S["files"]["bullet_10"]),
                                   S["tics"] + 5)
    c, d = {}, {}
    for key, (ran, got, r) in sorted(runs.items()):
        moved = max((got.get("moved") or {}).values()) if got.get("moved") else None
        c["%s: runs the file" % key] = ran
        c["%s: hit at 10 m/s, no piece moved (%s m)" % (key, _r(moved))] = moved is not None and moved < HELD
        c["%s: the ball bounced off (its speed %s m/s)" % (key, _r(got.get("ball_speed_y"), 2))] = \
            got.get("ball_speed_y") is not None and got["ball_speed_y"] < 0.5
        d[key] = {"moved": _r(moved), "ball": got.get("ball"), "exit": r["exit"] if r else None}
    tests[name] = _test(c, d)


def t_make(args, out, scenes, P, tests):
    R = P.get("operator")
    name = "T11.c5 Make Destructible: seeds, volumes, made again"
    if not R:
        tests[name] = _test({"the checks were made": False})
        return
    vol = R.get("volume") or 0.0
    c = {"the same seed, the same pieces (%s)" % R.get("pieces"): R.get("same_seed_same_pieces") is True,
         "another seed, other pieces": R.get("other_seed_other_pieces") is True,
         "the pieces' volumes add up to the cube's (%s m3)" % _r(vol): abs(vol - 1.0) < 0.02,
         "made again: the same pieces (%s), none left over" % R.get("again_count"):
             R.get("again_names_same") is True and R.get("again_same_pieces") is True,
         "the original kept on layer 20": R.get("source_kept_on_layer_20") is True}
    tests[name] = _test(c, R)


def t_view(args, out, scenes, P, tests):
    import p11b_tests as tb
    S = P.get("view")
    name = "T11.c6 The Remix View: destructibles in Ayhan's colours"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    c, d = {}, {}
    root = S["roots"]["physx_cpu"]
    m = tb.view_probe(args, out, "p11c_view_model", _blend(scenes, S["files"]["physx_cpu"]),
                      {"BGE_REMIX_P11B_PART": "model"})
    built = (m.get("steps") or {}).get("s_build") or {}
    els, warns = built.get("elements") or [], built.get("warnings") or []
    e = tb._find(els, root, root, "body:")
    c["the model was built"] = m["ran"] and bool(els)
    c["the parent piece: a destructible with its pieces counted (%s)" % (e and e["info"])] = \
        bool(e) and e["info"].startswith("destructible, ") and " pieces" in e["info"] and e["state"] == "WHITE"
    budget = [w for w in warns if w["code"] == "PHY_DESTRUCT_BUDGET"]
    c["more pieces than Max Pieces (%d): the budget's warning" % S["max"]] = len(budget) == 1
    m2 = tb.view_probe(args, out, "p11c_view_bullet", _blend(scenes, S["files"]["bullet"]),
                       {"BGE_REMIX_P11B_PART": "model"})
    w2 = ((m2.get("steps") or {}).get("s_build") or {}).get("warnings") or []
    c["under Bullet: noted, breaking needs PhysX"] = m2["ran"] and \
        len([w for w in w2 if w["code"] == "PHY_DESTRUCT_ENGINE"]) == 1
    frames = (10, 25, 55, 80)
    want = {10: "WHITE", 25: "BLUE", 55: "GREEN", 80: "YELLOW"}
    r = tb.view_probe(args, out, "p11c_view_run", _blend(scenes, S["files"]["physx_cpu"]),
                      {"BGE_REMIX_P11B_PART": "run", "BGE_REMIX_P11B_FRAMES": ",".join(str(f) for f in frames)})
    steps = r.get("steps") or {}
    c["Run ran"] = r["ran"]
    live = {}
    for f in frames:
        s = steps.get("s_run_%d" % f) or {}
        j = [l for l in s.get("live") or [] if l["owner"] == root and l["kind"].startswith("body:")]
        live[f] = j[0] if j else None
        c["frame %d: %s (%s)" % (f, want[f], j[0]["state"] if j else None)] = bool(j) and j[0]["state"] == want[f]
    d.update({"element": e, "budget warning": budget, "live": live, "errors": m.get("errors"),
              "run": {k: r.get(k) for k in ("exit", "seconds", "last_step", "crash")}})
    tests[name] = _test(c, d)


def t_crash(args, out, scenes, P, tests):
    S = P.get("crash")
    name = "T11.c7 The crash check"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    ran, got, r = _run(args.ours, out, S["file"], _blend(scenes, S["file"]), S["tics"] + 5)
    c = {"ran to the end": ran,
         "the destructible was found": got.get("made") is True,
         "broken-off pieces ended (%s)" % got.get("ended_broken_off"): (got.get("ended_broken_off") or 0) >= 1,
         "damaged after its parent piece was ended": got.get("damaged_after_root") is True,
         "every piece ended (%s left)" % got.get("left"): got.get("left") == 0,
         "asked for after: gone (a RuntimeError)": got.get("gone") == "RuntimeError",
         "no other error (%s)" % got.get("errors"): not got.get("errors")}
    tests[name] = _test(c, {k: got.get(k) for k in ("ended_broken_off", "left", "gone", "errors")})


def normal(args, out, scenes, E, tests, sheets):
    P = E.get("p11c") or {}
    only = _only()
    for key, fn in (("wall", t_wall), ("pillar", t_pillar), ("budget", t_budget), ("engines", t_engines),
                    ("make", t_make), ("view", t_view), ("crash", t_crash)):
        if not only or key in only:
            fn(args, out, scenes, P, tests)


def rtx(args, out, scenes, E, tests, sheets, report):
    """S11.c1: the wall hit at 10 m/s in Remix (numbers only)"""
    P = E.get("p11c") or {}
    S = P.get("wall")
    name = "S11.c1 The wall breaking in Remix (numbers only)"
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    tag = "p11c_wall_rtx"
    env = {"RTX_ENABLE_ASYNC_COMPILATION": "0", "BGE_REMIX_P11_OUT": os.path.join(out, tag + "_p11.json")}
    r = p8.play(args.ours, out, tag, _blend(scenes, S["files"]["physx_cpu_10_rtx"]), env, frames=S["tics"] + 5,
                gl_debug=False, extra=FIXED)
    probe = r.get("probe") or {}
    got = p2.read_json(os.path.join(out, tag + "_p11.json")) or {}
    c = {"ran with Remix drawing": bool(r["ran"]) and bool(probe.get("remix_drawing"))}
    d = {"frame_ms_median": _r(probe.get("frame_ms_median"), 2), "frame_ms_p95": _r(probe.get("frame_ms_p95"), 2),
         "physics_ms_mean": _r(probe.get("physics_ms_mean"), 2), "broken off": got.get("broken_off"),
         "groups": got.get("groups")}
    tests[name] = _test(c, d)
    report += ["", "B2 the wall breaking in Remix: frame %s ms (p95 %s), physics %s ms, %s pieces broken off" %
               (d["frame_ms_median"], d["frame_ms_p95"], d["physics_ms_mean"], d["broken off"])]
