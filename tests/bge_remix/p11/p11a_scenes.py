"""BGE-Remix p11a: the scenes for P11 Part A (physics and motion in Remix's
picture). Runs inside our Blender (Python 3.5: no f-strings), from
make_scenes_p11.py; make(folder, E) saves the .blend files into folder and
writes what the tests expect into E["p11a"].

All of them look through P9's orthographic camera (12 m across, 960 x 540:
80 pixels a metre), in front of P9's grey backdrop 3 m behind.

p11a_motion_remix.blend   A2, the motion check (RTX Remix on). In front of
    the backdrop:
      Slider   an orange box (0.6 m, Dynamic) sliding on a frictionless
               ledge, pushed to 6 m/s and back between x -4.5 and 4.5
      Ball     a white ball (0.3 m, Rigid Body) fired across from the left
               every 1.5 s (14 m/s, a little up), removed after 1.25 s
      Wheel    a disc of 16 orange and blue slices spinning twice a second;
               WheelStill the same disc, still (the sharpness it should have)
      Arm      an armature swinging a skinned bar (1.4 m) +-55 degrees
      Flag     a 1 x 0.7 m flag waving (a shape key, its geometry new every
               frame) and moving 3 m/s back and forth
    The probe (P11Shots) takes BGE_REMIX_P11_SHOTS screenshots, the first
    BGE_REMIX_P11_AFTER s after Remix's first frame, then one every
    BGE_REMIX_P11_GAP s, and writes where each moving thing was (this tic and
    the one before) to BGE_REMIX_P11_OUT. BGE_REMIX_P11_PAN (m/s) moves the
    camera back and forth along x.
p11a_soft.blend / p11a_soft_remix.blend   A3, the softness check (the OpenGL
    picture, then Remix's). Three 3.2 m boards (one texture pixel a screen
    pixel): Lines (black and white bars 1, 2 and 4 texture pixels wide,
    upright above, lying below), Star (a 36-spoke star) and Grooves (a grey
    board with a normal map of grooves 8 pixels apart).
p11a_soft_persp.blend / p11a_soft_persp_remix.blend   the same through a
    perspective camera (50 mm, 18.75 m back: the boards the same size)
p11a_gpu_<engine>.blend   A4, sharing the graphics card (bullet, physx_cpu,
    physx_gpu; RTX Remix on): P6's walled floor; BGE_REMIX_P11_BOXES boxes
    are added once Remix draws, and the probe measures the next 600 tics
    (frame time, physics time).
p11a_substeps_<engine>_s<k>.blend   A12 (bullet, physx_cpu; substeps 1, 2,
    4): a ball thrown at a 1 m thick wall six times (12 and 30 m/s by
    turns), a Collision sensor on the ball for the wall's "wall" property.
    The probe counts the real bounces (the ball's speed along x turning
    back) and the sensor's hits.
p11a_scaled_<engine>.blend   A17 (bullet, physx_cpu): three spawners add a
    box at tic 5: Plain (scale 1), Scaled (scale 2), Child (scale 1, its
    parent's scale 2). Each adds AddedShape (no physics) and AddedBody (a
    Rigid Body box, 0.5 m) that falls onto the floor; the probe records the
    added boxes' world scale, and where the bodies rest.
"""

import math
import os

import bpy

import make_scenes_p2 as p2
import make_scenes_p3 as p3
import make_scenes_p6 as m6
import make_scenes_p9 as m9
import p96_scenes as s96

ENGINES = m6.ENGINES[:2]          # bullet, physx_cpu (A12, A17: the normal run)
GPU_ENGINES = m6.ENGINES          # bullet, physx_cpu, physx_gpu (A4)
SUBSTEPS = (1, 2, 4)

# A2's layout (metres; x across, z up, y 0 the objects' plane)
SLIDER_Z = 2.4
SLIDER_SIZE = 0.6
SLIDER_SPEED = 6.0
SLIDER_RANGE = 4.5
LEDGE_Z = 2.0
BALL_R = 0.3
BALL_START = (-6.6, 0.0, 0.5)
BALL_VELOCITY = (14.0, 0.0, 4.0)
BALL_EVERY = 90                   # tics
BALL_LIFE = 75
WHEEL = (-4.5, -1.9)
WHEEL_STILL = (-2.6, -1.9)
WHEEL_R = 0.7
WHEEL_TURNS = 2.0                 # a second
ARM_PIVOT = (-0.3, -0.9)
ARM_LENGTH = 1.4
ARM_SWING = 55.0                  # degrees either way
ARM_PERIOD = 1.2                  # seconds
FLAG = (3.4, -2.0)
FLAG_SIZE = (1.0, 0.7)
FLAG_RANGE = (2.1, 4.7)
FLAG_SPEED = 3.0

