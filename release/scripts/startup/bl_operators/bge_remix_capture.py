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

"""BGE-Remix P12 (A2): File > Import > RTX Remix Capture.

An RTX Remix capture (the stage file of a capture folder) comes in as a new
scene, read with the bridge's OpenUSD (bge_remix_usd.dll):

- each Remix mesh one Blender mesh, each place it was drawn an object
  sharing it (linked copies), its material on the object;
- each material an RTX Remix material (P9's node), Remix's AperturePBR
  values on the node's inputs and its textures as Texture nodes; the
  inputs the node has no place for are kept with the material
  (bge_remix_capture_inputs) for the mod export;
- Remix's lights as lamps, the reverse of how BGE-Remix sends lamps to Remix
  (remix_light.cc), so a lamp sent and read back is the same light;
- the camera as the scene camera.

The capture's units and up axis (a game in centimetres, Y up) become
Blender's metres and Z up: points p' = K p, matrices M' = K M K^-1, so
objects keep their own scale. The capture's own units, axis and path stay
with the scene (bge_remix_capture) for the mod export (A3). Every object and
material keeps its Remix hash (bge_remix_capture_hash), shown in the
Object and Material tabs.

Each DDS texture is decoded once to a PNG copy beside it (<name>.dds.png),
which Blender shows; the material keeps the DDS's path for Remix. A report
says what came in and what was left out or missing.
"""

import math
import os

import bpy
from bpy.props import StringProperty
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ImportHelper

HASH = "bge_remix_capture_hash"

# AperturePBR's inputs and the RTX Remix node's (values; textures below)
NODE_VALUES = {
    "diffuse_color_constant": "Albedo",
    "opacity_constant": "Opacity",
    "reflection_roughness_constant": "Roughness",
    "metallic_constant": "Metallic",
    "emissive_color_constant": "Emissive Color",
    "emissive_intensity": "Emissive Intensity",
    "anisotropy": "Anisotropy",
    "thin_film_thickness_constant": "Thin Film",
    "displace_in": "Displace In",
    "displace_out": "Displace Out",
    "ior_constant": "IOR",
    "transmittance_color": "Transmittance",
    "transmittance_measurement_distance": "Transmittance Distance",
    "thin_wall_thickness": "Thin Wall Thickness",
    "subsurface_transmittance_color": "Subsurface Color",
    "subsurface_radius": "Subsurface Radius",
}
# Remix's colour constants are sRGB (the bridge sends the node's linear ones
# as sRGB, bridge_scene.cpp srgb3): these come in as linear
SRGB_INPUTS = ("diffuse_color_constant", "emissive_color_constant", "transmittance_color",
               "subsurface_transmittance_color")


def linear(c):
    c = min(max(float(c), 0.0), 1.0)
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


# textures: input, the node's input, read as data (not colour)
NODE_TEXTURES = (
    ("diffuse_texture", "Albedo", False),
    ("normalmap_texture", "Normal", True),
    ("reflectionroughness_texture", "Roughness", True),
    ("metallic_texture", "Metallic", True),
    ("emissive_mask_texture", "Emissive Color", False),
    ("height_texture", "Height", True),
    ("transmittance_texture", "Transmittance", False),
    ("subsurface_transmittance_texture", "Subsurface Color", False),
)
# read into the node's options rather than its inputs
NODE_OPTIONS = ("enable_emission", "enable_thin_film", "thin_walled", "enable_opacity", "blend_enabled",
                "blend_type", "alpha_test_type", "alpha_test_reference_value", "use_legacy_alpha_state")


def capture_space(meters_per_unit, z_up):
    """K: the capture's space into Blender's (metres, Z up) and its inverse"""
    from mathutils import Matrix
    s = float(meters_per_unit) if meters_per_unit and meters_per_unit > 0.0 else 1.0
    K = Matrix.Scale(s, 4)
    if not z_up:
        # Y up to Z up: (x, y, z) -> (x, -z, y)
        K = Matrix.Rotation(math.radians(90.0), 4, 'X') * K
    return K, K.inverted()


