import bpy
import os

class VIVID_OT_export_asset(bpy.types.Operator):
    bl_idname = "vivid.export_asset"
    bl_label = "Export Asset"
    bl_description = "Exports all objects in the 'Asset' collection as a single FBX file."

    def execute(self, context):
        self.report({'INFO'}, "Starting Export Asset process...")

        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        asset_dest_path = prefs.asset_destination_path
        if not asset_dest_path:
            self.report({'ERROR'}, "Asset Destination path not set in Addon Preferences.")
            return {'CANCELLED'}

        asset_collection = bpy.data.collections.get("Asset")
        if not asset_collection:
            self.report({'ERROR'}, "Collection 'Asset' not found. Please generate asset and LODs first.")
            return {'CANCELLED'}

        export_file_name = "ExportedAsset"
        for obj in asset_collection.objects:
            if obj.name.endswith("_LOD0"):
                export_file_name = obj.name.replace("_LOD0", "")
                break
        
        export_filepath = os.path.join(asset_dest_path, f"{export_file_name}.fbx")

        self.report({'INFO'}, f"Step 1: Exporting all objects in 'Asset' collection to {export_filepath}...")

        bpy.ops.object.select_all(action='DESELECT')
        for obj in asset_collection.objects:
            if obj.type == 'MESH':
                obj.select_set(True)

        if not context.selected_objects:
            self.report({'ERROR'}, "No mesh objects found in 'Asset' collection to export.")
            return {'CANCELLED'}

        context.view_layer.objects.active = context.selected_objects[0]

        bpy.ops.export_scene.fbx(
            filepath=export_filepath,
            use_selection=True,
            object_types={'MESH'},
            bake_space_transform=True,
            # Removed 'apply_scale' as it's unrecognized in Blender 4.3+
            use_mesh_modifiers=True,
            mesh_smooth_type='FACE',
            axis_forward='-Z',
            axis_up='Y'
        )
        self.report({'INFO'}, f"Asset exported to: {export_filepath}")
        self.report({'INFO'}, "Export Asset process completed.")
        return {'FINISHED'}

