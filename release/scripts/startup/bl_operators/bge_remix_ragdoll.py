# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

"""BGE-Remix P11 (B1): Make Ragdoll.

For the active armature, one capsule (a Rigid Body, Capsule bounds, invisible
in the game, drawn as wire, on the armature's layers) per bone, parented to
its bone, and a Cone Twist Rigid Body Joint from each capsule to its parent
bone's, its limits from the bone's IK limits where set. The top capsule is
the articulation's root (moves freely), so under PhysX the capsules are one
articulation once the ragdoll is let go.

In the game the capsules follow the bones until a script sets
bge.constraints.getArticulation(armature).ragdoll = True; then they fall from
the pose, at the bones' speed, and the bones follow them; False hands the
bones back to their animation.

Each capsule has the ID properties bge_ragdoll_bone (its bone, read by the
game) and bge_ragdoll_armature (for making it again).
"""

import math

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, FloatProperty
from mathutils import Matrix


def capsule_mesh(name, radius, length, segments=12, rings=4):
    """A capsule along Z, centred on the origin, `length` long in all."""
    half = max(length * 0.5 - radius, 0.0)
    verts = [(0.0, 0.0, -half - radius)]
    # the rings from the bottom up: the lower cap's (from its pole), then the upper's
    for side in (-1.0, 1.0):
        order = range(1, rings + 1) if side < 0 else range(rings, 0, -1)
        for k in order:
            a = (math.pi * 0.5) * (rings - k) / rings  # 0 at the equator
            r = radius * math.cos(a)
            z = side * (half + radius * math.sin(a))
            for s in range(segments):
                t = 2.0 * math.pi * s / segments
                verts.append((r * math.cos(t), r * math.sin(t), z))
    verts.append((0.0, 0.0, half + radius))
    nring = 2 * rings
    faces = []
    top = len(verts) - 1
    for s in range(segments):
        faces.append((0, 1 + (s + 1) % segments, 1 + s))
    for ring in range(nring - 1):
        a0 = 1 + ring * segments
        b0 = a0 + segments
        for s in range(segments):
            s1 = (s + 1) % segments
            faces.append((a0 + s, a0 + s1, b0 + s1, b0 + s))
    last = 1 + (nring - 1) * segments
    for s in range(segments):
        faces.append((last + s, last + (s + 1) % segments, top))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return me


def bone_limits(pb, twist, swing):
    """the joint's twist and swing from the bone's IK limits where set (twist
    about the bone's Y, swing about its X and Z: the largest either way),
    else the operator's"""
    def span(use, lo, hi):
        return max(abs(lo), abs(hi)) if use else None
    t = span(pb.use_ik_limit_y, pb.ik_min_y, pb.ik_max_y)
    sx = span(pb.use_ik_limit_x, pb.ik_min_x, pb.ik_max_x)
    sz = span(pb.use_ik_limit_z, pb.ik_min_z, pb.ik_max_z)
    swings = [v for v in (sx, sz) if v is not None]
    return (twist if t is None else t), (max(swings) if swings else swing)