def usd_matrix(m):
    """USD's 16 numbers (row vectors, the translation last) as a Blender
    Matrix (column vectors)"""
    from mathutils import Matrix
    return Matrix([[m[c * 4 + r] for c in range(4)] for r in range(4)])


def _floats(data, width):
    import numpy as np
    return np.frombuffer(data, dtype=np.float32).reshape(-1, width).copy()


def _ints(data):
    import numpy as np
    return np.frombuffer(data, dtype=np.int32).copy()


def build_mesh(m, K):
    """a Blender mesh from a capture mesh (its points in Blender's space)"""
    import numpy as np
    me = bpy.data.meshes.new(m["name"])
    k3 = np.array([[K[r][c] for c in range(3)] for r in range(3)], dtype=np.float64)
    pts = _floats(m["points"], 3).astype(np.float64).dot(k3.T)
    sizes = _ints(m["face_sizes"])
    corners = _ints(m["corners"])
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", pts.astype(np.float32).ravel())
    me.loops.add(len(corners))
    me.loops.foreach_set("vertex_index", corners)
    me.polygons.add(len(sizes))
    starts = np.zeros(len(sizes), dtype=np.int32)
    if len(sizes) > 1:
        starts[1:] = np.cumsum(sizes)[:-1]
    me.polygons.foreach_set("loop_start", starts)
    me.polygons.foreach_set("loop_total", sizes)
    me.update(calc_edges=True)
    if m.get("uvs"):
        me.uv_textures.new("UVMap")
        me.uv_layers[0].data.foreach_set("uv", _floats(m["uvs"], 2).ravel())
    if m.get("colors"):
        col = _floats(m["colors"], 4)
        layer = me.vertex_colors.new("Col")
        layer.data.foreach_set("color", np.ascontiguousarray(col[:, :3]).ravel())
        if (col[:, 3] < 0.999).any():
            alpha = me.vertex_colors.new("Alpha")
            a = np.repeat(col[:, 3:4], 3, axis=1)
            alpha.data.foreach_set("color", np.ascontiguousarray(a).ravel())
    if m.get("normals"):
        n = _floats(m["normals"], 3).astype(np.float64).dot(k3.T)
        length = np.sqrt((n * n).sum(axis=1))
        length[length < 1e-12] = 1.0
        n = n / length[:, None]
        me.polygons.foreach_set("use_smooth", [True] * len(sizes))
        me.use_auto_smooth = True
        me.normals_split_custom_set([tuple(v) for v in n.tolist()])
    me.show_double_sided = bool(m.get("double_sided"))
    me[HASH] = m["hash"]
    return me


def _image(path, report, cache):
    """the image Blender shows for a DDS texture: its PNG copy beside it
    (made once), or the file itself when it is not a DDS"""
    if path in cache:
        return cache[path]
    ima = None
    shown = path
    if path.lower().endswith(".dds"):
        shown = path + ".png"
        if not os.path.isfile(shown) or os.path.getmtime(shown) < os.path.getmtime(path):
            import _bge_remix
            ok, err = _bge_remix.dds_to_png(path, shown)
            if not ok:
                report.append("texture %s could not be decoded: %s" % (os.path.basename(path), err))
                shown = None
    if shown:
        try:
            ima = bpy.data.images.load(shown, check_existing=True)
            ima["bge_remix_capture_dds"] = path
        except RuntimeError as e:
            report.append("texture %s could not be loaded: %s" % (os.path.basename(shown), e))
    cache[path] = ima
    return ima


