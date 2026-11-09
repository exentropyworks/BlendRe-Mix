"""BGE-Remix p11b: the scenes for P11 Part B step 1 (B1, articulations).
Runs inside our Blender (Python 3.5: no f-strings), from make_scenes_p11.py;
make(folder, E) saves the .blend files into folder and writes what the tests
expect into E["p11b"]. Each scene's own script writes what it measured to
BGE_REMIX_P11_OUT at its last tic.

p11b_chain_<variant>.blend   the heavy chain: a 0.3 m block at 8 m up, then
    12 links (0.12 x 0.12 x 0.5 m, 1 kg) laid out level along x, joined end
    to end by Ball joints, and a 100 kg ball (0.3 m; 100 times a link) on
    the last one. It swings down and hangs. The script measures every
    joint's gap (the distance between the joint's point on its two bodies)
    each tic.
      physx_cpu_art, physx_gpu_art   PhysX, the block the root of an
                                     articulation fixed to the world
      physx_cpu_plain                PhysX, the block Static, ordinary joints
      bullet                         Bullet, the block Static (also run in
                                     stock 2.79b)
p11b_ragdoll_<engine>.blend   (physx_cpu, bullet) a mannequin armature (12
    bones: hips, spine, chest, head, upper and lower arms and legs) standing
    on a 1.2 m platform at the top of six steps; Make Ragdoll gave it its
    capsules (Cone Twist joints: 30 degrees of twist, 45 of swing); a grey
    box parented to each bone shows the bone. At tic 30 the script lets the
    ragdoll go (getArticulation(armature).ragdoll = True) and pushes the
    chest towards the steps; at tic 300 puts it back on the bones. It
    measures the capsules' joint gaps and angles, how far each bone's box is
    from its capsule while the ragdoll is let go, and where the capsules are
    after.
p11b_door_physx_cpu.blend   a door (1 x 0.06 x 2 m, 10 kg) on a Hinge to a
    post (the root, fixed to the world): it opens up to 90 degrees one way
    and 10 the other. At tic 20 a 5 kg box is thrown at its far end (3 m/s):
    it swings open to its 90 degree limit; at tic 120 the script turns its
    hinge at 1 radian a second (setJointSpeed), closing it to 10 degrees
    past shut, its other limit.
p11b_arm_physx_cpu.blend   a two-joint arm: a 0.3 m base (the root, fixed),
    an upper arm (0.6 m) and a forearm (0.5 m) on Hinges about y, level
    along x. The script drives them (setJointTarget) to 30 and -45 degrees
    at tic 2, to -20 and 60 at tic 240, to 45 and 30 at tic 480.
p11b_bridge_<engine>.blend   (physx_cpu, bullet) a rope bridge: a post on
    the left (the root, fixed), ten planks (0.5 x 1 x 0.08 m) hanging on an
    arc (the end ones sloping 25 degrees) joined by Hinges about y, the last
    one hinged to a Static post on the right (tied at both ends), and a Ball
    joint from plank 4 to plank 6 (a loop). At tic
    60 a 0.3 m box is set down on the second plank and sent across at 2 m/s.
p11b_crash_physx_cpu.blend   the crash check: a 12 link chain (its block the
    root, fixed) and the mannequin on the floor. Tic 20 a link is removed;
    tic 40 a box is added and joined to link 3 (createConstraint); tics 60
    to 150 the mannequin's ragdoll is let go and put back ten times; tic 170
    the added joint is removed; tic 190 the chain's root is removed.
"""

import math
import os

import bpy

import make_scenes_p2 as p2
import make_scenes_p6 as m6
import make_scenes_p9 as m9

TICS_CHAIN = 360
LINKS = 12
LINK = (0.12, 0.12, 0.5)
ROOT_Z = 8.0
WEIGHT_R = 0.3
WEIGHT_MASS = 100.0  # (100 times a link)

COMMON = '''\
import json, math, os
import bge
from mathutils import Vector
env = os.environ
scene = bge.logic.getCurrentScene()
g = bge.logic.globalDict
cons = bge.constraints

def obj(name):
    return scene.objects.get(name)

def art_of(ob):
    if ob is None or not hasattr(cons, "getArticulation"):
        return None
    try:
        return cons.getArticulation(ob)
    except Exception:
        return None

def write(st):
    path = env.get("BGE_REMIX_P11_OUT")
    if path:
        with open(path, "w") as f:
            json.dump(st, f, indent=1)

def gaps_now(st):
    """each joint's gap: (owner, target, point on the owner, point on the target)"""
    out = {}
    for name, (a, b, pa, pb) in st["joints"].items():
        A, B = obj(a), obj(b)
        if A is None or B is None:
            continue
        wa = A.worldTransform * Vector(pa)
        wb = B.worldTransform * Vector(pb)
        out[name] = (wa - wb).length
    return out

def joint_points(pairs):
    """the joints' points on both bodies, from where they are now: (name, owner, target, point on the owner)"""
    j = {}
    for name, a, b, pa in pairs:
        A, B = obj(a), obj(b)
        w = A.worldTransform * Vector(pa)
        j[name] = (a, b, list(pa), list(B.worldTransform.inverted() * w))
    return j

def track_gaps(st, key="max_gap"):
    m = st.setdefault(key, {})
    for k, v in gaps_now(st).items():
        if v > m.get(k, 0.0):
            m[k] = v
'''