class OBJECT_OT_bge_remix_make_ragdoll(Operator):
    """Capsules on the armature's bones, joined, for a ragdoll in the game (PhysX)"""
    bl_idname = "object.bge_remix_make_ragdoll"
    bl_label = "Make Ragdoll"
    bl_options = {'REGISTER', 'UNDO'}

    thickness = FloatProperty(
        name="Thickness",
        description="Each capsule's radius, as a part of its bone's length",
        default=0.2, min=0.02, max=0.5)
    mass = FloatProperty(
        name="Mass",
        description="The ragdoll's mass in all, shared between the capsules by their size",
        default=70.0, min=0.01, soft_max=1000.0)
    swing = FloatProperty(
        name="Swing",
        description="How far each joint bends from its rest, either way (a bone's IK limits, where set, "
                    "come first)",
        default=math.radians(45.0), min=0.0, max=math.radians(170.0), subtype='ANGLE')
    twist = FloatProperty(
        name="Twist",
        description="How far each joint turns about its bone, either way (a bone's IK limit in Y, where "
                    "set, comes first)",
        default=math.radians(30.0), min=0.0, max=math.radians(170.0), subtype='ANGLE')
    min_length = FloatProperty(
        name="Shortest Bone",
        description="Bones shorter than this get no capsule (they follow their parent)",
        default=0.02, min=0.0, soft_max=1.0, subtype='DISTANCE')
    deform_only = BoolProperty(
        name="Deforming Bones Only",
        description="Capsules only for the bones that deform the mesh",
        default=True)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'ARMATURE' and context.mode == 'OBJECT'

    def execute(self, context):
        scene = context.scene
        arm = context.active_object

        # made again: the old capsules go
        for ob in [o for o in bpy.data.objects if o.get("bge_ragdoll_armature") == arm.name]:
            me = ob.data if ob.type == 'MESH' else None
            for sc in ob.users_scene:
                sc.objects.unlink(ob)
            bpy.data.objects.remove(ob)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)

        bones = [pb for pb in arm.pose.bones
                 if pb.bone.length >= self.min_length and (pb.bone.use_deform or not self.deform_only)]
        if not bones:
            self.report({'WARNING'}, "No bones to put capsules on")
            return {'CANCELLED'}

        sizes = {}
        for pb in bones:
            length = pb.bone.length
            radius = min(max(length * self.thickness, 0.005), length * 0.5)
            half = max(length * 0.5 - radius, 0.0)
            sizes[pb.name] = (length, radius,
                              math.pi * radius * radius * (2.0 * half + 4.0 / 3.0 * radius))
        volume = sum(v[2] for v in sizes.values()) or 1.0

        scene.update()
        capsules = {}
        to_z = Matrix.Rotation(math.radians(-90.0), 4, 'X')  # the capsule's Z along the bone's Y
        for pb in bones:
            length, radius, vol = sizes[pb.name]
            name = "%s.%s.capsule" % (arm.name, pb.name)
            ob = bpy.data.objects.new(name, capsule_mesh(name, radius, length))
            scene.objects.link(ob)
            ob.layers = arm.layers
            ob.draw_type = 'WIRE'
            ob.hide_render = True  # (invisible in the game)
            game = ob.game
            game.physics_type = 'RIGID_BODY'
            game.use_collision_bounds = True
            game.collision_bounds_type = 'CAPSULE'
            game.mass = max(self.mass * vol / volume, 0.01)
            ob["bge_ragdoll_bone"] = pb.name
            ob["bge_ragdoll_armature"] = arm.name
            ob.parent = arm
            ob.parent_type = 'BONE'
            ob.parent_bone = pb.name
            capsules[pb.name] = (ob, length)
        scene.update()
        for pb in bones:
            ob, length = capsules[pb.name]
            ob.matrix_world = arm.matrix_world * pb.matrix * Matrix.Translation((0.0, length * 0.5, 0.0)) * to_z
        scene.update()

        roots = 0
        for pb in bones:
            ob, length = capsules[pb.name]
            parent = pb.parent
            while parent is not None and parent.name not in capsules:
                parent = parent.parent
            if parent is None:
                ob.bge_articulation = 'FREE'
                roots += 1
                continue
            con = ob.constraints.new('RIGID_BODY_JOINT')
            con.name = "Ragdoll Joint"
            con.target = capsules[parent.name][0]
            con.pivot_type = 'CONE_TWIST'
            con.use_linked_collision = True  # (Disable Linked Collision: joined capsules pass through)
            # the pivot at the bone's head, the joint's X along the bone
            con.pivot_x, con.pivot_y, con.pivot_z = 0.0, 0.0, -length * 0.5
            con.axis_x, con.axis_y, con.axis_z = 0.0, math.radians(-90.0), 0.0
            twist, swing = bone_limits(pb, self.twist, self.swing)
            con.use_angular_limit_x = con.use_angular_limit_y = con.use_angular_limit_z = True
            con.limit_angle_max_x = twist
            con.limit_angle_max_y = swing
            con.limit_angle_max_z = swing

        if scene.game_settings.physics_engine != 'PHYSX':
            self.report({'WARNING'}, "%d capsules made; the ragdoll is one articulation under PhysX (World > "
                                     "Physics)" % len(capsules))
        else:
            self.report({'INFO'}, "%d capsules made (%d root%s)" % (len(capsules), roots, "" if roots == 1 else "s"))
        context.scene.objects.active = arm
        return {'FINISHED'}


classes = (
    OBJECT_OT_bge_remix_make_ragdoll,
)