def build_material(mt, report, images):
    from .bge_remix_material import make_remix_material, _set
    mat = bpy.data.materials.new(mt["name"])
    node = make_remix_material(mat)
    nt = mat.node_tree
    inputs = mt["inputs"]
    translucent = "Translucent" in (mt.get("mdl") or "") or "Translucent" in (mt.get("sub_identifier") or "")
    node.remix_type = 'TRANSLUCENT' if translucent else 'OPAQUE'
    kept = {}
    for name, value in inputs.items():
        if name in NODE_VALUES:
            sock = NODE_VALUES[name]
            if isinstance(value, tuple):
                if name in SRGB_INPUTS:
                    value = tuple(linear(c) for c in value[:3])
                v = tuple(value[:3]) + ((1.0,) if node.inputs[sock].type == 'RGBA' else ())
                _set(node, sock, v if node.inputs[sock].type != 'VECTOR' else tuple(value[:3]))
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                _set(node, sock, float(value))
        elif name not in NODE_OPTIONS and not any(name == t[0] for t in NODE_TEXTURES):
            kept[name] = value if not isinstance(value, dict) else value.get("asset", "")
    # emission and thin film switched off keep their values at nothing
    if inputs.get("enable_emission") is False:
        _set(node, "Emissive Intensity", 0.0)
    elif "emissive_intensity" not in inputs and inputs.get("enable_emission") is True:
        _set(node, "Emissive Intensity", 1.0)
    if inputs.get("enable_thin_film") is False:
        _set(node, "Thin Film", 0.0)
    if translucent:
        node.use_thin_walled = bool(inputs.get("thin_walled", False))
    # blending (the material's game transparency)
    try:
        if inputs.get("blend_enabled"):
            node.blend = 'ADDITIVE' if inputs.get("blend_type") in (1, 5) else 'BLENDED'
        elif inputs.get("alpha_test_type") not in (None, 0, 7):
            node.blend = 'ALPHA_TEST'
            ref = inputs.get("alpha_test_reference_value")
            if isinstance(ref, (int, float)):
                node.alpha_cutoff = max(0.0, min(1.0, float(ref) / (255.0 if ref > 1.0 else 1.0)))
        elif inputs.get("enable_opacity"):
            node.blend = 'BLENDED'
    except TypeError:
        pass
    # textures
    geometry = None
    y = 300
    for name, sock, data in NODE_TEXTURES:
        value = inputs.get(name)
        if not isinstance(value, dict) or not value.get("asset"):
            continue
        if not value.get("exists"):
            report.append("material %s: %s %s is missing: it comes in without it" % (mt["name"], name,
                                                                                    value["asset"]))
            continue
        ima = _image(value["path"], report, images)
        if ima is None:
            continue
        if geometry is None:
            geometry = nt.nodes.new("ShaderNodeGeometry")
            geometry.location = (-760, 0)
        tex = bpy.data.textures.new("%s_%s" % (mt["name"], name), 'IMAGE')
        tex.image = ima
        tnode = nt.nodes.new("ShaderNodeTexture")
        tnode.texture = tex
        tnode.location = (-380, y)
        tnode.label = name
        y -= 260
        nt.links.new(geometry.outputs["UV"], tnode.inputs["Vector"])
        nt.links.new(tnode.outputs["Color"], node.inputs[sock])
        if data:
            try:
                ima.colorspace_settings.name = 'Non-Color'
            except TypeError:
                pass
        if name == "diffuse_texture" and inputs.get("enable_opacity"):
            nt.links.new(tnode.outputs["Value"], node.inputs["Opacity"])
        tex["bge_remix_capture_dds"] = value["path"]
    mat[HASH] = mt["hash"]
    mat["bge_remix_capture_mdl"] = mt.get("mdl") or ""
    if kept:
        mat["bge_remix_capture_inputs"] = kept
    return mat


