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

        # Find _Optimized mesh
        optimized_mesh_obj = None
        if optimized_collection:
            for obj in optimized_collection.objects:
                if obj.type == 'MESH' and obj.name.endswith("_Optimized"):
                    optimized_mesh_obj = obj
                    break
        if not optimized_mesh_obj:
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.name.endswith("_Optimized"):
                    optimized_mesh_obj = obj
                    break

        if not optimized_mesh_obj:
            self.report({'ERROR'}, "No object ending with '_Optimized' found in scene. Please ensure your optimized mesh is correctly named.")
            return {'CANCELLED'}

        # Compute base and target names
        base = optimized_mesh_obj.name[:-10] if optimized_mesh_obj.name.endswith('_Optimized') else optimized_mesh_obj.name
        cinema_name = f"{base}_Cinema"

        # Remove any existing Cinema object with the same name for idempotence
        existing = bpy.data.objects.get(cinema_name)
        if existing:
            try:
                # Unlink from all collections first
                for coll in list(existing.users_collection):
                    try:
                        coll.objects.unlink(existing)
                    except Exception:
                        pass
                bpy.data.objects.remove(existing, do_unlink=True)
            except Exception:
                pass

        # Create a duplicated object with duplicated mesh data (independent copy)
        new_obj = optimized_mesh_obj.copy()
        try:
            new_obj.data = optimized_mesh_obj.data.copy()
        except Exception:
            new_obj.data = optimized_mesh_obj.data
        new_obj.name = cinema_name
        try:
            new_obj.data.name = cinema_name
        except Exception:
            pass

        # Link to Cinema collection
        try:
            cinema_collection.objects.link(new_obj)
        except Exception:
            # Fallback to scene root
            try:
                bpy.context.scene.collection.objects.link(new_obj)
            except Exception:
                pass

        # Apply all modifiers on the new Cinema object (do not affect Optimized)
        try:
            if context.view_layer.objects.get(new_obj.name) is None:
                # Ensure it's in the active view layer; linking above should handle this.
                pass
        except Exception:
            pass
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            pass
        try:
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj
        except Exception:
            pass

        failed = []
        try:
            for m in list(getattr(new_obj, 'modifiers', []) or []):
                try:
                    bpy.ops.object.modifier_apply(modifier=m.name)
                except Exception:
                    failed.append(m.name)
        except Exception:
            pass
        if failed:
            self.report({'WARNING'}, f"Some modifiers could not be applied on {cinema_name}: {', '.join(failed)}")

        self.report({'INFO'}, f"Generated Cinema mesh: {cinema_name} in 'Cinema' collection.")
        return {'FINISHED'}

