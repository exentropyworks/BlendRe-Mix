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

"""BGE-Remix P12 round 4 (A4): File > Export > RTX Remix Asset (for the
Toolkit).

The RTX Remix Toolkit takes models in as FBX, OBJ, glTF or LXO and pictures
as PNG (among others), and converts them itself (its ingestion); it uses
only assets it ingested. So the selected meshes go out in a form it
ingests, into one folder:

- <name>.fbx: the meshes, with Blender's own FBX exporter (modifiers
  applied, in metres, placed relative to the world origin);
- <material>_<type>.png: each RTX Remix material's pictures, named by what
  they are (albedo, normal, roughness, metallic, emissive, height). A value
  with no picture (a plain roughness, say) becomes a small one-colour
  picture: the Toolkit builds its materials from pictures. Normal maps are
  OpenGL style (Blender's);
- <name>_readme.txt: each material and its pictures, with the Toolkit's
  texture type for each, so the texture sets are assigned in one pass.

What an asset cannot carry is reported: lamps (the Toolkit adds its own
lights), cameras, empties and other objects that are not meshes, logic and
physics, materials that are not RTX Remix materials.
"""

import os

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

# what the last export did (the tests read it)
LAST = {}

# the pictures: type, the node's input, the Toolkit's texture type, colour
# (sRGB) or data
PICTURES = (
    ("albedo", "Albedo", "Albedo", True),
    ("normal", "Normal", "Normal - OpenGL", False),
    ("roughness", "Roughness", "Roughness", False),
    ("metallic", "Metallic", "Metallic", False),
    ("emissive", "Emissive Color", "Emissive Mask", True),
    ("height", "Height", "Other (height)", False),
)
CONSTANT_SIZE = 4     # a one-colour picture's size


class AssetError(Exception):
    pass


