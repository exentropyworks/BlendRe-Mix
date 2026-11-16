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

"""BGE-Remix P11 (B2): Make Destructible.

On the active mesh: Blender's bundled Cell Fracture cuts it into pieces
(seed points from Seed: the same seed, the same pieces); or, with several
meshes selected, those are the pieces. The pieces are one compound rigid
body: the largest is the parent (ID property bge_destructible, with
bge_destructible_strength and bge_destructible_anchored), every piece has
bge_destructible_of (the parent's name). Under Bullet and stock Blender 2.79b
that is one solid object that never breaks; under PhysX the game breaks it
with NVIDIA Blast (impacts over Strength, bge.constraints.explode, the
weight on an anchored base). The original moves to layer 20, kept for making
it again (bge_destructible_source on the parent).
"""

import random

import bpy
import bmesh
from bpy.types import Operator
from bpy.props import BoolProperty, FloatProperty, IntProperty
from mathutils import Matrix, Vector


def hull_volume(points):
    """the volume of the points' convex hull"""
    bm = bmesh.new()
    try:
        for p in points:
            bm.verts.new(p)
        bm.verts.ensure_lookup_table()
        bmesh.ops.convex_hull(bm, input=bm.verts[:])
        return abs(bm.calc_volume(signed=False))
    finally:
        bm.free()


def mesh_volume(ob):
    """the volume of the piece's convex hull, in the world (Cell Fracture's
    pieces of a convex object are convex; a boolean's faces may be turned
    either way, which the mesh's own volume would count against each other)"""
    mw = ob.matrix_world
    try:
        return hull_volume([mw * v.co for v in ob.data.vertices])
    except (AttributeError, ValueError, RuntimeError):
        lo = Vector([min(c[i] for c in ob.bound_box) for i in range(3)])
        hi = Vector([max(c[i] for c in ob.bound_box) for i in range(3)])
        s = mw.to_scale()
        return abs((hi.x - lo.x) * (hi.y - lo.y) * (hi.z - lo.z) * s.x * s.y * s.z)


def remove_object(ob):
    me = ob.data if ob.type == 'MESH' else None
    for sc in ob.users_scene:
        sc.objects.unlink(ob)
    bpy.data.objects.remove(ob)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def fracture(scene, src, count, seed, margin):
    """Cell Fracture's cells of src from count seeded points inside its bounds"""
    from object_fracture_cell import fracture_cell_setup
    rng = random.Random(seed)
    lo = Vector([min(c[i] for c in src.bound_box) for i in range(3)])
    hi = Vector([max(c[i] for c in src.bound_box) for i in range(3)])
    mw = src.matrix_world
    pts = [mw * Vector((rng.uniform(lo.x, hi.x), rng.uniform(lo.y, hi.y), rng.uniform(lo.z, hi.z)))
           for _i in range(count)]
    me = bpy.data.meshes.new("bge_destructible_points")
    me.from_pydata([tuple(p) for p in pts], [], [])
    pob = bpy.data.objects.new("bge_destructible_points", me)
    scene.objects.link(pob)
    pob.parent = src
    pob.matrix_parent_inverse = mw.inverted()
    pob.matrix_world = Matrix.Identity(4)
    scene.update()
    try:
        cells = fracture_cell_setup.cell_fracture_objects(
            scene, src, source={'VERT_CHILD'}, source_limit=0, source_noise=0.0, clean=True,
            use_smooth_faces=False, use_data_match=True, use_debug_points=False, margin=margin,
            material_index=0, use_debug_redraw=False, cell_scale=(1.0, 1.0, 1.0))
        cells = fracture_cell_setup.cell_fracture_boolean(
            scene, src, cells, use_debug_bool=False, clean=True, use_island_split=False, use_interior_hide=False,
            use_debug_redraw=False, level=0)
    finally:
        remove_object(pob)
    return cells


