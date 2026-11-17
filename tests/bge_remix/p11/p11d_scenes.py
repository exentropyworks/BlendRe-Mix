"""BGE-Remix p11d: the scenes for P11 Part B step 3 (B3, game fluids). Runs
inside our Blender (Python 3.5: no f-strings), from make_scenes_p11.py;
make(folder, E) saves the .blend files into folder and writes what the
tests expect into E["p11d"]. Each scene's own script writes what it
measured to BGE_REMIX_P11_OUT at its last tic.

Every volume is made by Make Fluid Volume. The pool: a 6 x 6 x 2 m box of
water standing on the floor (its surface at 2 m); the floor's top at 0.

p11d_pool_<engine>.blend   (physx_cpu, bullet) a 1 m box of 300 kg and one
    of 2000 kg let go with their bottoms at the surface. At the last tic
    (10 s) the script records where they are, how fast they move, how much
    of the light one is under (submerged), the volume's settings and the
    objects in it.
p11d_drop_physx_cpu.blend   a light ball (0.25 m, 20 kg) dropped from 3 m
    above the pool's surface: its height and speed every tic; the engine's
    splash lines (BGE_REMIX_SPLASH_LOG) say where it splashed.
p11d_drop_physx_cpu_remix.blend   the same with Remix on (the fake runtime:
    the splash sent to Remix's GPU particles; the RTX run: in Remix).
p11d_river_physx_cpu.blend   a 20 x 4 x 1 m channel of water with a 1 m/s
    current along x; a 2 x 1 x 0.2 m raft of 100 kg upstream: how far it
    drifts from tic 30 to tic 330 (5 s), and sideways.
p11d_versus_<water|lava>.blend   the pool of water, and of lava: a 1 m box
    of 1500 kg let go at the surface; a 300 kg one let go 1 m down (how fast
    it starts up after the first step); a 300 kg one thrown in sideways at
    5 m/s (its speed a second later).
p11d_plank_physx_cpu.blend   a 2 x 0.4 x 0.2 m plank of 30 kg stood on its
    end in the pool, tipped 6 degrees: after 10 s, how far its length is
    from level.
p11d_view_<engine>.blend   (physx_cpu, bullet) the pool for the Remix View:
    a 2000 kg box let go 0.5 m above the surface (in at about frame 19), a
    light ball (0.25 m, 40 kg) 5 m above (in at about frame 61); and the
    river's channel beside it (its current's arrows). One physics step a
    frame (Use Frame Rate off).
p11d_lava_remix.blend   a lava pool (the Lava preset from Make Fluid Volume)
    with Remix on, for the fake runtime: its flipbook and its glow.
p11d_crash_physx_cpu.blend   the crash check: the pool with three boxes
    floating; tic 60 one is ended, tic 90 the pool is ended, tic 100 its
    volume (fetched at tic 10) is asked for again, tic 110 a box is added
    where the pool was; the boxes left fall to the bottom.
Make Fluid Volume itself (while the scenes are made): its settings, the
    Ghost and its bounds, the Water preset on a mesh without a material (a
    flipbook; a UV map made), a material of its own kept, Lava's preset
    (its glow wired), made again.
"""

import math
import os

import bpy
from mathutils import Vector

import make_scenes_p2 as p2
import make_scenes_p6 as m6
import make_scenes_p9 as m9

TICS = 600          # 10 s
TICS_RIVER = 330
TICS_VERSUS = 540
TICS_CRASH = 160
SURFACE = 2.0

COMMON = '''\
import json, os
import bge
from mathutils import Vector
env = os.environ
scene = bge.logic.getCurrentScene()
g = bge.logic.globalDict
cons = bge.constraints
def obj(name):
    return scene.objects.get(name)
def fluid(ob):
    if ob is None or not hasattr(cons, "getFluid"):
        return None
    try:
        return cons.getFluid(ob)
    except Exception:
        return None
def write(st):
    path = env.get("BGE_REMIX_P11_OUT")
    if path:
        with open(path, "w") as f:
            json.dump(st, f, indent=1)
'''

