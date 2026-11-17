"""BGE-Remix P12: OpenUSD, Remix modding and USD exchange
(run_local.bat p12rtx, also run_p12_rtx.bat).

--rtx (the real RTX Remix runtime): this round, the C1 check (does Remix
capture a BGE-Remix scene?)
--normal: the tests that need no real Remix (none yet this round)

The tracks (each its own scene module and test module):
  p12a  Part A: Remix modding (this round: C1, capture)

BGE_REMIX_P12_TRACKS (comma separated) runs only those tracks.
"""

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "p9"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "p6"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "p8"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "p2"))
import run_p2 as p2  # noqa: E402  (running Blender, contact sheets)
import run_p8 as p8  # noqa: E402  (the player, pictures, the fake runtime)

TRACKS = ("p12a",)


def make_scenes(ours, out):
    scenes = os.path.join(out, "scenes")
    shutil.rmtree(scenes, ignore_errors=True)
    os.makedirs(scenes, exist_ok=True)
    code, text, _ = p2.run([p2.exe(ours, "blender"), "--background", "--factory-startup", "--python",
                            os.path.join(HERE, "make_scenes_p12.py"), "--", scenes],
                           p2.base_env(out, "make"), os.path.join(out, "make_scenes_p12.log"), timeout=1800)
    expected = p2.read_json(os.path.join(scenes, "p12_expected.json")) or {}
    if code != 0 or not expected:
        print("\n".join((text or "").splitlines()[-40:]))
        raise SystemExit("making the P12 scenes failed, see make_scenes_p12.log")
    return scenes, expected


def track_modules():
    """the tracks' test modules; BGE_REMIX_P12_TRACKS (comma separated) runs only those (a fix round's reruns)"""
    import importlib
    only = [t.strip() for t in os.environ.get("BGE_REMIX_P12_TRACKS", "").split(",") if t.strip()]
    return [(t, importlib.import_module(t + "_tests")) for t in TRACKS if not only or t in only]


def summary(title, tests, sheets, report_lines, name):
    lines = [title, "=" * 70, ""]
    for test, t in tests.items():
        lines.append("%-56s %s" % (test, p2.mark(t["ok"])))
        for check, ok in t["checks"].items():
            lines.append("      %s %s" % ("ok    " if ok else "FAILED", check))
    if report_lines:
        lines += [""] + report_lines
    if sheets:
        lines += ["", "Picture sheets:"] + ["  %-16s %s" % kv for kv in sheets.items() if kv[1]]
    ok = all(t["ok"] for t in tests.values()) and bool(tests)
    lines += ["", "ALL PASSED" if ok else "SOMETHING FAILED (see results_%s.json and the logs)" % name]
    return {"all_ok": ok, "tests": tests, "sheets": sheets}, lines


def run_tracks(args, out, rtx):
    scenes, E = make_scenes(args.ours, out)
    tests, sheets, report = {}, {}, []
    for track, mod in track_modules():
        try:
            if rtx:
                mod.rtx(args, out, scenes, E, tests, sheets, report)
            else:
                mod.normal(args, out, scenes, E, tests, sheets)
        except Exception:
            import traceback
            tests["%s: the track's tests ran" % track] = {"ok": False, "checks": {"ran without an error": False},
                                                          "detail": traceback.format_exc()}
    if E.get("failed"):
        tests["P12 scenes made"] = {"ok": False, "checks": {k + " made": False for k in E["failed"]},
                                    "detail": E["failed"]}
    name = "p12_rtx" if rtx else "p12"
    title = ("BGE-Remix P12 (RTX run: your RTX card, the real RTX Remix runtime)" if rtx else
             "BGE-Remix P12: OpenUSD (normal run)")
    res, lines = summary(title, tests, sheets, report, name)
    return res, lines, name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--official")
    ap.add_argument("--mock")
    ap.add_argument("--results", help="the phases' results")
    ap.add_argument("--normal", action="store_true", help="the normal run (the fake runtime)")
    ap.add_argument("--rtx", action="store_true", help="the RTX run (the real runtime)")
    args = ap.parse_args()
    args.ours = os.path.abspath(args.ours)
    p8.OURS["build"] = args.ours
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    args.results = os.path.abspath(args.results or os.path.dirname(out))
    if args.rtx:
        res, lines, name = run_tracks(args, out, True)
    else:
        if not args.mock:
            ap.error("--mock is needed (the fake RTX Remix runtime)")
        res, lines, name = run_tracks(args, out, False)
    with open(os.path.join(out, "results_%s.json" % name), "w") as f:
        json.dump(res, f, indent=2, default=str)
    text = "\n".join(lines) + "\n"
    with open(os.path.join(out, "summary_%s.txt" % name), "w") as f:
        f.write(text)
    print(text)
    sys.exit(0 if res["all_ok"] else 1)


if __name__ == "__main__":
    main()
