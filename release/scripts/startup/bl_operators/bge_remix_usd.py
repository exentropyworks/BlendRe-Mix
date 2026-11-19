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

"""BGE-Remix P12 round 6: File > Export and File > Import > Universal Scene
Description (.usd, .usda, .usdc): scenes to and from other tools.

Export (the whole scene, or the selected objects): meshes with their
modifiers applied (faces, normals, UVs, vertex colours; split by material
into GeomSubsets), the hierarchy (each object's transform relative to its
parent; empties as plain transforms), materials as UsdPreviewSurface (any
tool reads it: colour, roughness, metallic, emission, opacity, normal map,
IOR, with their pictures) and RTX Remix materials also as Remix's
AperturePBR, lamps as UsdLux lights (the mod export's rules), cameras.
Metres, Z up. The text is written in Python (bge_remix_usd_text.py); for
.usdc and .usd the bridge's OpenUSD turns it into USD's binary form. The
file is read back the way the import reads it before the export reports
success. Pictures are copied into a textures folder beside the file.

Import reads any tool's file through the bridge's OpenUSD (references,
payloads, instancing, every way of storing normals and UVs) into a new
scene: meshes (an instanced reference's copies sharing one mesh), the
hierarchy (transforms as empties), materials as RTX Remix materials (from
AperturePBR when the file has it, else from the preview surface), lamps,
cameras. Y-up and centimetre files come in Z up and in metres. What it
cannot take is listed in the report, never dropped silently.
"""

import os
import shutil

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import bge_remix_usd_text as ut
from .bge_remix_capture import HASH, build_lamp, build_material, build_mesh, capture_space, \
    usd_matrix
from .bge_remix_mod import TEXTURE_KIND, Export, rigid, srgb3, usd_rows
from .bge_remix_mod_text import ident

LAST = {}
EXTENSIONS = {'USDA': ".usda", 'USDC': ".usdc", 'USD': ".usd"}
MESH_TYPES = ('MESH', 'CURVE', 'SURFACE', 'FONT')

# an AperturePBR texture input, the preview surface's input it feeds, the
# texture's output read there, and whether it is data (not colour)
PREVIEW_OF = (
    ("diffuse_texture", "diffuseColor", "rgb", False),
    ("normalmap_texture", "normal", "rgb", True),
    ("reflectionroughness_texture", "roughness", "r", True),
    ("metallic_texture", "metallic", "r", True),
    ("emissive_mask_texture", "emissiveColor", "rgb", False),
)
# the capture marks build_material leaves that a USD import has no use for
# (bge_remix_capture_inputs, AperturePBR's inputs the node has no place
# for, stays: the export writes them back)
CAPTURE_MARKS = (HASH, "bge_remix_capture_mdl", "bge_remix_capture_had", "bge_remix_capture_options",
                 "bge_remix_capture_blend")


class UsdError(Exception):
    pass


def _drop(idblock, keys):
    for k in keys:
        if k in idblock:
            del idblock[k]


# ---------------------------------------------------------------------------
# export