CHAIN_SCRIPT = COMMON + '''
st = g.setdefault("p11b", {"tic": 0})
st["tic"] += 1
tic = st["tic"]
if tic == 1:
    st["joints"] = joint_points(PAIRS)
    st["start_weight"] = list(obj("Weight").worldPosition)
if tic >= 1:
    track_gaps(st)
if tic == 5:
    a = art_of(obj("Root"))
    st["articulation"] = None if a is None else {"links": len(a.links), "fixed": a.fixed,
                                                 "ordinary": len(a.ordinaryJoints)}
if tic == TICS:
    st["final_gap"] = gaps_now(st)
    st["weight"] = list(obj("Weight").worldPosition)
    st["max_total"] = sum(st["max_gap"].values())
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


def set_root(ob, kind):
    """the object's Articulation Root (Physics tab): 'FREE' or 'FIXED'"""
    try:
        ob.bge_articulation = kind
    except (AttributeError, TypeError):
        ob["bge_articulation"] = 1 if kind == 'FREE' else 2


def joint(ob, target, kind, pivot, axis=(0.0, 0.0, 0.0), no_collide=True):
    c = m6.joint(ob, target, kind, pivot, axis)
    c.use_linked_collision = no_collide
    return c


def chain(scene, prefix, root, n, mats, weight=True):
    """n links along x from the root's face; the pairs (joint name, owner,
    target, the joint's point on the owner) for the script"""
    pairs = []
    prev = root
    x0 = 0.15
    for i in range(n):
        ob = m6.box(scene, "%sLink%02d" % (prefix, i), LINK, (x0 + LINK[2] * (i + 0.5), 0.0, ROOT_Z),
                    mats[i % 2], mass=1.0, rotation=(0.0, math.radians(90.0), 0.0))
        joint(ob, prev, 'BALL', (0.0, 0.0, -0.5))
        pairs.append(("%sJ%02d" % (prefix, i), ob.name, prev.name, (0.0, 0.0, -0.5)))
        prev = ob
    if weight:
        end = x0 + LINK[2] * n
        w = m6.ball(scene, "Weight", WEIGHT_R, (end + WEIGHT_R, 0.0, ROOT_Z),
                    m6.material("ChWeight", (0.85, 0.3, 0.2)), mass=WEIGHT_MASS)
        joint(w, prev, 'BALL', (-WEIGHT_R, 0.0, 0.0))
        pairs.append(("%sJWeight" % prefix, w.name, prev.name, (-WEIGHT_R, 0.0, 0.0)))
    return pairs


CHAIN_VARIANTS = (
    ("physx_cpu_art", 'PHYSX', 'CPU', True),
    ("physx_gpu_art", 'PHYSX', 'GPU', True),
    ("physx_cpu_plain", 'PHYSX', 'CPU', False),
    ("bullet", 'BULLET', None, False),
)


def make_chain(folder, E):
    files = {}
    for key, engine, device, art in CHAIN_VARIANTS:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11bChain")
        m6.box(scene, "Floor", (20.0, 6.0, 0.2), (3.0, 0.0, -0.1), m6.material("ChFloor", (0.5, 0.5, 0.5)),
               physics='STATIC')
        if art:
            root = m6.box(scene, "Root", 0.3, (0.0, 0.0, ROOT_Z), m6.material("ChRoot", (0.2, 0.4, 0.9)))
            set_root(root, 'FIXED')
        else:
            root = m6.box(scene, "Root", 0.3, (0.0, 0.0, ROOT_Z), m6.material("ChRoot", (0.2, 0.4, 0.9)),
                          physics='STATIC')
        mats = (m6.material("ChA", (0.9, 0.9, 0.9)), m6.material("ChB", (0.3, 0.3, 0.3)))
        pairs = chain(scene, "", root, LINKS, mats)
        p2.camera(scene, (3.0, -16.0, 4.5), (3.0, 0.0, 4.5), lens=28.0)
        m6.set_engine(scene, engine, device)
        m9.logic(scene, "P11bChain", CHAIN_SCRIPT.replace("PAIRS", repr(pairs)).replace("TICS", str(TICS_CHAIN)))
        p2.add_probe(scene)
        scene["bge_remix"] = 0
        scene.update()
        name = "p11b_chain_" + key
        p2.save(os.path.join(folder, name + ".blend"))
        files[key] = name
    E["chain"] = {"files": files, "tics": TICS_CHAIN, "links": LINKS + 2, "joints": LINKS + 1,
                  "articulated": [k for k, _e, _d, a in CHAIN_VARIANTS if a]}


# ---------------------------------------------------------------------------
# the mannequin (ragdoll, crash check)

BONES = (
    # name, head, tail, parent
    ("Hips", (0.0, 0.0, 0.95), (0.0, 0.0, 1.1), None),
    ("Spine", (0.0, 0.0, 1.1), (0.0, 0.0, 1.35), "Hips"),
    ("Chest", (0.0, 0.0, 1.35), (0.0, 0.0, 1.55), "Spine"),
    ("Head", (0.0, 0.0, 1.58), (0.0, 0.0, 1.83), "Chest"),
    ("UpperArm.L", (0.2, 0.0, 1.5), (0.47, 0.0, 1.5), "Chest"),
    ("ForeArm.L", (0.47, 0.0, 1.5), (0.72, 0.0, 1.5), "UpperArm.L"),
    ("UpperArm.R", (-0.2, 0.0, 1.5), (-0.47, 0.0, 1.5), "Chest"),
    ("ForeArm.R", (-0.47, 0.0, 1.5), (-0.72, 0.0, 1.5), "UpperArm.R"),
    ("Thigh.L", (0.1, 0.0, 0.93), (0.1, 0.0, 0.5), "Hips"),
    ("Shin.L", (0.1, 0.0, 0.5), (0.1, 0.0, 0.08), "Thigh.L"),
    ("Thigh.R", (-0.1, 0.0, 0.93), (-0.1, 0.0, 0.5), "Hips"),
    ("Shin.R", (-0.1, 0.0, 0.5), (-0.1, 0.0, 0.08), "Thigh.R"),
)


def mannequin(scene, name, location, rotation_z=0.0):
    """the armature, a box on each bone (bone-parented, no physics) and Make
    Ragdoll's capsules; returns the armature and the capsules' joints
    (name, capsule, parent capsule, the joint's point on the capsule)"""
    arm_data = bpy.data.armatures.new(name + "Data")
    arm = bpy.data.objects.new(name, arm_data)
    scene.objects.link(arm)
    arm.location = location
    arm.rotation_euler = (0.0, 0.0, rotation_z)
    arm.game.physics_type = 'NO_COLLISION'
    scene.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for bname, head, tail, parent in BONES:
        eb = arm_data.edit_bones.new(bname)
        eb.head, eb.tail = head, tail
        eb.roll = 0.0
        if parent:
            eb.parent = arm_data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    scene.update()
    grey = m6.material(name + "Vis", (0.7, 0.7, 0.7))
    for bname, head, tail, parent in BONES:
        length = math.sqrt(sum((tail[k] - head[k]) ** 2 for k in range(3)))
        vis = p2.cube(scene, "%s.Vis.%s" % (name, bname), 1.0, (0.0, 0.0, 0.0), grey)
        vis.scale = (0.08, length * 0.9, 0.08)
        vis.game.physics_type = 'NO_COLLISION'
        vis.parent = arm
        vis.parent_type = 'BONE'
        vis.parent_bone = bname
        scene.update()
        pb = arm.pose.bones[bname]
        from mathutils import Matrix
        vis.matrix_world = arm.matrix_world * pb.matrix * Matrix.Translation((0.0, length * 0.5, 0.0)) * \
            Matrix.Scale(1.0, 4)
        vis.scale = (0.08, length * 0.9, 0.08)
    scene.update()
    scene.objects.active = arm
    for ob in scene.objects:
        ob.select = ob == arm
    ret = bpy.ops.object.bge_remix_make_ragdoll(thickness=0.15, mass=70.0, swing=math.radians(45.0), twist=math.radians(30.0),
                                                min_length=0.02, deform_only=True)
    joints = []
    for ob in scene.objects:
        if ob.get("bge_ragdoll_armature") != name:
            continue
        for c in ob.constraints:
            if c.type == 'RIGID_BODY_JOINT' and c.target:
                joints.append((ob.name, ob.name, c.target.name, (c.pivot_x, c.pivot_y, c.pivot_z)))
    capsules = sorted(ob.name for ob in scene.objects if ob.get("bge_ragdoll_armature") == name)
    vis = {b[0]: "%s.Vis.%s" % (name, b[0]) for b in BONES}
    caps = {ob["bge_ragdoll_bone"]: ob.name for ob in scene.objects if ob.get("bge_ragdoll_armature") == name}
    return arm, joints, capsules, vis, caps, list(ret)


RAGDOLL_SCRIPT = COMMON + '''
st = g.setdefault("p11b", {"tic": 0, "follow_max": 0.0, "follow": []})
st["tic"] += 1
tic = st["tic"]
arm = obj("Mannequin")
rag = art_of(arm)
if tic == 1:
    st["start"] = {c: list(obj(c).worldPosition) for c in CAPS.values()}
    st["ragdoll_found"] = rag is not None
    st["ragdoll_at_start"] = None if rag is None else rag.ragdoll
    # (the joints' points as the joints were made: the capsules on the bones)
    st["joints"] = joint_points(PAIRS)
