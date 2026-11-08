"""BGE-Remix p11a: the tests of P11 Part A (physics and motion in Remix's
picture). The scenes: p11a_scenes.py.

normal(args, out, scenes, E, tests, sheets)   no RTX card needed
  T11.a12  collisions with substeps (A12, test first): with Bullet and PhysX
           at substeps 1, 2 and 4, the Collision sensor fires once for every
           real bounce
  T11.a17  adding from a scaled child (A17, test first): the added boxes'
           size from each spawner, both engines alike, and each body's
           physics shape the size it is drawn
rtx(args, out, scenes, E, tests, sheets, report)   the real RTX Remix runtime
  S11.a2   motion trails: behind each moving thing against ahead of it, and
           the spinning wheel's slices against the still one's, with the
           default settings, DLAA, ray reconstruction off, frame generation
           off and the camera panning (numbers only: no pass mark yet)
  S11.a3   softness: the boards' contrast and fine detail in Remix's picture
           against the OpenGL picture, at the default settings, DLSS
           Quality, DLAA, ray reconstruction off, render scale 1, Remix's
           reference mode and a 1920 x 1080 window (numbers only)
  S11.a4   sharing the graphics card: 1,000, 3,000 and 5,000 boxes with
           Bullet, PhysX on the CPU and PhysX on the GPU, Remix drawing:
           frame time, physics time, graphics memory and load (numbers only)
"""

import json
import math
import os
import subprocess
import threading
import time

import run_p2 as p2
import run_p8 as p8

FIXED = ["-g", "fixedtime", "=", "1"]      # one 1/60 s physics step per frame
NO_REMIX = ["-g", "remix", "=", "0"]

# Remix's option values (rtx_options.h, rtx_dlss.h): graphicsPreset Custom 4;
# dlssPreset Custom 2; qualityDLSS MaxQuality 3, FullResolution (DLAA) 5
CUSTOM = "rtx.graphicsPreset=4;rtx.dlssPreset=2"
MOTION_RUNS = (
    ("default", "your settings (DLSS Auto, ray reconstruction)", {}),
    ("dlaa", "DLAA (full resolution)", {"BGE_REMIX_RTX_SET": CUSTOM + ";rtx.qualityDLSS=5"}),
    ("pan", "the camera panning (1.5 m/s)", {"BGE_REMIX_P11_PAN": "1.5"}),
)
# (round 1 also ran ray reconstruction off and frame generation off: no trail
# either; the RTX 3080 has no frame generation, Remix's log says)
DLAA = {"BGE_REMIX_RTX_SET": CUSTOM + ";rtx.qualityDLSS=5"}
# (key, label, environment, window size, the scene, its OpenGL picture, the
# orthographic camera's factor back: None for a perspective camera)
SOFT_RUNS = (
    ("default", "your settings", {}, None, "remix", "opengl", 100),
    ("quality", "DLSS Quality", {"BGE_REMIX_RTX_SET": CUSTOM + ";rtx.qualityDLSS=3"}, None, "remix", "opengl", 100),
    ("dlaa", "DLAA", DLAA, None, "remix", "opengl", 100),
    ("rr_off", "ray reconstruction off", {"BGE_REMIX_RTX_SET": "rtx.enableRayReconstruction=False"}, None, "remix",
     "opengl", 100),
    ("scale1", "render scale 1.0", {"BGE_REMIX_RTX_SET": "rtx.graphicsPreset=4;rtx.resolutionScale=1.0"}, None,
     "remix", "opengl", 100),
    ("reference", "Remix's reference mode", {"BGE_REMIX_RTX_SET": "rtx.useDenoiserReferenceMode=True"}, None,
     "remix", "opengl", 100),
    ("big", "a 1920 x 1080 window", {}, (1920, 1080), "remix", "opengl", 100),
    ("back20_dlaa", "DLAA, the orthographic camera 240 m back (not 1,200)", dict(DLAA, BGE_REMIX_ORTHO_BACK="20"),
     None, "remix", "opengl", 20),
    ("back5_dlaa", "DLAA, the orthographic camera 60 m back", dict(DLAA, BGE_REMIX_ORTHO_BACK="5"), None, "remix",
     "opengl", 5),
    ("persp_default", "a perspective camera, your settings", {}, None, "persp_remix", "persp_opengl", None),
    ("persp_dlaa", "a perspective camera, DLAA", DLAA, None, "persp_remix", "persp_opengl", None),
)
SHOTS = 6
AFTER = 8.0
GAP = 0.5
GPU_COUNTS = (1000, 3000, 5000)


