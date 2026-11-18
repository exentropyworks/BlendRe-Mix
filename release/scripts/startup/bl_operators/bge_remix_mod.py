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

"""BGE-Remix P12 round 3 (A3): File > Export > RTX Remix Mod.

The changes made to a scene imported from an RTX Remix capture
(bge_remix_capture.py) go out as a Remix mod: a folder holding mod.usda and
its textures, for the game's rtx-remix/mods. Only what changed goes in: the
import left a fingerprint on each mesh, material, lamp and place, and this
compares them.

- a mesh edited: it replaces that mesh wherever the game draws it (the
  game's own switched off); each place keeps its own material;
- objects and lamps parented to an imported object: added to that object's
  mesh, wherever the game draws it, placed relative to it;
- a material changed: it replaces that material (Remix's AperturePBR, its
  textures as DDS: the capture's own copied when untouched, the others
  encoded with the bridge's encoder);
- a lamp changed: it replaces that light.

What a mod cannot carry is reported, not dropped silently: a place moved,
deleted, copied, given another mesh or material, physics, logic and game
properties, modifiers, new objects not parented to an imported one. A mod
changes how things look, not where the game puts them.

Everything goes back to the capture's units and up axis (K^-1, the reverse
of the import). The mod is read back with the bridge's OpenUSD before the
export reports success. The USD text is written by bge_remix_mod_text.py.
"""

import json
import math
import os
import shutil
import tempfile

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from . import bge_remix_mod_text as mt
from .bge_remix_capture import FP, HASH, NODE_TEXTURES, capture_space

# what the last export did (the tests read it): folder, report, counts
LAST = {}

# the textures each kind of AperturePBR has, and how they are encoded
OPAQUE_TEXTURES = ("diffuse_texture", "normalmap_texture", "reflectionroughness_texture", "metallic_texture",
                   "emissive_mask_texture", "height_texture", "subsurface_transmittance_texture")
TRANSLUCENT_TEXTURES = ("normalmap_texture", "transmittance_texture", "emissive_mask_texture")
TEXTURE_KIND = {"diffuse_texture": 'COLOR', "normalmap_texture": 'NORMAL', "reflectionroughness_texture": 'SCALAR',
                "metallic_texture": 'SCALAR', "emissive_mask_texture": 'COLOR', "height_texture": 'SCALAR',
                "transmittance_texture": 'COLOR', "subsurface_transmittance_texture": 'COLOR'}
# the blending options of a capture material, written back as they were
# when the node's blending is the one they gave it
BLEND_OPTIONS = ("blend_enabled", "blend_type", "alpha_test_type", "alpha_test_reference_value",
                 "use_legacy_alpha_state")
MIN_LIGHT_RADIUS = 0.02  # remix_light.cc


class ModError(Exception):
    pass