if tic == 30:
    try:
        rag.ragdoll = True
        st["on"] = True
    except Exception as ex:
        st["on_error"] = repr(ex)
if tic == 31:
    st["start_on"] = {c: list(obj(c).worldPosition) for c in CAPS.values()}
    chest = obj(CAPS["Chest"])
    chest.applyImpulse(chest.worldPosition, (PUSH, 0.0, 0.0))
    a = art_of(obj(CAPS["Hips"]))
    st["articulation"] = None if a is None else {"links": len(a.links), "fixed": a.fixed,
                                                 "ordinary": len(a.ordinaryJoints)}
if 32 <= tic < 300:
    track_gaps(st)
    # each joint within its limits (twist, both swings; degrees)
    if rag is not None and tic >= 33:
        try:
            lim = st.setdefault("limits", {"twist": 0.0, "swing": 0.0})
            end = {"twist": 0.0, "swing": 0.0}
            for link in rag.links[1:]:
                t = abs(math.degrees(rag.getJointPosition(link, 3)))
                w = max(abs(math.degrees(rag.getJointPosition(link, 4))),
                        abs(math.degrees(rag.getJointPosition(link, 5))))
                end = {"twist": max(end["twist"], t), "swing": max(end["swing"], w)}
            lim["twist"] = max(lim["twist"], end["twist"])
            lim["swing"] = max(lim["swing"], end["swing"])
            st["limits_end"] = end  # (where they are now: at the last tic, at rest)
        except Exception as ex:
            st["limits_error"] = repr(ex)
    # each bone's box against its capsule (both at the bone's middle)
    worst = 0.0
    for bone, cap in CAPS.items():
        v, c = obj(VIS[bone]), obj(cap)
        if v is not None and c is not None:
            worst = max(worst, (v.worldPosition - c.worldPosition).length)
    st["follow_max"] = max(st["follow_max"], worst)
    if tic % 30 == 0:
        st["follow"].append([tic, round(worst, 5)])
