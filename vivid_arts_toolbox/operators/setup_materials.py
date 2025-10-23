# vivid_arts_toolbox/operators/setup_materials.py
import os
import bpy
from bpy.types import Operator

from ..utils import project_dirs, resource_or_legacy

BAKE_EXTS = (".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp")


def _find_optimized_object():
    obj = bpy.context.active_object
    if obj and obj.type == 'MESH' and obj.name.endswith("_Optimized"):
        return obj
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.endswith("_Optimized"):
            return o
    return None


def _gather_textures_for_object(bake_dir: str, object_name: str):
    """Return mapping: {udim: {bakername: path, ...}, ...} for files named
    (objectname)_(udim)_(bakername).ext inside bake_dir.
    """
    out = {}
    if not os.path.isdir(bake_dir):
        return out
    prefix = (object_name + "_").lower()

    def ensure(u):
        if u not in out:
            out[u] = {}

    for fn in os.listdir(bake_dir):
        full = os.path.join(bake_dir, fn)
        if not os.path.isfile(full) or not fn.lower().endswith(BAKE_EXTS):
            continue
        name_no_ext = os.path.splitext(fn)[0]
        low = name_no_ext.lower()
        if not low.startswith(prefix):
            continue
        parts = name_no_ext.split("_")
        if len(parts) < 3:
            continue
        # parts: [objectname tokens ...] we expect the last two tokens to be [udim, baker]
        # Since object name can contain underscores, find udim token from the end
        udim_token = parts[-2]
        baker = parts[-1]
        if not (udim_token.isdigit() and len(udim_token) == 4 and int(udim_token) >= 1001):
            # Not a UDIM-conforming name
            continue
        ensure(udim_token)
        out[udim_token][baker] = full
    return out


def _append_or_get_template(template_name: str = "Delighter"):
    """Append the material named template_name from resources/Delighter.blend if needed."""
    mat = bpy.data.materials.get(template_name)
    if mat:
        return mat
    path = str(resource_or_legacy("Delighter.blend"))
    if not os.path.isfile(path):
        return None
    try:
        with bpy.data.libraries.load(path, link=False) as (data_from, data_to):
            if template_name in (data_from.materials or []):
                data_to.materials = [template_name]
        return bpy.data.materials.get(template_name)
    except Exception:
        return None


def _clone_material_from_template(dst_name: str, template: bpy.types.Material) -> bpy.types.Material:
    mat = bpy.data.materials.get(dst_name)
    if mat is None:
        mat = bpy.data.materials.new(dst_name)
    mat.use_nodes = True
    try:
        dst_nt = mat.node_tree
        src_nt = template.node_tree
        # clear
        for n in list(dst_nt.nodes):
            dst_nt.nodes.remove(n)
        # copy nodes
        node_map = {}
        for n in src_nt.nodes:
            nn = dst_nt.nodes.new(type=n.bl_idname)
            try:
                nn.name = n.name
            except Exception:
                pass
            nn.label = getattr(n, 'label', nn.label)
            nn.location = getattr(n, 'location', (0, 0))
            nn.width = getattr(n, 'width', nn.width)
            nn.height = getattr(n, 'height', nn.height)
            nn.hide = getattr(n, 'hide', False)
            try:
                if hasattr(nn, 'node_tree') and hasattr(n, 'node_tree'):
                    nn.node_tree = n.node_tree
            except Exception:
                pass
            node_map[n] = nn
        # copy links
        def _sock_idx(seq, sock):
            try:
                return seq[:].index(sock)
            except ValueError:
                try:
                    names = [s.name for s in seq]
                    return names.index(getattr(sock, 'name', ''))
                except Exception:
                    return -1
        for lk in src_nt.links:
            a = node_map.get(lk.from_node)
            b = node_map.get(lk.to_node)
            if not (a and b):
                continue
            ai = _sock_idx(lk.from_node.outputs, lk.from_socket)
            bi = _sock_idx(lk.to_node.inputs, lk.to_socket)
            if ai >= 0 and bi >= 0:
                dst_nt.links.new(a.outputs[ai], b.inputs[bi])
    except Exception:
        pass
    try:
        mat.use_fake_user = True
    except Exception:
        pass
    return mat


_COLORSPACE = {
    'BaseColorTransfer': 'sRGB',
}

def _set_images_by_baker(material: bpy.types.Material, baker_to_path: dict):
    nt = material.node_tree
    if not nt:
        return
    for baker, path in baker_to_path.items():
        node = nt.nodes.get(baker)
        if not (node and hasattr(node, 'image')):
            # Template doesn't have this node; skip
            continue
        node.image = None
        if not (path and os.path.isfile(path)):
            continue
        try:
            img = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
            try:
                if getattr(img, 'packed_file', None):
                    img.unpack(method='USE_ORIGINAL')
            except Exception:
                pass
            node.image = img
            cs = _COLORSPACE.get(baker, 'Non-Color')
            try:
                node.image.colorspace_settings.name = cs
            except Exception:
                pass
        except Exception:
            pass
    # Fallback: if AOWide node exists but no AOWide texture, reuse AO texture
    try:
        aowide_node = nt.nodes.get('AOWide')
        if aowide_node and hasattr(aowide_node, 'image'):
            has_aowide = 'AOWide' in baker_to_path and os.path.isfile(baker_to_path.get('AOWide', ''))
            ao_path = baker_to_path.get('AO')
            if (not has_aowide) and ao_path and os.path.isfile(ao_path):
                img = bpy.data.images.load(bpy.path.abspath(ao_path), check_existing=True)
                try:
                    if getattr(img, 'packed_file', None):
                        img.unpack(method='USE_ORIGINAL')
                except Exception:
                    pass
                aowide_node.image = img
                try:
                    aowide_node.image.colorspace_settings.name = _COLORSPACE.get('AOWide', 'Non-Color')
                except Exception:
                    pass
    except Exception:
        pass