# A3's boards
BOARD = 3.2                       # metres: 256 pixels at 80 a metre
BOARD_PX = 256
BOARD_Z = 0.6
BOARDS = (("lines", -4.0), ("star", 0.0), ("grooves", 4.0))
PERSP_LENS = 50.0
# camera_for_remix (source/blender/remix/intern/remix_light.cc): the size kept
# at near + half of min(far - near, 2 x 12 m), P9's camera clipping 0.1..100
ORTHO_KEEP = 0.1 + 0.5 * min(100.0 - 0.1, 2 * 12.0)


def rect(x0, z0, x1, z1):
    """a rectangle of the view (metres) on screen: left, top, right, bottom"""
    return [s96.screen_x(x0), s96.screen_y(z1), s96.screen_x(x1), s96.screen_y(z0)]


def physical(name, colour, roughness=0.7, metallic=0.0):
    ma = m9.physical(name, colour, metallic, roughness)
    ma.diffuse_color = colour
    return ma


def finish(scene, probes):
    """P2's probe (the frames, the end of the game) and the scene's own"""
    for name, body in probes:
        m9.logic(scene, name, body)
    p2.add_probe(scene)
    scene.update()


def save(folder, name, remix):
    for sc in bpy.data.scenes:
        sc["bge_remix_pipeline"] = 1
    return m9.save_copy(folder, name, remix=remix, tone=0)


# ---------------------------------------------------------------------------
# A2: the motion check

SHOTS_SCRIPT = '''\
# BGE-Remix P11 A2: screenshots once Remix draws; where each moving thing is
import json, math, os, time
import bge
env = os.environ
scene = bge.logic.getCurrentScene()
g = bge.logic.globalDict
st = g.setdefault("p11a", {"start": None, "taken": [], "prev": {}, "tic": 0, "cam_prev": None})
st["tic"] += 1
cam = scene.active_camera
pan = float(env.get("BGE_REMIX_P11_PAN", "0") or 0)
if pan > 0:
    # back and forth along x, 1 m either way
    t = st["tic"] / 60.0
    period = 4.0 / pan
    ph = (t % period) / period
    x = -1.0 + 4.0 * ph if ph < 0.5 else 3.0 - 4.0 * ph
    p = cam.worldPosition.copy()
    p.x = x
    cam.worldPosition = p

def flat(v):
    return [round(v[0], 4), round(v[2], 4)]

def where():
    out = {}
    for ob in scene.objects:
        name = ob.name
        if name in ("Slider", "Flag", "Wheel", "WheelStill"):
            out[name] = flat(ob.worldPosition)
        elif name == "Ball":
            out["Ball#%d" % id(ob)] = flat(ob.worldPosition)
        elif name == "Arm":
            ch = ob.channels["Bone"]
            tip = ob.worldTransform * ch.pose_tail
            out["ArmTip"] = flat(tip)
    return out

now = where()
shots = [s for s in env.get("BGE_REMIX_P11_SHOTS", "").split(";") if s]
if shots and st["start"] is None and (bge.render.isRemixDrawing() or env.get("BGE_REMIX_P11_NO_REMIX") == "1"):
    st["start"] = time.perf_counter()
if shots and st["start"] is not None and len(st["taken"]) < len(shots):
    after = float(env.get("BGE_REMIX_P11_AFTER", "8"))
    gap = float(env.get("BGE_REMIX_P11_GAP", "0.5"))
    if time.perf_counter() - st["start"] >= after + gap * len(st["taken"]):
        path = shots[len(st["taken"])]
        bge.render.makeScreenshot(path)
        st["taken"].append({"path": path, "tic": st["tic"], "now": now, "prev": st["prev"],
                            "cam": flat(cam.worldPosition), "cam_prev": st["cam_prev"] or flat(cam.worldPosition),
                            "window": [bge.render.getWindowWidth(), bge.render.getWindowHeight()]})
        out = env.get("BGE_REMIX_P11_OUT")
        if out:
            with open(out, "w") as f:
                json.dump({"shots": st["taken"]}, f, indent=1)
st["prev"] = now
st["cam_prev"] = flat(cam.worldPosition)
'''

SLIDER_SCRIPT = '''\
# BGE-Remix P11 A2: the slider at SPEED m/s along x, back at +-RANGE
import bge
ob = bge.logic.getCurrentController().owner
d = ob.get("dir", 1)
x = ob.worldPosition.x
if x > RANGE:
    d = -1
elif x < -RANGE:
    d = 1
ob["dir"] = d
v = ob.worldLinearVelocity.copy()
v.x = d * SPEED
v.y = 0.0
ob.worldLinearVelocity = v
'''