if tic == 299:
    st["hips_on"] = list(obj(CAPS["Hips"]).worldPosition)
    st["head_on"] = list(obj(CAPS["Head"]).worldPosition)
if tic == 300:
    try:
        rag.ragdoll = False
        st["off"] = True
    except Exception as ex:
        st["off_error"] = repr(ex)
if tic in (303, 340):
    st["back_%d" % tic] = max((Vector(st["start"][c]) - obj(c).worldPosition).length for c in CAPS.values())
    st["ragdoll_now_%d" % tic] = None if rag is None else rag.ragdoll
if tic == 341:
    write(st)
'''

RAGDOLL_ENGINES = (("physx_cpu", 'PHYSX', 'CPU'), ("bullet", 'BULLET', None))
PLATFORM = 1.2
STEP_H, STEP_D, STEPS = 0.2, 0.4, 6
PUSH = 25.0


def stairs(scene):
    grey = m6.material("StGrey", (0.55, 0.55, 0.55))
    m6.box(scene, "Platform", (2.0, 3.0, PLATFORM), (-0.4, 0.0, PLATFORM * 0.5), grey, physics='STATIC')
    for k in range(STEPS):
        top = PLATFORM - STEP_H * (k + 1)
        x = 0.6 + STEP_D * (k + 0.5)
        m6.box(scene, "Step%d" % k, (STEP_D, 3.0, top), (x, 0.0, top * 0.5), grey, physics='STATIC')
    m6.box(scene, "Floor", (20.0, 6.0, 0.2), (5.0, 0.0, -0.1), grey, physics='STATIC')


def make_ragdoll(folder, E):
    files = {}
    made = {}
    for key, engine, device in RAGDOLL_ENGINES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11bRagdoll")
        m6.set_engine(scene, engine, device)
        stairs(scene)
        arm, joints, capsules, vis, caps, ret = mannequin(scene, "Mannequin", (0.2, 0.0, PLATFORM))
        made[key] = {"ret": ret, "capsules": len(capsules), "joints": len(joints)}
        p2.camera(scene, (1.6, -9.0, 1.8), (1.6, 0.0, 0.9), lens=30.0)
        body = (RAGDOLL_SCRIPT.replace("PAIRS", repr(joints)).replace("CAPS", repr(caps))
                .replace("VIS", repr(vis)).replace("PUSH", repr(PUSH)))
        m9.logic(scene, "P11bRagdoll", body)
        p2.add_probe(scene)
        scene["bge_remix"] = 0
        scene.update()
        name = "p11b_ragdoll_" + key
        remix_view()
        p2.save(os.path.join(folder, name + ".blend"))
        files[key] = name
    E["ragdoll"] = {"files": files, "tics": 345, "bones": len(BONES), "made": made, "twist": 30, "swing": 45,
                    "platform": PLATFORM, "steps_end_x": 0.6 + STEP_D * STEPS}


# ---------------------------------------------------------------------------
# the door

DOOR_SCRIPT = COMMON + '''
st = g.setdefault("p11b", {"tic": 0, "angles": [], "max_angle": -9.0, "min_angle": 9.0, "speeds": []})
st["tic"] += 1
tic = st["tic"]
door, post = obj("Door"), obj("Post")
a = art_of(door)
if tic == 2:
    st["articulation"] = None if a is None else {"links": len(a.links), "fixed": a.fixed}