POOL_SCRIPT = COMMON + '''
st = g.setdefault("p11d", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 2:
    v = fluid(obj("Pool"))
    st["fluid"] = None if v is None else {"type": v.type, "density": v.density, "drag": v.drag,
                                         "current": list(v.current), "splashes": v.splashes,
                                         "volume": v.volume.name}
    st["floor_is_fluid"] = fluid(obj("Floor")) is not None
if tic == TICS:
    for n in ("Light", "Heavy"):
        o = obj(n)
        st[n] = {"z": o.worldPosition.z, "speed": o.getLinearVelocity().length}
    v = fluid(obj("Pool"))
    st["submerged_light"] = v.submerged(obj("Light")) if v else None
    st["objects"] = sorted(o.name for o in v.objects) if v else None
    write(st)
'''

DROP_SCRIPT = COMMON + '''
import time
st = g.setdefault("p11d", {"tic": 0, "z": [], "speed": []})
# (the RTX run: the ball held until RTX Remix draws; it takes about half a
# minute to start)
WAIT = env.get("BGE_REMIX_P11D_WAIT_REMIX") == "1"
if WAIT and not st.get("go"):
    st.setdefault("waited", time.time())
    if not st.get("held"):
        obj("Ball").suspendDynamics()
        st["held"] = True
    drawing = bge.render.isRemixDrawing() if hasattr(bge.render, "isRemixDrawing") else False
    if drawing or time.time() - st["waited"] > 150.0:
        st["go"] = True
        st["remix_drawing"] = drawing
        obj("Ball").restoreDynamics()
if st.get("go") or not WAIT:
    st["tic"] += 1
    st.setdefault("times", []).append(time.time())
    b = obj("Ball")
    st["z"].append(b.worldPosition.z)
    st["speed"].append(b.getLinearVelocity().length)
    if st["tic"] == TICS:
        t = st["times"]
        dt = sorted(y - x for x, y in zip(t, t[1:]))
        st["frame_ms_median"] = 1000.0 * dt[len(dt) // 2] if dt else None
        st["frame_ms_p95"] = 1000.0 * dt[int(len(dt) * 0.95)] if dt else None
        del st["times"]
        write(st)
        if WAIT:
            bge.logic.endGame()
'''

RIVER_SCRIPT = COMMON + '''
st = g.setdefault("p11d", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 30:
    st["from"] = list(obj("Raft").worldPosition)
if tic == TICS:
    st["to"] = list(obj("Raft").worldPosition)
    v = fluid(obj("River"))
    st["current"] = list(v.current) if v else None
    write(st)
'''

VERSUS_SCRIPT = COMMON + '''
st = g.setdefault("p11d", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 1:
    obj("Thrown").setLinearVelocity((5.0, 0.0, 0.0), False)
if tic == 2:
    st["pushed_up_speed"] = obj("Pushed").getLinearVelocity().z
if tic == 61:
    st["thrown_speed"] = obj("Thrown").getLinearVelocity().x
if tic == TICS:
    st["heavy_z"] = obj("Heavy").worldPosition.z
    write(st)
'''

PLANK_SCRIPT = COMMON + '''
st = g.setdefault("p11d", {"tic": 0})
st["tic"] += 1
if st["tic"] == TICS:
    o = obj("Plank")
    st["length_axis"] = list(o.worldOrientation.col[2])
    st["z"] = o.worldPosition.z
    write(st)
'''

CRASH_SCRIPT = COMMON + '''
st = g.setdefault("p11d", {"tic": 0, "errors": []})
st["tic"] += 1
tic = st["tic"]
if tic == 10:
    g["p11d_v"] = fluid(obj("Pool"))
    st["made"] = g["p11d_v"] is not None
if tic == 60:
    obj("Box0").endObject()
if tic == 90:
    obj("Pool").endObject()
if tic == 100:
    try:
        g["p11d_v"].current
        st["gone"] = "no error"
    except RuntimeError:
        st["gone"] = "RuntimeError"
    except Exception as ex:
        st["gone"] = repr(ex)
    try:
        g["p11d_v"].current = (1.0, 0.0, 0.0)
        st["set_gone"] = "no error"
    except RuntimeError:
        st["set_gone"] = "RuntimeError"
    except Exception as ex:
        st["set_gone"] = repr(ex)
if tic == 110:
    try:
        scene.addObject("Spare", obj("SparePlace"))
    except Exception as ex:
        st["errors"].append("tic 110: %r" % ex)
if tic == TICS:
    # (round 1: "SparePlace", the empty it is added at, counted as a box)
    st["left"] = {o.name: o.worldPosition.z for o in scene.objects if o.name.startswith("Box") or o.name == "Spare"}
    write(st)
'''


