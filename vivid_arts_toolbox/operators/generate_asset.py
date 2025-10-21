import bpy
import os

class VIVID_OT_generate_asset(bpy.types.Operator):
    bl_idname = "vivid.generate_asset"
    bl_label = "Generate Cinema Model"
    bl_description = "Creates a 'Cinema' collection and duplicates the _Optimized mesh as _Cinema."

    def execute(self, context):
        self.report({'INFO'}, "Starting Generate Cinema Model process...")
        optimized_collection = bpy.data.collections.get("Optimized")
        cinema_collection = bpy.data.collections.get("Cinema")

        if not cinema_collection:
            cinema_collection = bpy.data.collections.new("Cinema")
            bpy.context.scene.collection.children.link(cinema_collection)
            self.report({'INFO'}, "Created new collection: 'Cinema'.")

        optimized_mesh_obj = None
        cage_mesh_obj = None
        high_poly_obj = None

        # Find _Optimized, _Cage, and _HighPoly objects
        if optimized_collection:
            for obj in optimized_collection.objects:
                if obj.type == 'MESH':
                    if obj.name.endswith("_Optimized"):
                        optimized_mesh_obj = obj
                    elif obj.name.endswith("_Cage"):
                        cage_mesh_obj = obj
                    elif obj.name.endswith("_HighPoly"):
                        high_poly_obj = obj
                if optimized_mesh_obj and cage_mesh_obj and high_poly_obj:
                    break
        
        # Fallback search if not found in collection (or collection doesn't exist)
        # This ensures objects are found even if not in the 'Optimized' collection initially
        if not optimized_mesh_obj or not cage_mesh_obj or not high_poly_obj:
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    if obj.name.endswith("_Optimized") and not optimized_mesh_obj:
                        optimized_mesh_obj = obj
                    elif obj.name.endswith("_Cage") and not cage_mesh_obj:
                        cage_mesh_obj = obj
                    elif obj.name.endswith("_HighPoly") and not high_poly_obj:
                        high_poly_obj = obj
                if optimized_mesh_obj and cage_mesh_obj and high_poly_obj:
                    break # Break once all three are found

        # Error handling if required objects are not found
        if not optimized_mesh_obj:
            self.report({'ERROR'}, "No object ending with '_Optimized' found in scene. Please ensure your optimized mesh is correctly named.")
            return {'CANCELLED'}
        if not cage_mesh_obj:
            self.report({'ERROR'}, "No object ending with '_Cage' found in scene. Please ensure your cage mesh is correctly named.")
            return {'CANCELLED'}

        # (Removed FBX export; Generate Asset should not perform external file exports.)

        # Handle high_poly_texture_path initialization for clarity and warnings
        high_poly_texture_path = ""
        if high_poly_obj:
            # Iterate through materials and their nodes to find the diffuse texture
            for mat_slot in high_poly_obj.data.materials:
                if mat_slot.material: # Ensure the material slot actually has a material assigned
                    for node in mat_slot.material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            # Check for common diffuse texture naming conventions
                            if "_HighPoly_u0_v0_diffuse.png" in node.image.filepath or "_HighPoly_u0_v0_diffuse.exr" in node.image.filepath:
                                high_poly_texture_path = bpy.path.abspath(node.image.filepath)
                                self.report({'INFO'}, f"Found HighPoly diffuse texture: {high_poly_texture_path}")
                                break # Found the texture, exit inner loop
                        if high_poly_texture_path:
                            break # Found the texture, exit middle loop
                if high_poly_texture_path:
                    break # Found the texture, exit outer loop
        
            if not high_poly_texture_path:
                self.report({'WARNING'}, "No diffuse texture found for '_HighPoly' object. The BaseColor_Transfer_DLBC baker might not work as expected without it.")
        else:
            self.report({'WARNING'}, "No '_HighPoly' object found. The BaseColor_Transfer_DLBC baker might not work as expected without it.")
            high_poly_texture_path = "" # Ensure it's an empty string if not found

        # Duplicate and rename the Optimized mesh to _Cinema
        self.report({'INFO'}, "Duplicating Optimized mesh to _Cinema and moving to Cinema collection...")

        bpy.ops.object.select_all(action='DESELECT')
        optimized_mesh_obj.select_set(True)
        context.view_layer.objects.active = optimized_mesh_obj  # Set active for duplication

        bpy.ops.object.duplicate_move()  # Duplicate the selected object
        lod0_obj = context.active_object  # The duplicated object becomes the active object

        new_name = optimized_mesh_obj.name.replace("_Optimized", "_Cinema")
        lod0_obj.name = new_name  # Rename the duplicated object
        lod0_obj.data.name = new_name  # Rename the mesh data block

        # Link _Cinema to the Cinema collection and unlink from other collections if necessary
        if optimized_collection and lod0_obj.name in optimized_collection.objects:
            optimized_collection.objects.unlink(lod0_obj)
        if lod0_obj.name not in cinema_collection.objects:
            cinema_collection.objects.link(lod0_obj)

        self.report({'INFO'}, f"Generated Cinema mesh: {lod0_obj.name} in 'Cinema' collection.")
        self.report({'INFO'}, "Generate Cinema Model process completed.")
        return {'FINISHED'}

