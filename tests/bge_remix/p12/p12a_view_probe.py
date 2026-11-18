"""BGE-Remix P12 round 5: the Remix View of a capture scene (run inside our
Blender with its window, by p12a_tests.py, on a file p12a_probe.py viewfile
saved).

The file's 3D view is a Remix View in Check mode. After the window has
drawn a few times the model is built (Refresh) and the Remix layer is
written out: its elements (kind, name, owner, info) and its warnings (code,
level, owner, name, text). Then Blender quits.

Environment: BGE_REMIX_P12V_OUT (the JSON written).
"""

import json
import os
import traceback

import bpy

try:
    import _bge_gameview as gv
except ImportError:
    gv = None

OUT = os.environ.get("BGE_REMIX_P12V_OUT", "p12a_view.json")
result = {"steps": {}, "errors": [], "finished": False}


def window():
    return bpy.context.window_manager.windows[0]


def main_area():
    areas = [a for a in window().screen.areas if a.type in ('GAME_VIEW', 'VIEW_3D')]
    areas.sort(key=lambda a: (a.type != 'GAME_VIEW', -a.width * a.height))
    return areas[0] if areas else None


def override():
    win = window()
    area = main_area()
    region = [r for r in area.regions if r.type == 'WINDOW'][0]
    return {"window": win, "screen": win.screen, "area": area, "region": region}


def remix_layer():
    keep = ("index", "kind", "name", "owner", "state", "info")
    els = gv.elements("REMIX") if gv else []
    warnings = gv.warnings() if gv else []
    return {"elements": [{k: e.get(k) for k in keep} for e in els],
            "warnings": [{"code": w["code"], "level": w["level"], "owner": w["owner"], "name": w["name"],
                          "text": w["text"]} for w in warnings if w["layer"] == "REMIX"],
            "model": gv.model() if gv else None,
            "is_game_view": bool(getattr(main_area().spaces.active, "is_game_view", False))}


def s_build():
    ret = bpy.ops.view3d.gameview_refresh(override())
    r = remix_layer()
    r["ret"] = list(ret)
    return r


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
        print("P12 view probe: could not write the results: %r" % ex, flush=True)


class P12ViewProbe(bpy.types.Operator):
    bl_idname = "wm.bge_remix_p12_view_probe"
    bl_label = "BGE-Remix P12 view probe"
    _timer = None
    _ticks = 0

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        self._ticks += 1
        for a in window().screen.areas:
            a.tag_redraw()
        if self._ticks < 15:
            return {'PASS_THROUGH'}
        try:
            result["steps"]["build"] = s_build()
        except Exception:
            result["errors"].append(traceback.format_exc())
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


bpy.utils.register_class(P12ViewProbe)
bpy.ops.wm.bge_remix_p12_view_probe('INVOKE_DEFAULT')
