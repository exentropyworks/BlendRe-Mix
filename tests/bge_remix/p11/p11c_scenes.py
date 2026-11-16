"""BGE-Remix p11c: the scenes for P11 Part B step 2 (B2, destruction with
NVIDIA Blast). Runs inside our Blender (Python 3.5: no f-strings), from
make_scenes_p11.py; make(folder, E) saves the .blend files into folder and
writes what the tests expect into E["p11c"]. Each scene's own script writes
what it measured to BGE_REMIX_P11_OUT at its last tic.

Every destructible is made by Make Destructible (Cell Fracture, a seed):
its pieces are named <source>.000, .001, ...

p11c_wall_<engine>_<speed>.blend   (physx_cpu: 10 and 3 m/s; bullet: 10)
    a 4 x 0.3 x 2 m wall standing on the floor: 40 pieces, seed 1,
    Strength 40 N s, 600 kg, Anchored Base. At tic 2 a 20 kg ball (0.15 m)
    1.2 m in front of its middle, 1 m up, is thrown at it. The script
    records the destructible (pieces, bonds), then at the last tic its
    groups, the pieces broken off, how far each piece moved and how far the
    two top corner pieces moved.
p11c_pillar_physx_cpu.blend   a 0.5 x 0.5 x 3 m pillar: 30 pieces, seed 2,
    Anchored Base. At tic 30 the script explodes it at mid-height (1.5 m,
    radius 0.6 m, damage 4): the pieces inside break loose and are thrown
    out; the top, held by nothing, falls.
p11c_budget_physx_cpu.blend   six 0.8 m crates on the floor in a row, 80
    pieces each (seeds 11-16, not anchored), Max Pieces 200. The script
    explodes crate k at tic 20 + 10 k (k = 0..5, at its centre, radius 1 m,
    damage 6) and counts the broken-off pieces every tic.
p11c_view_<engine>.blend   (physx_cpu, bullet) the wall for the Remix View
    (Max Pieces 3): at tic 20 a script damages it a little at its middle
    (radius 0.3 m, damage 0.5: no bond breaks), at tic 50 explodes it there
    (radius 0.8 m, damage 4).
p11c_crash_physx_cpu.blend   the crash check: the wall; tic 20 an explosion,
    tic 30 five broken-off pieces are ended, tic 40 the parent piece is
    ended, tic 50 the wall is damaged again through the destructible
    fetched at tic 10, tics 60-100 every piece left is ended (one a tic and
    then the rest), tic 110 the destructible is asked for again (gone).
Make Destructible itself (while the scenes are made): two cubes made with
    seed 3 give the same pieces, seed 4 others; the pieces' volumes add up
    to the cube's; making it again replaces the pieces.
"""

import os

import bpy
from mathutils import Vector

import make_scenes_p2 as p2
import make_scenes_p6 as m6
import make_scenes_p9 as m9

WALL = {"size": (4.0, 0.3, 2.0), "pieces": 40, "seed": 1, "strength": 40.0, "mass": 600.0}
TICS_WALL = 90
TICS_PILLAR = 180
TICS_BUDGET = 150
TICS_CRASH = 130
CRATES = 6
CRATE_PIECES = 80
MAX_PIECES = 200

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
def pieces(base):
    return [o for o in scene.objects if o.name.startswith(base + ".")]
def destructible(ob):
    if ob is None or not hasattr(cons, "getDestructible"):
        return None
    try:
        return cons.getDestructible(ob)
    except Exception:
        return None
def write(st):
    path = env.get("BGE_REMIX_P11_OUT")
    if path:
        with open(path, "w") as f:
            json.dump(st, f, indent=1)