class OBJECT_OT_bge_remix_make_destructible(Operator):
    """Pieces (Cell Fracture) the game breaks apart: impacts, explosions, its own weight (PhysX)"""
    bl_idname = "object.bge_remix_make_destructible"
    bl_label = "Make Destructible"
    bl_options = {'REGISTER', 'UNDO'}

    pieces = IntProperty(
        name="Pieces",
        description="How many pieces Cell Fracture cuts it into (about: empty cells are left out)",
        default=20, min=2, soft_max=200, max=1000)
    seed = IntProperty(
        name="Seed",
        description="The same seed gives the same pieces",
        default=1, min=0)
    strength = FloatProperty(
        name="Strength",
        description="The impulse (N s) a hit needs to break it where it lands",
        default=100.0, min=0.01, soft_max=10000.0)
    mass = FloatProperty(
        name="Mass",
        description="Its mass in all (kg), shared between the pieces by their volume",
        default=100.0, min=0.01, soft_max=100000.0)
    anchored = BoolProperty(
        name="Anchored Base",
        description="Its bottom pieces are held by the ground (a wall, a building)",
        default=False)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        scene = context.scene
        ob = context.active_object
        selected = [o for o in context.selected_objects if o.type == 'MESH' and o != ob]

        # made before: the original again, the old pieces go
        root = None
        if ob.get("bge_destructible"):
            root = ob
        elif ob.get("bge_destructible_of"):
            root = scene.objects.get(ob["bge_destructible_of"])
        source = None
        if root is not None:
            source = bpy.data.objects.get(root.get("bge_destructible_source", ""))
            key = root.name
            for o in [o for o in bpy.data.objects if o.get("bge_destructible_of") == key]:
                remove_object(o)
            if source is None:
                self.report({'ERROR'}, "The original of %s is gone: make it again from a mesh" % key)
                return {'CANCELLED'}
            selected = []
        else:
            source = ob

        if selected:
            # the selected meshes are the pieces (fractured already)
            cells = [ob] + selected
            source = None
        else:
            size = max(source.dimensions) if max(source.dimensions) > 0 else 1.0
            if "bge_destructible_layers" in source:
                layers = [bool(x) for x in source["bge_destructible_layers"]]
            else:
                layers = list(source.layers)
            cells = fracture(scene, source, self.pieces, self.seed, margin=0.0002 * size)
            if not cells:
                self.report({'ERROR'}, "Cell Fracture made no pieces")
                return {'CANCELLED'}
            for c in cells:
                c.layers = layers
            source["bge_destructible_layers"] = [1 if x else 0 for x in layers]
            # the original, kept on layer 20 (out of the game)
            source.layers = [False] * 19 + [True]

        # the same order every time: by height, then x, then y
        def where(o):
            c = o.matrix_world * (sum((Vector(v) for v in o.bound_box), Vector()) / 8.0)
            return (round(c.z, 4), round(c.x, 4), round(c.y, 4))
        cells.sort(key=where)
        volumes = [max(mesh_volume(c), 1e-9) for c in cells]
        total = sum(volumes)
        root = cells[max(range(len(cells)), key=lambda i: volumes[i])]
        base = source.name if source else root.name
        for i, c in enumerate(cells):
            if source is not None:
                c.name = "%s.%03d" % (base, i)
                c.data.name = c.name
        key = root.name
        scene.update()
        for c, vol in zip(cells, volumes):
            for k in ("bge_destructible", "bge_destructible_source"):
                if k in c:
                    del c[k]
            c["bge_destructible_of"] = key
            game = c.game
            game.physics_type = 'RIGID_BODY'
            game.use_collision_bounds = True
            game.collision_bounds_type = 'CONVEX_HULL'
            game.collision_margin = 0.0
            game.use_collision_compound = True
            game.mass = max(self.mass * vol / total, 0.01)
            if c is not root:
                mw = c.matrix_world.copy()
                c.parent = root
                c.matrix_world = mw
        root["bge_destructible"] = 1
        root.bge_destructible_strength = self.strength
        root.bge_destructible_anchored = self.anchored
        if source is not None:
            root["bge_destructible_source"] = source.name
        if self.anchored:
            # (Bullet and stock 2.79b: a wall that stands where it is)
            root.game.physics_type = 'STATIC'
            root.game.use_collision_compound = True
        scene.update()
        for o in context.selected_objects:
            o.select = False
        root.select = True
        scene.objects.active = root
        if scene.game_settings.physics_engine != 'PHYSX':
            self.report({'WARNING'}, "%d pieces made; they break under PhysX (World > Physics), here they stay "
                                     "whole" % len(cells))
        else:
            self.report({'INFO'}, "%d pieces made (%s the parent)" % (len(cells), key))
        return {'FINISHED'}


classes = (
    OBJECT_OT_bge_remix_make_destructible,
)
