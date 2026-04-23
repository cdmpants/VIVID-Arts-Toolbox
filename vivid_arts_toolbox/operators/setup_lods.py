# vivid_arts_toolbox/operators/setup_lods.py

import bpy
import re
from ..decimate import decimate_to_new_object
import math


# === VIVID: ShadowProxy naming helpers ===
def _vat_make_shadowproxy_name(obj_name: str, kind: str) -> str:
    """Create a name like '<Base>_<kind>_LOD#' from '<Base>_LOD#'."""
    m = re.search(r'(.*)(_LOD\d+)$', obj_name)
    if m:
        return f"{m.group(1)}_{kind}{m.group(2)}"
    return f"{obj_name}_{kind}"


def _collect_cinema_sources():
    """Return list of src objects to process: the base _Cinema and any _Cinema_Var# in their collections."""
    out = []
    # Base Cinema
    cinema = bpy.data.collections.get('Cinema')
    if cinema:
        for o in cinema.objects:
            if o.type == 'MESH' and (o.name.endswith('_Cinema') or o.name == 'Cinema'):
                out.append(o)
                break
    # Variants
    for coll in bpy.data.collections:
        if coll.name.startswith('Cinema_Var'):
            for o in coll.objects:
                if o.type == 'MESH' and ('_Cinema_Var' in o.name or o.name == coll.name):
                    out.append(o)
                    break
    return [o for o in out if o]


