"""BGE-Remix P12 Part A: the test scenes (made by make_scenes_p12.py).

The room (P12's capture round trip; this round its C1 check): floor, four
walls and a ceiling, with a box, a sphere, a Brick wall (the Brick preset)
and a glass pane (a Glass shader), lit by two point lamps; all made here, no
game material. The scene's script (C1_SCRIPT) waits until RTX Remix draws,
then 2 s later presses Remix's capture key (Ctrl+Shift+Q, released 10 frames
later) and waits for a capture file in DXVK_CAPTURE_PATH (at most 20 s more)
before it ends the game. What it saw goes to BGE_REMIX_P12_OUT.
"""

import os

import bpy

import make_scenes_p2 as p2
import make_scenes_p3 as p3
import make_scenes_p6 as m6
import make_scenes_p9 as m9

C1_SCRIPT = '''\
import ctypes, json, os, time
import bge
env = os.environ
g = bge.logic.globalDict
st = g.setdefault("p12c1", {"tic": 0})
VK_CONTROL, VK_SHIFT, VK_Q, KEYUP = 0x11, 0x10, 0x51, 0x0002
def keys(up):
    u = ctypes.windll.user32
    for vk in ((VK_Q, VK_SHIFT, VK_CONTROL) if up else (VK_CONTROL, VK_SHIFT, VK_Q)):
        u.keybd_event(vk, 0, KEYUP if up else 0, 0)
def captures():
    folder = env.get("DXVK_CAPTURE_PATH") or ""
    try:
        return sorted(n for n in os.listdir(folder) if n.startswith("capture") and ".usd" in n)
    except OSError:
        return []
def write():
    path = env.get("BGE_REMIX_P12_OUT")
    if path:
        with open(path, "w") as f:
            json.dump(st, f, indent=1)
now = time.time()
st["tic"] += 1
st.setdefault("start", now)
if "drawing_at" not in st:
    drawing = bge.render.isRemixDrawing() if hasattr(bge.render, "isRemixDrawing") else False
    if drawing or now - st["start"] > 150.0:
        st["drawing_at"] = now
        st["remix_drawing"] = drawing
        st["captures_before"] = captures()
elif "pressed_at" not in st:
    if now - st["drawing_at"] >= 2.0:
        try:
            u = ctypes.windll.user32
            st["foreground_title"] = ""
            h = u.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(h, buf, 256)
            st["foreground_title"] = buf.value
            keys(False)
            st["pressed_at"] = now
            st["pressed_tic"] = st["tic"]
        except Exception as e:
            st["press_error"] = repr(e)
            st["pressed_at"] = now
            st["pressed_tic"] = st["tic"]
else:
    if not st.get("released") and st["tic"] >= st["pressed_tic"] + 10:
        if "press_error" not in st:
            keys(True)
        st["released"] = True
    new = [n for n in captures() if n not in st.get("captures_before", [])]
    if new and "capture_seen_at" not in st:
        st["capture_seen_at"] = now
    # once a capture file is there, 5 s more for Remix to finish writing it
    done = ("capture_seen_at" in st and now - st["capture_seen_at"] >= 5.0) or now - st["pressed_at"] >= 20.0
    if st.get("released") and done:
        st["captures_new"] = new
        st["seconds_after_press"] = round(now - st["pressed_at"], 2)
        write()
        bge.logic.endGame()
'''


def room(scene):
    """floor, four walls, a ceiling (4 x 6 m, 3 m high), static, grey"""
    grey = m6.material("P12Room", (0.6, 0.6, 0.58))
    parts = {"Floor": ((4.0, 6.0, 0.2), (0.0, 0.0, -0.1)),
             "Ceiling": ((4.0, 6.0, 0.2), (0.0, 0.0, 3.1)),
             "WallN": ((4.0, 0.2, 3.0), (0.0, 3.1, 1.5)),
             "WallS": ((4.0, 0.2, 3.0), (0.0, -3.1, 1.5)),
             "WallE": ((0.2, 6.0, 3.0), (2.1, 0.0, 1.5)),
             "WallW": ((0.2, 6.0, 3.0), (-2.1, 0.0, 1.5))}
    for name, (size, at) in parts.items():
        m6.box(scene, name, size, at, grey, physics='STATIC')


def brick_material():
    from bl_operators.bge_remix_presets import apply_preset
    ma = bpy.data.materials.new("P12Brick")
    apply_preset(ma, 'BRICK')
    return ma


def make_room(folder):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = p3.base_scene()
    scene.name = "P12Room"
    scene.game_settings.fps = 60
    p2.world(scene, (0.05, 0.05, 0.06))
    room(scene)
    m6.box(scene, "Box", 0.6, (-0.9, 1.0, 0.3), m6.material("P12Box", (0.7, 0.45, 0.2)), physics='STATIC')
    m6.ball(scene, "Sphere", 0.35, (0.8, 1.2, 0.35), m6.material("P12Sphere", (0.3, 0.5, 0.8)), physics='STATIC')
    m6.box(scene, "BrickWall", (2.0, 0.25, 1.2), (0.0, 2.4, 0.6), brick_material(), physics='STATIC')
    glass, _nt, _s = p3.shader_material("P12Glass", "ShaderNodeBsdfGlass", Color=(1, 1, 1, 1), IOR=1.5)
    m6.box(scene, "GlassPane", (1.2, 0.02, 1.0), (0.0, 0.2, 0.9), glass, physics='STATIC')
    p2.lamp(scene, "LampA", 'POINT', (-1.2, -1.0, 2.6), energy=3.0, distance=8.0)
    p2.lamp(scene, "LampB", 'POINT', (1.2, 1.5, 2.6), energy=2.0, color=(1.0, 0.85, 0.7), distance=8.0)
    p2.camera(scene, (1.6, -2.7, 1.7), (-0.1, 1.2, 0.7), lens=22.0)
    m9.logic(scene, "P12C1", C1_SCRIPT)
    p2.add_probe(scene)
    scene["bge_remix"] = 1
    scene.update()
    p2.save(os.path.join(folder, "p12_room.blend"))
    return {"file": "p12_room.blend",
                 "meshes": ["Floor", "Ceiling", "WallN", "WallS", "WallE", "WallW", "Box", "Sphere",
                            "BrickWall", "GlassPane"],
                 "lamps": ["LampA", "LampB"]}


def make(folder, E):
    E["p12a"] = {"room": make_room(folder)}
