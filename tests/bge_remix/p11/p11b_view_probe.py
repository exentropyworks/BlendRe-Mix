# BGE-Remix p11b probe: the Remix View's articulation colours (B1) in
# Blender's UI (Python 3.5), then quits.
#   blender -p 0 0 1600 900 <file> --python p11b_view_probe.py
#
# Parts (BGE_REMIX_P11B_PART):
#   model  the model built (Check mode): the physics layer's elements and the
#          warnings
#   run    Run on the whole scene, suspended after each of
#          BGE_REMIX_P11B_FRAMES (comma separated) frames, started over each
#          time: the live states of the physics layer's joints
# Results: BGE_REMIX_P11B_OUT (JSON).

import json
import os
import traceback

import bpy

try:
    import _bge_gameview as gv
except ImportError:
    gv = None

OUT = os.environ.get("BGE_REMIX_P11B_OUT", "p11b_view.json")
DIR = os.environ.get("BGE_REMIX_P11B_DIR", os.path.dirname(os.path.abspath(OUT)))
PART = os.environ.get("BGE_REMIX_P11B_PART", "model")
FRAMES = [int(f) for f in os.environ.get("BGE_REMIX_P11B_FRAMES", "10").split(",") if f.strip()]

result = {"steps": {}, "errors": [], "finished": False, "part": PART}
QUEUE = []


def window():
    return bpy.context.window_manager.windows[0]


def main_area():
    areas = [a for a in window().screen.areas if a.type in ('GAME_VIEW', 'VIEW_3D')]
    areas.sort(key=lambda a: (a.type != 'GAME_VIEW', -a.width * a.height))
    return areas[0] if areas else None


def region():
    return [r for r in main_area().regions if r.type == 'WINDOW'][0]


def override():
    win = window()
    return {"window": win, "screen": win.screen, "area": main_area(), "region": region(),
            "scene": bpy.context.scene}


def physics():
    keep = ("index", "kind", "name", "owner", "state", "info")
    els = gv.elements("PHYSICS") if gv else []
    warnings = gv.warnings() if gv else []
    return {"elements": [{k: e[k] for k in keep} for e in els],
            "warnings": [{"code": w["code"], "level": w["level"], "owner": w["owner"], "name": w["name"],
                          "text": w["text"]} for w in warnings if w["layer"] == "PHYSICS"]}


def s_build():
    ret = bpy.ops.view3d.gameview_refresh(override())
    r = physics()
    r["ret"] = list(ret)
    return r


def run_op(fn, **kw):
    try:
        return list(fn(override(), **kw))
    except RuntimeError as ex:
        return ["error: %s" % ex]


def live_joints():
    out = []
    for l in gv.live():
        if l["kind"].startswith(("joint:", "body:")):
            out.append({k: l[k] for k in ("kind", "owner", "name", "state", "present", "text")})
    return out


def make_run(frames):
    def s_run():
        bpy.ops.gameview.mode(override(), mode='RUN')
        ret = run_op(bpy.ops.gameview.run, scope='SCENE', suspend_after=frames,
                     shot=os.path.join(DIR, "run_%d.png" % frames))
        r = {"ret": ret, "frames": frames, "live": live_joints()}
        r["stop"] = run_op(bpy.ops.gameview.run_stop, keep='NO')
        return r
    s_run.__name__ = "s_run_%d" % frames
    return s_run


def queue_all():
    QUEUE.append((5, s_build))
    if PART == "run":
        for f in FRAMES:
            QUEUE.append((5, make_run(f)))


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return repr(value)


def write():
    try:
        with open(OUT, "w") as f:
            json.dump(_clean(result), f, indent=1)
    except (OSError, TypeError, ValueError) as ex:
        print("P11b probe: could not write the results: %r" % ex, flush=True)


def step(name, fn):
    print("P11b step", name, flush=True)
    try:
        result["steps"][name] = fn()
    except Exception:
        result["errors"].append("%s: %s" % (name, traceback.format_exc()))
    result["last_step"] = name
    write()


class P11bProbe(bpy.types.Operator):
    bl_idname = "wm.bge_remix_p11b_probe"
    bl_label = "BGE-Remix p11b probe"
    _timer = None
    _ticks = 0

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        self._ticks += 1
        for a in window().screen.areas:
            a.tag_redraw()
        if self._ticks < 10:
            return {'PASS_THROUGH'}
        if not result.get("queued"):
            result["queued"] = True
            queue_all()
        if QUEUE:
            wait, fn = QUEUE[0]
            if wait > 0:
                QUEUE[0] = (wait - 1, fn)
                return {'PASS_THROUGH'}
            QUEUE.pop(0)
            step(fn.__name__, fn)
            return {'PASS_THROUGH'}
        result["finished"] = True
        context.window_manager.event_timer_remove(self._timer)
        write()
        context.user_preferences.view.use_quit_dialog = False
        bpy.ops.wm.quit_blender()
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}


bpy.utils.register_class(P11bProbe)
bpy.ops.wm.bge_remix_p11b_probe('INVOKE_DEFAULT')
