"""BGE-Remix P12 Part A: Remix modding, the tests (run by run_p12.py).

rtx(...)
  C12.1  C1, capture (recorded, not required): the room plays with the real
         RTX Remix runtime; 2 s after Remix starts drawing, the scene's
         script presses Remix's capture key (Ctrl+Shift+Q), the capture
         folder set to the results (DXVK_CAPTURE_PATH) and Remix's log too
         (DXVK_LOG_PATH). Recorded: whether a capture file appears, and how
         many meshes, materials and lights it holds; Remix's log lines about
         capturing. Expected from Remix's code: none of our meshes (Remix
         skips what is drawn through its API), or no capture at all. The
         test passes when the run itself worked (Remix drew, the key was
         pressed); its finding goes to the report.

normal(...): nothing yet this round.
"""

import os
import shutil

import run_p2 as p2
import run_p8 as p8


def _test(c, d=None):
    return {"ok": all(c.values()) and bool(c), "checks": c, "detail": d}


def _files(folder, sub, skip_ext=()):
    path = os.path.join(folder, sub)
    if not os.path.isdir(path):
        return []
    return sorted(n for n in os.listdir(path)
                  if os.path.isfile(os.path.join(path, n)) and not n.lower().endswith(skip_ext))


def _capture_contents(folder):
    """a capture folder: its stages and what is beside them"""
    stages = sorted(n for n in os.listdir(folder) if n.startswith("capture") and ".usd" in n) \
        if os.path.isdir(folder) else []
    return {"folder": folder, "stages": stages,
            "stage_bytes": {n: os.path.getsize(os.path.join(folder, n)) for n in stages},
            "meshes": _files(folder, "meshes"), "materials": _files(folder, "materials", (".mdl",)),
            "lights": _files(folder, "lights"), "textures": _files(folder, "textures")}


def _remix_log_lines(folders):
    lines = []
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for n in sorted(os.listdir(folder)):
            if not n.endswith(".log"):
                continue
            try:
                with open(os.path.join(folder, n), encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "apture" in line:
                            lines.append("%s: %s" % (n, line.strip()))
            except OSError:
                pass
    return lines[:40]


def t_capture(args, out, scenes, P, tests, report):
    name = "C12.1 C1, capture (recorded, not required)"
    S = P.get("room")
    if not S:
        tests[name] = _test({"the scenes were made": False})
        return
    tag = "p12_c1_rtx"
    caps = os.path.join(out, "c1_captures")
    logs = os.path.join(out, "c1_remix_logs")
    for d in (caps, logs):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    res = os.path.join(out, tag + "_p12.json")
    if os.path.isfile(res):
        os.remove(res)
    env = {"RTX_ENABLE_ASYNC_COMPILATION": "0", "BGE_REMIX_P12_OUT": res,
           "DXVK_CAPTURE_PATH": caps, "DXVK_LOG_PATH": logs,
           # Remix refuses to capture while replacement assets are on
           "BGE_REMIX_RTX_SET": "rtx.enableReplacementAssets=False"}
    r = p8.play(args.ours, out, tag, os.path.join(scenes, S["file"]), env, frames=100000, gl_debug=False)
    got = p2.read_json(res) or {}
    # where Remix may have put it: our folder, else its defaults beside the
    # player or the scene (the folder the player ran in)
    places = [caps, os.path.join(args.ours, "rtx-remix", "captures"), os.path.join(scenes, "rtx-remix", "captures")]
    found = [_capture_contents(f) for f in places]
    found = [f for f in found if f["stages"]]
    log_lines = _remix_log_lines([logs, os.path.join(args.ours, "rtx-remix", "logs"),
                                  os.path.join(scenes, "rtx-remix", "logs")])
    if not found:
        verdict = "no capture"
    else:
        f = found[0]
        verdict = "a capture with %d mesh(es), %d material(s), %d light(s)" % (
            len(f["meshes"]), len(f["materials"]), len(f["lights"]))
    ours = len(S.get("meshes") or [])
    c = {"ran with Remix drawing": bool(got.get("remix_drawing")),
         "the capture key pressed": "pressed_at" in got and "press_error" not in got}
    d = {"verdict": verdict, "captures": found, "remix_log": log_lines,
         "foreground window": got.get("foreground_title"), "seconds after the key": got.get("seconds_after_press"),
         "press_error": got.get("press_error"), "exit": r.get("exit"), "the room's meshes": ours}
    tests[name] = _test(c, d)
    report += ["", "C1, capture: %s (the room has %d meshes and 2 lamps; Remix's log: %d line(s) about capturing)" %
               (verdict, ours, len(log_lines))]
    report += ["    " + l for l in log_lines[:8]]


def normal(args, out, scenes, E, tests, sheets):
    pass


def rtx(args, out, scenes, E, tests, sheets, report):
    P = E.get("p12a") or {}
    t_capture(args, out, scenes, P, tests, report)
