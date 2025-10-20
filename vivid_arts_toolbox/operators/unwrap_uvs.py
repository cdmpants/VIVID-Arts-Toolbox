import bpy
from bpy.types import Operator


def _active_mesh(context):
    obj = context.active_object
    return obj if (obj and obj.type == 'MESH') else None


def _ensure_uvmap(me, name="UVMap"):
    uvs = getattr(me, 'uv_layers', None)
    if not uvs:
        return None
    for layer in uvs:
        if layer.name == name:
            uvs.active = layer
            uvs.active_index = list(uvs).index(layer)
            return layer
    layer = uvs.new(name=name)
    uvs.active = layer
    uvs.active_index = list(uvs).index(layer)
    return layer


def _smart_project(obj, angle_limit_deg: float = 89.0, island_margin: float = 0.0):
    prev_mode = obj.mode
    try:
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=angle_limit_deg, island_margin=island_margin)
    finally:
        try:
            if obj.mode != prev_mode:
                bpy.ops.object.mode_set(mode=prev_mode)
        except Exception:
            pass


def _pack_into_udims(obj, udim_count: int, margin_norm: float):
    if udim_count <= 1:
        prev = obj.mode
        try:
            if obj.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.select_all(action='SELECT')
            bpy.ops.uv.pack_islands(rotate=True, margin=max(0.0, float(margin_norm)))
        finally:
            try:
                if obj.mode != prev:
                    bpy.ops.object.mode_set(mode=prev)
            except Exception:
                pass
        return

    import math
    cols = int(math.ceil(math.sqrt(udim_count)))
    rows = int(math.ceil(udim_count / cols))
    me = obj.data
    uv = me.uv_layers.active
    if not (uv and me.polygons and me.loops):
        return
    # First, pack islands in EDIT mode
    prev = obj.mode
    try:
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.select_all(action='SELECT')
        bpy.ops.uv.pack_islands(rotate=True, margin=max(0.0, float(margin_norm)))
        # Snapshot polygon -> tile assignment planning while in edit mode
        polys = list(me.polygons)
        total = len(polys)
        if total == 0:
            return
        per_tile = max(1, total // udim_count)
        tile_index = 0
        assigned = 0
        tile_coords = []
        for r in range(rows):
            for c in range(cols):
                tile_coords.append((c, r))
        tile_coords = tile_coords[:udim_count]
        poly_tile = []  # list of (poly, (tu,tv))
        for poly in polys:
            if tile_index >= udim_count:
                tile_index = udim_count - 1
            poly_tile.append((poly, tile_coords[tile_index]))
            assigned += 1
            if assigned >= per_tile:
                tile_index += 1
                assigned = 0
    finally:
        try:
            if obj.mode != prev:
                bpy.ops.object.mode_set(mode=prev)
        except Exception:
            pass
    # Now write UV coordinates in OBJECT mode to avoid index errors on uv.data
    for poly, (tu, tv) in poly_tile:
        for li in poly.loop_indices:
            if li < len(uv.data):
                luv = uv.data[li].uv
                luv.x = (luv.x % 1.0) + tu
                luv.y = (luv.y % 1.0) + tv


class VIVID_OT_unwrap_uvs(Operator):
    bl_idname = "vivid.unwrap_uvs"
    bl_label = "Unwrap UVs"
    bl_description = "Placeholder: Smart UV Project with Angle Limit 89, then pack into UDIMs per UI selection"

    def execute(self, context):
        obj = _active_mesh(context)
        if not obj:
            self.report({'ERROR'}, "Select a mesh to unwrap.")
            return {'CANCELLED'}
        me = obj.data
        if not me:
            self.report({'ERROR'}, "Active mesh has no data.")
            return {'CANCELLED'}
        if not _ensure_uvmap(me, name="UVMap"):
            self.report({'ERROR'}, "Could not create/find UVMap.")
            return {'CANCELLED'}
        # Compute normalized margins from Pixel Margin and 1/8 Texture Resolution
        try:
            res = int(getattr(context.scene, 'vivid_uv_texture_res', '8192'))
        except Exception:
            res = 8192
        try:
            px_margin = int(getattr(context.scene, 'vivid_uv_pixel_margin', 3))
        except Exception:
            px_margin = 3
        eff_res = max(1, int(res) // 8)
        margin_norm = float(px_margin) / float(eff_res)

        _smart_project(obj, angle_limit_deg=89.0, island_margin=margin_norm)
        try:
            udims = int(getattr(context.scene, 'vivid_uv_udim_tiles', '0'))
        except Exception:
            udims = 0
        _pack_into_udims(obj, max(udims, 0), margin_norm)
        self.report({'INFO'}, "Unwrap + pack complete (placeholder)")
        return {'FINISHED'}


CLASSES = (VIVID_OT_unwrap_uvs,)

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
