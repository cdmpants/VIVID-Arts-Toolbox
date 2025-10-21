# vivid_arts_toolbox/operators/setup_lods.py

import bpy
import os
import re
from .. import utils
from .. import preferences


# === VIVID: ShadowProxy naming helper ===
def _vat_make_shadowproxy_name(obj_name: str) -> str:
    m = re.search(r'(.*)(_LOD\d+)$', obj_name)
    if m:
        return f"{m.group(1)}_ShadowProxy{m.group(2)}"
    return f"{obj_name}_ShadowProxy"


class VIVID_OT_setup_lods(bpy.types.Operator):
    bl_idname = "vivid.setup_lods"
    bl_label = "Setup LODs"
    bl_description = "Generates collider meshes, exports LOD0 for external processing, imports and sets up other LODs."
    # Operator reads settings from scene.vivid_lod_props
    def execute(self, context):
        self.report({'INFO'}, "Starting Setup LODs process...")

        sprops = getattr(context.scene, 'vivid_lod_props', None)
        prefs = context.preferences.addons[__package__.split('.')[0]].preferences

        # Determine source object (_Cinema or _Cinema_Var#)
        src = None
        if context.active_object and context.active_object.type == 'MESH' and (
            context.active_object.name.endswith('_Cinema') or '_Cinema_Var' in context.active_object.name):
            src = context.active_object
        if not src:
            cinema = bpy.data.collections.get('Cinema')
            if cinema:
                for o in cinema.objects:
                    if o.type == 'MESH' and o.name.endswith('_Cinema'):
                        src = o
                        break
        if not src:
            self.report({'ERROR'}, "No _Cinema source found. Generate Cinema Model first.")
            return {'CANCELLED'}

        # Parse base label and variant index
        m = re.match(r'(.+)_Cinema(?:_Var(\d+))?$', src.name)
        if not m:
            self.report({'ERROR'}, f"Unexpected Cinema name format: {src.name}")
            return {'CANCELLED'}
        base = m.group(1)
        var_idx = m.group(2)
        base_label = base if not var_idx else f"{base}_Var{var_idx}"

        # Ensure LOD collection
        lod_coll_name = 'LOD' if not var_idx else f'LOD_Var{var_idx}'
        lod_coll = bpy.data.collections.get(lod_coll_name)
        if not lod_coll:
            lod_coll = bpy.data.collections.new(lod_coll_name)
            context.scene.collection.children.link(lod_coll)

        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}
        blend_dir = os.path.dirname(blend_filepath)
        lods_dir = os.path.join(blend_dir, "LODs")
        os.makedirs(lods_dir, exist_ok=True)

        # Save original materials from src and prepare temporary color grid material for export
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
        # Assign temporary export mat
        src.data.materials.clear(); src.data.materials.append(temp_mat)

        # Export Cinema (as base) to DAE for external pipeline
        dae_path = os.path.join(lods_dir, f"{base_label}_Cinema.dae")
        prev_vis = getattr(src, 'hide_viewport', False)
        prev_sel = src.select_get()
        try:
            src.hide_set(False)
        except Exception:
            try:
                src.hide_viewport = False
            except Exception:
                pass
        bpy.ops.object.select_all(action='DESELECT')
        src.select_set(True)
        context.view_layer.objects.active = src
        bpy.ops.wm.collada_export(filepath=dae_path, selected=True, apply_modifiers=True)
        try:
            src.hide_set(prev_vis)
        except Exception:
            try:
                src.hide_viewport = prev_vis
            except Exception:
                pass
        src.select_set(prev_sel)
        self.report({'INFO'}, f"Exported {dae_path}")
        # Restore original materials on src
        src.data.materials.clear()
        for m in original_mats:
            src.data.materials.append(m)

        # Generate LOD0–3 with MeshLab/PyMeshLab
        face_count = len(src.data.polygons)
        ratios = {
            0: float(getattr(sprops, 'lod0_ratio', 0.08) or 0.08),
            1: float(getattr(sprops, 'lod1_ratio', 0.40) or 0.40),
            2: float(getattr(sprops, 'lod2_ratio', 0.16) or 0.16),
            3: float(getattr(sprops, 'lod3_ratio', 0.064) or 0.064),
        }
        ok = False
        if getattr(prefs, 'enable_pymeshlab_automation', False):
            ok = utils.generate_lods_with_pymeshlab(context, dae_path, lods_dir, src, face_count, ratios)
        else:
            ok = utils.generate_lods_with_meshlabserver(self, context, dae_path, lods_dir, src, face_count, ratios)
        if not ok:
            self.report({'ERROR'}, "LOD generation failed.")
            return {'CANCELLED'}

        # Import LOD0–3 into LOD collection and reapply original materials
        lod_names = []
        for i in range(0, 4):
            lod_path = os.path.join(lods_dir, f"{base_label}_LOD{i}.dae")
            if not os.path.exists(lod_path):
                self.report({'ERROR'}, f"Missing {lod_path}")
                return {'CANCELLED'}
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
            lod.data.materials.clear()
            for m in original_mats:
                lod.data.materials.append(m)
            lod_names.append(lod.name)

        # Data Transfer (normals from LOD0) — do not add to LOD0 itself
        lod0_imp = bpy.data.objects.get(f"{base_label}_LOD0")
        if lod0_imp:
            for name in lod_names:
                if name.endswith('_LOD0'):
                    continue
                lod = bpy.data.objects.get(name)
                if not lod:
                    continue
                mod = lod.modifiers.new("DataTransfer", 'DATA_TRANSFER')
                mod.object = lod0_imp
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

        self.report({'INFO'}, f"Setup LODs complete. Objects placed in collection '{lod_coll_name}'.")
        return {'FINISHED'}

