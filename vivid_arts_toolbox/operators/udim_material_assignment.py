# vivid_arts_toolbox/operators/udim_material_assignment.py
import bpy
import math
from bpy.types import Operator
import os
from .setup_materials import _append_or_get_template, _clone_material_from_template, _gather_textures_for_object, _set_images_by_baker
from ..utils import project_dirs


def _find_target_object():
    obj = bpy.context.active_object
    if obj and obj.type == 'MESH':
        return obj
    # Fallback to *_Optimized if nothing active
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.endswith("_Optimized"):
            return o
    return None


def _uv_tile_index(x: float) -> int:
    EPS = 1e-6
    n = math.floor(x)
    if x >= 0.0 and n >= 1 and (x - n) >= 0.0 and (x - n) < EPS:
        x = x - EPS
    return int(math.floor(x))


def _poly_udim(obj, poly_index) -> int:
    me = obj.data
    uv_layer = me.uv_layers.active or (me.uv_layers[0] if me.uv_layers else None)
    if not uv_layer:
        return 1001
    poly = me.polygons[poly_index]
    # Use first loop's UV to decide tile
    loop_index = poly.loop_start
    luv = uv_layer.data[loop_index].uv
    u = _uv_tile_index(float(luv.x))
    v = _uv_tile_index(float(luv.y))
    return 1001 + u + v * 10


class VIVID_OT_udim_material_assignment(Operator):
    bl_idname = "vivid.udim_material_assignment"
    bl_label = "Assign UDIM Materials"
    bl_description = "Assign faces on the active mesh to materials named (objectname)_(udim) based on UV tiles; create any missing UDIM materials and refresh textures for existing ones."

    def execute(self, context):
        obj = _find_target_object()
        if not obj:
            self.report({'ERROR'}, "No active mesh (or *_Optimized) object found")
            return {'CANCELLED'}
        me = obj.data
        if not getattr(me, 'uv_layers', None) or len(me.uv_layers) == 0:
            self.report({'WARNING'}, "Object has no UVs; skipping UDIM assignment")
            return {'CANCELLED'}

        # Determine UDIMs present in the mesh by sampling polygons
        present_udims = set()
        for poly in me.polygons:
            present_udims.add(_poly_udim(obj, poly.index))
        if not present_udims:
            self.report({'INFO'}, "No UDIM tiles detected; nothing to assign")
            return {'FINISHED'}

        # Ensure materials exist for all present UDIMs
        name_prefix = obj.name + "_"
        # Try to gather textures best-effort (use BakeTextures Part1 if present, else root) for the object's base name without LOD suffix
        try:
            base_for_textures = obj.name
            for suf in ("_LOD0","_LOD1","_LOD2","_LOD3","_MeshCollider","_ShadowProxy"):
                if base_for_textures.endswith(suf):
                    base_for_textures = base_for_textures[: -len(suf)]
            _, _, bake_tex = project_dirs()
            part1_dir = os.path.join(bake_tex, "Part1")
            if os.path.isdir(part1_dir):
                tex_map = _gather_textures_for_object(part1_dir, base_for_textures)
                if not tex_map:
                    tex_map = _gather_textures_for_object(bake_tex, base_for_textures)
            else:
                tex_map = _gather_textures_for_object(bake_tex, base_for_textures)
        except Exception:
            tex_map = {}

        # Prepare template for creating missing materials
        template = _append_or_get_template("Delighter")

        # Build current map and create missing
        udim_to_slot = {}
        for i, m in enumerate(me.materials):
            if not m or not m.name.startswith(name_prefix):
                continue
            tail = m.name[len(name_prefix):]
            if tail.isdigit():
                udim_to_slot[int(tail)] = i

        # Create any missing UDIM materials and wire textures for them; refresh textures for existing ones
        for udim in sorted(present_udims):
            if udim not in udim_to_slot:
                # Create new material
                mat_name = f"{obj.name}_{udim}"
                if template:
                    mat = _clone_material_from_template(mat_name, template)
                else:
                    mat = bpy.data.materials.new(mat_name)
                    mat.use_nodes = True
                # Wire textures best-effort
                try:
                    _set_images_by_baker(mat, tex_map.get(str(udim), {}))
                except Exception:
                    pass
                me.materials.append(mat)
                udim_to_slot[udim] = len(me.materials) - 1
            else:
                # Refresh textures for existing material if we can
                slot_index = udim_to_slot[udim]
                mat = me.materials[slot_index]
                try:
                    _set_images_by_baker(mat, tex_map.get(str(udim), {}))
                except Exception:
                    pass

        # Assign per polygon
        for poly in me.polygons:
            udim = _poly_udim(obj, poly.index)
            slot = udim_to_slot.get(udim)
            if slot is not None:
                poly.material_index = slot
        self.report({'INFO'}, "Created/updated UDIM materials and assigned faces by tiles")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_udim_material_assignment)

def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_udim_material_assignment)
    except Exception:
        pass
