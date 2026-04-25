import bpy
import os


def _release_asset_dir(context):
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences
    release_root = getattr(prefs, 'release_directory', '') or ''
    blend_path = bpy.data.filepath
    if not blend_path:
        raise RuntimeError("Save your .blend file first.")
    blend_dir = os.path.dirname(blend_path)

    parts = os.path.normpath(blend_dir).split(os.sep)
    lower_parts = [p.lower() for p in parts]
    if 'production' in lower_parts:
        idx = lower_parts.index('production')
        sub_after = parts[idx + 1:]
        if release_root:
            return os.path.join(release_root, *sub_after)
        parts[idx] = 'Release'
        return os.path.join(*parts)
    if release_root:
        return os.path.join(release_root, os.path.basename(blend_dir))
    return os.path.join(os.path.dirname(blend_dir), 'Release', os.path.basename(blend_dir))


def _is_locomotion_object(obj: bpy.types.Object) -> bool:
    return any(collection.name == 'Locomotion' for collection in getattr(obj, 'users_collection', []) or [])


class VIVID_OT_export_lods(bpy.types.Operator):
    bl_idname = "vivid.export_lods"
    bl_label = "Export LODs"
    bl_description = "Exports LOD FBXs (including variants and ShadowProxies) to the mirrored Release directory."

    def execute(self, context):
        try:
            release_dir = _release_asset_dir(context)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        # Tidy structure: export meshes into Release/Game/Mesh
        mesh_dir = os.path.join(release_dir, "Game", "Mesh")
        os.makedirs(mesh_dir, exist_ok=True)

        # Collect LOD objects: any *_LOD0..3 and *_ShadowProxy[_LOD*] and colliders
        lod_candidates = []
        seen = set()
        for o in bpy.data.objects:
            if o.type != 'MESH':
                continue
            n = o.name
            # Skip LOD Cages entirely (names like *_LOD#_Cage or in LOD_Cage collection)
            if "_Cage" in n or any(c.name == 'LOD_Cage' for c in getattr(o, 'users_collection', []) or []):
                continue
            if _is_locomotion_object(o) or any(s in n for s in ["_LOD0", "_LOD1", "_LOD2", "_LOD3", "_ShadowProxy", "_MeshCollider", "_ConvexCollider"]):
                if o.name in seen:
                    continue
                seen.add(o.name)
                lod_candidates.append(o)

        if not lod_candidates:
            self.report({'ERROR'}, "No LODs/Proxies found to export.")
            return {'CANCELLED'}

        # Compute UDIM grid mapping per LOD index to match merge_udims.py logic.
        # Merge step arranges tiles on a grid of size n = ceil(sqrt(total unique UDIMs in that LOD's baked textures)),
        # placed row-major in ascending UDIM order. We mirror that here for UV remapping so meshes align with merged atlases.
        lod_udims_map = {0: set(), 1: set(), 2: set(), 3: set()}
        for o in lod_candidates:
            for i in (0, 1, 2, 3):
                if o.name.endswith(f"_LOD{i}"):
                    try:
                        for ud in _collect_udims(o):
                            lod_udims_map[i].add(int(ud))
                    except Exception:
                        pass
                    break
        import math
        lod_global_udims_sorted = {i: sorted(v) for i, v in lod_udims_map.items() if v}
        lod_grid_n = {i: max(1, int(math.ceil(math.sqrt(len(v))))) for i, v in lod_global_udims_sorted.items()}

        exported = 0
        for obj in lod_candidates:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            out_path = os.path.join(mesh_dir, f"{obj.name}.fbx")
            # Optional UV remap for merged UDIMs (non-destructive): apply only for LOD meshes
            sprops = getattr(context.scene, 'vivid_lod_props', None)
            merge_udims = bool(getattr(sprops, 'merge_udims', False)) if sprops else False
            did_remap = False
            saved_uv = None
            # Temporarily strip materials during export; restore after
            saved_mats = list(obj.data.materials) if getattr(obj.data, 'materials', None) else []
            try:
                if getattr(obj.data, 'materials', None):
                    obj.data.materials.clear()
            except Exception:
                pass
            if merge_udims and any(obj.name.endswith(f"_LOD{i}") for i in (0,1,2,3)):
                try:
                    # Determine UDIM tiles present on this object by scanning active UV layer
                    udims = _collect_udims(obj)
                    if udims:
                        # Find this object's LOD index and use the global union for mapping/grid size
                        lod_idx = None
                        for i in (0, 1, 2, 3):
                            if obj.name.endswith(f"_LOD{i}"):
                                lod_idx = i
                                break
                        global_udims = lod_global_udims_sorted.get(lod_idx, sorted(set(udims)))
                        n = lod_grid_n.get(lod_idx, max(1, int(math.ceil(math.sqrt(len(global_udims))))))
                        _apply_uv_grid_remap(obj, udims, n, global_udims)
                        did_remap = True
                except Exception:
                    did_remap = False
            try:
                bpy.ops.export_scene.fbx(
                    filepath=out_path,
                    use_selection=True,
                    object_types={'MESH'},
                    bake_space_transform=True,
                    use_mesh_modifiers=True,
                    mesh_smooth_type='FACE',
                    axis_forward='-Z',
                    axis_up='Y'
                )
                self.report({'INFO'}, f"Exported: {out_path}")
                exported += 1
            except Exception as e:
                self.report({'ERROR'}, f"Failed exporting {obj.name}: {e}")
            finally:
                # Restore original UVs if we remapped
                if did_remap:
                    try:
                        _restore_uv_grid_remap(obj)
                    except Exception:
                        pass
                # Restore materials
                try:
                    if getattr(obj.data, 'materials', None) is not None:
                        obj.data.materials.clear()
                        for m in saved_mats:
                            obj.data.materials.append(m)
                except Exception:
                    pass

        if exported == 0:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported {exported} LOD FBXs to: {mesh_dir}")
        return {'FINISHED'}