'''

WALL_SCRIPT = COMMON + '''
st = g.setdefault("p11c", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 1:
    ps = pieces("Wall")
    st["rest"] = {o.name: list(o.worldPosition) for o in ps}
    top = max(o.worldPosition.z for o in ps)
    high = [o for o in ps if o.worldPosition.z > top - 0.35]
    st["corners"] = [min(high, key=lambda o: o.worldPosition.x).name, max(high, key=lambda o: o.worldPosition.x).name]
if tic == 2:
    # (round 1: at tic 1 the destructible is not built yet: its bonds are
    # found at the first physics step)
    ps = pieces("Wall")
    d = destructible(ps[0]) if ps else None
    st["made"] = None if d is None else {"pieces": len(d.pieces), "bonds": d.bonds, "anchored": d.anchored,
                                         "strength": d.strength, "root": d.root.name if d.root else None}
if tic == 3:
    obj("Ball").setLinearVelocity((0.0, SPEED, 0.0), False)
if tic == TICS:
    ps = pieces("Wall")
    d = destructible(ps[0]) if ps else None
    st["groups"] = d.groups if d else None
    st["broken_off"] = len(d.brokenOff) if d else 0
    st["bonds_broken"] = d.bondsBroken if d else None
    moved = {}
    for o in ps:
        r = st["rest"].get(o.name)
        if r:
            moved[o.name] = (o.worldPosition - Vector(r)).length
    st["moved"] = moved
    st["corner_moved"] = [moved.get(n) for n in st["corners"]]
    st["ball"] = list(obj("Ball").worldPosition)
    st["ball_speed_y"] = obj("Ball").getLinearVelocity()[1]
    write(st)
'''

PILLAR_SCRIPT = COMMON + '''
st = g.setdefault("p11c", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 1:
    ps = pieces("Pillar")
    st["rest"] = {o.name: list(o.worldPosition) for o in ps}
    st["top"] = max(ps, key=lambda o: o.worldPosition.z).name
    st["base"] = [o.name for o in ps if o.worldPosition.z < 0.4]
    d = destructible(ps[0])
    st["made"] = None if d is None else {"pieces": len(d.pieces), "bonds": d.bonds}
if tic == 30:
    st["hit"] = cons.explode((0.0, 0.0, 1.5), 0.6, 4.0) if hasattr(cons, "explode") else None
if tic == TICS:
    ps = pieces("Pillar")
    d = destructible(ps[0]) if ps else None
    top = obj(st["top"])
    st["top_drop"] = (st["rest"][st["top"]][2] - top.worldPosition.z) if top else None
    st["base_moved"] = max(((obj(n).worldPosition - Vector(st["rest"][n])).length for n in st["base"] if obj(n)),
                           default=None)
    st["groups"] = d.groups if d else None
    st["broken_off"] = len(d.brokenOff) if d else 0
    write(st)
'''

BUDGET_SCRIPT = COMMON + '''
st = g.setdefault("p11c", {"tic": 0, "most": 0, "counts": []})
st["tic"] += 1
tic = st["tic"]
if tic == 1:
    g["p11c_d"] = [destructible(pieces("Crate%d" % k)[0]) for k in range(CRATES)]
    st["made"] = [None if d is None else len(d.pieces) for d in g["p11c_d"]]
for k in range(CRATES):
    if tic == 20 + 10 * k:
        c = obj("CrateCentre%d" % k)
        cons.explode(c.worldPosition, 1.0, 6.0)
loose = []
for d in g["p11c_d"]:
    try:
        loose.append(len(d.brokenOff) if d else 0)
    except RuntimeError:
        loose.append(0)
st["most"] = max(st["most"], sum(loose))
st["counts"].append(sum(loose))
if tic == TICS:
    st["per_crate"] = loose
    write(st)
'''

VIEW_SCRIPT = COMMON + '''
st = g.setdefault("p11c", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 20:
    d = destructible(pieces("Wall")[0])
    if d:
        d.damage((0.0, -0.15, 1.0), 0.3, 0.5)
if tic == 50 and hasattr(cons, "explode"):
    cons.explode((0.0, -0.3, 1.0), 0.8, 4.0)
'''

CRASH_SCRIPT = COMMON + '''
st = g.setdefault("p11c", {"tic": 0, "errors": []})
st["tic"] += 1
tic = st["tic"]
if tic == 10:
    g["p11c_d"] = destructible(pieces("Wall")[0])
    st["made"] = g["p11c_d"] is not None
if tic == 20:
    cons.explode((0.0, -0.3, 1.0), 0.8, 4.0)
if tic == 30:
    try:
        off = g["p11c_d"].brokenOff
        for o in off[:5]:
            o.endObject()
        st["ended_broken_off"] = min(5, len(off))
    except Exception as ex:
        st["errors"].append("tic 30: %r" % ex)
if tic == 40:
    try:
        g["p11c_d"].root.endObject()
    except Exception as ex:
        st["errors"].append("tic 40: %r" % ex)
if tic == 50:
    try:
        g["p11c_d"].damage((1.5, -0.15, 1.5), 0.5, 2.0)
        st["damaged_after_root"] = True
    except Exception as ex:
        st["errors"].append("tic 50: %r" % ex)
if 60 <= tic < 100:
    ps = pieces("Wall")
    if ps:
        ps[0].endObject()
if tic == 100:
    for o in pieces("Wall"):
        o.endObject()
if tic == 110:
    try:
        g["p11c_d"].groups
        st["gone"] = "no error"
    except RuntimeError as ex:
        st["gone"] = "RuntimeError"
    except Exception as ex:
        st["gone"] = repr(ex)
if tic == TICS:
    st["left"] = len(pieces("Wall"))
    write(st)
'''


def remix_view():
    """the Default screen's largest 3D View made a Remix View (Check mode),
    through the camera (for the Remix View test's probe)"""
    areas = []
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type in ('VIEW_3D', 'GAME_VIEW'):
                areas.append((screen.name != "Default", -(area.width * area.height), screen.name, area))
    areas.sort(key=lambda t: t[:3])
    if not areas:
        return False
    space = areas[0][3].spaces.active
    space.is_game_view = True
    space.game_view_mode = 'CHECK'
    space.region_3d.view_perspective = 'CAMERA'
    return True


def make_destructible(scene, ob, **kw):
    """Make Destructible on ob; the parent piece's name"""
    for o in scene.objects:
        o.select = o == ob
    scene.objects.active = ob
    ret = bpy.ops.object.bge_remix_make_destructible(**kw)
    if 'FINISHED' not in ret:
        raise RuntimeError("Make Destructible on %s: %s" % (ob.name, ret))
    return scene.objects.active.name


def floor(scene, size=12.0):
    return m6.box(scene, "Floor", (size, size, 0.2), (0.0, 0.0, -0.1), m6.material("CFloor", (0.5, 0.5, 0.5)),
                  physics='STATIC')


def wall(scene):
    src = m6.box(scene, "Wall", WALL["size"], (0.0, 0.0, WALL["size"][2] * 0.5),
                 m6.material("CWall", (0.75, 0.62, 0.45)), physics='STATIC')
    return make_destructible(scene, src, pieces=WALL["pieces"], seed=WALL["seed"], strength=WALL["strength"],
                             mass=WALL["mass"], anchored=True)


def save(folder, name):
    p2.save(os.path.join(folder, name + ".blend"))
    return name


def make_wall(folder, E):
    files = {}
    roots = {}
    for key, engine, speed in (("physx_cpu_10", 'PHYSX', 10.0), ("physx_cpu_3", 'PHYSX', 3.0),
                               ("bullet_10", 'BULLET', 10.0)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11cWall")
        m6.set_engine(scene, engine, 'CPU' if engine == 'PHYSX' else None)
        floor(scene)
        roots[key] = wall(scene)
        m6.ball(scene, "Ball", 0.15, (0.0, -1.2, 1.0), m6.material("CBall", (0.2, 0.3, 0.8)), mass=20.0)
        p2.camera(scene, (5.0, -7.0, 2.5), (0.0, 0.0, 1.0), lens=30.0)
        m9.logic(scene, "P11cWall", WALL_SCRIPT.replace("SPEED", repr(speed)).replace("TICS", str(TICS_WALL)))
        p2.add_probe(scene)
        scene["bge_remix"] = 0
        scene.update()
        files[key] = save(folder, "p11c_wall_" + key)
        if key == "physx_cpu_10":
            # the RTX run's (in Remix)
            scene["bge_remix"] = 1
            files[key + "_rtx"] = save(folder, "p11c_wall_" + key + "_rtx")
    E["wall"] = {"files": files, "tics": TICS_WALL, "roots": roots, "pieces_asked": WALL["pieces"]}


def make_pillar(folder, E):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11cPillar")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    floor(scene)
    src = m6.box(scene, "Pillar", (0.5, 0.5, 3.0), (0.0, 0.0, 1.5), m6.material("CPillar", (0.6, 0.6, 0.65)),
                 physics='STATIC')
    # (round 1: at 100 N s the top, 900 kg falling, broke the foot apart:
    # concrete's pieces need more)
    root = make_destructible(scene, src, pieces=30, seed=2, strength=5000.0, mass=1800.0, anchored=True)
    p2.camera(scene, (4.0, -6.0, 2.0), (0.0, 0.0, 1.4), lens=30.0)
    m9.logic(scene, "P11cPillar", PILLAR_SCRIPT.replace("TICS", str(TICS_PILLAR)))
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    E["pillar"] = {"file": save(folder, "p11c_pillar_physx_cpu"), "tics": TICS_PILLAR, "root": root}


def make_budget(folder, E):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11cBudget")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    scene.bge_destruction_max_pieces = MAX_PIECES
    floor(scene, 20.0)
    roots = []
    for k in range(CRATES):
        x = -5.0 + 2.0 * k
        src = m6.box(scene, "Crate%d" % k, 0.8, (x, 0.0, 0.4), m6.material("CCrate%d" % k, (0.7, 0.5, 0.25)))
        roots.append(make_destructible(scene, src, pieces=CRATE_PIECES, seed=11 + k, strength=100.0, mass=40.0,
                                       anchored=False))
        centre = bpy.data.objects.new("CrateCentre%d" % k, None)
        scene.objects.link(centre)
        centre.location = (x, 0.0, 0.4)
    p2.camera(scene, (0.0, -12.0, 4.0), (0.0, 0.0, 0.5), lens=28.0)
    m9.logic(scene, "P11cBudget", BUDGET_SCRIPT.replace("TICS", str(TICS_BUDGET)).replace("CRATES", str(CRATES)))
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    E["budget"] = {"file": save(folder, "p11c_budget_physx_cpu"), "tics": TICS_BUDGET, "crates": CRATES,
                   "max": MAX_PIECES, "roots": roots, "explode_tics": [20 + 10 * k for k in range(CRATES)]}


def make_view(folder, E):
    files = {}
    roots = {}
    for key, engine in (("physx_cpu", 'PHYSX'), ("bullet", 'BULLET')):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11cView")
        m6.set_engine(scene, engine, 'CPU' if engine == 'PHYSX' else None)
        scene.bge_destruction_max_pieces = 1  # (round 1: 3 was more than the explosion freed)
        floor(scene)
        roots[key] = wall(scene)
        p2.camera(scene, (5.0, -7.0, 2.5), (0.0, 0.0, 1.0), lens=30.0)
        m9.logic(scene, "P11cView", VIEW_SCRIPT)
        scene["bge_remix"] = 0
        scene.update()
        remix_view()
        files[key] = save(folder, "p11c_view_" + key)
    E["view"] = {"files": files, "roots": roots, "max": 1, "pieces_asked": WALL["pieces"]}


def make_crash(folder, E):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11cCrash")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    floor(scene)
    root = wall(scene)
    p2.camera(scene, (5.0, -7.0, 2.5), (0.0, 0.0, 1.0), lens=30.0)
    m9.logic(scene, "P11cCrash", CRASH_SCRIPT.replace("TICS", str(TICS_CRASH)))
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    E["crash"] = {"file": save(folder, "p11c_crash_physx_cpu"), "tics": TICS_CRASH, "root": root}


def _centres(scene, base, origin):
    scene.update()  # (round 1: the pieces' world matrices were not yet up to date)
    out = []
    for o in scene.objects:
        if o.name.startswith(base + ".") and o.get("bge_destructible_of"):
            c = o.matrix_world * (sum((Vector(v) for v in o.bound_box), Vector()) / 8.0) - origin
            out.append([c.x, c.y, c.z])
    return sorted(out, key=lambda c: (round(c[2], 2), round(c[0], 2), round(c[1], 2)))


def _same(a, b, tol=1e-3):
    """the same pieces: as many, each centre within tol"""
    if len(a) != len(b):
        return False
    left = list(b)
    for c in a:
        near = [k for k, d in enumerate(left) if max(abs(c[i] - d[i]) for i in range(3)) < tol]
        if not near:
            return False
        del left[near[0]]
    return True


def make_operator_checks(folder, E):
    """Make Destructible itself: the same seed, the same pieces; the volumes;
    made again"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11cMake")
    r = {}
    made = {}
    for name, x, seed in (("CubeA", 0.0, 3), ("CubeB", 5.0, 3), ("CubeC", 10.0, 4)):
        src = m6.box(scene, name, 1.0, (x, 0.0, 0.5), m6.material("M" + name, (0.5, 0.6, 0.7)), physics='STATIC')
        made[name] = make_destructible(scene, src, pieces=12, seed=seed, strength=100.0, mass=10.0, anchored=False)
    a = _centres(scene, "CubeA", Vector((0.0, 0.0, 0.0)))
    b = _centres(scene, "CubeB", Vector((5.0, 0.0, 0.0)))
    c = _centres(scene, "CubeC", Vector((10.0, 0.0, 0.0)))
    r["pieces"] = {"A": len(a), "B": len(b), "C": len(c)}
    r["same_seed_same_pieces"] = _same(a, b) and len(a) > 1
    r["other_seed_other_pieces"] = not _same(a, c)
    # (round 1: the meshes' own volumes came to half the cube: a boolean's
    # faces turned either way; the pieces are convex: their hulls')
    from bl_operators.bge_remix_destructible import mesh_volume
    vol = 0.0
    for o in scene.objects:
        if o.name.startswith("CubeA.") and o.get("bge_destructible_of"):
            vol += mesh_volume(o)
    r["volume"] = vol
    r["volume_of_the_cube"] = 1.0
    # made again (from the parent piece): the same pieces, none left over
    root = scene.objects[made["CubeA"]]
    before = sorted(o.name for o in scene.objects if o.name.startswith("CubeA."))
    make_destructible(scene, root, pieces=12, seed=3, strength=100.0, mass=10.0, anchored=False)
    after = sorted(o.name for o in scene.objects if o.name.startswith("CubeA."))
    r["again_names_same"] = before == after
    r["again_count"] = len(after)
    r["again_same_pieces"] = _same(_centres(scene, "CubeA", Vector((0.0, 0.0, 0.0))), a)
    r["source_kept_on_layer_20"] = bool(bpy.data.objects.get("CubeA")) and \
        bpy.data.objects["CubeA"].layers[19] and not any(bpy.data.objects["CubeA"].layers[:19])
    E["operator"] = r


def make(folder, E):
    E["p11c"] = P = {}
    for fn in (make_wall, make_pillar, make_budget, make_view, make_crash, make_operator_checks):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sub = {}
        fn(folder, sub)
        P.update(sub)