# ---------------------------------------------------------------------------
# helpers

def _blend(scenes, name):
    return os.path.join(scenes, name + ".blend")


def _plain_run(args, out, tag, blend, env, frames):
    """the player without Remix, one physics step a frame"""
    e = dict(env)
    e["BGE_REMIX_P2_FRAMES"] = str(frames)
    return p2.player(args.ours, out, tag, blend, e, size=(640, 360), args=FIXED + NO_REMIX)


def _test(c, d=None):
    return {"ok": bool(c) and all(c.values()), "checks": c, "detail": d or {}}


def _lum(a):
    return a[:, :, 0] * 0.2126 + a[:, :, 1] * 0.7152 + a[:, :, 2] * 0.0722


def _r(v, n=2):
    return None if v is None else round(v, n)


# ---------------------------------------------------------------------------
# T11.a12, T11.a17 (normal)

def t_substeps(args, out, scenes, P, tests):
    S = P.get("substeps")
    c, d = {}, {}
    if not S:
        tests["T11.a12 Collisions with substeps (A12)"] = _test({"the scenes were made": False})
        return
    for key, name in sorted(S["files"].items()):
        res = os.path.join(out, name + "_p11.json")
        if os.path.isfile(res):
            os.remove(res)
        r = _plain_run(args, out, name, _blend(scenes, name), {"BGE_REMIX_P11_OUT": res}, S["tics"])
        got = p2.read_json(res) or {}
        bounces, hits = got.get("bounces") or [], got.get("hits") or []
        throws = got.get("throws") or []
        d[key] = {"throws": throws, "bounces": bounces, "sensor hits": hits, "positive tics": got.get("positive")}
        c["%s: ran" % key] = r["exit"] == 0 and not r["traceback_in_output"] and bool(got)
        c["%s: %d throws, a real bounce each (%d)" % (key, S["throws"], len(bounces))] = \
            len(throws) == S["throws"] and len(bounces) == S["throws"]
        c["%s: the Collision sensor fired once a bounce (%d hits, %d bounces)" % (key, len(hits), len(bounces))] = \
            bool(bounces) and len(hits) == len(bounces)
    tests["T11.a12 Collisions with substeps (A12)"] = _test(c, d)


def t_scaled(args, out, scenes, P, tests):
    S = P.get("scaled")
    c, d = {}, {}
    if not S:
        tests["T11.a17 Adding from a scaled child (A17)"] = _test({"the scenes were made": False})
        return
    scales = {}
    for key, name in sorted(S["files"].items()):
        res = os.path.join(out, name + "_p11.json")
        if os.path.isfile(res):
            os.remove(res)
        r = _plain_run(args, out, name, _blend(scenes, name), {"BGE_REMIX_P11_OUT": res}, 160)
        got = p2.read_json(res) or {}
        c["%s: ran" % key] = r["exit"] == 0 and not r["traceback_in_output"] and bool(got)
        scales[key] = got.get("scale") or {}
        d[key] = got
        for sp in S["spawners"]:
            sc = (got.get("scale") or {}).get(sp + "/AddedBody")
            rest = (got.get("rest") or {}).get(sp + "/AddedBody")
            if sc and rest:
                want = S["size"] * 0.5 * sc[2]
                c["%s, %s: the body rests at half its drawn height (%.3f m, drawn %.3f)" % (key, sp, rest[2], want)] = \
                    abs(rest[2] - want) <= 0.03
            else:
                c["%s, %s: the body was added and came to rest" % (key, sp)] = False
    keys = sorted(scales)
    if len(keys) == 2:
        c["Bullet and PhysX give the added boxes the same size"] = scales[keys[0]] == scales[keys[1]]
    d["what comes out (world scale)"] = {k: {t: v[0] for t, v in s.items()} for k, s in scales.items()}
    tests["T11.a17 Adding from a scaled child (A17)"] = _test(c, d)