class SceneExport(Export):
    """one export: the scene gathered into bge_remix_usd_text's dicts, then
    written. The mod export's mesh, material and lamp rules, in Blender's
    own units (metres, Z up)"""

    def __init__(self, scene, path, report, selected_only=False):
        import numpy as np
        from mathutils import Matrix
        self.scene = scene
        self.path = path
        self.folder = os.path.dirname(path)
        self.report = report
        self.selected_only = selected_only
        self.K = Matrix.Identity(4)
        self.Kinv = Matrix.Identity(4)
        self.s = 1.0
        self.k3inv = np.identity(3, dtype=np.float64)
        self.textures = {}
        self.local_names = set()
        self.local_of = {}
        self.pictures = {}        # (image, alpha to red, flip green, to sRGB) -> ./textures/<file>
        self.picture_files = set()
        self.material_index = {}  # material name -> index in the scene's materials (None: not written)
        self.counts = {"objects": 0, "meshes": 0, "materials": 0, "lamps": 0, "cameras": 0, "empties": 0,
                       "pictures": 0, "textures": 0, "copied": 0}
        self.data = {"root": scene.name, "objects": [], "materials": []}

    # -- pictures -------------------------------------------------------------

    def texture(self, mat, tex, ima, name, output, directx):
        """an image wired into the RTX Remix node, copied beside the file:
        as it is, or (a roughness or metallic map read from its alpha, a
        DirectX normal map) as a PNG made to read the standard way"""
        kind = TEXTURE_KIND.get(name, 'COLOR')
        return self.picture(ima, alpha_to_red=(kind == 'SCALAR' and output == "Value"),
                            flip_green=(kind == 'NORMAL' and directx), to_srgb=(kind == 'COLOR'))

    def picture(self, ima, alpha_to_red=False, flip_green=False, to_srgb=False):
        if ima is None:
            return None
        src = bpy.path.abspath(ima.filepath, library=ima.library) if ima.filepath else ""
        plain = not alpha_to_red and not flip_green and ima.source == 'FILE' and not ima.packed_file and \
            not ima.is_dirty and os.path.isfile(src)
        key = (ima.name, alpha_to_red, flip_green, to_srgb and ima.is_float and not plain)
        if key in self.pictures:
            return self.pictures[key]
        stem, ext = os.path.splitext(os.path.basename(src)) if src else (ima.name, "")
        stem = ident(stem)
        if not plain:
            ext = ".png"
            stem += ("_alpha" if alpha_to_red else "") + ("_opengl" if flip_green else "")
        base = stem + ext.lower()
        n = 1
        while base.lower() in self.picture_files:
            n += 1
            base = "%s_%d%s" % (stem, n, ext.lower())
        self.picture_files.add(base.lower())
        folder = os.path.join(self.folder, "textures")
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, base)
        try:
            if plain:
                if os.path.abspath(src) != os.path.abspath(dst):
                    shutil.copyfile(src, dst)
                self.counts["copied"] += 1
            else:
                self.write_png(ima, dst, alpha_to_red, flip_green, to_srgb and ima.is_float)
        except (OSError, RuntimeError, ValueError) as e:
            self.note("the picture %s could not be written: %s: left out" % (ima.name, e))
            self.pictures[key] = None
            return None
        self.counts["pictures"] += 1
        rel = "./textures/" + base
        self.pictures[key] = rel
        return rel

    @staticmethod
    def write_png(ima, path, alpha_to_red, flip_green, to_srgb):
        import numpy as np
        w, h = ima.size
        ch = ima.channels
        if w <= 0 or h <= 0 or ch <= 0:
            raise ValueError("it has no pixels")
        px = np.array(ima.pixels[:], dtype=np.float32).reshape(-1, ch)
        rgba = np.ones((px.shape[0], 4), dtype=np.float32)
        rgba[:, :min(ch, 4)] = px[:, :4]
        if ch < 3:
            rgba[:, 1] = rgba[:, 2] = rgba[:, 0]
        if to_srgb:
            c = np.clip(rgba[:, :3], 0.0, 1.0)
            rgba[:, :3] = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)
        if alpha_to_red:
            rgba[:, 0] = rgba[:, 1] = rgba[:, 2] = rgba[:, 3]
            rgba[:, 3] = 1.0
        if flip_green:
            rgba[:, 1] = 1.0 - rgba[:, 1]
        out = bpy.data.images.new("bge_remix_usd_picture", w, h, alpha=True)
        try:
            out.pixels[:] = np.clip(rgba, 0.0, 1.0).ravel().tolist()
            out.filepath_raw = path
            out.file_format = 'PNG'
            out.save()
        finally:
            bpy.data.images.remove(out)

    # -- materials ------------------------------------------------------------

    def material_of(self, mat):
        """the material's index in the file's materials (written once); None
        for no material"""
        if mat is None:
            return None
        if mat.name in self.material_index:
            return self.material_index[mat.name]
        from .bge_remix_material import remix_node
        node = remix_node(mat) if mat.use_nodes else None
        if node is not None:
            ap = Export.material(self, mat)
            pv = self.preview_of_remix(mat, node, ap)
        else:
            ap = None
            pv = self.preview_of_classic(mat)
        self.data["materials"].append({"name": mat.name, "preview": pv, "aperture": ap})
        index = len(self.data["materials"]) - 1
        self.material_index[mat.name] = index
        self.counts["materials"] += 1
        return index

    def preview_of_remix(self, mat, node, ap):
        """the RTX Remix node as its nearest UsdPreviewSurface (linear
        colours, the same pictures)"""

        def col(sock):
            return tuple(float(c) for c in tuple(node.inputs[sock].default_value)[:3])

        def val(sock):
            return float(node.inputs[sock].default_value)

        translucent = node.remix_type == 'TRANSLUCENT'
        textures = {}
        for aname, pname, output, data in PREVIEW_OF:
            rel = (ap or {}).get("textures", {}).get(aname)
            if rel:
                textures[pname] = {"file": rel, "output": output, "raw": data, "normal": pname == "normal"}
        inputs = [("diffuseColor", col("Transmittance") if translucent else col("Albedo")),
                  ("roughness", min(max(val("Roughness"), 0.0), 1.0)),
                  ("metallic", min(max(val("Metallic"), 0.0), 1.0))]
        intensity = val("Emissive Intensity")
        if intensity > 0.0:
            inputs.append(("emissiveColor", tuple(c * intensity for c in col("Emissive Color"))))
        else:
            textures.pop("emissiveColor", None)
        if translucent:
            inputs.append(("ior", val("IOR")))
            inputs.append(("opacity", 0.25))
        else:
            inputs.append(("opacity", min(max(val("Opacity"), 0.0), 1.0)))
            # the albedo picture's alpha as the opacity (as the import wires it)
            op = node.inputs["Opacity"]
            if op.is_linked and "diffuseColor" in textures and op.links[0].from_socket.name == "Value" and \
                    node.inputs["Albedo"].is_linked and \
                    op.links[0].from_node == node.inputs["Albedo"].links[0].from_node:
                textures["opacity"] = {"file": textures["diffuseColor"]["file"], "output": "a", "raw": True}
            if node.blend == 'ALPHA_TEST':
                inputs.append(("opacityThreshold", min(max(float(node.alpha_cutoff), 0.0), 1.0)))
        return {"inputs": inputs, "textures": textures}

    def preview_of_classic(self, mat):
        """a Classic material as its nearest UsdPreviewSurface: its colour,
        opacity, roughness from its specular hardness, glow; its first
        colour picture and normal map"""
        from .bge_remix_material import _values
        v, _kind = _values(mat)
        inputs = [("diffuseColor", tuple(v["Albedo"][:3])), ("roughness", float(v["Roughness"])),
                  ("metallic", float(v["Metallic"])),
                  ("opacity", float(mat.alpha) if mat.use_transparency else 1.0)]
        if v["Emissive Intensity"] > 0.0:
            inputs.append(("emissiveColor", tuple(c * v["Emissive Intensity"] for c in v["Emissive Color"][:3])))
        textures = {}
        for i, slot in enumerate(mat.texture_slots):
            if slot is None or slot.texture is None or not mat.use_textures[i] or slot.texture.type != 'IMAGE':
                continue
            ima = slot.texture.image
            if ima is None:
                continue
            if slot.use_map_color_diffuse and "diffuseColor" not in textures:
                rel = self.picture(ima)
                if rel:
                    textures["diffuseColor"] = {"file": rel, "output": "rgb"}
                    if slot.use_map_alpha and mat.use_transparency:
                        textures["opacity"] = {"file": rel, "output": "a", "raw": True}
            elif slot.use_map_normal and "normal" not in textures:
                rel = self.picture(ima)
                if rel:
                    textures["normal"] = {"file": rel, "output": "rgb", "raw": True, "normal": True}
        return {"inputs": inputs, "textures": textures}

    # -- objects --------------------------------------------------------------

    def objects(self):
        """the objects to write, parents first"""
        scene = self.scene
        obs = [ob for ob in scene.objects if not self.selected_only or ob.select]
        chosen = set(ob.name for ob in obs)

        def depth(ob):
            d, p = 0, ob.parent
            while p is not None:
                d += 1
                p = p.parent
            return d

        obs.sort(key=lambda ob: (depth(ob), ob.name))
        return obs, chosen

    def gather(self):
        obs, chosen = self.objects()
        if not obs:
            raise UsdError("nothing to export" + (" (no object is selected)" if self.selected_only else ""))
        index, world = {}, {}
        # objects left out (a hemi lamp): kept as plain transforms when
        # something hangs from them
        has_children = set(ob.parent.name for ob in obs if ob.parent is not None)
        for ob in obs:
            p = ob.parent
            while p is not None and p.name not in index:
                p = p.parent
            parent = index[p.name] if p is not None else -1
            entry = {"name": ob.name, "kind": "XFORM", "parent": parent, "visible": not ob.hide_render}
            w = ob.matrix_world.copy()
            if ob.type in MESH_TYPES:
                data = self.mesh_of(ob)
                if data is not None:
                    entry["kind"] = "MESH"
                    entry["mesh"] = data
                    self.counts["meshes"] += 1
                else:
                    self.counts["empties"] += 1
            elif ob.type == 'LAMP':
                w = rigid(w)
                light = Export.light(self, ob, w, False)
                if light is None:
                    if ob.name not in has_children:
                        continue
                    self.counts["empties"] += 1
                else:
                    light.pop("matrix", None)
                    entry["kind"] = "LIGHT"
                    entry["light"] = light
                    self.counts["lamps"] += 1
            elif ob.type == 'CAMERA':
                w = rigid(w)
                entry["kind"] = "CAMERA"
                entry["camera"] = self.camera_of(ob)
                self.counts["cameras"] += 1
            else:
                if ob.type != 'EMPTY':
                    self.note("%s: a %s object has no USD form here: written as an empty" % (ob.name,
                                                                                         ob.type.lower()))
                self.counts["empties"] += 1
            local = w if parent < 0 else world[parent].inverted() * w
            entry["matrix"] = usd_rows(local)
            world[len(self.data["objects"])] = w
            index[ob.name] = len(self.data["objects"])
            self.data["objects"].append(entry)
        self.counts["objects"] = len(self.data["objects"])

    def mesh_of(self, ob):
        try:
            me = ob.to_mesh(self.scene, True, 'RENDER')
        except RuntimeError:
            me = None
        if me is None:
            self.note("%s: no mesh could be made of it: written as an empty" % ob.name)
            return None
        try:
            data = Export.mesh(self, me, None)
            if data is None:
                self.note("%s has no faces: written as an empty" % ob.name)
                return None
            data.pop("matrix", None)
            data["name"] = ob.data.name
            mats = [s.material for s in ob.material_slots]
            faces = [p.material_index for p in me.polygons]
            used = sorted(set(i for i in faces if i < len(mats) and mats[i] is not None))
            data["material"] = None
            if len(used) == 1 and all(i == used[0] for i in faces):
                data["material"] = self.material_of(mats[used[0]])
            elif used:
                data["subsets"] = [{"name": "material_%d" % i, "faces": [f for f, j in enumerate(faces) if j == i],
                                    "material": self.material_of(mats[i])} for i in used]
            return data
        finally:
            bpy.data.meshes.remove(me)

    def camera_of(self, ob):
        cd = ob.data
        r = self.scene.render
        aspect = (r.resolution_x * r.pixel_aspect_x) / max(r.resolution_y * r.pixel_aspect_y, 1e-6)
        ortho = cd.type == 'ORTHO'
        size = cd.ortho_scale * 10.0 if ortho else cd.sensor_width
        fit = cd.sensor_fit
        if fit == 'VERTICAL':
            v = cd.ortho_scale * 10.0 if ortho else cd.sensor_height
            h = v * aspect
        elif fit == 'HORIZONTAL' or aspect >= 1.0:
            h, v = size, size / aspect
        else:
            v, h = size, size * aspect
        return {"focal_length": float(cd.lens), "horizontal_aperture": float(h), "vertical_aperture": float(v),
                "clipping": (float(cd.clip_start), float(cd.clip_end)), "perspective": not ortho}

    # -- writing --------------------------------------------------------------

    def write(self):
        import _bge_remix
        text = ut.scene_text(self.data)
        ext = os.path.splitext(self.path)[1].lower()
        os.makedirs(self.folder or ".", exist_ok=True)
        if ext == ".usda":
            with open(self.path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        else:
            tmp = os.path.splitext(self.path)[0] + ".bge_remix_tmp.usda"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            try:
                ok, err = _bge_remix.usd_convert(tmp, self.path)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            if not ok:
                raise UsdError("the binary file could not be written: %s" % err)
        # read back the way the import reads it
        try:
            back = _bge_remix.usd_read(self.path)
        except RuntimeError as e:
            raise UsdError("the file written does not read back: %s" % e)
        bad = ut.check_read(self.data, back)
        if bad:
            raise UsdError("the file written does not read back as written: " + "; ".join(bad[:8]))


def export_usd(scene, path, report, selected_only=False):
    """the scene (or its selected objects) as a USD file at path"""
    LAST.clear()
    LAST.update({"path": None, "report": report})
    ex = SceneExport(scene, path, report, selected_only)
    ex.gather()
    ex.write()
    LAST.update({"path": path, "counts": ex.counts, "materials": [m["name"] for m in ex.data["materials"]],
                 "pictures": sorted(v for v in ex.pictures.values() if v)})
    return path


def light_of(scene, ob):
    """the Remix light a lamp is sent as (the mod export's rules): its type
    and attributes; None for one there is none like (for the tests)"""
    ex = SceneExport(scene, os.path.join(bpy.app.tempdir or ".", "x.usda"), [])
    light = Export.light(ex, ob, rigid(ob.matrix_world), False)
    return None if light is None else {"type": light["type"], "attrs": {a[1]: a[2] for a in light["attrs"]}}


# ---------------------------------------------------------------------------
# import

def _f(v):
    return float(v[0]) if isinstance(v, (list, tuple)) else float(v)


def _asset(inp):
    return {"asset": inp["text"], "path": inp["path"], "exists": bool(inp["exists"])}


def aperture_inputs(m):
    """AperturePBR's inputs as capture_read gives them (for build_material)"""
    out = {}
    for name, inp in m["aperture_inputs"].items():
        k, v = inp["kind"], inp["v"]
        if k == 0:
            out[name] = float(v[0])
        elif k == 1:
            out[name] = int(round(v[0]))
        elif k == 2:
            out[name] = bool(v[0])
        elif k in (3, 4, 5):
            out[name] = tuple(float(x) for x in v[:k - 1])
        elif k == 6:
            out[name] = _asset(inp)
        elif k == 7:
            out[name] = inp["text"]
    return out


def preview_inputs(m, report):
    """a UsdPreviewSurface as AperturePBR's inputs (colours as sRGB, as
    Remix's are), for build_material"""
    p = m["preview_inputs"]
    name = m["name"]
    out = {}

    def const(key, default):
        i = p.get(key)
        return default if i is None or i["kind"] == 6 else i["v"]

    def tex(key, want):
        i = p.get(key)
        if i is None or i["kind"] != 6 or not i["text"]:
            return None
        if i["output"] not in want:
            report.append("material %s: its %s reads the picture's %s channel: Blender reads its %s" % (
                name, key, i["output"], want[0]))
        return _asset(i)

    c = const("diffuseColor", (0.18, 0.18, 0.18, 0))
    out["diffuse_color_constant"] = srgb3(c[:3])
    out["reflection_roughness_constant"] = _f(const("roughness", (0.5,)))
    out["metallic_constant"] = _f(const("metallic", (0.0,)))
    opacity = _f(const("opacity", (1.0,)))
    out["opacity_constant"] = opacity
    e = const("emissiveColor", (0.0, 0.0, 0.0, 0))[:3]
    peak = max(e)
    if peak > 0.0 or (p.get("emissiveColor") or {}).get("kind") == 6:
        out["enable_emission"] = True
        out["emissive_color_constant"] = srgb3([x / peak for x in e]) if peak > 0.0 else (1.0, 1.0, 1.0)
        out["emissive_intensity"] = peak if peak > 0.0 else 1.0
    else:
        out["enable_emission"] = False
    ior = p.get("ior")
    if ior is not None and ior["kind"] != 6:
        out["ior_constant"] = _f(ior["v"])
    for key, aname, want in (("diffuseColor", "diffuse_texture", ("rgb",)),
                             ("normal", "normalmap_texture", ("rgb",)),
                             ("roughness", "reflectionroughness_texture", ("r",)),
                             ("metallic", "metallic_texture", ("r",)),
                             ("emissiveColor", "emissive_mask_texture", ("rgb",))):
        t = tex(key, want)
        if t:
            out[aname] = t
    # opacity: the colour picture's alpha, a cut-out, or blended
    op = p.get("opacity")
    threshold = _f(const("opacityThreshold", (0.0,)))
    textured = op is not None and op["kind"] == 6
    if textured:
        same = (p.get("diffuseColor") or {}).get("path") == op["path"] and op["output"] == "a"
        if same:
            out["enable_opacity"] = True
        else:
            report.append("material %s: its opacity comes from a picture of its own: left at %.3g" % (name, opacity))
    if threshold > 0.0 and (textured or opacity < 1.0):
        out["blend_enabled"] = False
        out["alpha_test_type"] = 4
        out["alpha_test_reference_value"] = min(threshold, 1.0)
    elif (textured and out.get("enable_opacity")) or opacity < 1.0:
        out["blend_enabled"] = True
        out["blend_type"] = 0
    return out


def build_usd_material(m, report, images):
    """an RTX Remix material for a file's material: from its AperturePBR
    when it has one, else from its preview surface, else plain"""
    if m["aperture"]:
        inputs = aperture_inputs(m)
        mdl, sub = m["mdl"], m["sub_identifier"]
    elif m["preview"]:
        inputs = preview_inputs(m, report)
        mdl, sub = "", ""
    else:
        inputs, mdl, sub = {}, "", ""
    mat = build_material({"name": m["name"], "hash": "", "mdl": mdl, "sub_identifier": sub, "inputs": inputs},
                         report, images)
    _drop(mat, CAPTURE_MARKS)
    if mat.node_tree:
        for n in mat.node_tree.nodes:
            tex = getattr(n, "texture", None)
            if tex is not None:
                _drop(tex, ("bge_remix_capture_dds", "bge_remix_capture_input"))
                if getattr(tex, "image", None) is not None:
                    _drop(tex.image, ("bge_remix_capture_dds",))
    return mat


def _mesh_data(m):
    """a read mesh as build_mesh takes it"""
    return {"name": m["name"], "hash": "", "points": m["points"], "face_sizes": m["face_sizes"],
            "corners": m["corners_data"], "normals": m["normals"], "uvs": m["uvs"], "colors": m["colors"],
            "double_sided": m["double_sided"]}


def import_usd(context, path, report):
    """the USD file at path as a new scene; returns it"""
    import _bge_remix
    from mathutils import Matrix
    LAST.clear()
    data = _bge_remix.usd_read(path)
    report.extend(l for l in data["report"].split("\n") if l.strip())
    K, Kinv = capture_space(data["meters_per_unit"], data["z_up"])
    s = K.to_scale()[0]
    Sinv = Matrix.Scale(1.0 / s, 4)
    scene = bpy.data.scenes.new(os.path.splitext(os.path.basename(path))[0])
    scene.render.engine = context.scene.render.engine
    scene["bge_remix_pipeline"] = 1  # RTX Remix materials (P9)
    scene["bge_remix_usd"] = {"path": os.path.abspath(path), "meters_per_unit": float(data["meters_per_unit"]),
                              "z_up": int(bool(data["z_up"]))}
    objects = ut.objects_from_read(data)
    nodes = data["nodes"]
    # how many objects use each mesh (shared: materials on the objects)
    users = {}
    for o in objects:
        if o["kind"] == "MESH":
            users[nodes[o["data_node"]]["index"]] = users.get(nodes[o["data_node"]]["index"], 0) + 1
    meshes, materials, images = {}, {}, {}

    def material(i):
        if i is None or i < 0:
            return None
        if i not in materials:
            materials[i] = build_usd_material(data["materials"][i], report, images)
        return materials[i]

    def mesh(i):
        if i in meshes:
            return meshes[i]
        import numpy as np
        m = data["meshes"][i]
        me = build_mesh(_mesh_data(m), K)
        _drop(me, (HASH,))
        subsets = m["subsets"]
        slots = 0
        if subsets:
            covered = set(f for sub in subsets for f in sub["faces"])
            first = 0 if len(covered) == m["faces"] else 1
            index = np.zeros(m["faces"], dtype=np.int32)
            for k, sub in enumerate(subsets):
                index[sub["faces"]] = k + first
            me.polygons.foreach_set("material_index", index)
            slots = len(subsets) + first
        meshes[i] = (me, slots, subsets and len(set(f for sub in subsets for f in sub["faces"])) != m["faces"])
        return meshes[i]

    made, world = [], []
    camera = None
    counts = {"objects": 0, "meshes": 0, "materials": 0, "lamps": 0, "cameras": 0, "empties": 0}
    for o in objects:
        node = nodes[o["data_node"]]
        M = usd_matrix(node["matrix"])
        ob = None
        if o["kind"] == "MESH":
            me, slots, whole_slot = mesh(node["index"])
            ob = bpy.data.objects.new(o["name"], me)
            w = K * M * Kinv
            mats = []
            if slots:
                mats = ([material(node["material"])] if whole_slot else []) + \
                    [material(i) for i in node["subset_materials"]]
            elif node["material"] >= 0:
                mats = [material(node["material"])]
            shared = users.get(node["index"], 1) > 1
            while len(me.materials) < len(mats):
                me.materials.append(None)
            for k, ma in enumerate(mats):
                if shared:
                    ob.material_slots[k].link = 'OBJECT'
                    ob.material_slots[k].material = ma
                elif ma is not None:
                    me.materials[k] = ma
        elif o["kind"] == "LIGHT":
            la = build_lamp(data["lights"][node["index"]], K, report)
            if la is not None:
                _drop(la, (HASH,))
                ob = bpy.data.objects.new(o["name"], la)
                counts["lamps"] += 1
            w = rigid(K * M * Sinv)
        elif o["kind"] == "CAMERA":
            c = data["cameras"][node["index"]]
            cd = bpy.data.cameras.new(o["data_name"])
            cd.sensor_fit = 'HORIZONTAL'
            if c["perspective"]:
                if c["horizontal_aperture"] > 0.0 and c["focal_length"] > 0.0:
                    cd.sensor_width = c["horizontal_aperture"]
                    cd.lens = c["focal_length"]
            else:
                cd.type = 'ORTHO'
                cd.ortho_scale = max(c["horizontal_aperture"] / 10.0 * s, 1e-4)
            cd.clip_start = max(c["near"] * s, 0.0001)
            cd.clip_end = max(c["far"] * s, cd.clip_start * 2.0)
            ob = bpy.data.objects.new(o["name"], cd)
            if camera is None:
                camera = ob
            counts["cameras"] += 1
            w = rigid(K * M * Sinv)
        else:
            w = K * M * Kinv
        if ob is None:
            ob = bpy.data.objects.new(o["name"], None)
            counts["empties"] += 1
        scene.objects.link(ob)
        if o["parent"] >= 0:
            ob.parent = made[o["parent"]]
            ob.matrix_parent_inverse = Matrix.Identity(4)
            try:
                ob.matrix_basis = world[o["parent"]].inverted() * w
            except ValueError:
                ob.matrix_world = w
        else:
            ob.matrix_basis = w
        if not o["visible"]:
            ob.hide = ob.hide_render = True
        made.append(ob)
        world.append(w)
    if camera is not None:
        scene.camera = camera
    counts["objects"] = len(made)
    counts["meshes"] = len(meshes)
    counts["materials"] = len(materials)
    scene["bge_remix_usd_counts"] = counts
    scene.update()
    LAST.update({"scene": scene.name, "report": report, "counts": counts})
    return scene


class IMPORT_SCENE_OT_bge_remix_usd(Operator, ImportHelper):
    """Import a Universal Scene Description file from any tool as a new scene: its meshes, hierarchy, """ \
        """materials (as RTX Remix materials), lights and cameras, in metres and Z up"""
    bl_idname = "import_scene.bge_remix_usd"
    bl_label = "Import Universal Scene Description"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".usd"
    filter_glob = StringProperty(default="*.usd;*.usda;*.usdc", options={'HIDDEN'})

    def execute(self, context):
        report = []
        try:
            scene = import_usd(context, self.filepath, report)
        except RuntimeError as e:
            self.report({'ERROR'}, "Universal Scene Description: %s" % e)
            print("BGE-Remix USD import: error: %s" % e)
            return {'CANCELLED'}
        except ImportError:
            self.report({'ERROR'}, "Universal Scene Description: this Blender has no RTX Remix bridge")
            return {'CANCELLED'}
        if context.screen is not None:
            context.screen.scene = scene
        else:
            for win in context.window_manager.windows:
                win.screen.scene = scene
        for line in report:
            self.report({'WARNING'}, line)
            print("BGE-Remix USD import: " + line)
        c = LAST["counts"]
        self.report({'INFO'}, "Universal Scene Description: %d objects, %d meshes, %d materials, %d lamps, "
                              "%d cameras%s" % (c["objects"], c["meshes"], c["materials"], c["lamps"], c["cameras"],
                                                "; %d note(s), see the Info log" % len(report) if report else ""))
        return {'FINISHED'}


class EXPORT_SCENE_OT_bge_remix_usd(Operator, ExportHelper):
    """Export the scene (or the selected objects) as Universal Scene Description for other tools: """ \
        """meshes, hierarchy, materials (preview surfaces; RTX Remix ones also as AperturePBR), lamps, cameras"""
    bl_idname = "export_scene.bge_remix_usd"
    bl_label = "Export Universal Scene Description"
    bl_options = {'REGISTER'}

    filename_ext = ".usda"
    filter_glob = StringProperty(default="*.usd;*.usda;*.usdc", options={'HIDDEN'})
    file_format = EnumProperty(name="Format", default='USDA',
                               items=(('USDA', "Text (.usda)", "USD's text form"),
                                      ('USDC', "Binary (.usdc)", "USD's binary form (smaller, faster to read)"),
                                      ('USD', "Binary (.usd)", "USD's binary form, as .usd")))
    use_selection = BoolProperty(name="Selected Objects Only", default=False,
                                 description="Export only the selected objects")

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def check(self, context):
        path = self.filepath
        for e in (".usda", ".usdc", ".usd"):
            if path.lower().endswith(e):
                path = path[:-len(e)]
                break
        new = path + EXTENSIONS[self.file_format]
        changed = new != self.filepath
        self.filepath = new
        return changed

    def execute(self, context):
        report = []
        path = bpy.path.abspath(self.filepath)
        if not any(path.lower().endswith(e) for e in EXTENSIONS.values()):
            path += EXTENSIONS[self.file_format]
        try:
            export_usd(context.scene, path, report, self.use_selection)
        except (UsdError, RuntimeError, OSError) as e:
            self.report({'ERROR'}, "Universal Scene Description: %s" % e)
            print("BGE-Remix USD export: error: %s" % e)
            LAST["error"] = str(e)
            return {'CANCELLED'}
        except ImportError:
            self.report({'ERROR'}, "Universal Scene Description: this Blender has no RTX Remix bridge")
            return {'CANCELLED'}
        for line in report:
            self.report({'WARNING'}, line)
            print("BGE-Remix USD export: " + line)
        c = LAST["counts"]
        self.report({'INFO'}, "Universal Scene Description: %s: %d objects, %d meshes, %d materials, %d lamps, "
                              "%d cameras, %d pictures%s" % (path, c["objects"], c["meshes"], c["materials"],
                                                             c["lamps"], c["cameras"], c["pictures"],
                                                             "; %d note(s), see the Info log" % len(report)
                                                             if report else ""))
        print("BGE-Remix USD export: wrote " + path)
        return {'FINISHED'}


classes = (
    IMPORT_SCENE_OT_bge_remix_usd,
    EXPORT_SCENE_OT_bge_remix_usd,
)