def build_lamp(l, K, report):
    """a lamp for a Remix light: the reverse of remix_light.cc (distance
    1 m); None for one Blender has no lamp for"""
    s = K.to_scale()[0]
    power = l["intensity"] * (2.0 ** l["exposure"])
    kind = l["kind"]
    cone = l["cone_angle"] if l["shaped"] else 180.0
    shaped = l["shaped"] and cone < 179.9
    if kind == 'SPHERE':
        r = max(l["radius"] * s, 0.02)
        la = bpy.data.lamps.new(l["name"], 'SPOT' if shaped else 'POINT')
        la.shadow_soft_size = r
        la.distance = 1.0
        if shaped:
            # a spot sent to Remix as a sphere: a Classic spot (E D / r^2)
            la["bge_physical"] = 0.0
        else:
            la["bge_physical"] = 1.0  # E D^2 / r^2
        la.energy = power * r * r
    elif kind == 'DISK':
        # a physical spot is Remix's disk (E D^2 / r^2)
        r = max(l["radius"] * s, 0.02)
        la = bpy.data.lamps.new(l["name"], 'SPOT')
        la.shadow_soft_size = r
        la.distance = 1.0
        la["bge_physical"] = 1.0
        la.energy = power * r * r
        shaped = True
    elif kind == 'DISTANT':
        la = bpy.data.lamps.new(l["name"], 'SUN')
        la.energy = power
        if l["angle"] > 0.0:
            la["bge_sun_angle"] = float(l["angle"])
    elif kind == 'RECT':
        w, h = max(l["width"] * s, 0.001), max(l["height"] * s, 0.001)
        la = bpy.data.lamps.new(l["name"], 'AREA')
        la.shape = 'RECTANGLE'
        la.size, la.size_y = w, h
        la.distance = 1.0
        # pi E D / (w h)
        la.energy = power * w * h / math.pi
    else:
        report.append("light %s: a %s light: Blender has no lamp like it, left out" % (l["name"], kind.lower()))
        return None
    if shaped and la.type == 'SPOT':
        half = math.radians(min(max(cone, 0.5), 90.0))
        la.spot_size = 2.0 * half
        soft = l["cone_softness"]
        denom = 1.0 - math.cos(half)
        la.spot_blend = max(0.0, min(1.0, soft / denom if denom > 1e-6 else 0.0))
    la.color = tuple(max(0.0, c) for c in l["color"])
    la[HASH] = l["hash"]
    return la


def import_capture(context, path, report):
    """the capture at path as a new scene; returns it"""
    import _bge_remix
    data = _bge_remix.capture_read(path)
    report.extend(data["report"])
    K, Kinv = capture_space(data["meters_per_unit"], data["z_up"])
    name = os.path.splitext(os.path.basename(path))[0]
    scene = bpy.data.scenes.new(name)
    scene.render.engine = context.scene.render.engine
    # its materials are RTX Remix materials: the RTX Remix pipeline (P9)
    scene["bge_remix_pipeline"] = 1
    scene["bge_remix_capture"] = {"path": os.path.abspath(path), "meters_per_unit": float(data["meters_per_unit"]),
                                  "z_up": int(bool(data["z_up"])), "game_name": data["game_name"],
                                  "exe_name": data["exe_name"]}
    images = {}
    meshes = [build_mesh(m, K) for m in data["meshes"]]
    materials = [build_material(mt, report, images) for mt in data["materials"]]
    for inst in data["instances"]:
        me = meshes[inst["mesh"]]
        ob = bpy.data.objects.new(inst["name"], me)
        scene.objects.link(ob)
        ob.matrix_world = K * usd_matrix(inst["matrix"]) * Kinv
        ob[HASH] = inst["hash"]
        ob["bge_remix_capture_mesh"] = data["meshes"][inst["mesh"]]["hash"]
        # the material on the object: places of one mesh may have others
        # (the game converts a shared mesh once for each set, P12)
        if inst["material"] >= 0:
            if not me.materials:
                me.materials.append(None)
            slot = ob.material_slots[0]
            slot.link = 'OBJECT'
            slot.material = materials[inst["material"]]
        if inst["sky"]:
            ob.hide = ob.hide_render = True
            report.append("instance %s: part of the sky: it comes in hidden" % inst["name"])
    lamps = 0
    for l in data["lights"]:
        la = build_lamp(l, K, report)
        if la is None:
            continue
        ob = bpy.data.objects.new(l["name"], la)
        scene.objects.link(ob)
        m = K * usd_matrix(l["matrix"]) * Kinv
        # a lamp's place and turn, not its scale (its size is in the lamp)
        loc, rot, _scale = m.decompose()
        from mathutils import Matrix
        ob.matrix_world = Matrix.Translation(loc) * rot.to_matrix().to_4x4()
        ob[HASH] = l["hash"]
        lamps += 1
    cam = data["camera"]
    if cam:
        cd = bpy.data.cameras.new("Camera")
        cd.sensor_fit = 'HORIZONTAL'
        if cam["horizontal_aperture"] > 0.0 and cam["focal_length"] > 0.0:
            cd.sensor_width = cam["horizontal_aperture"]
            cd.lens = cam["focal_length"]
        s = K.to_scale()[0]
        cd.clip_start = max(cam["near"] * s, 0.001)
        cd.clip_end = max(cam["far"] * s, cd.clip_start * 2.0)
        if not cam["perspective"]:
            cd.type = 'ORTHO'
        ob = bpy.data.objects.new("Camera", cd)
        scene.objects.link(ob)
        m = K * usd_matrix(cam["matrix"]) * Kinv
        loc, rot, _scale = m.decompose()
        from mathutils import Matrix
        ob.matrix_world = Matrix.Translation(loc) * rot.to_matrix().to_4x4()
        scene.camera = ob
    scene["bge_remix_capture_counts"] = {"meshes": len(meshes), "objects": len(data["instances"]),
                                         "materials": len(materials), "lamps": lamps, "camera": int(bool(cam))}
    scene.update()
    return scene


