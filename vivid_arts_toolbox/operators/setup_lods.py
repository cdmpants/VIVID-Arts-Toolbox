# vivid_arts_toolbox/operators/setup_lods.py

import bpy
import os
import re
from .. import utils
from .. import preferences
import math


# === VIVID: ShadowProxy naming helper ===
def _vat_make_shadowproxy_name(obj_name: str) -> str:
    m = re.search(r'(.*)(_LOD\d+)$', obj_name)
    if m:
        return f"{m.group(1)}_ShadowProxy{m.group(2)}"
    return f"{obj_name}_ShadowProxy"


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
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences

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
                    rf"^{re.escape(base_label)}_ShadowProxy(_LOD[0-3])?$",
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
            # Prepare paths
            blend_filepath = bpy.data.filepath
            if not blend_filepath:
                raise RuntimeError("Save your .blend file first!")
            blend_dir = os.path.dirname(blend_filepath)
            lods_dir = os.path.join(blend_dir, "LODs")
            os.makedirs(lods_dir, exist_ok=True)

            # Capture original materials from source (Cinema) — do not modify src slots
            original_mats = list(src.data.materials)
            self.report({'INFO'}, "Preparing temporary Color Grid for export...")
            temp_img = bpy.data.images.new(
                f"{base_label}_ColorGrid",
                width=64,
                height=64,
                alpha=True,
                float_buffer=False
            )
            temp_img.generated_type = 'COLOR_GRID'
            temp_mat = bpy.data.materials.new(f"{base_label}_TempExportMat")
            temp_mat.use_nodes = True
            nt = temp_mat.node_tree; nodes = nt.nodes; links = nt.links
            for n in list(nodes):
                nodes.remove(n)
            out = nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
            bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (0, 0)
            tex = nodes.new("ShaderNodeTexImage"); tex.location = (-300, 0); tex.image = temp_img
            links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            # Duplicate the source object with a single-user mesh and assign the temp material for export only
            dup = src.copy()
            dup.data = src.data.copy()
            try:
                context.scene.collection.objects.link(dup)
            except Exception:
                pass
            dup.matrix_world = src.matrix_world.copy()
            dup.data.materials.clear(); dup.data.materials.append(temp_mat)

            # Export the duplicate to DAE for external pipeline
            dae_path = os.path.join(lods_dir, f"{base_label}_Cinema.dae")
            bpy.ops.object.select_all(action='DESELECT')
            dup.select_set(True)
            context.view_layer.objects.active = dup
            bpy.ops.wm.collada_export(filepath=dae_path, selected=True, apply_modifiers=True)
            # Remove duplicate object and its mesh
            try:
                mesh_ref = dup.data
                bpy.data.objects.remove(dup, do_unlink=True)
                if mesh_ref and mesh_ref.users == 0:
                    bpy.data.meshes.remove(mesh_ref, do_unlink=True)
            except Exception:
                pass
            self.report({'INFO'}, f"Exported {dae_path}")

            # Generate LOD0–3 with MeshLab/PyMeshLab
            face_count = len(src.data.polygons)
            # Compute effective ratios relative to Cinema so utils can stay unchanged:
            # r0 = LOD0_target / Cinema_faces; r1..3 = r0 * (ratio_of_LOD0)
            try:
                lod0_target = int(getattr(sprops, 'lod0_target_tris', 10000) or 10000)
            except Exception:
                # Fallback to legacy ratio if new prop missing
                lod0_target = max(10, int(face_count * float(getattr(sprops, 'lod0_ratio', 0.08) or 0.08)))
            r0 = max(10, lod0_target) / max(1, face_count)
            r1_rel = float(getattr(sprops, 'lod1_ratio', 0.40) or 0.40)
            r2_rel = float(getattr(sprops, 'lod2_ratio', 0.16) or 0.16)
            r3_rel = float(getattr(sprops, 'lod3_ratio', 0.064) or 0.064)
            ratios = {
                0: float(r0),
                1: float(r0 * r1_rel),
                2: float(r0 * r2_rel),
                3: float(r0 * r3_rel),
            }
            ok = False
            if getattr(prefs, 'enable_pymeshlab_automation', False):
                ok = utils.generate_lods_with_pymeshlab(context, dae_path, lods_dir, src, face_count, ratios)
            else:
                ok = utils.generate_lods_with_meshlabserver(self, context, dae_path, lods_dir, src, face_count, ratios)
            if not ok:
                raise RuntimeError("LOD generation failed.")

            # Import LOD0–3 into LOD collection and reapply original materials
            lod_names = []
            # Determine filename prefix used by MeshLab outputs
            # For variants, outputs include "_Cinema_Var#"; for base, they strip "_Cinema"
            if '_Cinema_Var' in src.name:
                output_prefix = src.name
            elif src.name.endswith('_Cinema'):
                output_prefix = src.name[:-7]
            else:
                output_prefix = base_label
            for i in range(0, 4):
                lod_path = os.path.join(lods_dir, f"{output_prefix}_LOD{i}.dae")
                if not os.path.exists(lod_path):
                    raise RuntimeError(f"Missing {lod_path}")
                bpy.ops.wm.collada_import(filepath=lod_path, import_units=True, find_chains=True)
                lod = context.selected_objects[0] if context.selected_objects else None
                if not lod:
                    continue
                lod.name = f"{base_label}_LOD{i}"
                lod.data.name = f"{base_label}_LOD{i}"
                lod.rotation_euler = (0, 0, 0)
                lod.rotation_quaternion = (1, 0, 0, 0)
                bpy.ops.object.shade_smooth()
                for col in list(lod.users_collection):
                    col.objects.unlink(lod)
                lod_coll.objects.link(lod)
                # Reapply original materials
                lod.data.materials.clear()
                for m in original_mats:
                    lod.data.materials.append(m)
                # Assign faces by UDIM using the existing Cinema materials only, then prune extras
                _assign_faces_by_udim_existing_mats(lod)
                _prune_unused_materials(lod)
                lod_names.append(lod.name)

            # Data Transfer (normals from Cinema source) — apply to imported LODs, but skip LOD0
            src_obj = src  # use the original Cinema object as the transfer source
            if src_obj:
                for name in lod_names:
                    lod = bpy.data.objects.get(name)
                    if not lod:
                        continue
                    # Skip adding Data Transfer to LOD0
                    if name.endswith('_LOD0'):
                        continue
                    mod = lod.modifiers.new("DataTransfer", 'DATA_TRANSFER')
                    mod.object = src_obj
                    mod.use_loop_data = True
                    mod.data_types_loops = {'CUSTOM_NORMAL'}
                    mod.loop_mapping = 'POLYINTERP_LNORPROJ'

            # Optional MeshCollider from imported LOD0
            gen_collider = bool(getattr(sprops, 'generate_collider', True))
            collider_ratio = float(getattr(sprops, 'collider_ratio', 0.05))
            if gen_collider and bpy.data.objects.get(f"{base_label}_LOD0"):
                bpy.ops.object.select_all(action='DESELECT')
                lod0_imp = bpy.data.objects.get(f"{base_label}_LOD0")
                lod0_imp.select_set(True)
                context.view_layer.objects.active = lod0_imp
                bpy.ops.object.duplicate_move()
                collider = context.active_object
                collider.name = f"{base_label}_MeshCollider"
                collider.data.name = collider.name
                for col in list(collider.users_collection):
                    col.objects.unlink(collider)
                lod_coll.objects.link(collider)
                dec = collider.modifiers.new("Decimate_Collider", 'DECIMATE')
                dec.ratio = collider_ratio
                dec.use_collapse_triangulate = True
                # Remove materials and UVs from collider (left as-is visually)
                try:
                    collider.data.materials.clear()
                except Exception:
                    pass
                try:
                    uvs = collider.data.uv_layers
                    while uvs and len(uvs) > 0:
                        uvs.remove(uvs[0])
                except Exception:
                    pass
                # Viewport wireframe for mesh collider
                try:
                    collider.display_type = 'WIRE'
                except Exception:
                    pass

            # ShadowProxies, with per-LOD ratios
            gen_sp = bool(getattr(sprops, 'generate_shadow_proxies', True))
            if gen_sp:
                def _sp_ratio_for(name: str) -> float:
                    if name.endswith('_LOD0'):
                        return float(getattr(sprops, 'sp_lod0_ratio', 0.2))
                    if name.endswith('_LOD1'):
                        return float(getattr(sprops, 'sp_lod1_ratio', 0.2))
                    if name.endswith('_LOD2'):
                        return float(getattr(sprops, 'sp_lod2_ratio', 0.2))
                    if name.endswith('_LOD3'):
                        return float(getattr(sprops, 'sp_lod3_ratio', 0.2))
                    return 0.2
                for src_name in lod_names:
                    src_obj = bpy.data.objects.get(src_name)
                    if not src_obj:
                        continue
                    bpy.ops.object.select_all(action='DESELECT')
                    src_obj.select_set(True)
                    context.view_layer.objects.active = src_obj
                    bpy.ops.object.duplicate_move()
                    sp = context.active_object
                    sp.name = _vat_make_shadowproxy_name(src_obj.name)
                    sp.data.name = _vat_make_shadowproxy_name(src_obj.data.name)
                    for col in list(sp.users_collection):
                        col.objects.unlink(sp)
                    lod_coll.objects.link(sp)
                    dec = sp.modifiers.new("Decimate_ShadowProxy", 'DECIMATE')
                    dec.ratio = _sp_ratio_for(src_obj.name)
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

            # Rename UV layers
            for o in lod_coll.objects:
                if o.type == 'MESH' and o.data.uv_layers:
                    uvs = o.data.uv_layers
                    if len(uvs) > 0:
                        uvs[0].name = 'UVMap'
                    if len(uvs) > 1:
                        uvs[1].name = 'Lightmap'

            # Cleanup temp assets
            if temp_mat.name in bpy.data.materials:
                bpy.data.materials.remove(temp_mat, do_unlink=True)
            if temp_img.name in bpy.data.images:
                bpy.data.images.remove(temp_img, do_unlink=True)

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