if tic == 20:
    # the box thrown at the door's far end
    obj("Pusher").setLinearVelocity((0.0, PUSH, 0.0), False)
# the angle from where the door points (its x axis), and the joint's own
# (a joint's angle is its target's against its owner, as Bullet's: the post
# against the door, the door's turned over)
x = door.worldOrientation.col[0]
world = math.degrees(math.atan2(x[1], x[0]))
joint = None
speed = None
if a is not None:
    try:
        joint = math.degrees(a.getJointPosition(door))
        speed = a.getJointSpeed(door)
    except Exception as ex:
        st["joint_error"] = repr(ex)
if tic >= 21:
    st["max_angle"] = max(st["max_angle"], world)
    st["min_angle"] = min(st["min_angle"], world)
if joint is not None:
    st["joint_vs_world"] = max(st.get("joint_vs_world", 0.0), abs(joint + world))
if tic % 10 == 0:
    st["angles"].append([tic, round(world, 2), None if joint is None else round(joint, 2)])
if tic == 110:
    st["open"] = world
if tic == 120 and a is not None:
    try:
        a.setJointSpeed(door, SPEED, maxForce=500.0)
        st["motor"] = True
    except Exception as ex:
        st["motor_error"] = repr(ex)
if 140 <= tic <= 170 and speed is not None:
    st["speeds"].append(speed)
if tic == 260:
    st["closed"] = world
    write(st)
'''

# (the hinge's range in the joint's terms, -90 to 10: the door opens 90
# degrees towards the box's push and closes 10 past shut; closing, the joint
# turns at +1 radian a second)
# (round 1: thrown at 3 m/s the box swung the door only 60 degrees)
DOOR = {"lo": -90.0, "hi": 10.0, "open": 90.0, "shut": -10.0, "speed": 1.0, "push": 5.0, "tics": 265}


def make_door(folder, E):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11bDoor")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    m6.box(scene, "Floor", (10.0, 10.0, 0.2), (0.0, 0.0, -0.1), m6.material("DoFloor", (0.5, 0.5, 0.5)),
           physics='STATIC')
    post = m6.box(scene, "Post", (0.1, 0.1, 2.2), (0.0, 0.0, 1.3), m6.material("DoPost", (0.3, 0.3, 0.35)),
                  mass=5.0)
    set_root(post, 'FIXED')
    # (the door 0.3 m off the floor: the box, fallen, lies under its sweep)
    door = m6.box(scene, "Door", (1.0, 0.06, 2.0), (0.55, 0.0, 1.3), m6.material("DoDoor", (0.75, 0.55, 0.3)),
                  mass=10.0)
    m6.box(scene, "Pusher", 0.25, (0.85, -0.8, 1.0), m6.material("DoBox", (0.9, 0.2, 0.2)), mass=5.0)
    c = joint(door, post, 'HINGE', (-0.5, 0.0, 0.0), (0.0, math.radians(-90.0), 0.0))
    c.name = "Hinge"
    c.use_angular_limit_x = True
    c.limit_angle_min_x = math.radians(DOOR["lo"])
    c.limit_angle_max_x = math.radians(DOOR["hi"])
    p2.camera(scene, (2.5, -5.0, 4.0), (0.5, 0.5, 1.0), lens=30.0)
    m9.logic(scene, "P11bDoor", DOOR_SCRIPT.replace("PUSH", repr(DOOR["push"])).replace("SPEED", repr(DOOR["speed"])))
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    remix_view()
    p2.save(os.path.join(folder, "p11b_door_physx_cpu.blend"))
    E["door"] = dict(DOOR, file="p11b_door_physx_cpu", joint="Hinge")


# ---------------------------------------------------------------------------
# the arm

ARM_SCRIPT = COMMON + '''
st = g.setdefault("p11b", {"tic": 0, "log": []})
st["tic"] += 1
tic = st["tic"]
up, fore = obj("UpperArm"), obj("ForeArm")
a = art_of(obj("Base"))
def world_angles():
    """each link's turn about +y from level (the upper arm's, the forearm's
    against it)"""
    d1, d2 = up.worldOrientation.col[2], fore.worldOrientation.col[2]
    t1 = math.degrees(math.atan2(-d1[2], d1[0]))
    t12 = math.degrees(math.atan2(-d2[2], d2[0]))
    return t1, t12 - t1