class VIVID_OT_setup_lods(bpy.types.Operator):
    bl_idname = "vivid.setup_lods"
    bl_label = "Setup LODs"
    bl_description = "Generates collider meshes, exports LOD0 for external processing, imports and sets up other LODs."
    # Operator reads settings from scene.vivid_lod_props
    def execute(self, context):
        self.report({'INFO'}, "Starting Setup LODs process...")

        sprops = getattr(context.scene, 'vivid_lod_props', None)

        # Determine source objects to process (base + variants)
        sources = []
        if context.active_object and context.active_object.type == 'MESH' and (
            context.active_object.name.endswith('_Cinema') or '_Cinema_Var' in context.active_object.name):
            sources = [context.active_object]
        else:
            sources = _collect_cinema_sources()
        if not sources:
            self.report({'ERROR'}, "No Cinema sources found. Generate Cinema Model first.")
            return {'CANCELLED'}

        def _proc_one(src: bpy.types.Object):
            def _remove_data_transfer_modifiers(obj: bpy.types.Object):
                if not obj:
                    return
                try:
                    mods = list(getattr(obj, 'modifiers', []) or [])
                except Exception:
                    mods = []
                for m in mods:
                    try:
                        if getattr(m, 'type', None) == 'DATA_TRANSFER':
                            obj.modifiers.remove(m)
                    except Exception:
                        pass
            # Helper: assign faces by UDIM using only existing materials on the mesh
            def _assign_faces_by_udim_existing_mats(obj: bpy.types.Object):
                me = obj.data
                if not getattr(me, 'uv_layers', None) or len(me.uv_layers) == 0:
                    return
                # Build UDIM->slot mapping from the object's current materials
                import re as _re
                udim_to_slot = {}
                for i, m in enumerate(me.materials):
                    if not m or not isinstance(m.name, str):
                        continue
                    m4 = _re.search(r"(\d{4})$", m.name)
                    if not m4:
                        continue
                    try:
                        val = int(m4.group(1))
                    except Exception:
                        continue
                    if val >= 1001:
                        udim_to_slot[val] = i
                # Helper to compute UDIM from a polygon
                def _uv_tile_index(x: float) -> int:
                    EPS = 1e-6
                    n = math.floor(x)
                    if x >= 0.0 and n >= 1 and (x - n) >= 0.0 and (x - n) < EPS:
                        x = x - EPS
                    return int(math.floor(x))
                def _poly_udim(_obj, poly_index) -> int:
                    _me = _obj.data
                    uv_layer = _me.uv_layers.active or (_me.uv_layers[0] if _me.uv_layers else None)
                    if not uv_layer:
                        return 1001
                    poly = _me.polygons[poly_index]
                    loop_index = poly.loop_start
                    luv = uv_layer.data[loop_index].uv
                    u = _uv_tile_index(float(luv.x))
                    v = _uv_tile_index(float(luv.y))
                    return 1001 + u + v * 10
                # Assign per polygon only to slots that exist
                for poly in me.polygons:
                    udim = _poly_udim(obj, poly.index)
                    slot = udim_to_slot.get(udim)
                    if slot is not None:
                        poly.material_index = slot

            # Helper: prune any materials that no polygon uses
            def _prune_unused_materials(obj: bpy.types.Object):
                me = obj.data
                if not me.materials:
                    return
                used = set()
                for p in me.polygons:
                    used.add(p.material_index)
                # Remove unused slots from end to start to keep indices stable
                for idx in range(len(me.materials) - 1, -1, -1):
                    if idx not in used:
                        try:
                            me.materials.pop(index=idx)
                        except Exception:
                            # Fallback if pop with index not available in this Blender version
                            try:
                                mat = me.materials[idx]
                                me.materials.clear()
                                # Rebuild without the removed index
                            except Exception:
                                pass

            # Helper: remove existing LOD objects so the operator is idempotent
            def _remove_existing_lod_targets(collection: bpy.types.Collection, base_label: str):
                to_delete = []
                patterns = [
                    rf"^{re.escape(base_label)}_LOD[0-3]$",
                    rf"^{re.escape(base_label)}_MeshCollider$",
                    rf"^{re.escape(base_label)}_ShadowProxyHigh(_LOD[0-3])?$",
                    rf"^{re.escape(base_label)}_ShadowProxyLow(_LOD[0-3])?$",
                    # Back-compat cleanup for legacy names
                    rf"^{re.escape(base_label)}_ShadowProxy(_LOD[0-3])?$",
                    rf"^{re.escape(base_label)}_RefProxy$",
                    rf"^{re.escape(base_label)}_RefProxy_ShadowProxy$",
                ]
                for o in list(collection.objects):
                    for pat in patterns:
                        if re.match(pat, o.name):
                            to_delete.append(o)
                            break
                # Unlink from all collections and delete
                for o in to_delete:
                    try:
                        for col in list(o.users_collection):
                            col.objects.unlink(o)
                    except Exception:
                        pass
                    try:
                        bpy.data.objects.remove(o, do_unlink=True)
                    except Exception:
                        pass
            # Parse base label and variant index
            m = re.match(r'(.+)_Cinema(?:_Var(\d+))?$', src.name)
            base = None; var_idx = None
            if m:
                base = m.group(1); var_idx = m.group(2)
            elif src.name == 'Cinema' or src.name.startswith('Cinema_Var'):
                base = 'Cinema';
                if src.name.startswith('Cinema_Var'):
                    var_idx = re.sub(r'[^0-9]', '', src.name)
            else:
                raise RuntimeError(f"Unexpected Cinema name format: {src.name}")
            base_label = base if not var_idx else f"{base}_Var{var_idx}"

            # Ensure LOD collection
            lod_coll_name = 'LOD' if not var_idx else f'LOD_Var{var_idx}'
            lod_coll = bpy.data.collections.get(lod_coll_name)
            if not lod_coll:
                lod_coll = bpy.data.collections.new(lod_coll_name)
                context.scene.collection.children.link(lod_coll)
            else:
                # Make the operator idempotent per base_label in this collection
                _remove_existing_lod_targets(lod_coll, base_label)

            lod_names = []
            use_cinema_as_lod0 = bool(getattr(sprops, 'use_cinema_as_lod0', True))
            gen_reflection_proxy = bool(getattr(sprops, 'generate_reflection_proxy', True))

            # Optionally create LOD0 immediately from Cinema so downstream steps (e.g., ShadowProxy) can rely on LOD0 existing.
            if use_cinema_as_lod0:
                try:
                    lod0_obj = src.copy()
                    lod0_obj.data = src.data.copy()
                    lod0_obj.name = f"{base_label}_LOD0"
                    try:
                        lod0_obj.data.name = lod0_obj.name
                    except Exception:
                        pass
                    try:
                        lod0_obj.rotation_euler = (0, 0, 0)
                        lod0_obj.rotation_quaternion = (1, 0, 0, 0)
                    except Exception:
                        pass
                    # Link into LOD collection
                    try:
                        context.scene.collection.objects.link(lod0_obj)
                    except Exception:
                        pass
                    for col in list(getattr(lod0_obj, 'users_collection', []) or []):
                        if col is not lod_coll:
                            try:
                                col.objects.unlink(lod0_obj)
                            except Exception:
                                pass
                    try:
                        lod_coll.objects.link(lod0_obj)
                    except Exception:
                        pass
                    lod_names.append(lod0_obj.name)
                except Exception as e:
                    raise RuntimeError(f"Failed to create LOD0 from Cinema: {e}")
            # Capture original materials from source (Cinema)
            original_mats = list(src.data.materials)
            face_count = len(src.data.polygons)

            # Build UV weight dict from source mesh layers and scene properties
            uv_wt = {}
            src_uvs = src.data.uv_layers
            if src_uvs:
                uv1_w = float(getattr(sprops, 'uv1_decimation_weight', 1.0) or 1.0)
                uv2_w = float(getattr(sprops, 'uv2_decimation_weight', 0.5) or 0.5)
                if len(src_uvs) >= 1:
                    uv_wt[src_uvs[0].name] = uv1_w
                if len(src_uvs) >= 2:
                    uv_wt[src_uvs[1].name] = uv2_w
            preserve_open_edges = bool(getattr(sprops, 'preserve_open_edges', False))

            # Determine LOD face-count targets
            if use_cinema_as_lod0:
                lod0_faces = face_count
            else:
                lod0_faces = max(10, int(getattr(sprops, 'lod0_target_tris', 10000) or 10000))
            lod_targets = {
                0: lod0_faces,
                1: max(10, int(lod0_faces * float(getattr(sprops, 'lod1_ratio', 0.40) or 0.40))),
                2: max(10, int(lod0_faces * float(getattr(sprops, 'lod2_ratio', 0.16) or 0.16))),
                3: max(10, int(lod0_faces * float(getattr(sprops, 'lod3_ratio', 0.064) or 0.064))),
            }

            # --- Generate LOD0 (if not using Cinema copy) ---
            if not use_cinema_as_lod0:
                lod0 = decimate_to_new_object(
                    src, lod_targets[0], f"{base_label}_LOD0",
                    uv_weights=uv_wt, lock_boundary=preserve_open_edges,
                )
                lod_coll.objects.link(lod0)
                lod0.rotation_euler = (0, 0, 0)
                lod0.rotation_quaternion = (1, 0, 0, 0)
                bpy.ops.object.select_all(action='DESELECT')
                lod0.select_set(True)
                context.view_layer.objects.active = lod0
                bpy.ops.object.shade_smooth()
                for m in original_mats:
                    lod0.data.materials.append(m)
                _assign_faces_by_udim_existing_mats(lod0)
                _prune_unused_materials(lod0)
                lod_names.append(lod0.name)
                self.report({'INFO'}, f"Generated {lod0.name} ({len(lod0.data.polygons)} faces)")

            # --- Generate LOD1–3 from LOD0 ---
            lod0_obj = bpy.data.objects.get(f"{base_label}_LOD0")
            if not lod0_obj:
                raise RuntimeError("LOD0 not found; cannot generate LOD1-3")
            for i in (1, 2, 3):
                lod = decimate_to_new_object(
                    lod0_obj, lod_targets[i], f"{base_label}_LOD{i}",
                    uv_weights=uv_wt, lock_boundary=preserve_open_edges,
                )
                lod_coll.objects.link(lod)
                lod.rotation_euler = (0, 0, 0)
                lod.rotation_quaternion = (1, 0, 0, 0)
                bpy.ops.object.select_all(action='DESELECT')
                lod.select_set(True)
                context.view_layer.objects.active = lod
                bpy.ops.object.shade_smooth()
                for m in original_mats:
                    lod.data.materials.append(m)
                _assign_faces_by_udim_existing_mats(lod)
                _prune_unused_materials(lod)
                lod_names.append(lod.name)
                self.report({'INFO'}, f"Generated {lod.name} ({len(lod.data.polygons)} faces)")

            # --- MeshCollider from LOD0 (preserves UVs for runtime raycast painting) ---
            gen_collider = bool(getattr(sprops, 'generate_collider', True))
            collider_ratio = float(getattr(sprops, 'collider_ratio', 0.05))
            if gen_collider and lod0_obj:
                collider_target = max(10, int(len(lod0_obj.data.polygons) * collider_ratio))
                collider = decimate_to_new_object(
                    lod0_obj, collider_target, f"{base_label}_MeshCollider",
                    uv_weights=uv_wt, lock_boundary=preserve_open_edges,
                )
                lod_coll.objects.link(collider)
                collider.display_type = 'WIRE'
                self.report({'INFO'}, f"Generated {collider.name} ({len(collider.data.polygons)} faces)")

            # ShadowProxies (High + Low), with per-LOD ratios
            gen_sp_high = bool(getattr(sprops, 'generate_shadow_proxies', True))
            gen_sp_low = bool(getattr(sprops, 'generate_low_shadow_proxies', True))

            def _sp_ratio_high(name: str) -> float:
                if name.endswith('_LOD0'):
                    return float(getattr(sprops, 'sp_lod0_ratio', 0.2))
                if name.endswith('_LOD1'):
                    return float(getattr(sprops, 'sp_lod1_ratio', 0.2))
                if name.endswith('_LOD2'):
                    return float(getattr(sprops, 'sp_lod2_ratio', 0.2))
                if name.endswith('_LOD3'):
                    return float(getattr(sprops, 'sp_lod3_ratio', 0.2))
                return 0.2

            def _sp_ratio_low(name: str) -> float:
                if name.endswith('_LOD0'):
                    return float(getattr(sprops, 'sp_low_lod0_ratio', 0.01))
                if name.endswith('_LOD1'):
                    return float(getattr(sprops, 'sp_low_lod1_ratio', 0.02))
                if name.endswith('_LOD2'):
                    return float(getattr(sprops, 'sp_low_lod2_ratio', 0.04))
                if name.endswith('_LOD3'):
                    return float(getattr(sprops, 'sp_low_lod3_ratio', 0.06))
                return 0.05

            def _make_shadowproxies(kind: str, ratio_fn, dec_name: str):
                for src_name in lod_names:
                    src_obj = bpy.data.objects.get(src_name)
                    if not src_obj:
                        continue
                    bpy.ops.object.select_all(action='DESELECT')
                    src_obj.select_set(True)
                    context.view_layer.objects.active = src_obj
                    bpy.ops.object.duplicate_move()
                    sp = context.active_object
                    sp.name = _vat_make_shadowproxy_name(src_obj.name, kind)
                    try:
                        sp.data.name = _vat_make_shadowproxy_name(src_obj.data.name, kind)
                    except Exception:
                        pass
                    for col in list(sp.users_collection):
                        col.objects.unlink(sp)
                    lod_coll.objects.link(sp)

                    # Shadow proxies should never carry Data Transfer modifiers.
                    _remove_data_transfer_modifiers(sp)

                    dec = sp.modifiers.new(dec_name, 'DECIMATE')
                    dec.ratio = float(ratio_fn(src_obj.name))
                    dec.use_collapse_triangulate = True
                    # Remove materials and UVs from shadow proxy
                    try:
                        sp.data.materials.clear()
                    except Exception:
                        pass
                    try:
                        uvs = sp.data.uv_layers
                        while uvs and len(uvs) > 0:
                            uvs.remove(uvs[0])
                    except Exception:
                        pass

            if gen_sp_high:
                _make_shadowproxies("ShadowProxyHigh", _sp_ratio_high, "Decimate_ShadowProxyHigh")
            if gen_sp_low:
                _make_shadowproxies("ShadowProxyLow", _sp_ratio_low, "Decimate_ShadowProxyLow")

            # Rename UV layers
            for o in lod_coll.objects:
                if o.type == 'MESH' and o.data.uv_layers:
                    uvs = o.data.uv_layers
                    if len(uvs) > 0:
                        uvs[0].name = 'UVMap'
                    if len(uvs) > 1:
                        uvs[1].name = 'Lightmap'

            # Data Transfer (normals) — apply at the end: use imported LOD0 as the source, skip LOD0 itself
            src_lod0 = bpy.data.objects.get(f"{base_label}_LOD0")
            if src_lod0:
                for name in lod_names:
                    if name.endswith('_LOD0'):
                        continue
                    lod = bpy.data.objects.get(name)
                    if not lod:
                        continue
                    try:
                        mod = lod.modifiers.new("DataTransfer", 'DATA_TRANSFER')
                        mod.object = src_lod0
                        mod.use_loop_data = True
                        mod.data_types_loops = {'CUSTOM_NORMAL'}
                        mod.loop_mapping = 'POLYINTERP_LNORPROJ'
                    except Exception:
                        pass

            # Optional Reflection Proxy: based on LOD3 after processing
            if gen_reflection_proxy:
                lod3 = bpy.data.objects.get(f"{base_label}_LOD3")
                if lod3:
                    ref_name = re.sub(r'_LOD3$', '_RefProxy', lod3.name)
                    ref_sp_name = f"{ref_name}_ShadowProxy"

                    # Create RefProxy (independent mesh) and apply decimate
                    if not bpy.data.objects.get(ref_name):
                        try:
                            bpy.ops.object.select_all(action='DESELECT')
                            lod3.select_set(True)
                            context.view_layer.objects.active = lod3
                            bpy.ops.object.duplicate_move()
                            ref = context.active_object
                            ref.name = ref_name
                            try:
                                ref.data = lod3.data.copy()
                            except Exception:
                                pass
                            try:
                                ref.data.name = ref_name
                            except Exception:
                                pass
                            for col in list(ref.users_collection):
                                col.objects.unlink(ref)
                            lod_coll.objects.link(ref)

                            r = float(getattr(sprops, 'refproxy_ratio', 0.15) or 0.15)
                            r = max(0.0, min(1.0, r))
                            dec = ref.modifiers.new("Decimate_RefProxy", 'DECIMATE')
                            try:
                                dec.decimate_type = 'COLLAPSE'
                            except Exception:
                                pass
                            dec.ratio = r
                            try:
                                bpy.ops.object.modifier_apply(modifier=dec.name)
                            except Exception:
                                pass
                        except Exception:
                            pass

                    # Create RefProxy ShadowProxy from RefProxy (unapplied decimate)
                    ref_obj = bpy.data.objects.get(ref_name)
                    if ref_obj and not bpy.data.objects.get(ref_sp_name):
                        try:
                            bpy.ops.object.select_all(action='DESELECT')
                            ref_obj.select_set(True)
                            context.view_layer.objects.active = ref_obj
                            bpy.ops.object.duplicate_move()
                            sp = context.active_object
                            sp.name = ref_sp_name
                            try:
                                sp.data = ref_obj.data.copy()
                            except Exception:
                                pass
                            try:
                                sp.data.name = ref_sp_name
                            except Exception:
                                pass
                            for col in list(sp.users_collection):
                                col.objects.unlink(sp)
                            lod_coll.objects.link(sp)

                            # Shadow proxies should never carry Data Transfer modifiers.
                            _remove_data_transfer_modifiers(sp)

                            r2 = float(getattr(sprops, 'refproxy_sp_ratio', 0.20) or 0.20)
                            r2 = max(0.0, min(1.0, r2))
                            dec2 = sp.modifiers.new("Decimate_RefProxyShadowProxy", 'DECIMATE')
                            try:
                                dec2.decimate_type = 'COLLAPSE'
                            except Exception:
                                pass
                            dec2.ratio = r2
                        except Exception:
                            pass

        # Process all sources
        errs = []
        for src in sources:
            try:
                _proc_one(src)
            except Exception as e:
                errs.append(f"{src.name}: {e}")
        if errs:
            self.report({'WARNING'}, "Some variants failed: " + "; ".join(errs))
        self.report({'INFO'}, "Setup LODs complete for base and variants.")
        return {'FINISHED'}