def srgb(c):
    c = min(max(float(c), 0.0), 1.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def default_folder(context):
    """rtx_remix_assets/<name> beside the .blend (or the capture)"""
    scene = context.scene
    cap = scene.get("bge_remix_capture")
    here = bpy.path.abspath("//") if bpy.data.filepath else ""
    if not here and cap is not None and hasattr(cap, "get") and cap.get("path"):
        here = os.path.dirname(cap.get("path"))
    return os.path.join(here or os.getcwd(), "rtx_remix_assets", asset_name(context))


def asset_name(context):
    ob = context.scene.objects.active
    if ob is None or not ob.select:
        sel = [o for o in context.scene.objects if o.select]
        ob = sel[0] if sel else None
    return bpy.path.clean_name(ob.name if ob is not None else context.scene.name) or "asset"


def _straight_image(node, sock):
    """the image wired straight into the node's input and the texture
    node's output used ('Color' or 'Value'); (None, None) when nothing is
    wired, (False, None) when something else is"""
    inp = node.inputs.get(sock)
    if inp is None or not inp.is_linked:
        return None, None
    link = inp.links[0]
    tn = link.from_node
    tex = getattr(tn, "texture", None)
    ima = getattr(tex, "image", None) if tex is not None and tex.type == 'IMAGE' else None
    if tn.bl_idname != "ShaderNodeTexture" or ima is None:
        return False, None
    return ima, link.from_socket.name


class Export:
    """one asset export"""

    def __init__(self, context, folder, report):
        self.context = context
        self.scene = context.scene
        self.folder = folder
        self.report = report
        self.name = asset_name(context)
        self.materials = {}     # material name -> [(type, file, toolkit type, from)]
        self.counts = {"meshes": 0, "materials": 0, "pictures": 0}

    def note(self, line):
        if line not in self.report:
            self.report.append(line)

    def gather(self):
        sel = [ob for ob in self.scene.objects if ob.select]
        self.meshes = []
        for ob in sel:
            if ob.type == 'MESH':
                self.meshes.append(ob)
                g = ob.game
                if len(g.sensors) or len(g.controllers) or len(g.actuators) or len(g.properties):
                    self.note("%s: logic and game properties are not part of an asset" % ob.name)
                if ob.game.physics_type not in ('STATIC', 'NO_COLLISION'):
                    self.note("%s: physics is not part of an asset" % ob.name)
            elif ob.type == 'LAMP':
                self.note("%s: a lamp is not part of an asset (the Toolkit adds its own lights), left out" % ob.name)
            else:
                self.note("%s: a %s is not part of an asset (only meshes are), left out" % (ob.name,
                                                                                          ob.type.lower()))
        if not self.meshes:
            raise AssetError("no mesh is selected: select the meshes to export as an RTX Remix asset")

    def write(self):
        os.makedirs(self.folder, exist_ok=True)
        fbx = os.path.join(self.folder, self.name + ".fbx")
        if not hasattr(bpy.types, "EXPORT_SCENE_OT_fbx"):
            import addon_utils
            addon_utils.enable("io_scene_fbx", default_set=False)
        override = {"scene": self.scene, "selected_objects": self.meshes, "active_object": self.meshes[0],
                    "object": self.meshes[0]}
        ret = bpy.ops.export_scene.fbx(override, filepath=fbx, use_selection=True, object_types={'MESH'},
                                       use_mesh_modifiers=True, global_scale=1.0, apply_unit_scale=True,
                                       bake_anim=False, path_mode='STRIP')
        if 'FINISHED' not in ret or not os.path.isfile(fbx):
            raise AssetError("Blender's FBX exporter did not write %s" % fbx)
        self.counts["meshes"] = len(self.meshes)
        self.fbx = fbx
        done = set()
        for ob in self.meshes:
            for s in ob.material_slots:
                mat = s.material
                if mat is None or mat.name in done:
                    continue
                done.add(mat.name)
                self.material(mat)
        self.readme()
        return fbx

    # -- pictures -------------------------------------------------------------

    def material(self, mat):
        from .bge_remix_material import remix_node
        node = remix_node(mat) if mat.use_nodes else None
        if node is None:
            self.note("material %s is not an RTX Remix material (Material tab > RTX Remix): no pictures written"
                      % mat.name)
            return
        if node.remix_type == 'TRANSLUCENT':
            self.note("material %s is translucent: the Toolkit sets glass up itself (its pictures here are its "
                      "albedo, normal and emissive)" % mat.name)
        rows = []
        base = bpy.path.clean_name(mat.name)
        intensity = float(node.inputs["Emissive Intensity"].default_value)
        for kind, sock, toolkit, colour in PICTURES:
            ima, output = _straight_image(node, sock)
            if ima is False:
                self.note("material %s: its %s is not wired straight to an image: written as its plain value"
                          % (mat.name, sock))
                ima = None
            if ima is None and kind in ("normal", "height"):
                continue
            if ima is None and kind == "emissive" and intensity <= 0.0:
                continue
            path = os.path.join(self.folder, "%s_%s.png" % (base, kind))
            if ima is not None:
                self.picture(ima, output, kind, colour, node, path)
                how = "the picture %s" % ima.name
            else:
                v = node.inputs[sock].default_value
                self.constant(v, colour, kind, node, path)
                how = "its plain value %s" % (", ".join("%.3f" % c for c in tuple(v)[:3])
                                              if colour else "%.3f" % float(v))
            rows.append((kind, os.path.basename(path), toolkit, how))
            self.counts["pictures"] += 1
        if intensity > 0.0:
            rows.append(("emissive intensity", "", "the material's Emissive Intensity in the Toolkit",
                         "%.3f" % intensity))
        self.materials[mat.name] = rows
        self.counts["materials"] += 1

    def save_png(self, path, w, h, rgba):
        """rgba: w * h * 4 floats 0..1, rows from the bottom (Blender's)"""
        ima = bpy.data.images.new("bge_remix_asset_tmp", w, h, alpha=True)
        try:
            ima.pixels = rgba
            ima.filepath_raw = path
            ima.file_format = 'PNG'
            ima.save()
        finally:
            bpy.data.images.remove(ima)

    def constant(self, v, colour, kind, node, path):
        if colour:
            c = tuple(v)[:3]
            rgb = [srgb(x) for x in c]
            alpha = 1.0
            if kind == "albedo":
                op = node.inputs["Opacity"]
                alpha = 1.0 if op.is_linked else min(max(float(op.default_value), 0.0), 1.0)
            px = rgb + [alpha]
        else:
            g = min(max(float(v), 0.0), 1.0)
            px = [g, g, g, 1.0]
        n = CONSTANT_SIZE
        self.save_png(path, n, n, px * (n * n))

    def picture(self, ima, output, kind, colour, node, path):
        import numpy as np
        w, h = ima.size
        ch = ima.channels
        if w <= 0 or h <= 0 or ch <= 0:
            raise AssetError("the image %s could not be read" % ima.name)
        px = np.array(ima.pixels[:], dtype=np.float32).reshape(-1, ch)
        rgba = np.ones((px.shape[0], 4), dtype=np.float32)
        rgba[:, :min(ch, 4)] = px[:, :4]
        if ch < 3:
            rgba[:, 1] = rgba[:, 2] = rgba[:, 0]
        if colour and ima.is_float:
            c = np.clip(rgba[:, :3], 0.0, 1.0)
            rgba[:, :3] = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)
        if kind == "normal" and node.use_normal_directx:
            rgba[:, 1] = 1.0 - rgba[:, 1]
        if not colour and kind != "normal":
            # one channel, as grey: the texture's Value is the image's alpha
            # (as the bridge reads it), its Color the red
            g = rgba[:, 3].copy() if output == "Value" else rgba[:, 0].copy()
            rgba[:, 0] = rgba[:, 1] = rgba[:, 2] = g
            rgba[:, 3] = 1.0
        self.save_png(path, w, h, np.clip(rgba, 0.0, 1.0).ravel().tolist())

    def readme(self):
        lines = ["RTX Remix asset: %s" % self.name, "",
                 "Made by BGE-Remix (File > Export > RTX Remix Asset) for the RTX Remix Toolkit.", "",
                 "In the Toolkit's Ingest tab:",
                 "  Model(s):    %s (metres, placed relative to the world origin)" % os.path.basename(self.fbx),
                 "  Texture(s):  the pictures below, each with the texture type given; normal maps are",
                 "               OpenGL style (pick \"Normal - OpenGL\")", ""]
        for name in sorted(self.materials):
            lines.append("Material %s:" % name)
            for kind, file, toolkit, how in self.materials[name]:
                if file:
                    lines.append("  %-12s %-44s type: %-16s (%s)" % (kind, file, toolkit, how))
                else:
                    lines.append("  %-12s %s: %s" % (kind, toolkit, how))
            lines.append("")
        if self.report:
            lines += ["Left out:"] + ["  " + r for r in self.report] + [""]
        path = os.path.join(self.folder, self.name + "_readme.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
        self.readme_path = path


def export_asset(context, folder, report):
    """the selected meshes as an RTX Remix asset in folder; returns the
    FBX's path"""
    LAST.clear()
    ex = Export(context, folder, report)
    LAST.update({"folder": folder, "report": report, "path": None})
    ex.gather()
    path = ex.write()
    LAST.update({"path": path, "counts": ex.counts, "materials": ex.materials, "readme": ex.readme_path,
                 "name": ex.name})
    return path


class EXPORT_SCENE_OT_bge_remix_asset(Operator):
    """Export the selected meshes as an asset for the RTX Remix Toolkit to ingest: an FBX, each RTX Remix """ \
        """material's pictures as named PNGs, and a read-me"""
    bl_idname = "export_scene.bge_remix_asset"
    bl_label = "Export RTX Remix Asset"
    bl_options = {'REGISTER'}

    directory = StringProperty(name="Asset Folder", subtype='DIR_PATH',
                               description="The asset's folder (its FBX, pictures and read-me)")
    filter_folder = BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        if not self.directory:
            self.directory = default_folder(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        report = []
        folder = bpy.path.abspath(self.directory) if self.directory else default_folder(context)
        try:
            path = export_asset(context, folder, report)
        except AssetError as e:
            self.report({'ERROR'}, "RTX Remix Asset: %s" % e)
            print("BGE-Remix asset export: error: %s" % e)
            return {'CANCELLED'}
        for line in report:
            self.report({'WARNING'}, line)
            print("BGE-Remix asset export: " + line)
        c = LAST["counts"]
        self.report({'INFO'}, "RTX Remix Asset: %s: %d mesh(es), %d material(s), %d picture(s)%s" % (
            path, c["meshes"], c["materials"], c["pictures"],
            "; %d note(s), see the Info log" % len(report) if report else ""))
        print("BGE-Remix asset export: wrote " + path)
        return {'FINISHED'}


classes = (
    EXPORT_SCENE_OT_bge_remix_asset,
)