def normal(args, out, scenes, E, tests, sheets):
    P = E.get("p11a") or {}
    t_substeps(args, out, scenes, P, tests)
    t_scaled(args, out, scenes, P, tests)


# ---------------------------------------------------------------------------
# S11.a2: motion trails

def _screen(xz, cam, W, H, ortho):
    ppm = W / ortho
    return (W / 2.0 + (xz[0] - cam[0]) * ppm, H / 2.0 - (xz[1] - cam[1]) * ppm)


def _sample(img, cx, cy, ux, uy, along0, along1, half_across):
    """an image's pixels in a rectangle along (ux, uy) from along0 to along1
    off (cx, cy), half_across either side, and each one's place along: None
    when it leaves the picture"""
    import numpy as np
    H, W = img.shape[:2]
    a = np.arange(along0, along1, 1.0)
    b = np.arange(-half_across, half_across + 0.5, 1.0)
    if a.size == 0 or b.size == 0:
        return None, None
    A, B = np.meshgrid(a, b)
    xs = np.round(cx + A * ux - B * uy).astype(int)
    ys = np.round(cy + A * uy + B * ux).astype(int)
    if xs.min() < 0 or ys.min() < 0 or xs.max() >= W or ys.max() >= H:
        return None, None
    return img[ys, xs], A


OBJECT_DIST = 45.0   # colour difference from the wall (0-255 a channel, summed): the thing itself


def motion_metrics(pic, shot, M, wall_rgb):
    """for one picture, each moving thing found in the picture itself (its
    pixels near where the probe put it, back along its motion): how far it
    lags the probe (frames), and the wall just behind it against just ahead
    of it ("trail": the mean colour difference from the wall behind minus
    ahead, 0-255; 0 = no trail)"""
    import numpy as np
    if pic is None:
        return None
    dist = np.abs(pic[:, :, :3] - np.asarray(wall_rgb)).sum(axis=2)
    H, W = dist.shape
    out = {}
    for name, xz in shot["now"].items():
        base = name.split("#")[0]
        T = M["things"].get(base)
        prev = (shot.get("prev") or {}).get(name)
        if not T or not prev:
            continue
        sx, sy = _screen(xz, shot["cam"], W, H, M["ortho"])
        px, py = _screen(prev, shot["cam_prev"], W, H, M["ortho"])
        vx, vy = sx - px, sy - py
        speed = math.hypot(vx, vy)
        if speed < 1.0:
            continue
        ux, uy = vx / speed, vy / speed
        ppm = W / M["ortho"]
        hx, hz = T["half"][0] * ppm, T["half"][1] * ppm
        reach = abs(ux) * hx + abs(uy) * hz          # the thing's extent along its motion
        across = max(2.0, (abs(uy) * hx + abs(ux) * hz) * 0.7)
        # where it is in the picture: up to 6 frames behind the probe
        vals, A = _sample(dist, sx, sy, ux, uy, -(reach + 6 * speed), reach + speed, across)
        if vals is None:
            continue
        on = A[vals > OBJECT_DIST]
        if on.size < 10:
            continue
        trail_edge, lead_edge = float(np.percentile(on, 2)), float(np.percentile(on, 98))
        lag = -0.5 * (trail_edge + lead_edge) / speed
        gap, length = 3.0, 2.0 * reach
        behind, _ = _sample(dist, sx, sy, ux, uy, trail_edge - gap - length, trail_edge - gap, across)
        ahead, _ = _sample(dist, sx, sy, ux, uy, lead_edge + gap, lead_edge + gap + length, across)
        if behind is None or ahead is None:
            continue
        db, da = float(behind.mean()) / 3.0, float(ahead.mean()) / 3.0
        out[name] = {"trail": round(db - da, 2), "behind": round(db, 2), "ahead": round(da, 2),
                     "speed_px": round(speed, 1), "lag_frames": round(lag, 2),
                     "length_px": round(lead_edge - trail_edge, 1), "expected_px": round(2 * reach, 1)}
    return out


