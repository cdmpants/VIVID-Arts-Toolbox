# vivid_arts_toolbox/operators/setup_lods.py

import bpy
import os
from bpy.props import BoolProperty
from .. import utils
from .. import preferences


# === VIVID: ShadowProxy naming helper ===
def _vat_make_shadowproxy_name(obj_name: str) -> str:
    import re
    m = re.search(r'(.*)(_LOD\d+)$', obj_name)
    if m:
        return f"{m.group(1)}_ShadowProxy{m.group(2)}"
    return f"{obj_name}_ShadowProxy"


class VIVID_OT_setup_lods(bpy.types.Operator):
    bl_idname = "vivid.setup_lods"
    bl_label = "Setup LODs"
    bl_description = "Generates collider meshes, exports LOD0 for external processing, imports and sets up other LODs."

    generate_shadow_proxies: BoolProperty(
        name="Generate ShadowProxies",
        default=True,
        description="Toggle creation of ShadowProxy meshes."
    )
    generate_collider: BoolProperty(
        name="Generate Collider",
        default=True,
        description="Toggle creation of collider meshes."
    )
    is_convex_collider: BoolProperty(
        name="Is Convex",
        default=False,
        description="If true, generates a _ConvexCollider; otherwise _MeshCollider."
    )

    def execute(self, context):
        self.report({'INFO'}, "Starting Setup LODs process...")

        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        asset_collection = bpy.data.collections.get("Asset")
        if not asset_collection:
            self.report({'ERROR'}, "Collection 'Asset' not found. Please run 'Generate Asset' first.")
            return {'CANCELLED'}

        # Locate LOD0
        lod0_obj = next((o for o in asset_collection.objects if o.type == 'MESH' and o.name.endswith("_LOD0")), None)
        if not lod0_obj:
            self.report({'ERROR'}, "No *_LOD0 object found in Asset collection.")
            return {'CANCELLED'}

        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}
        blend_dir = os.path.dirname(blend_filepath)
        lods_dir = os.path.join(blend_dir, "LODs")
        os.makedirs(lods_dir, exist_ok=True)

        # Save original materials
        original_mats = list(lod0_obj.data.materials)

        # === Step 1: Collider (optional) ===
        if self.generate_collider:
            self.report({'INFO'}, "Generating Collider...")
            bpy.ops.object.select_all(action='DESELECT')
            lod0_obj.select_set(True)
            context.view_layer.objects.active = lod0_obj
            bpy.ops.object.duplicate_move()
            collider_obj = context.active_object

            suffix = "_ConvexCollider" if self.is_convex_collider else "_MeshCollider"
            new_name = lod0_obj.name.replace("_LOD0", suffix)
            collider_obj.name = new_name
            collider_obj.data.name = new_name
            if collider_obj.name not in asset_collection.objects:
                asset_collection.objects.link(collider_obj)

            dec = collider_obj.modifiers.new("Decimate_Collider", 'DECIMATE')
            dec.ratio = 0.05
            dec.use_collapse_triangulate = True
        else:
            self.report({'INFO'}, "Skipping Collider.")

        # === Step 2: Export LOD0 with TEMP material ===
        self.report({'INFO'}, "Preparing temporary Color Grid for LOD0 export...")
        temp_img = bpy.data.images.new(
            f"{lod0_obj.name}_ColorGrid",
            width=64,
            height=64,
            alpha=True,
            float_buffer=False
        )
        temp_img.generated_type = 'COLOR_GRID'
        temp_mat = bpy.data.materials.new(f"{lod0_obj.name}_TempExportMat")
        temp_mat.use_nodes = True
        nt = temp_mat.node_tree
        nodes = nt.nodes
        links = nt.links
        for n in list(nodes):
            nodes.remove(n)
        out = nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (0, 0)
        tex = nodes.new("ShaderNodeTexImage"); tex.location = (-300, 0); tex.image = temp_img
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        lod0_obj.data.materials.clear()
        lod0_obj.data.materials.append(temp_mat)

        # Export to DAE (force visibility)
        dae_path = os.path.join(lods_dir, f"{lod0_obj.name}.dae")
        prev_vis = lod0_obj.hide_viewport
        prev_sel = lod0_obj.select_get()
        try:
            lod0_obj.hide_set(False)
        except:
            lod0_obj.hide_viewport = False
        bpy.ops.object.select_all(action='DESELECT')
        lod0_obj.select_set(True)
        context.view_layer.objects.active = lod0_obj
        bpy.ops.wm.collada_export(filepath=dae_path, selected=True, apply_modifiers=True)
        try:
            lod0_obj.hide_set(prev_vis)
        except:
            lod0_obj.hide_viewport = prev_vis
        lod0_obj.select_set(prev_sel)
        self.report({'INFO'}, f"Exported {dae_path}")

        # === Step 3: Run MeshLab/PyMeshLab ===
        ok = False
        face_count = len(lod0_obj.data.polygons)
        if prefs.enable_pymeshlab_automation:
            ok = utils.generate_lods_with_pymeshlab(context, dae_path, lods_dir, lod0_obj, face_count)
        else:
            ok = utils.generate_lods_with_meshlabserver(self, context, dae_path, lods_dir, lod0_obj, face_count)
        if not ok:
            self.report({'ERROR'}, "LOD generation failed.")
            return {'CANCELLED'}

        # === Step 4: Import LOD1–3 ===
        base = lod0_obj.name.replace("_LOD0", "")
        lod_names = []
        for i in range(1, 4):
            lod_path = os.path.join(lods_dir, f"{base}_LOD{i}.dae")
            if not os.path.exists(lod_path):
                self.report({'ERROR'}, f"Missing {lod_path}")
                return {'CANCELLED'}
            bpy.ops.wm.collada_import(filepath=lod_path, import_units=True, find_chains=True)
            lod = context.selected_objects[0] if context.selected_objects else None
            if not lod:
                continue
            lod.name = f"{base}_LOD{i}"
            lod.data.name = f"{base}_LOD{i}"
            lod.rotation_euler = (0, 0, 0)
            lod.rotation_quaternion = (1, 0, 0, 0)
            bpy.ops.object.shade_smooth()
            # Unlink from other collections
            for col in list(lod.users_collection):
                if col != asset_collection:
                    col.objects.unlink(lod)
            if asset_collection not in lod.users_collection:
                asset_collection.objects.link(lod)
            # Assign original mats
            lod.data.materials.clear()
            for m in original_mats:
                lod.data.materials.append(m)
            lod_names.append(lod.name)

        # === Step 5: Restore LOD0 materials now ===
        lod0_obj.data.materials.clear()
        for m in original_mats:
            lod0_obj.data.materials.append(m)

        # === Step 6: Data Transfer mods ===
        for name in lod_names:
            lod = bpy.data.objects.get(name)
            if not lod:
                continue
            mod = lod.modifiers.new("DataTransfer", 'DATA_TRANSFER')
            mod.object = lod0_obj
            mod.use_loop_data = True
            mod.data_types_loops = {'CUSTOM_NORMAL'}
            mod.loop_mapping = 'POLYINTERP_LNORPROJ'

        # === Step 7: ShadowProxies ===
        if self.generate_shadow_proxies:
            for src in [lod0_obj] + [bpy.data.objects.get(n) for n in lod_names]:
                if not src:
                    continue
                bpy.ops.object.select_all(action='DESELECT')
                src.select_set(True)
                context.view_layer.objects.active = src
                bpy.ops.object.duplicate_move()
                sp = context.active_object
                sp.name = _vat_make_shadowproxy_name(src.name)
                sp.data.name = _vat_make_shadowproxy_name(src.data.name)
                # Unlink from other collections
                for col in list(sp.users_collection):
                    if col != asset_collection:
                        col.objects.unlink(sp)
                if asset_collection not in sp.users_collection:
                    asset_collection.objects.link(sp)
                dec = sp.modifiers.new("Decimate_ShadowProxy", 'DECIMATE')
                dec.ratio = 0.2
                dec.use_collapse_triangulate = True

        # === Step 8: Rename UV layers ===
        for o in asset_collection.objects:
            if o.type == 'MESH' and o.data.uv_layers:
                uvs = o.data.uv_layers
                if len(uvs) > 0:
                    uvs[0].name = 'UVMap'
                if len(uvs) > 1:
                    uvs[1].name = 'Lightmap'

        # === Step 9: Cleanup temp mat/img ===
        if temp_mat.name in bpy.data.materials:
            bpy.data.materials.remove(temp_mat, do_unlink=True)
        if temp_img.name in bpy.data.images:
            bpy.data.images.remove(temp_img, do_unlink=True)

        self.report({'INFO'}, "Setup LODs complete.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_setup_lods)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_setup_lods)

