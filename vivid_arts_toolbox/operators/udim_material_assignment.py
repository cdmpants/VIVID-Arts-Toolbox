# vivid_arts_toolbox/operators/udim_material_assignment.py
import bpy
import math
from bpy.types import Operator


def _find_optimized_object():
    obj = bpy.context.active_object
    if obj and obj.type == 'MESH' and obj.name.endswith("_Optimized"):
        return obj
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
    bl_description = "Assign faces on *_Optimized to materials named (objectname)_(udim) based on UV tiles"

    def execute(self, context):
        obj = _find_optimized_object()
        if not obj:
            self.report({'ERROR'}, "No *_Optimized object found")
            return {'CANCELLED'}
        me = obj.data
        if not getattr(me, 'uv_layers', None) or len(me.uv_layers) == 0:
            self.report({'WARNING'}, "Object has no UVs; skipping UDIM assignment")
            return {'CANCELLED'}

        # Build map from UDIM -> slot index for materials named object_udim
        name_prefix = obj.name + "_"
        udim_to_slot = {}
        for i, m in enumerate(me.materials):
            if not m or not m.name.startswith(name_prefix):
                continue
            tail = m.name[len(name_prefix):]
            if tail.isdigit():
                udim_to_slot[int(tail)] = i

        if not udim_to_slot:
            # Nothing to assign
            self.report({'INFO'}, "No UDIM-named materials found on object; nothing to assign")
            return {'FINISHED'}

        # Assign per polygon
        for poly in me.polygons:
            udim = _poly_udim(obj, poly.index)
            slot = udim_to_slot.get(udim)
            if slot is not None:
                poly.material_index = slot
        self.report({'INFO'}, "Assigned materials by UDIM tiles")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_udim_material_assignment)

def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_udim_material_assignment)
    except Exception:
        pass