BALLS_SCRIPT = '''\
# BGE-Remix P11 A2: a ball fired across every EVERY tics, for LIFE tics
import bge
ob = bge.logic.getCurrentController().owner
t = ob.get("t", 0) + 1
ob["t"] = t
if t % EVERY == 1:
    b = bge.logic.getCurrentScene().addObject("Ball", ob, LIFE)
    b.worldLinearVelocity = VELOCITY
'''

WHEEL_SCRIPT = '''\
# BGE-Remix P11 A2: TURNS turns a second about the view's axis
import math
import bge
ob = bge.logic.getCurrentController().owner
ob.applyRotation((0.0, 2.0 * math.pi * TURNS / 60.0, 0.0), False)
'''

ARM_SCRIPT = '''\
# BGE-Remix P11 A2: the bone swings +-SWING degrees, PERIOD s a swing
import math
import bge
from mathutils import Quaternion
ob = bge.logic.getCurrentController().owner
t = ob.get("t", 0) + 1
ob["t"] = t
a = math.radians(SWING) * math.sin(2.0 * math.pi * t / (60.0 * PERIOD))
ch = ob.channels["Bone"]
ch.rotation_mode = 0  # quaternion
ch.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), a)
ob.update()
'''

FLAG_SCRIPT = '''\
# BGE-Remix P11 A2: the flag along x at SPEED m/s between X0 and X1
import bge
ob = bge.logic.getCurrentController().owner
d = ob.get("dir", 1)
x = ob.worldPosition.x + d * SPEED / 60.0
if x > X1:
    x, d = X1, -1
elif x < X0:
    x, d = X0, 1
ob["dir"] = d
p = ob.worldPosition.copy()
p.x = x
ob.worldPosition = p
'''


def fill(text, **values):
    for k, v in values.items():
        text = text.replace(k, repr(v))
    return text


def disc(scene, name, centre, mats):
    """a disc of 16 slices facing the camera, the slices' materials by turns"""
    import bmesh
    me = bpy.data.meshes.new(name + "Mesh")
    bm = bmesh.new()
    mid = bm.verts.new((0.0, 0.0, 0.0))
    rim = [bm.verts.new((WHEEL_R * math.cos(2 * math.pi * k / 16), 0.0, WHEEL_R * math.sin(2 * math.pi * k / 16)))
           for k in range(16)]
    for k in range(16):
        f = bm.faces.new((mid, rim[k], rim[(k + 1) % 16]))   # facing the camera (-Y)
        f.material_index = k % 2
    bm.to_mesh(me)
    bm.free()
    for ma in mats:
        me.materials.append(ma)
    ob = bpy.data.objects.new(name, me)
    ob.location = (centre[0], 0.0, centre[1])
    scene.objects.link(ob)
    ob.game.physics_type = 'NO_COLLISION'
    return ob


def arm(scene, ma):
    """an armature with one bone hanging down from ARM_PIVOT, a bar skinned
    to it"""
    pivot = (ARM_PIVOT[0], 0.0, ARM_PIVOT[1])
    ad = bpy.data.armatures.new("ArmData")
    rig = bpy.data.objects.new("Arm", ad)
    rig.location = pivot
    scene.objects.link(rig)
    scene.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    b = ad.edit_bones.new("Bone")
    b.head = (0.0, 0.0, 0.0)
    b.tail = (0.0, 0.0, -ARM_LENGTH)
    b.roll = 0.0
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.pose.bones["Bone"].rotation_mode = 'QUATERNION'
    w = 0.12
    me = bpy.data.meshes.new("ArmBarMesh")
    verts, faces = [], []
    rings = 8
    for k in range(rings + 1):
        z = -ARM_LENGTH * k / rings
        verts += [(-w, -w, z), (w, -w, z), (w, w, z), (-w, w, z)]
    for k in range(rings):
        a = 4 * k
        for s in range(4):
            faces.append((a + s, a + (s + 1) % 4, a + 4 + (s + 1) % 4, a + 4 + s))
    faces += [(0, 3, 2, 1), (4 * rings, 4 * rings + 1, 4 * rings + 2, 4 * rings + 3)]
    faces = [tuple(reversed(f)) for f in faces]   # (facing out)
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(ma)
    bar = bpy.data.objects.new("ArmBar", me)
    scene.objects.link(bar)
    bar.parent = rig
    bar.parent_type = 'ARMATURE'   # skinned (BGE then leaves it out of the scene graph's parenting)
    bar.game.physics_type = 'NO_COLLISION'
    vg = bar.vertex_groups.new("Bone")
    vg.add(list(range(len(verts))), 1.0, 'REPLACE')
    mod = bar.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    return rig