class VIVID_OT_setup_materials(Operator):
    bl_idname = "vivid.setup_materials"
    bl_label = "Setup Materials"
    bl_description = "Create or refresh Delighter-based materials from //BakeTextures using UDIM-aware naming"

    def execute(self, context):
        obj = _find_optimized_object()
        if not obj:
            self.report({'ERROR'}, "No *_Optimized object found")
            return {'CANCELLED'}
        _, _, bake_tex = project_dirs()
        if not os.path.isdir(bake_tex):
            self.report({'ERROR'}, f"Missing BakeTextures folder: {bake_tex}")
            return {'CANCELLED'}
        # Gather textures for this object's name, preferring Part1 subfolder
        part1_dir = os.path.join(bake_tex, "Part1")
        if os.path.isdir(part1_dir):
            tex_map = _gather_textures_for_object(part1_dir, obj.name)
        else:
            tex_map = _gather_textures_for_object(bake_tex, obj.name)
        if not tex_map:
            # Fallback: try root even if Part1 exists but empty
            if os.path.isdir(part1_dir):
                tex_map = _gather_textures_for_object(bake_tex, obj.name)
        if not tex_map:
            self.report({'WARNING'}, "No baked textures found that match the object name (checked Part1 and root)")
        # Determine if current materials are conformant
        desired_names = {f"{obj.name}_{u}" for u in tex_map.keys()} or {f"{obj.name}_1001"}
        existing = [m.name for m in obj.data.materials if m]
        conformant = bool(existing) and all(any(n == dn for dn in desired_names) for n in existing)

        template = _append_or_get_template("Delighter")
        if not template:
            self.report({'ERROR'}, "Missing Delighter.blend or Delighter material in resources")
            return {'CANCELLED'}

        # Ensure slot list
        if not conformant:
            # Reset materials to desired set
            # Clear slots
            obj.data.materials.clear()
            for udim in sorted(tex_map.keys() or ['1001']):
                mat_name = f"{obj.name}_{udim}"
                mat = _clone_material_from_template(mat_name, template)
                obj.data.materials.append(mat)
        # Refresh textures on all target materials
        for i, m in enumerate(obj.data.materials):
            if not m:
                continue
            # Identify this slot's UDIM from its name
            udim = None
            try:
                parts = m.name.split('_')
                if len(parts) >= 2 and parts[-1].isdigit():
                    udim = parts[-1]
            except Exception:
                pass
            if not udim:
                # Default to 1001
                udim = '1001'
            _set_images_by_baker(m, tex_map.get(udim, {}))

        # Delegate face assignments to UDIM operator
        try:
            bpy.ops.vivid.udim_material_assignment('INVOKE_DEFAULT')
        except Exception:
            try:
                bpy.ops.vivid.udim_material_assignment()
            except Exception:
                pass

        # Also build reference materials for Part# subfolders, but do not assign them to the object
        try:
            for entry in sorted(os.listdir(bake_tex)):
                part_dir = os.path.join(bake_tex, entry)
                if not os.path.isdir(part_dir):
                    continue
                # Accept folder names like Part1, Part2, Part10 ...
                if not (entry.startswith('Part') and entry[4:].isdigit()):
                    continue
                part_token = entry  # e.g., Part1
                part_tex_map = _gather_textures_for_object(part_dir, obj.name)
                if not part_tex_map:
                    continue
                # For each UDIM, create/update a material named "<object>_<Part#>_<UDIM>"
                template = _append_or_get_template("Delighter")
                if not template:
                    continue
                for udim in sorted(part_tex_map.keys() or ['1001']):
                    mat_name = f"{obj.name}_{part_token}_{udim}"
                    mat = _clone_material_from_template(mat_name, template)
                    _set_images_by_baker(mat, part_tex_map.get(udim, {}))
                    try:
                        mat.use_fake_user = True
                    except Exception:
                        pass
        except Exception:
            pass

        self.report({'INFO'}, "Materials set up/refreshed from BakeTextures")
        # Set material preview render pass to Emission in 3D Viewports (best-effort)
        try:
            # Iterate all windows to robustly reach active screens
            for win in bpy.context.window_manager.windows:
                screen = win.screen
                for area in screen.areas:
                    if area.type != 'VIEW_3D':
                        continue
                    for space in area.spaces:
                        if getattr(space, 'type', '') != 'VIEW_3D':
                            continue
                        # Ensure we're in material/renderer shading; then set pass
                        try:
                            space.shading.type = 'MATERIAL'
                        except Exception:
                            pass
                        try:
                            space.shading.render_pass = 'EMIT'
                        except Exception:
                            pass
        except Exception:
            pass
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_setup_materials)

def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_setup_materials)
    except Exception:
        pass