def _collect_udims(obj: bpy.types.Object) -> list[int]:
    import math
    me = getattr(obj, 'data', None)
    if not me or not getattr(me, 'uv_layers', None):
        return []
    uv_layer = me.uv_layers.active
    if not uv_layer:
        return []
    udims = set()
    for loop in uv_layer.data:
        u, v = float(loop.uv.x), float(loop.uv.y)
        ud = int(math.floor(u)) + int(math.floor(v)) * 10 + 1001
        udims.add(ud)
    return sorted(udims)


def _apply_uv_grid_remap(obj: bpy.types.Object, udims: list[int], grid_n: int | None = None, global_udims: list[int] | None = None):
    """Scale and translate UVs from UDIM tiles into a square grid in 0..1 space.
    Deterministic order: sorted UDIM ascending, row-major.
    Stores original UVs on the mesh custom data layer for restoration.
    """
    import math
    me = obj.data
    if not me.uv_layers:
        return
    uv_layer = me.uv_layers.active
    # Save original UVs into a module-level cache keyed by mesh pointer
    backup = [(uv.uv.x, uv.uv.y) for uv in uv_layer.data]
    _UV_BACKUPS[me.as_pointer()] = backup
    # Build mapping
    # If provided, use the global UDIM ordering and grid size for the LOD to match merge_udims.py
    if global_udims:
        udims_sorted = [int(u) for u in global_udims]
    else:
        udims_sorted = sorted(set(int(u) for u in udims))
    n = grid_n if grid_n and grid_n > 0 else max(1, int(math.ceil(math.sqrt(len(udims_sorted)))))
    # Map UDIM -> (row, col)
    index_map = {ud: i for i, ud in enumerate(udims_sorted)}
    # Helper to compute tile index from UV
    def tile_of(u, v):
        return int((math.floor(u))) + int((math.floor(v))) * 10 + 1001
    # Remap all loops
    for loop in uv_layer.data:
        u, v = float(loop.uv.x), float(loop.uv.y)
        ud = tile_of(u, v)
        idx = index_map.get(ud, 0)
        row, col = divmod(idx, n)
        # Local UV inside tile
        u_local = u - math.floor(u)
        v_local = v - math.floor(v)
        loop.uv.x = (col + u_local) / n
        loop.uv.y = (row + v_local) / n


def _restore_uv_grid_remap(obj: bpy.types.Object):
    me = obj.data
    if not me.uv_layers:
        return
    uv_layer = me.uv_layers.active
    backup = _UV_BACKUPS.pop(me.as_pointer(), None)
    if not backup:
        return
    for (loop, (ux, uy)) in zip(uv_layer.data, backup):
        loop.uv.x = ux
        loop.uv.y = uy

# Module-level cache for UV backups during export
_UV_BACKUPS = {}


def register():
    bpy.utils.register_class(VIVID_OT_export_lods)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_export_lods)