def flag(scene, ma):
    """a flag (10 x 7 quads) with a shape key "Wave" its action plays back
    and forth"""
    nx, nz = 10, 7
    w, h = FLAG_SIZE
    verts = [(-w / 2 + w * i / nx, 0.0, -h / 2 + h * j / nz) for j in range(nz + 1) for i in range(nx + 1)]
    faces = [(j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i)
             for j in range(nz) for i in range(nx)]
    me = bpy.data.meshes.new("FlagMesh")
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(ma)
    ob = bpy.data.objects.new("Flag", me)
    ob.location = (FLAG[0], 0.0, FLAG[1])
    scene.objects.link(ob)
    ob.game.physics_type = 'NO_COLLISION'
    ob.shape_key_add(name="Basis")
    key = ob.shape_key_add(name="Wave")
    for i, v in enumerate(key.data):
        x = verts[i][0]
        amp = 0.12 * (x + w / 2) / w            # still at the pole, waving at the end
        v.co.z = verts[i][2] + amp * math.sin(2 * math.pi * (x + w / 2) / w * 1.5)
    act = bpy.data.actions.new("FlagWave")
    fc = act.fcurves.new('key_blocks["Wave"].value')
    for frame, value in ((1, 0.0), (10, 1.0), (20, 0.0)):
        fc.keyframe_points.insert(frame, value)
    keys = me.shape_keys
    keys.animation_data_create()
    keys.animation_data.action = act
    scene.objects.active = ob
    bpy.ops.logic.sensor_add(type='ALWAYS', object=ob.name)
    bpy.ops.logic.controller_add(type='LOGIC_AND', object=ob.name)
    bpy.ops.logic.actuator_add(type='ACTION', object=ob.name)
    s, c, a = ob.game.sensors[-1], ob.game.controllers[-1], ob.game.actuators[-1]
    a.action = act
    a.play_mode = 'PINGPONG'
    a.frame_start = 1
    a.frame_end = 20
    s.link(c)
    c.link(actuator=a)
    return ob


def make_motion(folder, E):
    scene = s96.scene_base("P11aMotion")
    # light from the camera's side, straight on: each shadow falls behind its
    # object, the same moving either way
    sun = scene.objects["Sun"]
    sun.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    scene.game_settings.fps = 60
    scene.game_settings.physics_gravity = 9.81
    orange = physical("P11_orange", (0.9, 0.45, 0.1))
    white = physical("P11_white", (0.85, 0.85, 0.85))
    blue = physical("P11_blue", (0.1, 0.25, 0.8))
    dark = physical("P11_dark", (0.08, 0.08, 0.08))
    for ma in (orange, white, blue, dark):
        ma.physics.friction = 0.0

    m6.box(scene, "Ledge", (11.2, 1.0, 0.2), (0.0, 0.0, LEDGE_Z), dark, physics='STATIC')
    slider = m6.box(scene, "Slider", SLIDER_SIZE, (0.0, 0.0, LEDGE_Z + 0.1 + SLIDER_SIZE / 2 + 0.01), orange,
                    physics='DYNAMIC')
    m6.logic(scene, slider, "p11_slider.py", fill(SLIDER_SCRIPT, SPEED=SLIDER_SPEED, RANGE=SLIDER_RANGE))

    ball = m6.ball(scene, "Ball", BALL_R, (0.0, 0.0, -20.0), white)
    ball.layers[1] = True
    ball.layers[0] = False
    spawner = bpy.data.objects.new("BallSpawner", None)
    spawner.location = BALL_START
    scene.objects.link(spawner)
    m6.logic(scene, spawner, "p11_balls.py",
             fill(BALLS_SCRIPT, EVERY=BALL_EVERY, LIFE=BALL_LIFE, VELOCITY=BALL_VELOCITY))

    wheel = disc(scene, "Wheel", WHEEL, (orange, blue))
    m6.logic(scene, wheel, "p11_wheel.py", fill(WHEEL_SCRIPT, TURNS=WHEEL_TURNS))
    disc(scene, "WheelStill", WHEEL_STILL, (orange, blue))

    rig = arm(scene, white)
    m6.logic(scene, rig, "p11_arm.py", fill(ARM_SCRIPT, SWING=ARM_SWING, PERIOD=ARM_PERIOD))
    fl = flag(scene, orange)
    m6.logic(scene, fl, "p11_flag.py", fill(FLAG_SCRIPT, SPEED=FLAG_SPEED, X0=FLAG_RANGE[0], X1=FLAG_RANGE[1]))

    finish(scene, [("P11Shots", SHOTS_SCRIPT)])
    name = save(folder, "p11a_motion_remix", 1)
    E["motion"] = {
        "file": name, "ortho": m9.ORTHO, "size": [m9.WIDTH, m9.HEIGHT],
        # half sizes (metres) of what is measured, and its kind
        "things": {"Slider": {"half": [SLIDER_SIZE / 2, SLIDER_SIZE / 2], "kind": "physics, Dynamic"},
                   "Ball": {"half": [BALL_R, BALL_R], "kind": "physics, Rigid Body, added and removed"},
                   "ArmTip": {"half": [0.16, 0.16], "kind": "skinned (an armature)"},
                   "Flag": {"half": [FLAG_SIZE[0] / 2, FLAG_SIZE[1] / 2 + 0.12], "kind": "deformed (a shape key)"}},
        "wheel": {"Wheel": list(WHEEL), "WheelStill": list(WHEEL_STILL), "radius": WHEEL_R, "turns": WHEEL_TURNS},
        "wall_rect": rect(-5.8, 2.9, -4.8, 3.3),
    }