def drive(t1, t2):
    a.setJointTarget(up, math.radians(t1), stiffness=STIFF, damping=DAMP)
    a.setJointTarget(fore, math.radians(t2), stiffness=STIFF, damping=DAMP)
if tic == 2:
    st["articulation"] = None if a is None else {"links": len(a.links), "fixed": a.fixed}
    if a is not None:
        try:
            drive(*TARGET1)
        except Exception as ex:
            st["drive_error"] = repr(ex)
if tic == 240 and a is not None:
    drive(*TARGET2)
if tic == 480 and a is not None:
    drive(*TARGET3)
t1, t2 = world_angles()
# (a joint's angle is its target's against its owner, as Bullet's: the
# parent's against the link, the link's turn turned over)
w1, w2 = -t1, -t2
j1 = j2 = None
if a is not None:
    try:
        j1, j2 = math.degrees(a.getJointPosition(up)), math.degrees(a.getJointPosition(fore))
    except Exception as ex:
        st["joint_error"] = repr(ex)
# the tip where the angles say, against where the forearm's end is
s = Vector((0.15, 0.0, Z))
r1, r12 = math.radians(t1), math.radians(t1 + t2)
want = s + 0.6 * Vector((math.cos(r1), 0.0, -math.sin(r1))) + 0.5 * Vector((math.cos(r12), 0.0, -math.sin(r12)))
tip = fore.worldTransform * Vector((0.0, 0.0, 0.5))
st["tip_err"] = max(st.get("tip_err", 0.0), (tip - want).length)
for k, lo, hi, tgt in (("hold1", 200, 239, TARGET1), ("hold2", 440, 479, TARGET2), ("hold3", 680, 719, TARGET3)):
    if lo <= tic <= hi:
        h = st.setdefault(k, {"world": [0.0, 0.0], "joint": [0.0, 0.0]})
        h["world"] = [max(h["world"][0], abs(w1 - tgt[0])), max(h["world"][1], abs(w2 - tgt[1]))]
        if j1 is not None:
            h["joint"] = [max(h["joint"][0], abs(j1 - w1)), max(h["joint"][1], abs(j2 - w2))]
if tic % 20 == 0:
    st["log"].append([tic, round(w1, 2), round(w2, 2), None if j1 is None else round(j1, 2),
                      None if j2 is None else round(j2, 2)])
if tic == 720:
    write(st)
'''

ARM = {"z": 1.5, "target1": (30.0, -45.0), "target2": (-20.0, 60.0), "target3": (45.0, 30.0),
       "stiffness": 5000.0, "damping": 300.0, "tics": 725}


def make_arm(folder, E):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11bArm")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    z = ARM["z"]
    base = m6.box(scene, "Base", 0.3, (0.0, 0.0, z), m6.material("ArBase", (0.3, 0.3, 0.35)), mass=5.0)
    set_root(base, 'FIXED')
    up = m6.box(scene, "UpperArm", (0.1, 0.1, 0.6), (0.45, 0.0, z), m6.material("ArUp", (0.9, 0.5, 0.2)),
                mass=1.0, rotation=(0.0, math.radians(90.0), 0.0))
    fore = m6.box(scene, "ForeArm", (0.08, 0.08, 0.5), (1.0, 0.0, z), m6.material("ArFore", (0.2, 0.5, 0.9)),
                  mass=1.0, rotation=(0.0, math.radians(90.0), 0.0))
    # (the hinge's axis, the joint's X, along world y: the links' own y)
    joint(up, base, 'HINGE', (0.0, 0.0, -0.5), (0.0, 0.0, math.radians(90.0)))
    joint(fore, up, 'HINGE', (0.0, 0.0, -0.5), (0.0, 0.0, math.radians(90.0)))
    p2.camera(scene, (0.6, -5.0, 1.4), (0.6, 0.0, 1.4), lens=30.0)
    body = (ARM_SCRIPT.replace("TARGET1", repr(ARM["target1"])).replace("TARGET2", repr(ARM["target2"]))
            .replace("TARGET3", repr(ARM["target3"]))
            .replace("STIFF", repr(ARM["stiffness"])).replace("DAMP", repr(ARM["damping"]))
            .replace("Z)", repr(z) + ")"))
    m9.logic(scene, "P11bArm", body)
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    p2.save(os.path.join(folder, "p11b_arm_physx_cpu.blend"))
    E["arm"] = dict(ARM, file="p11b_arm_physx_cpu")


# ---------------------------------------------------------------------------
# the rope bridge

BRIDGE_SCRIPT = COMMON + '''
st = g.setdefault("p11b", {"tic": 0, "max_speed": 0.0})
st["tic"] += 1
tic = st["tic"]
if tic == 1:
    st["joints"] = joint_points(PAIRS)
