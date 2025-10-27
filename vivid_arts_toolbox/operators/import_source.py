import bpy
import os
from bpy.types import Operator
import re


def _blend_dir():
    return bpy.path.abspath("//")


def _blend_base_noext():
    p = bpy.data.filepath
    return os.path.splitext(os.path.basename(p))[0] if p else "untitled"


def _ensure_collection(name: str):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        try:
            bpy.context.scene.collection.children.link(col)
        except Exception:
            pass
    return col


def _delete_default_collection_if_empty():
    col = bpy.data.collections.get("Collection")
    if not col:
        return
    try:
        if len(col.objects) == 0 and len(col.children) == 0:
            # Only unlink from scene if linked
            try:
                bpy.context.scene.collection.children.unlink(col)
            except Exception:
                pass
            bpy.data.collections.remove(col)
    except Exception:
        pass


class VIVID_OT_import_simplified(Operator):
    bl_idname = "vivid.import_simplified"
    bl_label = "Import Simplified Model"
    bl_description = "Import <blendname>_Simplified.fbx next to the .blend; optionally treat as Optimized"

    def execute(self, context):
        as_optimized = bool(getattr(context.scene, 'vivid_import_simplified_as_optimized', True))
        base = _blend_base_noext()
        folder = _blend_dir()
        fbx_path = os.path.join(folder, f"{base}_Simplified.fbx")
        if not os.path.isfile(fbx_path):
            self.report({'ERROR'}, f"Not found: {fbx_path}")
            return {'CANCELLED'}

        # Track objects before import
        before = set(bpy.data.objects)
        # Import FBX
        try:
            bpy.ops.import_scene.fbx(filepath=fbx_path, automatic_bone_orientation=True)
        except Exception as e:
            self.report({'ERROR'}, f"FBX import failed: {e}")
            return {'CANCELLED'}

        after = set(bpy.data.objects)
        new_objs = [o for o in after - before]
        if not new_objs:
            self.report({'WARNING'}, "No new objects detected after import")
            return {'FINISHED'}

        target_name = "Optimized" if as_optimized else "Simplified"
        # Desired base object name derived from FBX filename (without extension)
        fbx_base = os.path.splitext(os.path.basename(fbx_path))[0]  # e.g., Base_Simplified
        desired_base = fbx_base
        if as_optimized:
            # Replace trailing _Simplified (case-insensitive) with _Optimized; fallback to append
            if re.search(r"_Simplified$", desired_base, flags=re.IGNORECASE):
                desired_base = re.sub(r"_Simplified$", "_Optimized", desired_base, flags=re.IGNORECASE)
            elif not desired_base.endswith("_Optimized"):
                desired_base = f"{desired_base}_Optimized"
        target_col = _ensure_collection(target_name)

        for obj in new_objs:
            try:
                # Clear rotations
                obj.rotation_euler = (0.0, 0.0, 0.0)
            except Exception:
                pass
            # Link to target collection
            try:
                if obj.name not in target_col.objects:
                    target_col.objects.link(obj)
            except Exception:
                pass
            # Unlink from other scene root collections if applicable
            try:
                # Some importers create their own collections; keep simple: ensure in target
                for coll in list(obj.users_collection):
                    if coll is not target_col:
                        try:
                            coll.objects.unlink(obj)
                        except Exception:
                            pass
            except Exception:
                pass
            # Enforce imported object name based on FBX filename (primary for meshes)
            try:
                if obj.type == 'MESH':
                    obj.name = desired_base
            except Exception:
                pass

        _delete_default_collection_if_empty()

        # Create a data-linked Cage duplicate for the Optimized mesh (hidden, with Displace modifier)
        if as_optimized:
            try:
                opt_obj = bpy.data.objects.get(desired_base)
                if opt_obj and opt_obj.type == 'MESH':
                    cage_name = desired_base[:-10] + '_Cage' if desired_base.endswith('_Optimized') else desired_base + '_Cage'
                    if not bpy.data.objects.get(cage_name):
                        cage_obj = opt_obj.copy()
                        cage_obj.data = opt_obj.data  # share mesh data (data-linked)
                        cage_obj.name = cage_name
                        # Link to the same collection as the optimized object when possible
                        linked = False
                        try:
                            for coll in getattr(opt_obj, 'users_collection', []) or []:
                                coll.objects.link(cage_obj)
                                linked = True
                                break
                        except Exception:
                            linked = False
                        if not linked:
                            try:
                                bpy.context.scene.collection.objects.link(cage_obj)
                            except Exception:
                                pass
                        # Hide in viewport
                        try:
                            if hasattr(cage_obj, 'hide_set'):
                                cage_obj.hide_set(True)
                            else:
                                cage_obj.hide_viewport = True
                        except Exception:
                            pass
                        # Add a Displace modifier with default settings
                        try:
                            cage_obj.modifiers.new(name='Displace', type='DISPLACE')
                        except Exception:
                            pass
            except Exception:
                pass

        self.report({'INFO'}, f"Imported {len(new_objs)} object(s) to '{target_name}' collection")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_import_simplified)


def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_import_simplified)
    except Exception:
        pass