def make_volume(scene, ob, **kw):
    """Make Fluid Volume on ob"""
    for o in scene.objects:
        o.select = o == ob
    scene.objects.active = ob
    ret = bpy.ops.object.bge_remix_make_fluid_volume(**kw)
    if 'FINISHED' not in ret:
        raise RuntimeError("Make Fluid Volume on %s: %s" % (ob.name, ret))
    return ob


def plain_box(scene, name, size, location):
    """a box mesh without a material (Make Fluid Volume gives it its preset)"""
    bpy.ops.mesh.primitive_cube_add(location=location)
    ob = bpy.context.object
    ob.name = name
    ob.data.name = name + "Mesh"
    ob.scale = (size[0] * 0.5, size[1] * 0.5, size[2] * 0.5)
    scene.update()
    return ob


def floor(scene, size=30.0):
    return m6.box(scene, "Floor", (size, size, 0.2), (0.0, 0.0, -0.1), m6.material("DFloor", (0.5, 0.5, 0.5)),
                  physics='STATIC')


def pool(scene, name="Pool", fluid_type='WATER', x=0.0):
    ob = plain_box(scene, name, (6.0, 6.0, 2.0), (x, 0.0, 1.0))
    kw = {"fluid_type": fluid_type}
    if fluid_type == 'LAVA':
        kw.update(density=3100.0, drag=24.0)
    return make_volume(scene, ob, **kw)


def crate(scene, name, location, mass, size=1.0):
    return m6.box(scene, name, size, location, m6.material("D" + name, (0.7, 0.5, 0.25)), mass=mass)