if tic == 3:
    a = art_of(obj("LeftPost"))
    st["articulation"] = None if a is None else {"links": len(a.links), "fixed": a.fixed,
                                                 "ordinary": len(a.ordinaryJoints)}
if tic == 60:
    # a box set down on the second plank and sent across
    box = scene.addObject("Roller", obj("RollerAt"), 0)
    box["roller"] = True
    box.setLinearVelocity((ROLL, 0.0, 0.0), False)
if tic >= 1:
    track_gaps(st)
    for ob in scene.objects:
        if ob.name.startswith("Plank"):
            st["max_speed"] = max(st["max_speed"], ob.worldLinearVelocity.length)
        if ob.get("roller"):
            st["roller_min_z"] = min(st.get("roller_min_z", 99.0), ob.worldPosition.z)
            st["roller_max_x"] = max(st.get("roller_max_x", -99.0), ob.worldPosition.x)
if tic == 300:
    drop = [ob for ob in scene.objects if ob.get("roller")]
    st["drop_z"] = drop[0].worldPosition.z if drop else None
    st["mid_z"] = obj("Plank4").worldPosition.z
    st["final_gap"] = gaps_now(st)
    write(st)
'''

PLANKS = 10
ROLL = 2.0
# (round 1 laid the planks straight, end to end between the posts: tied at
# both ends, a straight bridge cannot sag, its joints pulled without end and
# PhysX's flew apart. A rope bridge hangs: the planks laid on an arc, the
# end ones sloping 25 degrees)
SAG = 25.0


def bridge_planks():
    """each plank's middle (x, z) and slope (radians), from the left post's
    face; and where the last one ends"""
    out = []
    ex, ez = -2.75, BRIDGE_Z
    for i in range(PLANKS):
        phi = math.radians(-SAG + 2.0 * SAG * (i + 0.5) / PLANKS)
        out.append((ex + 0.25 * math.cos(phi), ez + 0.25 * math.sin(phi), phi))
        ex += 0.5 * math.cos(phi)
        ez += 0.5 * math.sin(phi)
    return out, ex
BRIDGE_Z = 2.0


def make_bridge(folder, E):
    files = {}
    for key, engine, device in RAGDOLL_ENGINES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = m6.base("P11bBridge")
        m6.set_engine(scene, engine, device)
        grey = m6.material("BrGrey", (0.45, 0.45, 0.45))
        wood = m6.material("BrWood", (0.7, 0.5, 0.3))
        m6.box(scene, "Floor", (12.0, 6.0, 0.2), (0.0, 0.0, -0.1), grey, physics='STATIC')
        if engine == 'PHYSX':
            left = m6.box(scene, "LeftPost", (0.3, 0.3, BRIDGE_Z), (-2.9, 0.0, BRIDGE_Z * 0.5), grey, mass=20.0)
            set_root(left, 'FIXED')
        else:
            # (Bullet has no articulations: the post stands still)
            left = m6.box(scene, "LeftPost", (0.3, 0.3, BRIDGE_Z), (-2.9, 0.0, BRIDGE_Z * 0.5), grey,
                          physics='STATIC')
        layout, end_x = bridge_planks()
        right = m6.box(scene, "RightPost", (0.3, 0.3, BRIDGE_Z), (end_x + 0.15, 0.0, BRIDGE_Z * 0.5), grey,
                       physics='STATIC')
        hinge_y = (0.0, 0.0, math.radians(90.0))
        pairs = []
        prev = left
        planks = []
        for i in range(PLANKS):
            px, pz, phi = layout[i]
            p = m6.box(scene, "Plank%d" % i, (0.5, 1.0, 0.08), (px, 0.0, pz), wood, mass=2.0, rotation=(0.0, -phi, 0.0))
            c = joint(p, prev, 'HINGE', (-0.5, 0.0, 0.0), hinge_y)
            c.name = "Hinge%d" % i
            pairs.append(("Hinge%d" % i, p.name, prev.name, (-0.5, 0.0, 0.0)))
            prev = p
            planks.append(p)
        c = joint(planks[-1], right, 'HINGE', (0.5, 0.0, 0.0), hinge_y)
        c.name = "ToRightPost"
        pairs.append(("ToRightPost", planks[-1].name, right.name, (0.5, 0.0, 0.0)))
        c = joint(planks[4], planks[6], 'BALL', (0.5, 0.0, 0.0))
        c.name = "Loop"
        pairs.append(("Loop", planks[4].name, planks[6].name, (0.5, 0.0, 0.0)))
        roller = m6.box(scene, "Roller", 0.3, (0.0, 0.0, -30.0), m6.material("BrRoller", (0.9, 0.2, 0.2),
                                                                              friction=0.2), mass=2.0)
        roller.layers[1] = True
        roller.layers[0] = False
        at = bpy.data.objects.new("RollerAt", None)
        scene.objects.link(at)
        at.location = (layout[1][0], 0.0, layout[1][1] + 0.25)
        p2.camera(scene, (0.0, -8.0, 2.6), (0.0, 0.0, 1.6), lens=30.0)
        m9.logic(scene, "P11bBridge", BRIDGE_SCRIPT.replace("PAIRS", repr(pairs)).replace("ROLL", repr(ROLL)))
        p2.add_probe(scene)
        scene["bge_remix"] = 0
        scene.update()
        name = "p11b_bridge_" + key
        remix_view()
        p2.save(os.path.join(folder, name + ".blend"))
        files[key] = name
    E["bridge"] = {"files": files, "tics": 305, "links": PLANKS + 1, "ordinary": ["ToRightPost", "Loop"],
                   "articulated": ["Hinge%d" % i for i in range(PLANKS)], "z": BRIDGE_Z}


# ---------------------------------------------------------------------------
# the crash check

CRASH_SCRIPT = COMMON + '''
st = g.setdefault("p11b", {"tic": 0, "links": {}, "toggles": 0, "errors": []})
st["tic"] += 1
tic = st["tic"]
def links_now(name):
    a = art_of(obj(name))
    return None if a is None else len(a.links)
