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

# <pep8 compliant>

"""BGE-Remix P11 (B3): Make Fluid Volume.

The active mesh becomes a volume of water or lava: things float in it by
their mass and size, are slowed by it and carried along by its current
(PhysX). Its settings are ID properties (bge_fluid, bge_fluid_type 0 water
or 1 lava, bge_fluid_density, bge_fluid_drag, bge_fluid_current along the
object's own axes, bge_fluid_splashes), so stock Blender 2.79b opens and
plays the file. The object is a static Ghost with Convex Hull bounds: things
pass through it (under Bullet and stock 2.79b they fall through it), and a
Collision sensor on it sees what goes in. Its surface is the top of its
hull. Without a material it gets the Water or Lava preset (a flipbook, so it
moves in Remix); a mesh without a UV map gets one projected from above (a
UV unit a metre).
"""

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty

TYPES = (('WATER', "Water", "1000 kg/m³; things float in it by their mass and size", 0),
         ('LAVA', "Lava", "3100 kg/m³ and thick: it holds things higher and stops them sooner", 1))
DENSITY = {'WATER': 1000.0, 'LAVA': 3100.0}
DRAG = {'WATER': 3.0, 'LAVA': 24.0}
PRESET = {'WATER': 'WATER', 'LAVA': 'LAVA'}


def _type_changed(self, context):
    self.density = DENSITY[self.fluid_type]
    self.drag = DRAG[self.fluid_type]


def has_material(ob):
    return any(s.material is not None for s in ob.material_slots)


def uv_from_above(ob):
    """a UV map projected from above: a UV unit a metre, in the world"""
    me = ob.data
    me.uv_textures.new("UVMap")
    uv = me.uv_layers.active.data
    mw = ob.matrix_world
    for loop in me.loops:
        co = mw * me.vertices[loop.vertex_index].co
        uv[loop.index].uv = (co.x, co.y)


def set_prop(ob, name, value):
    """through the property the Physics tab registers, or as an ID property"""
    if hasattr(bpy.types.Object, name):
        setattr(ob, name, value)
    else:
        ob[name] = value


class OBJECT_OT_bge_remix_make_fluid_volume(Operator):
    """Water or lava that things float in, are slowed by and are carried along by (PhysX)"""
    bl_idname = "object.bge_remix_make_fluid_volume"
    bl_label = "Make Fluid Volume"
    bl_options = {'REGISTER', 'UNDO'}

    fluid_type = EnumProperty(
        name="Type",
        description="Water or lava (sets the density and drag)",
        items=TYPES, default='WATER', update=_type_changed)
    density = FloatProperty(
        name="Density",
        description="How much the fluid weighs (kg/m³): lighter things than the fluid they push aside float",
        default=1000.0, min=1.0, soft_max=20000.0)
    drag = FloatProperty(
        name="Drag",
        description="How quickly things in it slow down, moving and turning (per second, when wholly under)",
        default=3.0, min=0.0, soft_max=100.0)
    current = FloatVectorProperty(
        name="Current",
        description="Its flow (m/s) along the object's own axes: things in it are carried towards that speed",
        size=3, default=(0.0, 0.0, 0.0), subtype='VELOCITY', unit='VELOCITY')
    splashes = BoolProperty(
        name="Splashes",
        description="A splash where something goes in fast",
        default=True)

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and context.mode == 'OBJECT'

    def invoke(self, context, event):
        ob = context.active_object
        # made again: its settings as they are
        if ob.get("bge_fluid"):
            self.fluid_type = 'LAVA' if ob.get("bge_fluid_type", 0) == 1 else 'WATER'
            self.density = float(ob.get("bge_fluid_density", DENSITY[self.fluid_type]))
            self.drag = float(ob.get("bge_fluid_drag", DRAG[self.fluid_type]))
            if "bge_fluid_current" in ob:
                self.current = tuple(float(x) for x in ob["bge_fluid_current"])[:3]
            self.splashes = bool(ob.get("bge_fluid_splashes", 1))
        return self.execute(context)

    def execute(self, context):
        ob = context.active_object
        ob["bge_fluid"] = 1
        # (the type first: the Physics tab's Type sets its density and drag;
        # the operator's own then)
        set_prop(ob, "bge_fluid_type", self.fluid_type if hasattr(bpy.types.Object, "bge_fluid_type") else
                 (1 if self.fluid_type == 'LAVA' else 0))
        set_prop(ob, "bge_fluid_density", float(self.density))
        set_prop(ob, "bge_fluid_drag", float(self.drag))
        set_prop(ob, "bge_fluid_current", tuple(float(x) for x in self.current))
        set_prop(ob, "bge_fluid_splashes", bool(self.splashes) if hasattr(bpy.types.Object, "bge_fluid_splashes")
                 else (1 if self.splashes else 0))
        # things pass through it: a static Ghost, its hull the volume
        game = ob.game
        game.physics_type = 'STATIC'
        game.use_ghost = True
        game.use_collision_bounds = True
        game.collision_bounds_type = 'CONVEX_HULL'
        game.collision_margin = 0.0
        # its look: the preset, when it has no material of its own
        made = ""
        if not has_material(ob):
            from .bge_remix_presets import apply_preset
            if not ob.data.uv_textures:
                uv_from_above(ob)
            ma = bpy.data.materials.new(PRESET[self.fluid_type].capitalize())
            apply_preset(ma, PRESET[self.fluid_type])
            if ob.material_slots:
                ob.material_slots[0].material = ma
            else:
                ob.data.materials.append(ma)
            try:
                from bge_remix import atlas
                atlas.bake_flipbook(ma, 16)
            except (ImportError, ValueError) as ex:
                self.report({'WARNING'}, "The %s preset's flipbook: %s" % (ma.name, ex))
            made = "; it has the %s preset" % ma.name
        if context.scene.game_settings.physics_engine != 'PHYSX':
            self.report({'WARNING'}, "%s is a fluid volume%s; things float in it under PhysX (World > Physics), here "
                                     "they fall through it" % (ob.name, made))
        else:
            self.report({'INFO'}, "%s is a %s volume%s" % (ob.name, self.fluid_type.lower(), made))
        return {'FINISHED'}


classes = (
    OBJECT_OT_bge_remix_make_fluid_volume,
)