class IMPORT_SCENE_OT_bge_remix_capture(Operator, ImportHelper):
    """Import an RTX Remix capture as a new scene: its meshes, materials (as RTX Remix materials), """ \
        """lights and camera, each with its Remix hash"""
    bl_idname = "import_scene.bge_remix_capture"
    bl_label = "Import RTX Remix Capture"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".usda"
    filter_glob = StringProperty(default="*.usd;*.usda;*.usdc", options={'HIDDEN'})

    def execute(self, context):
        report = []
        try:
            scene = import_capture(context, self.filepath, report)
        except RuntimeError as e:
            self.report({'ERROR'}, "RTX Remix Capture: %s" % e)
            return {'CANCELLED'}
        except ImportError:
            self.report({'ERROR'}, "RTX Remix Capture: this Blender has no RTX Remix bridge")
            return {'CANCELLED'}
        # the new scene shown (every window's: also when run in the background)
        if context.screen is not None:
            context.screen.scene = scene
        else:
            for win in context.window_manager.windows:
                win.screen.scene = scene
        c = scene["bge_remix_capture_counts"]
        for line in report:
            self.report({'WARNING'}, line)
            print("BGE-Remix capture import: " + line)
        self.report({'INFO'}, "RTX Remix Capture: %d meshes, %d objects, %d materials, %d lamps%s%s" % (
            c["meshes"], c["objects"], c["materials"], c["lamps"], ", the camera" if c["camera"] else "",
            "; %d note(s), see the Info log" % len(report) if report else ""))
        return {'FINISHED'}


class OBJECT_PT_bge_remix_capture(Panel):
    """BGE-Remix P12: the Remix hash of an object from a capture"""
    bl_label = "RTX Remix Capture"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob is not None and HASH in ob

    def draw(self, context):
        ob = context.object
        col = self.layout.column()
        col.label("Hash: %s" % ob[HASH])
        if "bge_remix_capture_mesh" in ob:
            col.label("Mesh: %s" % ob["bge_remix_capture_mesh"])


class MATERIAL_PT_bge_remix_capture(Panel):
    """BGE-Remix P12: the Remix hash of a material from a capture"""
    bl_label = "RTX Remix Capture"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ma = context.material
        return ma is not None and HASH in ma

    def draw(self, context):
        ma = context.material
        col = self.layout.column()
        col.label("Hash: %s" % ma[HASH])
        if ma.get("bge_remix_capture_mdl"):
            col.label("Shader: %s" % ma["bge_remix_capture_mdl"])


classes = (
    IMPORT_SCENE_OT_bge_remix_capture,
    OBJECT_PT_bge_remix_capture,
    MATERIAL_PT_bge_remix_capture,
)