try:
    if tic == 10:
        st["links"]["start"] = links_now("Root")
    if tic == 20:
        obj("Link06").endObject()
    if tic == 22:
        st["links"]["link removed"] = links_now("Root")
    if tic == 40:
        # (added where link 3 is, joined at its middle, not colliding with it)
        link3 = obj("Link03")
        box = scene.addObject("Extra", link3, 0)
        box["extra"] = True
        cid = cons.createConstraint(box.getPhysicsId(), link3.getPhysicsId(), cons.POINTTOPOINT_CONSTRAINT,
                                    0.0, 0.0, 0.0, flag=128)
        st["added_joint"] = cid.getConstraintId() if hasattr(cid, "getConstraintId") else None
    if tic == 42:
        st["links"]["box joined"] = links_now("Root")
    arm = obj("Mannequin")
    if 60 <= tic <= 150 and tic % 10 == 0 and arm is not None:
        rag = art_of(arm)
        rag.ragdoll = not rag.ragdoll
        st["toggles"] += 1
    if tic == 170 and st.get("added_joint"):
        cons.removeConstraint(st["added_joint"])
    if tic == 172:
        st["links"]["joint removed"] = links_now("Root")
    if tic == 190:
        obj("Root").endObject()
    if tic == 192:
        st["links"]["root removed"] = links_now("Link01")
except Exception as ex:
    st["errors"].append("tic %d: %r" % (tic, ex))
if tic == 200:
    write(st)
'''


def make_crash(folder, E):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = m6.base("P11bCrash")
    m6.set_engine(scene, 'PHYSX', 'CPU')
    grey = m6.material("CrGrey", (0.5, 0.5, 0.5))
    m6.box(scene, "Floor", (20.0, 10.0, 0.2), (3.0, 0.0, -0.1), grey, physics='STATIC')
    root = m6.box(scene, "Root", 0.3, (0.0, 0.0, ROOT_Z), m6.material("CrRoot", (0.2, 0.4, 0.9)))
    set_root(root, 'FIXED')
    mats = (m6.material("CrA", (0.9, 0.9, 0.9)), m6.material("CrB", (0.3, 0.3, 0.3)))
    chain(scene, "", root, LINKS, mats, weight=False)
    extra = m6.box(scene, "Extra", 0.3, (0.0, 0.0, -30.0), m6.material("CrExtra", (0.9, 0.2, 0.2)), mass=1.0)
    extra.layers[1] = True
    extra.layers[0] = False
    mannequin(scene, "Mannequin", (6.0, 3.0, 0.0))
    p2.camera(scene, (3.0, -18.0, 4.0), (3.0, 0.0, 3.5), lens=28.0)
    m9.logic(scene, "P11bCrash", CRASH_SCRIPT)
    p2.add_probe(scene)
    scene["bge_remix"] = 0
    scene.update()
    p2.save(os.path.join(folder, "p11b_crash_physx_cpu.blend"))
    # links: the root and 12; then link 6 gone: the root and links 0-5; the
    # box joined to link 3: one more; its joint removed: back; the root gone:
    # the rest is no articulation (no root)
    E["crash"] = {"file": "p11b_crash_physx_cpu", "tics": 205,
                  "links": {"start": LINKS + 1, "link removed": 7, "box joined": 8, "joint removed": 7,
                            "root removed": None},
                  "toggles": 10}


def make(folder, E):
    E["p11b"] = P = {}
    for fn in (make_chain, make_ragdoll, make_door, make_arm, make_bridge, make_crash):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sub = {}
        fn(folder, sub)
        P.update(sub)
