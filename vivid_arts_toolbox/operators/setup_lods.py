import bpy

# === VIVID: ShadowProxy naming helper ===
def _vat_make_shadowproxy_name(obj_name: str) -> str:
    """Insert '_ShadowProxy' immediately before the trailing _LOD suffix if present.
    Examples:
        'KAT_GroundFormation_11_LOD0' -> 'KAT_GroundFormation_11_ShadowProxy_LOD0'
        'SomeMesh' -> 'SomeMesh_ShadowProxy'
    """
    import re
    m = re.search(r'(.*)(_LOD\d+)$', obj_name)
    if m:
        return f"{m.group(1)}_ShadowProxy{m.group(2)}"
    return f"{obj_name}_ShadowProxy"

import os

from bpy.props import BoolProperty
from .. import utils
from .. import preferences

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

        lod0_obj = None
        for obj in asset_collection.objects:
            if obj.type == 'MESH' and obj.name.endswith("_LOD0"):
                lod0_obj = obj
                break
        if not lod0_obj:
            self.report({'ERROR'}, "No object ending with '_LOD0' found in 'Asset' collection. Please run 'Generate Asset' first.")
            return {'CANCELLED'}

        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}
        blend_dir = os.path.dirname(blend_filepath)
        lods_dir = os.path.join(blend_dir, "LODs")
        os.makedirs(lods_dir, exist_ok=True)

        if self.generate_collider:
            self.report({'INFO'}, "Step 1: Generating Collider mesh...")

            bpy.ops.object.select_all(action='DESELECT')
            lod0_obj.select_set(True)
            context.view_layer.objects.active = lod0_obj

            bpy.ops.object.duplicate_move()
            collider_obj = context.active_object

            collider_suffix = "_ConvexCollider" if self.is_convex_collider else "_MeshCollider"
            new_collider_name = lod0_obj.name.replace("_LOD0", collider_suffix)
            collider_obj.name = new_collider_name
            collider_obj.data.name = new_collider_name

            if collider_obj.name not in asset_collection.objects:
                asset_collection.objects.link(collider_obj)

            decimate_mod = collider_obj.modifiers.new(name="Decimate_Collider", type='DECIMATE')
            decimate_mod.ratio = 0.05
            decimate_mod.use_collapse_triangulate = True

            self.report({'INFO'}, f"Generated Collider: {collider_obj.name}")
        else:
            self.report({'INFO'}, "Skipping Collider generation as requested.")

        self.report({'INFO'}, "Step 2: Exporting LOD0 as DAE for LOD processing...")
        bpy.ops.object.select_all(action='DESELECT')
        lod0_obj.select_set(True)
        context.view_layer.objects.active = lod0_obj

        lod0_dae_filepath = os.path.join(lods_dir, f"{lod0_obj.name}.dae")
        bpy.ops.wm.collada_export(
            filepath=lod0_dae_filepath,
            selected=True,
            apply_modifiers=True,
        )
        self.report({'INFO'}, f"Exported LOD0 DAE: {lod0_dae_filepath}")

        lod_generation_successful = False
        initial_face_count = len(lod0_obj.data.polygons)

        if prefs.enable_pymeshlab_automation:
            # PyMeshLab does not require operator for reporting, it uses context directly.
            lod_generation_successful = utils.generate_lods_with_pymeshlab(context, lod0_dae_filepath, lods_dir, lod0_obj, initial_face_count)
        else:
            # Pass 'self' (the operator instance) for reporting
            lod_generation_successful = utils.generate_lods_with_meshlabserver(self, context, lod0_dae_filepath, lods_dir, lod0_obj, initial_face_count)
            if not lod_generation_successful:
                self.report({'WARNING'}, "LOD generation requires manual MeshLab processing or a correct 'MeshLab Server Path' in preferences.")
                self.report({'WARNING'}, "Please manually use MeshLab to import LOD0.dae, generate LOD1, LOD2, and LOD3, and save them as separate DAE files in the 'LODs' folder.")
                self.report({'WARNING'}, "Expected files: YOURASSETNAME_LOD1.dae, YOURASSETNAME_LOD2.dae, YOURASSETNAME_LOD3.dae")
                return {'CANCELLED'}

        if not lod_generation_successful:
            self.report({'ERROR'}, "LOD generation failed. Check messages above for details.")
            return {'CANCELLED'}

        self.report({'INFO'}, "Step 4: Importing LOD1, LOD2, LOD3 from LOD generation output...")
        lod_names = []
        original_base_name = lod0_obj.name.replace("_LOD0", "")
        
        for i in range(1, 4): 
            lod_suffix = f"_LOD{i}"
            lod_file_name = f"{original_base_name}{lod_suffix}.dae"
            lod_filepath = os.path.join(lods_dir, lod_file_name)

            if not os.path.exists(lod_filepath):
                self.report({'ERROR'}, f"LOD file not found: {lod_filepath}. LOD generation (automated or manual) might have failed.")
                return {'CANCELLED'}

            bpy.ops.wm.collada_import(
                filepath=lod_filepath,
                import_units=True,
                find_chains=True,
            )
            imported_lod_obj = context.selected_objects[0] if context.selected_objects else None
            if imported_lod_obj:
                imported_lod_obj.name = f"{original_base_name}{lod_suffix}"
                imported_lod_obj.data.name = f"{original_base_name}{lod_suffix}"

                imported_lod_obj.rotation_euler = (0, 0, 0)
                imported_lod_obj.rotation_quaternion = (1, 0, 0, 0)

                bpy.ops.object.shade_smooth()

                if imported_lod_obj.users_collection:
                    for col in imported_lod_obj.users_collection:
                        if col != asset_collection:
                            col.objects.unlink(imported_lod_obj)
                if imported_lod_obj.name not in asset_collection.objects:
                    asset_collection.objects.link(imported_lod_obj)

                if lod0_obj.data.materials:
                    imported_lod_obj.data.materials.clear()
                    for mat_slot in lod0_obj.data.materials:
                        if hasattr(mat_slot, 'material'):
                            material_to_append = mat_slot.material
                        else:
                            material_to_append = mat_slot 
                        if material_to_append:
                            imported_lod_obj.data.materials.append(material_to_append)
                        else:
                            self.report({'WARNING'}, f"Skipping empty material slot from LOD0 for {imported_lod_obj.name}.")
                else:
                    self.report({'WARNING'}, "LOD0 has no materials. Skipping material assignment to LODs.")
                
                lod_names.append(imported_lod_obj.name)
                self.report({'INFO'}, f"Imported and set up: {imported_lod_obj.name}")
            else:
                self.report({'ERROR'}, f"Failed to import {lod_file_name}.")
                return {'CANCELLED'}

        self.report({'INFO'}, "Step 5: Adding Data Transfer modifiers to LOD1, LOD2, LOD3...")
        bpy.ops.object.select_all(action='DESELECT')

        for i in range(1, 4):
            lod_obj_name = f"{original_base_name}_LOD{i}"
            lod_obj = bpy.data.objects.get(lod_obj_name)

            if lod_obj:
                lod_obj.select_set(True)
                context.view_layer.objects.active = lod_obj

                data_transfer_mod = lod_obj.modifiers.new(name="DataTransfer", type='DATA_TRANSFER')
                data_transfer_mod.object = lod0_obj
                data_transfer_mod.use_loop_data = True
                data_transfer_mod.data_types_loops = {'CUSTOM_NORMAL'}
                data_transfer_mod.loop_mapping = 'POLYINTERP_LNORPROJ'

                self.report({'INFO'}, f"Added Data Transfer to {lod_obj.name}.")
                bpy.ops.object.select_all(action='DESELECT')
            else:
                self.report({'WARNING'}, f"Could not find {lod_obj_name} for Data Transfer. Skipping.")

        if self.generate_shadow_proxies:
            self.report({'INFO'}, "Step 6: Generating ShadowProxy meshes...")
            all_lods_to_process = [lod0_obj] + [bpy.data.objects.get(name) for name in lod_names]
            
            for original_lod_obj in all_lods_to_process:
                if original_lod_obj:
                    bpy.ops.object.select_all(action='DESELECT')
                    original_lod_obj.select_set(True)
                    context.view_layer.objects.active = original_lod_obj

                    bpy.ops.object.duplicate_move()
                    shadow_proxy_obj = context.active_object

                    # FIXED: correct naming — insert _ShadowProxy before _LOD#
                    shadow_proxy_obj.name = _vat_make_shadowproxy_name(original_lod_obj.name)
                    shadow_proxy_obj.data.name = _vat_make_shadowproxy_name(original_lod_obj.data.name)

                    if shadow_proxy_obj.name not in asset_collection.objects:
                        asset_collection.objects.link(shadow_proxy_obj)

                    # Keep decimate for proxies
                    decimate_mod_sp = shadow_proxy_obj.modifiers.new(name="Decimate_ShadowProxy", type='DECIMATE')
                    decimate_mod_sp.ratio = 0.2
                    decimate_mod_sp.use_collapse_triangulate = True

                    # REMOVED: Displace modifier (creation/strength) — no longer used

                    self.report({'INFO'}, f"Generated ShadowProxy: {shadow_proxy_obj.name}")
        else:
            self.report({'INFO'}, "Skipping ShadowProxy generation as requested.")

        self.report({'INFO'}, "Step 7: Renaming UV maps (first to UVMap, second to Lightmap)...")
        for obj in asset_collection.objects:
            if obj.type == 'MESH' and obj.data and obj.data.uv_layers:
                uv_layers = obj.data.uv_layers
                if len(uv_layers) > 0 and uv_layers[0].name != 'UVMap':
                    uv_layers[0].name = 'UVMap'
                    self.report({'INFO'}, f"Renamed first UV layer to UVMap for {obj.name}.")
                if len(uv_layers) > 1 and uv_layers[1].name != 'Lightmap':
                    uv_layers[1].name = 'Lightmap'
                    self.report({'INFO'}, f"Renamed second UV layer to Lightmap for {obj.name}.")

        self.report({'INFO'}, "Setup LODs process completed.")
        return {'FINISHED'}