def srgb(c):
    c = min(max(float(c), 0.0), 1.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def srgb3(v):
    return tuple(srgb(c) for c in tuple(v)[:3])


def clamp(v, lo, hi):
    return min(max(float(v), lo), hi)


def usd_rows(m):
    """a Blender Matrix (column vectors) as USD's 16 numbers (rows)"""
    return [float(m[c][r]) for r in range(4) for c in range(4)]


def rigid(m):
    """the place and turn of a matrix, without its scale"""
    from mathutils import Matrix
    loc, rot, _scale = m.decompose()
    return Matrix.Translation(loc) * rot.to_matrix().to_4x4()


def default_folder(scene):
    """the game's rtx-remix/mods/<scene name>, from the capture's path
    (.../rtx-remix/captures/capture_x.usda); else mods/<scene name> beside
    the capture"""
    cap = scene.get("bge_remix_capture") or {}
    path = cap.get("path", "") if hasattr(cap, "get") else ""
    here = os.path.dirname(path) if path else bpy.path.abspath("//")
    name = bpy.path.clean_name(scene.name) or "mod"
    if os.path.basename(here.rstrip("\\/")).lower() == "captures":
        return os.path.join(os.path.dirname(here.rstrip("\\/")), "mods", name)
    return os.path.join(here, "mods", name)


class Export:
    """one export: the scene's changes gathered, then written"""

    def __init__(self, scene, folder, report):
        cap = scene.get("bge_remix_capture")
        if not cap:
            raise ModError("this scene did not come from an RTX Remix capture (File > Import > RTX Remix "
                           "Capture makes one)")
        self.cap = cap.to_dict() if hasattr(cap, "to_dict") else dict(cap)
        self.scene = scene
        self.folder = folder
        self.report = report
        self.K, self.Kinv = capture_space(self.cap.get("meters_per_unit", 1.0), self.cap.get("z_up", 1))
        self.s = self.K.to_scale()[0]
        import numpy as np
        self.k3inv = np.array([[self.Kinv[r][c] for c in range(3)] for r in range(3)], dtype=np.float64)
        self.mod = {"meters_per_unit": float(self.cap.get("meters_per_unit", 1.0)),
                    "z_up": int(self.cap.get("z_up", 1)), "looks": {}, "local_looks": {}, "meshes": {},
                    "lights": {}}
        self.textures = {}       # (image, input, output, flip) -> relative path
        self.local_names = set()
        self.local_of = {}       # material name -> its BGE_Remix_Looks path
        self.counts = {"meshes": 0, "added": 0, "materials": 0, "lights": 0, "textures": 0, "copied": 0}

    def note(self, line):
        if line not in self.report:
            self.report.append(line)

    # -- what changed -------------------------------------------------------

    def gather(self):
        """what changed and what a mod cannot carry: the engine's capture
        check (remix_capture.cc), the one the Remix View shows"""
        import _bge_remix
        check = _bge_remix.capture_check(self.scene.name)
        if check is None:
            raise ModError("this scene did not come from an RTX Remix capture (File > Import > RTX Remix "
                           "Capture makes one)")
        for _code, _ob, text in check["notes"]:
            self.note(text)
        objects, meshes, materials = bpy.data.objects, bpy.data.meshes, bpy.data.materials
        self.meshes = {h: meshes[name] for h, name in check["meshes"]}
        self.children = {h: (objects[place], [objects[n] for n in names])
                         for h, place, names in check["groups"]}
        self.lamps = [objects[n] for n in check["lamps"]]
        self.changed_materials = [materials[n] for n in check["materials"]]
        self.objects = check["objects"]
        return bool(self.meshes or self.children or self.lamps or self.changed_materials)

    # -- writing --------------------------------------------------------------

    def write(self):
        os.makedirs(os.path.join(self.folder, "textures"), exist_ok=True)
        mod = self.mod
        for mat in self.changed_materials:
            d = self.material(mat)
            if d is not None:
                mod["looks"]["mat_" + mat[HASH]] = d
                self.counts["materials"] += 1
        for h, me in sorted(self.meshes.items()):
            data = self.mesh(me, None)
            if data is None:
                self.note("mesh %s has no faces: left out" % me.name)
                continue
            used = set(p.material_index for p in me.polygons)
            if len(used) > 1:
                self.note("mesh %s: its faces have %d materials; in the mod each place shows its own material on "
                          "all of them" % (me.name, len(used)))
            mod["meshes"]["mesh_" + h] = {"preserve": 0, "meshes": {"replacement": data}, "lights": {}}
            self.counts["meshes"] += 1
        for mh, (place, added) in sorted(self.children.items()):
            # (the check said which go in; the others are in its notes)
            added = [c for c in added if self.objects.get(c.name, ("NONE",))[0] == "ADDED"]
            if not added:
                continue
            entry = mod["meshes"].setdefault("mesh_" + mh, {"preserve": 1, "meshes": {}, "lights": {}})
            used = {"replacement", "mesh"}
            Pinv = place.matrix_world.inverted()
            for c in added:
                name = mt.ident(c.name, used)
                if c.type == 'LAMP':
                    m = self.Kinv * Pinv * rigid(c.matrix_world) * self.K
                    light = self.light(c, m, under_mesh=True)
                    if light is not None:
                        entry["lights"][name] = light
                        self.counts["added"] += 1
                elif c.type in ('MESH', 'CURVE', 'SURFACE', 'FONT', 'META'):
                    data = self.added_mesh(c, self.Kinv * Pinv * c.matrix_world * self.K)
                    if data is not None:
                        entry["meshes"][name] = data
                        self.counts["added"] += 1
        for ob in self.lamps:
            light = self.light(ob, self.Kinv * rigid(ob.matrix_world) * self.K, under_mesh=False)
            if light is not None:
                mod["lights"]["light_" + ob[HASH]] = light
                self.counts["lights"] += 1
        path = os.path.join(self.folder, "mod.usda")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(mt.mod_text(mod))
        self.read_back(path)
        return path

    def read_back(self, path):
        """the mod opened with the bridge's OpenUSD and checked against what
        was written"""
        import _bge_remix
        tmp = tempfile.mkdtemp(prefix="bge_remix_mod_")
        try:
            dump_path = os.path.join(tmp, "mod.json")
            ok, err = _bge_remix.usd_dump(path, dump_path)
            if not ok:
                raise ModError("the mod written (%s) does not open with OpenUSD: %s" % (path, err))
            with open(dump_path, encoding="utf-8") as f:
                dump = json.load(f)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        bad = mt.check_dump(self.mod, dump)
        if bad:
            raise ModError("the mod written (%s) does not read back as written: %s" % (path, "; ".join(bad)))
        self.dump = dump

    # -- meshes ---------------------------------------------------------------

    def mesh(self, me, matrix):
        """a mesh's faces in the capture's units (points K^-1), its normals,
        UVs and colours per corner; None without faces"""
        import numpy as np
        nv, nl, npoly = len(me.vertices), len(me.loops), len(me.polygons)
        if npoly == 0 or nv == 0:
            return None
        co = np.zeros(nv * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        pts = co.reshape(-1, 3).astype(np.float64).dot(self.k3inv.T)
        vidx = np.zeros(nl, dtype=np.int32)
        me.loops.foreach_get("vertex_index", vidx)
        starts = np.zeros(npoly, dtype=np.int32)
        totals = np.zeros(npoly, dtype=np.int32)
        me.polygons.foreach_get("loop_start", starts)
        me.polygons.foreach_get("loop_total", totals)
        # the corners face by face
        offsets = np.cumsum(totals) - totals
        corner = np.arange(int(totals.sum())) - np.repeat(offsets, totals) + np.repeat(starts, totals)
        data = {"points": [tuple(p) for p in pts.tolist()], "counts": totals.tolist(),
                "indices": vidx[corner].tolist(), "double_sided": bool(me.show_double_sided), "matrix": matrix}
        me.calc_normals_split()
        nrm = np.zeros(nl * 3, dtype=np.float32)
        me.loops.foreach_get("normal", nrm)
        me.free_normals_split()
        n = nrm.reshape(-1, 3).astype(np.float64)[corner].dot(self.k3inv.T)
        length = np.sqrt((n * n).sum(axis=1))
        length[length < 1e-12] = 1.0
        data["normals"] = [tuple(v) for v in (n / length[:, None]).tolist()]
        uv = me.uv_layers.active
        if uv is not None:
            a = np.zeros(nl * 2, dtype=np.float32)
            uv.data.foreach_get("uv", a)
            data["uvs"] = [tuple(v) for v in a.reshape(-1, 2)[corner].tolist()]
        col = me.vertex_colors.get("Col") or me.vertex_colors.active
        if col is not None:
            a = np.zeros(nl * 3, dtype=np.float32)
            col.data.foreach_get("color", a)
            data["colors"] = [tuple(v) for v in a.reshape(-1, 3)[corner].tolist()]
            alpha = me.vertex_colors.get("Alpha")
            if alpha is not None and alpha != col:
                b = np.zeros(nl * 3, dtype=np.float32)
                alpha.data.foreach_get("color", b)
                data["opacities"] = b.reshape(-1, 3)[corner][:, 0].tolist()
        return data

    def added_mesh(self, ob, matrix):
        """an added object as a Mesh (its modifiers applied), bound to its
        material(s)"""
        try:
            me = ob.to_mesh(self.scene, True, 'RENDER')
        except RuntimeError:
            me = None
        if me is None:
            self.note("%s: no mesh could be made of it, left out" % ob.name)
            return None
        try:
            data = self.mesh(me, usd_rows(matrix))
            if data is None:
                self.note("%s has no faces: left out" % ob.name)
                return None
            mats = [s.material for s in ob.material_slots]
            index = [p.material_index for p in me.polygons]
            used = sorted(set(i for i in index if i < len(mats) and mats[i] is not None))
            if len(used) == 1 and all(i == used[0] for i in index):
                data["binding"] = self.binding(mats[used[0]])
            elif used:
                subsets = []
                for i in used:
                    faces = [f for f, j in enumerate(index) if j == i]
                    subsets.append({"name": "material_%d" % i, "faces": faces, "binding": self.binding(mats[i])})
                data["subsets"] = subsets
            if not used:
                self.note("%s has no material: Remix shows it with its default one" % ob.name)
            return data
        finally:
            bpy.data.meshes.remove(me)

    def binding(self, mat):
        """the material path an added mesh is bound to: the capture's
        material when the mod replaces it, else a copy of the material in
        BGE_Remix_Looks"""
        if mat is None:
            return None
        h = mat.get(HASH)
        if h and "mat_" + h in self.mod["looks"]:
            return "/RootNode/Looks/mat_" + h
        if mat.name in self.local_of:
            return self.local_of[mat.name]
        d = self.material(mat)
        if d is None:
            self.local_of[mat.name] = None
            return None
        name = mt.ident(mat.name, self.local_names)
        self.mod["local_looks"][name] = d
        self.local_of[mat.name] = "/RootNode/BGE_Remix_Looks/" + name
        self.counts["materials"] += 1
        return self.local_of[mat.name]

    # -- materials ------------------------------------------------------------

    def material(self, mat):
        """an RTX Remix material as AperturePBR (as the import read it,
        reversed: the colours back to sRGB); None for another kind"""
        from .bge_remix_material import remix_node
        node = remix_node(mat) if mat.use_nodes else None
        if node is None:
            self.note("material %s is not an RTX Remix material (Material tab > RTX Remix): left out" % mat.name)
            return None
        translucent = node.remix_type == 'TRANSLUCENT'
        had = set((mat.get("bge_remix_capture_had") or {}).keys())
        inputs = []
        names = set()

        def add(name, v):
            if name not in names:
                names.add(name)
                inputs.append((None, name, v))

        def col(sock):
            return tuple(node.inputs[sock].default_value)[:3]

        def val(sock):
            return float(node.inputs[sock].default_value)

        textures = self.material_textures(mat, node, translucent)
        if not translucent:
            add("diffuse_color_constant", srgb3(col("Albedo")))
            add("opacity_constant", clamp(val("Opacity"), 0.0, 1.0))
            add("reflection_roughness_constant", clamp(val("Roughness"), 0.0, 1.0))
            add("metallic_constant", clamp(val("Metallic"), 0.0, 1.0))
            if val("Anisotropy") != 0.0 or "anisotropy" in had:
                add("anisotropy", val("Anisotropy"))
            film = val("Thin Film")
            if film > 0.0 or had & {"enable_thin_film", "thin_film_thickness_constant"}:
                add("enable_thin_film", film > 0.0)
                if film > 0.0:
                    add("thin_film_thickness_constant", film)
            if "height_texture" in textures or had & {"displace_in", "displace_out"}:
                add("displace_in", max(val("Displace In"), 0.0))
                add("displace_out", max(val("Displace Out"), 0.0))
            sss = val("Subsurface") > 0.0
            if sss or had & {"subsurface_transmittance_color", "subsurface_radius"}:
                add("subsurface_transmittance_color", srgb3(col("Subsurface Color")))
                add("subsurface_radius", tuple(node.inputs["Subsurface Radius"].default_value)[:3])
                if sss and "subsurface_diffusion_profile" not in had:
                    add("subsurface_diffusion_profile", True)
            self.blending(mat, node, add)
        else:
            add("ior_constant", clamp(val("IOR"), 1.0, 3.0))
            add("transmittance_color", srgb3(col("Transmittance")))
            add("transmittance_measurement_distance", max(val("Transmittance Distance"), 0.001))
            add("thin_walled", bool(node.use_thin_walled))
            if node.use_thin_walled or "thin_wall_thickness" in had:
                add("thin_wall_thickness", max(val("Thin Wall Thickness"), 0.001))
        intensity = val("Emissive Intensity")
        if intensity > 0.0 or had & {"enable_emission", "emissive_intensity", "emissive_color_constant"}:
            add("enable_emission", intensity > 0.0)
            add("emissive_color_constant", srgb3(col("Emissive Color")))
            add("emissive_intensity", max(intensity, 0.0))
        # the capture's inputs the node has no place for, as they were
        kept = mat.get("bge_remix_capture_inputs")
        kept = kept.to_dict() if hasattr(kept, "to_dict") else (kept or {})
        for name in sorted(kept):
            kind = mt.INPUT_TYPES.get(name)
            v = kept[name]
            if kind is None or kind == "asset":
                if kind == "asset" and v:
                    self.note("material %s: its %s (%s) is not carried into the mod" % (mat.name, name, v))
                continue
            if isinstance(v, (list, tuple)):
                v = tuple(v)
            add(name, v)
        return {"mdl": "AperturePBR_Translucent" if translucent else "AperturePBR_Opacity", "inputs": inputs,
                "textures": textures}

    def blending(self, mat, node, add):
        """the node's Blend as Remix's options (as the bridge sends them);
        a capture material's own, when its blending is as it came in"""
        was = mat.get("bge_remix_capture_blend")
        if was is not None and was.get("blend") == node.blend and \
                abs(float(was.get("cutoff", -1.0)) - node.alpha_cutoff) < 1e-6:
            options = mat.get("bge_remix_capture_options")
            options = options.to_dict() if hasattr(options, "to_dict") else (options or {})
            for name in BLEND_OPTIONS:
                if name in options:
                    add(name, options[name])
            return
        add("use_legacy_alpha_state", False)
        if node.blend == 'ADDITIVE':
            add("blend_enabled", True)
            add("blend_type", mt.BLEND_EMISSIVE)
            add("alpha_test_type", mt.ALPHA_TEST_ALWAYS)
        elif node.blend == 'BLENDED':
            add("blend_enabled", True)
            add("blend_type", mt.BLEND_ALPHA)
            add("alpha_test_type", mt.ALPHA_TEST_ALWAYS)
        elif node.blend == 'ALPHA_TEST':
            add("blend_enabled", False)
            add("alpha_test_type", mt.ALPHA_TEST_GREATER)
            add("alpha_test_reference_value", int(round(clamp(node.alpha_cutoff, 0.0, 1.0) * 255.0)))
        else:
            add("blend_enabled", False)
            add("alpha_test_type", mt.ALPHA_TEST_ALWAYS)

    def material_textures(self, mat, node, translucent):
        """the images wired straight into the node, as DDS files in the
        mod's textures folder: {input: ./textures/<file>}"""
        allowed = TRANSLUCENT_TEXTURES if translucent else OPAQUE_TEXTURES
        out = {}
        for name, sock, _data in NODE_TEXTURES:
            inp = node.inputs.get(sock)
            if inp is None or not inp.is_linked:
                continue
            if name not in allowed:
                if not (translucent and name == "diffuse_texture"):
                    self.note("material %s: its %s image is left out (a %s material has none)" %
                              (mat.name, sock, "translucent" if translucent else "opaque"))
                continue
            link = inp.links[0]
            tn = link.from_node
            tex = getattr(tn, "texture", None)
            ima = getattr(tex, "image", None) if tex is not None and tex.type == 'IMAGE' else None
            if tn.bl_idname != "ShaderNodeTexture" or ima is None:
                self.note("material %s: its %s is not wired straight to an image: left out (only images go "
                          "into a mod)" % (mat.name, sock))
                continue
            rel = self.texture(mat, tex, ima, name, link.from_socket.name, bool(node.use_normal_directx))
            if rel:
                out[name] = rel
        return out

    def texture(self, mat, tex, ima, name, output, directx):
        key = (ima.name, name, output, directx)
        if key in self.textures:
            return self.textures[key]
        kind = TEXTURE_KIND[name]
        dds = tex.get("bge_remix_capture_dds")
        import _bge_remix
        untouched = (not ima.is_dirty) and ima.get(FP) is not None and \
            ima.get(FP) == _bge_remix.capture_fp("IMAGE", ima.name)
        rel = None
        if dds and untouched and tex.get("bge_remix_capture_input") == name and output == "Color" and \
                os.path.isfile(dds):
            # the capture's own file, as it was
            base = os.path.basename(dds)
            dst = os.path.join(self.folder, "textures", base)
            if os.path.abspath(dst) != os.path.abspath(dds):
                shutil.copyfile(dds, dst)
            rel = "./textures/" + base
            self.counts["copied"] += 1
        else:
            base = "%s_%s.dds" % (mt.ident(mat.name), name)
            if self.encode(ima, kind, output, directx, os.path.join(self.folder, "textures", base), mat.name, name):
                rel = "./textures/" + base
                self.counts["textures"] += 1
        self.textures[key] = rel
        return rel

    def encode(self, ima, kind, output, directx, path, mat_name, name):
        """an image as a DDS with the bridge's encoder (rows from the top:
        Remix reads a mod's UVs the other way up)"""
        import numpy as np
        import _bge_remix
        w, h = ima.size
        ch = ima.channels
        if w <= 0 or h <= 0 or ch <= 0:
            self.note("material %s: the image %s of its %s could not be read: left out" % (mat_name, ima.name, name))
            return False
        px = np.array(ima.pixels[:], dtype=np.float32).reshape(-1, ch)
        rgba = np.ones((px.shape[0], 4), dtype=np.float32)
        rgba[:, :min(ch, 4)] = px[:, :4]
        if ch < 3:
            rgba[:, 1] = rgba[:, 2] = rgba[:, 0]
        if kind == 'COLOR' and ima.is_float:
            # float images hold linear colour
            c = np.clip(rgba[:, :3], 0.0, 1.0)
            rgba[:, :3] = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)
        if kind == 'NORMAL' and directx:
            rgba[:, 1] = 1.0 - rgba[:, 1]
        if kind == 'SCALAR' and output == "Value":
            # the texture's Value: the image's alpha (as the bridge reads it)
            rgba[:, 0] = rgba[:, 3]
        data = (np.clip(rgba, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8).tobytes()
        ok, err = _bge_remix.dds_write(path, w, h, data, kind, True)
        if not ok:
            self.note("material %s: the image %s could not be written as DDS: %s" % (mat_name, ima.name, err))
        return ok

    # -- lights ---------------------------------------------------------------

    def light(self, ob, m, under_mesh):
        """a lamp as a Remix light (as remix_light.cc sends it), m its
        transform in the capture's space; None for one Remix has none like"""
        la = ob.data
        s = self.s
        energy = float(la.energy)
        color = tuple(abs(c) for c in la.color)
        dist = max(float(la.distance), 0.001)
        scale = ob.matrix_world.to_scale()
        physical = la.type in ('POINT', 'SPOT') and float(la.get("bge_physical", 0.0)) != 0.0
        attrs = [("color3f", "color", color)]
        shaped = False
        if la.type == 'SUN':
            if under_mesh:
                self.note("%s: a sun cannot hang under a mesh in a mod (Remix ignores it), left out" % ob.name)
                return None
            kind = "DistantLight"
            angle = float(la.get("bge_sun_angle", 0.0)) or 0.53
            attrs += [("float", "intensity", energy), ("float", "angle", angle)]
        elif la.type == 'AREA':
            kind = "RectLight"
            w = max(la.size * abs(scale[0]), 0.001)
            h = max((la.size if la.shape == 'SQUARE' else la.size_y) * abs(scale[1]), 0.001)
            attrs += [("float", "intensity", math.pi * energy * dist / (w * h)), ("float", "width", w / s),
                      ("float", "height", h / s)]
        elif la.type in ('POINT', 'SPOT'):
            r = max(float(la.shadow_soft_size), MIN_LIGHT_RADIUS)
            if physical and la.type == 'SPOT':
                kind = "DiskLight"
                intensity = energy * dist * dist / (r * r)
            else:
                kind = "SphereLight"
                intensity = energy * dist * dist / (r * r) if physical else energy * dist / (r * r)
            attrs += [("float", "intensity", intensity), ("float", "radius", r / s)]
            if la.type == 'SPOT':
                shaped = True
                half = la.spot_size * 0.5
                blend = clamp(la.spot_blend, 0.0, 1.0)
                attrs += [("float", "shaping:cone:angle", math.degrees(half)),
                          ("float", "shaping:cone:softness", (1.0 - math.cos(half)) * blend),
                          ("float", "shaping:focus", 0.0)]
                if la.use_halo and la.halo_intensity > 0.0:
                    attrs.append(("float", "volumetric_radiance_scale", 1.0 + la.halo_intensity))
        else:
            self.note("%s: a %s lamp has no Remix light like it, left out" % (ob.name, la.type.lower()))
            return None
        attrs += [("float", "exposure", 0.0), ("bool", "enableColorTemperature", False)]
        return {"type": kind, "attrs": attrs, "shaped": shaped, "matrix": usd_rows(m)}


def export_mod(scene, folder, report):
    """the scene's changes as a mod in folder; report gets what was left
    out. Returns the mod.usda path, or None when nothing changed (nothing is
    written then)."""
    LAST.clear()
    ex = Export(scene, folder, report)
    LAST.update({"folder": folder, "report": report, "path": None})
    if not ex.gather():
        LAST["counts"] = ex.counts
        return None
    path = ex.write()
    LAST.update({"path": path, "counts": ex.counts, "mod": ex.mod})
    return path


class EXPORT_SCENE_OT_bge_remix_mod(Operator):
    """Export what was changed in a scene imported from an RTX Remix capture as an RTX Remix mod """ \
        """(mod.usda and its textures, for the game's rtx-remix/mods)"""
    bl_idname = "export_scene.bge_remix_mod"
    bl_label = "Export RTX Remix Mod"
    bl_options = {'REGISTER'}

    directory = StringProperty(name="Mod Folder", subtype='DIR_PATH',
                               description="The mod's folder (the game's rtx-remix/mods/<name>)")
    filter_folder = BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def invoke(self, context, event):
        if not self.directory:
            self.directory = default_folder(context.scene)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        report = []
        folder = bpy.path.abspath(self.directory) if self.directory else default_folder(context.scene)
        try:
            path = export_mod(context.scene, folder, report)
        except ModError as e:
            self.report({'ERROR'}, "RTX Remix Mod: %s" % e)
            print("BGE-Remix mod export: error: %s" % e)
            return {'CANCELLED'}
        except ImportError:
            self.report({'ERROR'}, "RTX Remix Mod: this Blender has no RTX Remix bridge")
            return {'CANCELLED'}
        for line in report:
            self.report({'WARNING'}, line)
            print("BGE-Remix mod export: " + line)
        if path is None:
            self.report({'INFO'}, "RTX Remix Mod: nothing was changed since the import: no mod written")
            print("BGE-Remix mod export: nothing changed")
            return {'FINISHED'}
        c = LAST["counts"]
        self.report({'INFO'}, "RTX Remix Mod: %s: %d mesh(es) replaced, %d object(s) and lamp(s) added, "
                    "%d material(s), %d light(s), %d texture(s) encoded, %d copied%s" % (
                        path, c["meshes"], c["added"], c["materials"], c["lights"], c["textures"], c["copied"],
                        "; %d note(s), see the Info log" % len(report) if report else ""))
        print("BGE-Remix mod export: wrote " + path)
        return {'FINISHED'}


classes = (
    EXPORT_SCENE_OT_bge_remix_mod,
)