# ---------------------------------------------------------------------------
# A3: the softness check

def lines_px(i, j):
    """bars: the left third 1 pixel wide, the middle 2, the right 4; upright
    in the top half, lying in the bottom half"""
    third = BOARD_PX // 3
    width = 1 if i < third else (2 if i < 2 * third else 4)
    k = (i if j >= BOARD_PX // 2 else j) // width
    v = 0.9 if k % 2 == 0 else 0.05
    return (v, v, v, 1.0)


def star_px(i, j):
    x = (i + 0.5) / BOARD_PX - 0.5
    y = (j + 0.5) / BOARD_PX - 0.5
    a = math.atan2(y, x)
    v = 0.9 if int(math.floor(a / (2 * math.pi) * 72)) % 2 == 0 else 0.05
    if x * x + y * y > 0.24:
        v = 0.5
    return (v, v, v, 1.0)


def grooves_px(i, j):
    """a normal map: a groove every 8 pixels (a V across x)"""
    k = i % 8
    nx = -0.5 if k < 4 else 0.5
    if k in (0, 7):
        nx = 0.0
    nz = math.sqrt(1.0 - nx * nx)
    return (0.5 + 0.5 * nx, 0.5, 0.5 + 0.5 * nz, 1.0)


def board_image(name, fn, non_color=False):
    img = bpy.data.images.new(name, BOARD_PX, BOARD_PX, alpha=True)
    if non_color:
        img.colorspace_settings.name = 'Non-Color'
    px = []
    for j in range(BOARD_PX):
        for i in range(BOARD_PX):
            px.extend(fn(i, j))
    img.pixels = px
    img.pack(as_png=True)
    return img


def make_soft(folder, E):
    scene = s96.scene_base("P11aSoft")
    rects = {}
    for key, x in BOARDS:
        ma = p3.bi_material("P11_board_" + key, (0.8, 0.8, 0.8))
        if key == "grooves":
            p3.bi_slot(ma, board_image("P11_" + key, grooves_px, non_color=True), normal=True)
        else:
            p3.bi_slot(ma, board_image("P11_" + key, lines_px if key == "lines" else star_px), color=True)
        s96.uv_square(scene, "Board_" + key, BOARD, (x, 0.0, BOARD_Z), ma)
        h = BOARD / 2
        r = rect(x - h, BOARD_Z - h, x + h, BOARD_Z + h)
        rects[key] = r
        if key == "lines":
            # the six bar groups, each inset 4 pixels
            t, b = r[1], r[3]
            mid = (t + b) // 2
            cols = [r[0] + (r[2] - r[0]) * k // 3 for k in range(4)]
            for k, wpx in enumerate((1, 2, 4)):
                rects["lines_up_%d" % wpx] = [cols[k] + 4, t + 4, cols[k + 1] - 4, mid - 4]
                rects["lines_flat_%d" % wpx] = [cols[k] + 4, mid + 4, cols[k + 1] - 4, b - 4]
    finish(scene, [])
    files = {"opengl": save(folder, "p11a_soft", 0), "remix": save(folder, "p11a_soft_remix", 1)}
    # the Render tab's DLSS setting (BRMX_quality_from_scene: 4 Quality, 5 DLAA),
    # the way a person sets it (round 1 set Remix's options from outside, and
    # Remix's Auto preset sometimes undid them)
    for tag, dlss in (("quality", 4), ("dlaa", 5)):
        scene["bge_remix_dlss"] = dlss
        files["remix_" + tag] = save(folder, "p11a_soft_remix_" + tag, 1)
    del scene["bge_remix_dlss"]
    # the same through a perspective camera: 50 mm on a 32 mm wide sensor,
    # far enough back that the boards' plane is 12 m across, as before
    cam = scene.camera
    cam.data.type = 'PERSP'
    cam.data.lens = PERSP_LENS
    cam.data.sensor_width = 32.0
    cam.data.sensor_fit = 'HORIZONTAL'
    cam.location = (0.0, -m9.ORTHO * PERSP_LENS / 32.0, 0.0)
    scene.update()
    files["persp_opengl"] = save(folder, "p11a_soft_persp", 0)
    files["persp_remix"] = save(folder, "p11a_soft_persp_remix", 1)
    scene["bge_remix_dlss"] = 5
    files["persp_remix_dlaa"] = save(folder, "p11a_soft_persp_remix_dlaa", 1)
    del scene["bge_remix_dlss"]
    E["soft"] = {"files": files, "rects": rects, "size": [m9.WIDTH, m9.HEIGHT],
                 # the orthographic camera reaches Remix moved back (factor x 12 m) and keeps
                 # its size KEEP m in front: at the boards (20 m) the picture is this much smaller
                 "ortho_keep": ORTHO_KEEP, "ortho_board_distance": 20.0}


# ---------------------------------------------------------------------------
# A4: sharing the graphics card

GPU_PROBE = '''\
# BGE-Remix P11 A4: boxes added once Remix draws; the next TICS tics measured
import json, os, time
import bge
env = os.environ
scene = bge.logic.getCurrentScene()
g = bge.logic.globalDict
st = g.setdefault("p11gpu", {"added": None, "times": [], "physics": [], "waited": time.perf_counter()})
now = time.perf_counter()
drawing = bge.render.isRemixDrawing() or env.get("BGE_REMIX_P11_NO_REMIX") == "1"
if st["added"] is None and (drawing or now - st["waited"] > 150.0):
    n = int(env.get("BGE_REMIX_P11_BOXES", "1000"))
    side = int(round(n ** (1.0 / 3.0) + 0.4999))
    k = 0
    spawner = scene.objects["Spawner"]
    for z in range(side):
        for y in range(side):
            for x in range(side):
                if k < n:
                    b = scene.addObject("BenchBox", spawner, 0)
                    b.worldPosition = ((x - side / 2.0) * 0.6, (y - side / 2.0) * 0.6, 1.0 + z * 0.6)
                    k += 1
    st["added"] = k
    st["drawing"] = drawing
    print("BGE-Remix P11 A4: %d boxes added" % k)
elif st["added"] is not None:
    st["times"].append(now)
    info = bge.logic.getProfileInfo()
    if "Physics:" in info:
        st["physics"].append(info["Physics:"][0])
    if len(st["times"]) >= TICS:
        t = st["times"][30:]
        d = sorted(b - a for a, b in zip(t, t[1:]))
        ph = st["physics"][30:]
        out = {"boxes": st["added"], "remix_drawing": st["drawing"], "frames": len(st["times"]),
               "frame_ms_median": 1000.0 * d[len(d) // 2] if d else None,
               "frame_ms_p95": 1000.0 * d[int(len(d) * 0.95)] if d else None,
               "physics_ms_mean": sum(ph) / len(ph) if ph else None,
               "objects": len(scene.objects)}
        path = env.get("BGE_REMIX_P11_OUT") or env.get("BGE_REMIX_P2_OUT")
        if path:
            with open(path, "w") as f:
                json.dump(out, f, indent=1)
        bge.logic.endGame()
'''

GPU_TICS = 600


def make_gpu(folder, E):
    files = {}
    for key, engine, device in GPU_ENGINES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11aGpu")
        grey = m6.material("GpuGround", (0.5, 0.5, 0.5))
        m6.box(scene, "Floor", (60.0, 60.0, 0.2), (0, 0, -0.1), grey, physics='STATIC')
        for k, (x, y) in enumerate(((-30.5, 0), (30.5, 0), (0, -30.5), (0, 30.5))):
            m6.box(scene, "GpuWall%d" % k, (1.0 if x else 60.0, 60.0 if x else 1.0, 4.0), (x, y, 2.0), grey,
                   physics='STATIC')
        bb = m6.box(scene, "BenchBox", 0.5, (0, 0, -20), m6.material("GpuBoxMa", (0.8, 0.6, 0.2)))
        bb.layers[1] = True
        bb.layers[0] = False
        spawner = bpy.data.objects.new("Spawner", None)
        scene.objects.link(spawner)
        p2.camera(scene, (0.0, -30.0, 20.0), (0.0, 0.0, 0.0), lens=24.0)
        m6.set_engine(scene, engine, device)
        m9.logic(scene, "P11Gpu", GPU_PROBE.replace("TICS", str(GPU_TICS)))
        scene["bge_remix"] = 1
        scene["bge_remix_pipeline"] = 1   # RTX Remix (an unset pipeline is Classic)
        scene.update()
        path = os.path.join(folder, "p11a_gpu_%s.blend" % key)
        p2.save(path)
        files[key] = os.path.basename(path)[:-6]
    E["gpu"] = {"files": files, "tics": GPU_TICS}


# ---------------------------------------------------------------------------
# A12: collisions with substeps

SUBSTEP_PROBE = '''\
# BGE-Remix P11 A12: the ball thrown at the wall every EVERY tics; the real
# bounces and the Collision sensor's hits counted
import json, os
import bge
env = os.environ
scene = bge.logic.getCurrentScene()
g = bge.logic.globalDict
st = g.setdefault("p11sub", {})
for k, v in (("tic", 0), ("bounces", []), ("hits", []), ("vx", None), ("throws", []), ("positive", 0)):
    st.setdefault(k, v)
st["tic"] += 1
tic = st["tic"]
ball = scene.objects["Ball"]
if tic % EVERY == 1 and len(st["throws"]) < THROWS:
    speed = SPEEDS[len(st["throws"]) % len(SPEEDS)]
    ball.worldPosition = START
    ball.worldLinearVelocity = (speed, 0.0, 0.0)
    ball.worldAngularVelocity = (0.0, 0.0, 0.0)
    st["throws"].append([tic, speed])
    st["vx"] = speed
else:
    vx = ball.worldLinearVelocity.x
    if st["vx"] is not None and st["vx"] > 0.5 and vx < -0.5 and ball.worldPosition.x > WALL_NEAR:
        st["bounces"].append(tic)
    st["vx"] = vx
s = ball.sensors["HitWall"]
if s.positive:
    st["positive"] += 1
end = int(env.get("BGE_REMIX_P2_FRAMES", "600"))
if tic >= end - 2:
    path = env.get("BGE_REMIX_P11_OUT")
    if path:
        with open(path, "w") as f:
            json.dump(st, f, indent=1)
'''

HIT_SCRIPT = '''\
# BGE-Remix P11 A12: the sensor's hits (it fires on touching the wall)
import bge
c = bge.logic.getCurrentController()
s = c.sensors["HitWall"]
if s.positive:
    g = bge.logic.globalDict.setdefault("p11sub", {})
    g.setdefault("hits", []).append(g.get("tic", 0))
'''

SUB_EVERY = 90
SUB_THROWS = 6
SUB_SPEEDS = (12.0, 30.0)
SUB_START = (0.0, 0.0, 0.3)
WALL_X = 6.0


def make_substeps(folder, E):
    files = {}
    for key, engine, device in ENGINES:
        for sub in SUBSTEPS:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            scene = m6.base("P11aSubsteps")
            scene.game_settings.physics_step_sub = sub
            ground = m6.material("SubGround", (0.5, 0.5, 0.5), friction=0.0)
            m6.box(scene, "Floor", (30.0, 6.0, 0.2), (0, 0, -0.1), ground, physics='STATIC')
            # (round 1 fix: the wall bounces too; with the floor's elasticity 0
            # the ball, its 0.6 times the wall's 0, stopped dead at the wall)
            bouncy = m6.material("SubWall", (0.6, 0.6, 0.6), friction=0.0, bounce=1.0)
            wall = m6.box(scene, "Wall", (1.0, 6.0, 3.0), (WALL_X + 0.5, 0, 1.5), bouncy, physics='STATIC')
            prop = wall.game.properties
            bpy.context.scene.objects.active = wall
            bpy.ops.object.game_property_new(type='BOOL', name="wall")
            del prop
            ball = m6.ball(scene, "Ball", 0.25, SUB_START, m6.material("SubBall", (0.9, 0.9, 0.9), friction=0.0,
                                                                        bounce=0.6))
            scene.objects.active = ball
            bpy.ops.logic.sensor_add(type='COLLISION', name="HitWall", object=ball.name)
            s = ball.game.sensors[-1]
            s.property = "wall"
            bpy.ops.logic.controller_add(type='PYTHON', object=ball.name)
            c = ball.game.controllers[-1]
            t = bpy.data.texts.new("p11_hit.py")
            t.write(HIT_SCRIPT)
            c.mode = 'SCRIPT'
            c.text = t
            s.link(c)
            p2.camera(scene, (2.0, -14.0, 3.0), (2.0, 0.0, 0.5), lens=30.0)
            m6.set_engine(scene, engine, device)
            body = (SUBSTEP_PROBE.replace("EVERY", str(SUB_EVERY)).replace("THROWS", str(SUB_THROWS))
                    .replace("SPEEDS", repr(SUB_SPEEDS)).replace("START", repr(SUB_START))
                    .replace("WALL_NEAR", repr(WALL_X - 1.5)))
            m9.logic(scene, "P11Sub", body)
            p2.add_probe(scene)
            scene["bge_remix"] = 0
            scene.update()
            name = "p11a_substeps_%s_s%d" % (key, sub)
            p2.save(os.path.join(folder, name + ".blend"))
            files["%s_s%d" % (key, sub)] = name
    E["substeps"] = {"files": files, "throws": SUB_THROWS, "every": SUB_EVERY, "speeds": list(SUB_SPEEDS),
                     "tics": SUB_EVERY * SUB_THROWS + 30}


# ---------------------------------------------------------------------------
# A17: adding from a scaled child

SCALED_PROBE = '''\
# BGE-Remix P11 A17: each spawner adds AddedShape and AddedBody at tic 5;
# their world scale at tic 6, where the bodies rest at tic 150
import json, os
import bge
env = os.environ
scene = bge.logic.getCurrentScene()
g = bge.logic.globalDict
st = g.setdefault("p11sc", {"tic": 0, "added": {}, "scale": {}, "rest": {}})
st["tic"] += 1
tic = st["tic"]
if tic == 5:
    for sp in ("Plain", "Scaled", "Child"):
        for what in ("AddedShape", "AddedBody"):
            ob = scene.addObject(what, scene.objects["Spawner" + sp], 0)
            ob["tag"] = sp + "/" + what
if tic in (6, 150):
    for ob in scene.objects:
        tag = ob.get("tag")
        if not tag:
            continue
        if tic == 6:
            st["scale"][tag] = [round(v, 4) for v in ob.worldScale]
        else:
            st["rest"][tag] = [round(v, 4) for v in ob.worldPosition]
if tic == 151:
    path = env.get("BGE_REMIX_P11_OUT")
    if path:
        with open(path, "w") as f:
            json.dump(st, f, indent=1)
'''

SPAWNERS = (("Plain", -3.0, 1.0, None), ("Scaled", 0.0, 2.0, None), ("Child", 3.0, 1.0, 2.0))
ADDED = 0.5


def make_scaled(folder, E):
    files = {}
    for key, engine, device in ENGINES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11aScaled")
        grey = m6.material("ScGround", (0.5, 0.5, 0.5))
        m6.box(scene, "Floor", (20.0, 8.0, 0.2), (0, 0, -0.1), grey, physics='STATIC')
        shape = p2.cube(scene, "AddedShape", ADDED, (0, 0, -20), m6.material("ScShape", (0.2, 0.5, 0.9)))
        shape.game.physics_type = 'NO_COLLISION'
        body = m6.box(scene, "AddedBody", ADDED, (0, 0, -22), m6.material("ScBody", (0.9, 0.5, 0.2)), unscaled=True)
        for ob in (shape, body):
            ob.layers[1] = True
            ob.layers[0] = False
        for name, x, scale, parent_scale in SPAWNERS:
            sp = bpy.data.objects.new("Spawner" + name, None)
            scene.objects.link(sp)
            if parent_scale:
                par = bpy.data.objects.new("SpawnerParent", None)
                scene.objects.link(par)
                par.location = (x, 0.0, 2.0)
                par.scale = (parent_scale,) * 3
                sp.parent = par
                sp.location = (0.0, 0.0, 0.0)
            else:
                sp.location = (x, 0.0, 2.0)
                sp.scale = (scale,) * 3
        p2.camera(scene, (0.0, -14.0, 2.0), (0.0, 0.0, 1.0), lens=30.0)
        m6.set_engine(scene, engine, device)
        m9.logic(scene, "P11Scaled", SCALED_PROBE)
        p2.add_probe(scene)
        scene["bge_remix"] = 0
        scene.update()
        name = "p11a_scaled_%s" % key
        p2.save(os.path.join(folder, name + ".blend"))
        files[key] = name
    E["scaled"] = {"files": files, "size": ADDED,
                   "spawners": {n: {"own": s, "parent": ps} for n, x, s, ps in SPAWNERS}}


def make(folder, E):
    E["p11a"] = P = {}
    # (each scene starts from Blender's empty factory settings)
    for fn in (make_motion, make_soft, make_gpu, make_substeps, make_scaled):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sub = {}
        fn(folder, sub)
        P.update(sub)