def scene_for(name, engine='PHYSX'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base(name)
    m6.set_engine(scene, engine, 'CPU' if engine == 'PHYSX' else None)
    floor(scene)
    return scene


def save(folder, name, remix=0):
    for sc in bpy.data.scenes:
        sc["bge_remix"] = remix
    p2.save(os.path.join(folder, name + ".blend"))
    return name


def make_pool(folder, E):
    files = {}
    for key, engine in (("physx_cpu", 'PHYSX'), ("bullet", 'BULLET')):
        scene = scene_for("P11dPool", engine)
        pool(scene)
        crate(scene, "Light", (-1.5, 0.0, SURFACE + 0.5), 300.0)
        crate(scene, "Heavy", (1.5, 0.0, SURFACE + 0.5), 2000.0)
        p2.camera(scene, (8.0, -10.0, 5.0), (0.0, 0.0, 1.5), lens=30.0)
        m9.logic(scene, "P11dPool", POOL_SCRIPT.replace("TICS", str(TICS)))
        p2.add_probe(scene)
        scene.update()
        files[key] = save(folder, "p11d_pool_" + key)
    E["pool"] = {"files": files, "tics": TICS, "surface": SURFACE, "light_depth": 0.3, "heavy_z": 0.5}


def make_drop(folder, E):
    scene = scene_for("P11dDrop")
    pool(scene)
    m6.ball(scene, "Ball", 0.25, (0.5, -0.3, SURFACE + 3.25), m6.material("DBall", (0.9, 0.3, 0.2)), mass=20.0)
    p2.camera(scene, (8.0, -10.0, 5.0), (0.0, 0.0, 2.0), lens=30.0)
    m9.logic(scene, "P11dDrop", DROP_SCRIPT.replace("TICS", str(TICS)))
    p2.add_probe(scene)
    scene.update()
    files = {"physx_cpu": save(folder, "p11d_drop_physx_cpu"),
             "physx_cpu_remix": save(folder, "p11d_drop_physx_cpu_remix", remix=1)}
    E["drop"] = {"files": files, "tics": TICS, "surface": SURFACE, "radius": 0.25, "at": [0.5, -0.3]}


def river(scene, x=0.0, y=0.0):
    ob = plain_box(scene, "River", (20.0, 4.0, 1.0), (x, y, 0.5))
    return make_volume(scene, ob, fluid_type='WATER', current=(1.0, 0.0, 0.0))


def make_river(folder, E):
    scene = scene_for("P11dRiver")
    river(scene)
    crate(scene, "Raft", (-6.0, 0.0, 1.0), 100.0, size=(2.0, 1.0, 0.2))
    p2.camera(scene, (0.0, -16.0, 6.0), (0.0, 0.0, 0.5), lens=30.0)
    m9.logic(scene, "P11dRiver", RIVER_SCRIPT.replace("TICS", str(TICS_RIVER)))
    p2.add_probe(scene)
    scene.update()
    E["river"] = {"file": save(folder, "p11d_river_physx_cpu"), "tics": TICS_RIVER, "seconds": 5.0}


def make_versus(folder, E):
    files = {}
    for key in ("water", "lava"):
        scene = scene_for("P11dVersus")
        pool(scene, fluid_type=key.upper())
        crate(scene, "Heavy", (-1.5, 0.0, SURFACE + 0.5), 1500.0)
        crate(scene, "Pushed", (1.5, -1.5, SURFACE - 0.5), 300.0)
        crate(scene, "Thrown", (-2.0, 2.0, SURFACE + 0.2), 300.0)
        p2.camera(scene, (8.0, -10.0, 5.0), (0.0, 0.0, 1.5), lens=30.0)
        m9.logic(scene, "P11dVersus", VERSUS_SCRIPT.replace("TICS", str(TICS_VERSUS)))
        p2.add_probe(scene)
        scene.update()
        files[key] = save(folder, "p11d_versus_" + key)
    E["versus"] = {"files": files, "tics": TICS_VERSUS, "surface": SURFACE, "lava_depth": 1500.0 / 3100.0}


def make_plank(folder, E):
    scene = scene_for("P11dPlank")
    pool(scene)
    crate(scene, "Plank", (0.0, 0.0, SURFACE + 0.2), 30.0, size=(0.4, 0.2, 2.0))
    bpy.data.objects["Plank"].rotation_euler = (0.0, 0.1, 0.0)
    p2.camera(scene, (8.0, -10.0, 5.0), (0.0, 0.0, 1.5), lens=30.0)
    m9.logic(scene, "P11dPlank", PLANK_SCRIPT.replace("TICS", str(TICS)))
    p2.add_probe(scene)
    scene.update()
    E["plank"] = {"file": save(folder, "p11d_plank_physx_cpu"), "tics": TICS}


def remix_view():
    """the Default screen's largest 3D View made a Remix View (Check mode)"""
    import p11c_scenes as sc
    return sc.remix_view()


def make_view(folder, E):
    files = {}
    for key, engine in (("physx_cpu", 'PHYSX'), ("bullet", 'BULLET')):
        scene = scene_for("P11dView", engine)
        pool(scene)
        river(scene, y=8.0)
        crate(scene, "Heavy", (1.5, 0.0, SURFACE + 1.0), 2000.0)
        m6.ball(scene, "Ball", 0.25, (-1.5, 0.0, SURFACE + 5.25), m6.material("DBall", (0.9, 0.3, 0.2)), mass=40.0)
        p2.camera(scene, (10.0, -14.0, 8.0), (0.0, 3.0, 1.0), lens=30.0)
        # (one 1/60 s step a frame: the Run's frames are the physics' own,
        # so the box goes in at the frame planned)
        scene.game_settings.use_frame_rate = False
        scene.update()
        remix_view()
        files[key] = save(folder, "p11d_view_" + key)
    E["view"] = {"files": files, "pool": "Pool", "river": "River", "ball": "Ball", "heavy": "Heavy",
                 "frames": {"10": "WHITE", "24": "BLUE", "45": "GREEN", "200": "GREEN"}}


def make_lava(folder, E):
    scene = scene_for("P11dLava")
    pool(scene, fluid_type='LAVA')
    crate(scene, "Rock", (0.0, 0.0, SURFACE + 0.5), 1500.0)
    p2.camera(scene, (8.0, -10.0, 5.0), (0.0, 0.0, 1.5), lens=30.0)
    p2.add_probe(scene)
    scene.update()
    ma = bpy.data.objects["Pool"].material_slots[0].material
    E["lava"] = {"file": save(folder, "p11d_lava_remix", remix=1), "material": ma.name if ma else None,
                 "fps": int(ma.get("bge_remix_atlas_fps", 0)) if ma else None,
                 "frames": int(ma.get("bge_remix_atlas_frames", 0)) if ma else None}


def make_crash(folder, E):
    scene = scene_for("P11dCrash")
    pool(scene)
    for k in range(3):
        crate(scene, "Box%d" % k, (-1.5 + 1.5 * k, 0.0, SURFACE + 0.5), 300.0)
    spare = crate(scene, "Spare", (0.0, 0.0, 0.0), 300.0)
    spare.layers = [False] * 19 + [True]
    place = bpy.data.objects.new("SparePlace", None)
    scene.objects.link(place)
    place.location = (0.0, 2.0, 2.0)
    p2.camera(scene, (8.0, -10.0, 5.0), (0.0, 0.0, 1.5), lens=30.0)
    m9.logic(scene, "P11dCrash", CRASH_SCRIPT.replace("TICS", str(TICS_CRASH)))
    p2.add_probe(scene)
    scene.update()
    E["crash"] = {"file": save(folder, "p11d_crash_physx_cpu"), "tics": TICS_CRASH}


def _settings(ob):
    return {"bge_fluid": ob.get("bge_fluid"), "type": ob.get("bge_fluid_type"),
            "density": ob.get("bge_fluid_density"), "drag": ob.get("bge_fluid_drag"),
            "current": [round(float(x), 4) for x in ob["bge_fluid_current"]] if "bge_fluid_current" in ob else None,
            "splashes": ob.get("bge_fluid_splashes"), "physics": ob.game.physics_type, "ghost": ob.game.use_ghost,
            "bounds": ob.game.collision_bounds_type if ob.game.use_collision_bounds else None,
            "materials": [s.material.name if s.material else None for s in ob.material_slots],
            "uv": len(ob.data.uv_textures)}


def make_operator_checks(folder, E):
    """Make Fluid Volume itself"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11dMake")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    r = {}
    # a mesh without a material or a UV map
    a = plain_box(scene, "Plain", (4.0, 4.0, 1.0), (0.0, 0.0, 0.5))
    for layer in list(a.data.uv_textures):
        a.data.uv_textures.remove(layer)
    r["plain_uv_before"] = len(a.data.uv_textures)
    make_volume(scene, a)
    r["plain"] = _settings(a)
    ma = a.material_slots[0].material if a.material_slots else None
    r["plain_preset"] = ma.get("bge_remix_preset") if ma else None
    r["plain_flipbook"] = int(ma.get("bge_remix_atlas", 0)) if ma else None
    # a mesh with its own material: kept
    b = m6.box(scene, "Own", (2.0, 2.0, 1.0), (6.0, 0.0, 0.5), m6.material("DOwn", (0.2, 0.4, 0.8)),
               physics='STATIC')
    make_volume(scene, b, current=(0.5, 0.0, 0.0))
    r["own"] = _settings(b)
    # lava: its preset, glowing
    c = plain_box(scene, "Hot", (2.0, 2.0, 1.0), (12.0, 0.0, 0.5))
    make_volume(scene, c, fluid_type='LAVA', density=3100.0, drag=24.0)
    r["hot"] = _settings(c)
    lm = c.material_slots[0].material if c.material_slots else None
    r["hot_preset"] = lm.get("bge_remix_preset") if lm else None
    r["hot_flipbook"] = int(lm.get("bge_remix_atlas", 0)) if lm else None
    r["hot_fps"] = int(lm.get("bge_remix_atlas_fps", 0)) if lm else None
    glow = None
    if lm is not None and lm.node_tree is not None:
        from bl_operators.bge_remix_material import remix_node
        node = remix_node(lm)
        if node is not None:
            sock = node.inputs.get("Emissive Color")
            glow = {"wired": bool(sock and sock.is_linked and sock.links[0].from_socket.name == "Emissive"),
                    "intensity": node.inputs["Emissive Intensity"].default_value}
    r["hot_glow"] = glow
    # made again: Plain made lava; its material kept (it has one now)
    make_volume(scene, a, fluid_type='LAVA', density=3100.0, drag=24.0)
    r["again"] = _settings(a)
    E["operator"] = r


def make(folder, E):
    E["p11d"] = P = {}
    for fn in (make_pool, make_drop, make_river, make_versus, make_plank, make_view, make_lava, make_crash,
               make_operator_checks):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sub = {}
        fn(folder, sub)
        P.update(sub)