def wheel_metrics(shot, M):
    """the spinning wheel's slices: their spread of brightness against the
    still wheel's (1 = as sharp as standing still)"""
    import numpy as np
    pic = p8.picture(shot["path"])
    if pic is None:
        return None
    lum = _lum(pic)
    H, W = lum.shape
    res = {}
    for name in ("Wheel", "WheelStill"):
        cx, cy = _screen(M["wheel"][name], shot["cam"], W, H, M["ortho"])
        r = M["wheel"]["radius"] * W / M["ortho"]
        ys, xs = np.mgrid[0:H, 0:W]
        d = np.hypot(xs - cx, ys - cy)
        ring = (d > 0.3 * r) & (d < 0.85 * r)
        if not ring.any():
            return None
        res[name] = float(lum[ring].std())
    if not res.get("WheelStill"):
        return None
    return round(res["Wheel"] / res["WheelStill"], 3)


def s_motion(args, out, scenes, P, tests, sheets, report):
    import numpy as np
    import run_p9 as r9
    M = P.get("motion")
    c, d = {}, {}
    if not M:
        tests["S11.a2 Motion trails in Remix (A2)"] = _test({"the scene was made": False})
        return
    table, sheet = [], []
    for key, label, extra in MOTION_RUNS:
        tag = "p11a_motion_" + key
        res = os.path.join(out, tag + "_shots.json")
        paths = [os.path.join(out, "%s_%d.png" % (tag, k)) for k in range(SHOTS)]
        for p in [res] + paths:
            if os.path.isfile(p):
                os.remove(p)
        env = dict(r9.TEXTURE_ENV)
        env.update({"BGE_REMIX_P11_SHOTS": ";".join(paths), "BGE_REMIX_P11_AFTER": str(AFTER),
                    "BGE_REMIX_P11_GAP": str(GAP), "BGE_REMIX_P11_OUT": res})
        env.update(extra)
        r = p8.play(args.ours, out, tag, _blend(scenes, M["file"]), env, frames=60,
                    seconds=AFTER + GAP * SHOTS + 2.0, debug=True, extra=FIXED)
        shots = (p2.read_json(res) or {}).get("shots") or []
        shots = [s for s in shots if os.path.isfile(s["path"])]
        c["%s: ran in Remix, %d pictures" % (label, SHOTS)] = bool(r["ran"]) and len(shots) == SHOTS
        per, wheels, black = {}, [], []
        for s in shots:
            pic = p8.picture(s["path"])
            if pic is None:
                continue
            if float(pic.mean()) < 20.0:
                black.append(os.path.basename(s["path"]))
                continue
            wall = np.median(p8.crop(pic, M["wall_rect"])[:, :, :3].reshape(-1, 3), axis=0)
            m = motion_metrics(pic, s, M, wall) or {}
            for name, v in m.items():
                per.setdefault(name.split("#")[0], []).append(v)
            w = wheel_metrics(s, M)
            if w is not None:
                wheels.append(w)
        summary = {}
        for thing, vals in per.items():
            trails = sorted(v["trail"] for v in vals)
            lags = sorted(v["lag_frames"] for v in vals)
            summary[thing] = {"trail_median": trails[len(trails) // 2], "trail_max": trails[-1],
                              "samples": len(trails), "speed_px": vals[0]["speed_px"],
                              "lag_frames_median": lags[len(lags) // 2]}
        st = r.get("stats") or {}
        # (P11 fix: a frame Remix had no new picture for showed the cleared,
        # black window; round 1 caught one in a picture)
        c["%s: no black picture (%s)" % (label, ", ".join(black) or "none")] = not black
        d[key] = {"label": label, "things": summary, "wheel_sharpness": wheels, "black": black,
                  "frames_kept": st.get("frames_kept"), "frames_blank": st.get("frames_blank"), "all": per}
        table.append("  %-12s %s   wheel %s" % (key, "  ".join(
            "%s %s (lag %s)" % (t, _r(summary[t]["trail_median"], 1), _r(summary[t]["lag_frames_median"], 1))
            for t in sorted(summary)),
            _r(sorted(wheels)[len(wheels) // 2] if wheels else None, 2)) +
            "   frames with no new picture: %s kept, %s blank" % (st.get("frames_kept"), st.get("frames_blank")))
        if shots:
            sheet.append(("%s: picture 1" % label, shots[0]["path"]))
            if key == "default" and len(shots) > 1:
                sheet.append(("%s: picture 2" % label, shots[1]["path"]))
    tests["S11.a2 Motion trails in Remix (A2, numbers only)"] = _test(c, d)
    sheets["p11a_motion"] = p2.contact_sheet(sheet, os.path.join(out, "sheet_p11a_motion.png"))
    report += ["", "A2 motion trails (the wall behind each thing minus ahead of it, colour difference 0-255:",
               "0 = no trail; lag: frames the picture is behind the game; wheel: its slices' contrast",
               "against the still wheel's, 1 = as sharp):"] + table


# ---------------------------------------------------------------------------
# S11.a3: softness

def soft_metrics(pic, rects):
    """per board region: contrast (p95 - p5) / (p95 + p5) and fine detail
    (the mean step between neighbours over the mean brightness)"""
    import numpy as np
    if pic is None:
        return None
    lum = _lum(pic)
    out = {}
    for key, r in rects.items():
        reg = lum[r[1]:r[3], r[0]:r[2]]
        if reg.size == 0:
            continue
        lo, hi = np.percentile(reg, 5), np.percentile(reg, 95)
        mean = float(reg.mean()) or 1.0
        steps = (abs(np.diff(reg, axis=1)).mean() + abs(np.diff(reg, axis=0)).mean()) / 2.0
        out[key] = {"contrast": round(float((hi - lo) / max(hi + lo, 1e-6)), 3),
                    "detail": round(float(steps / mean), 4)}
    return out


def _scaled_rects(rects, k, size, base):
    """the rectangles shrunk by k about the picture's centre, then to the
    window's size"""
    cx, cy = base[0] / 2.0, base[1] / 2.0
    f = size[0] / float(base[0])
    out = {}
    for key, r in rects.items():
        out[key] = [int(round((cx + (r[0] - cx) * k) * f)), int(round((cy + (r[1] - cy) * k) * f)),
                    int(round((cx + (r[2] - cx) * k) * f)), int(round((cy + (r[3] - cy) * k) * f))]
    return out


def s_soft(args, out, scenes, P, tests, sheets, report):
    import run_p9 as r9
    S = P.get("soft")
    c, d = {}, {}
    if not S:
        tests["S11.a3 Softness in Remix (A3)"] = _test({"the scene was made": False})
        return
    keys = ["lines_up_1", "lines_up_2", "lines_up_4", "star", "grooves"]
    table, sheet, refs = [], [], {}
    for ref in ("opengl", "persp_opengl"):
        gl = p8.play(args.ours, out, "p11a_soft_" + ref, _blend(scenes, S["files"][ref]),
                     {"BGE_REMIX_P2_SHOT_FRAME": "100"}, frames=120)
        refs[ref] = soft_metrics(p8.picture(gl.get("screenshot")), S["rects"])
        c["the %s picture" % ref.replace("_", " ")] = bool(gl["ran"]) and bool(refs[ref])
        d[ref] = refs[ref]
        sheet.append((ref.replace("_", " "), gl.get("screenshot")))
        if refs[ref]:
            table.append("  %-14s %s" % (ref, "  ".join("%s %.2f" % (k, refs[ref][k]["contrast"])
                                                       for k in keys if k in refs[ref])))
    for key, label, extra, size, scene_key, ref_key, factor in SOFT_RUNS:
        env = dict(r9.TEXTURE_ENV)
        env.update(extra)
        old = p8.SIZE
        if size:
            p8.SIZE = size
        try:
            r = p8.play(args.ours, out, "p11a_soft_" + key, _blend(scenes, S["files"][scene_key]), env,
                        frames=p8.REMIX_FRAMES, seconds=r9.TEXTURE_SECONDS, debug=True)
        finally:
            p8.SIZE = old
        k = 1.0
        if factor:
            back = factor * 12.0
            k = (back + S["ortho_keep"]) / (back + S["ortho_board_distance"])
        rects = _scaled_rects(S["rects"], k, size or S["size"], S["size"])
        m = soft_metrics(p8.picture(r.get("screenshot")), rects)
        c["%s: ran in Remix, every texture in" % label] = bool(r["ran"]) and r9.textures_in(r) and bool(m)
        ref = refs.get(ref_key)
        rel = {}
        if m and ref:
            for kk in m:
                if kk in ref and ref[kk]["contrast"] > 0:
                    rel[kk] = {"contrast_vs_opengl": round(m[kk]["contrast"] / ref[kk]["contrast"], 3),
                               "detail_vs_opengl": round(m[kk]["detail"] / max(ref[kk]["detail"], 1e-6), 3)}
        d[key] = {"label": label, "measured": m, "against_opengl": rel}
        if m:
            table.append("  %-14s %s" % (key, "  ".join("%s %.2f" % (kk, m[kk]["contrast"]) for kk in keys if kk in m)))
        sheet.append((label, r.get("screenshot")))
    tests["S11.a3 Softness in Remix (A3, numbers only)"] = _test(c, d)
    sheets["p11a_soft"] = p2.contact_sheet(sheet, os.path.join(out, "sheet_p11a_soft.png"))
    report += ["", "A3 softness (contrast of each board region, 0-1; the OpenGL pictures first):"] + table


# ---------------------------------------------------------------------------
# S11.a4: sharing the graphics card

class GpuWatch(object):
    """nvidia-smi's graphics memory and load every half second while a run
    goes (nothing when nvidia-smi is not there)"""

    def __init__(self):
        self.samples, self.proc, self.thread = [], None, None

    def __enter__(self):
        try:
            self.proc = subprocess.Popen(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                                          "--format=csv,noheader,nounits", "-lms", "500"],
                                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
        except OSError:
            self.proc = None
            return self
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        return self

    def _read(self):
        for line in self.proc.stdout:
            try:
                mem, util = (float(x) for x in line.strip().split(",")[:2])
                self.samples.append((time.time(), mem, util))
            except ValueError:
                pass

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def summary(self, since=None):
        s = [x for x in self.samples if since is None or x[0] >= since]
        if not s:
            return {}
        return {"memory_mb_peak": max(x[1] for x in s), "load_pct_mean": round(sum(x[2] for x in s) / len(s), 1),
                "samples": len(s)}


def s_gpu(args, out, scenes, P, tests, sheets, report):
    G = P.get("gpu")
    c, d = {}, {}
    if not G:
        tests["S11.a4 Sharing the graphics card (A4)"] = _test({"the scenes were made": False})
        return
    table = []
    for n in GPU_COUNTS:
        row = []
        for key in ("bullet", "physx_cpu", "physx_gpu"):
            name = G["files"].get(key)
            if not name:
                continue
            tag = "p11a_gpu_%s_%d" % (key, n)
            env = {"RTX_ENABLE_ASYNC_COMPILATION": "0", "BGE_REMIX_P11_BOXES": str(n)}
            with GpuWatch() as watch:
                start = time.time()
                r = p8.play(args.ours, out, tag, _blend(scenes, name), env, frames=G["tics"], gl_debug=False,
                            extra=FIXED)
            probe = r.get("probe") or {}
            # (the memory and load while the boxes fall: the run's last part)
            gpu = watch.summary(since=start + max(0.0, r.get("seconds_total", 0) - 15.0))
            c["%s, %d boxes: ran with Remix drawing" % (key, n)] = bool(r["ran"]) and bool(probe.get("remix_drawing"))
            d[tag] = {"frame_ms_median": _r(probe.get("frame_ms_median")), "frame_ms_p95": _r(probe.get("frame_ms_p95")),
                      "physics_ms_mean": _r(probe.get("physics_ms_mean")), "gpu": gpu,
                      "log_says_gpu": "PhysX uses the GPU" in (r.get("text") or "")}
            row.append("%s %s/%s ms %s MB" % (key, _r(probe.get("frame_ms_median"), 1),
                                              _r(probe.get("physics_ms_mean"), 1), gpu.get("memory_mb_peak")))
        table.append("  %5d boxes: %s" % (n, "   ".join(row)))
    tests["S11.a4 Sharing the graphics card (A4, numbers only)"] = _test(c, d)
    report += ["", "A4 sharing the graphics card (frame / physics ms, graphics memory at its peak):"] + table


def rtx(args, out, scenes, E, tests, sheets, report):
    P = E.get("p11a") or {}
    s_motion(args, out, scenes, P, tests, sheets, report)
    s_soft(args, out, scenes, P, tests, sheets, report)
    s_gpu(args, out, scenes, P, tests, sheets, report)
