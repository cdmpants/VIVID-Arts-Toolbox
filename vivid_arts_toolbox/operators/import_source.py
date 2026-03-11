import bpy
import os
from bpy.types import Operator
import re

from .. import utils


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


class VIVID_OT_setup_normals_mesh(Operator):
    bl_idname = "vivid.setup_normals_mesh"
    bl_label = "Setup Normals Mesh"
    bl_description = "Duplicate the Optimized mesh to _Normal, decimate it, and transfer custom normals back onto Optimized"

    def execute(self, context):
        dec_ratio = float(getattr(context.scene, 'vivid_normals_decimate_ratio', 0.16) or 0.16)
        dec_ratio = max(0.0, min(1.0, dec_ratio))

        def _iter_optimized_targets():
            # Prefer the dedicated Optimized collection if present
            opt_coll = bpy.data.collections.get('Optimized')
            if opt_coll:
                for o in list(opt_coll.objects):
                    if o and o.type == 'MESH' and isinstance(o.name, str) and o.name.endswith('_Optimized'):
                        yield o
                return
            # Fallback: scan all objects
            for o in bpy.data.objects:
                if o and o.type == 'MESH' and isinstance(o.name, str) and o.name.endswith('_Optimized'):
                    yield o

        optimized_objs = list(_iter_optimized_targets())
        if not optimized_objs:
            self.report({'ERROR'}, "No *_Optimized mesh objects found.")
            return {'CANCELLED'}

        created = 0
        updated = 0
        skipped = 0
        for obj in optimized_objs:
            base = re.sub(r'_Optimized$', '', obj.name)
            normal_name = f"{base}_Normal"
            normal_obj = bpy.data.objects.get(normal_name)

            if normal_obj and normal_obj.type != 'MESH':
                skipped += 1
                continue

            # Create *_Normal if missing
            if not normal_obj:
                normal_obj = obj.copy()
                # Mesh-linked duplicate: share the same mesh datablock as *_Optimized
                normal_obj.data = obj.data
                normal_obj.name = normal_name
                try:
                    normal_obj.data.name = normal_name
                except Exception:
                    pass

                # Link to the same collection(s) as optimized when possible
                linked = False
                try:
                    for coll in getattr(obj, 'users_collection', []) or []:
                        coll.objects.link(normal_obj)
                        linked = True
                        break
                except Exception:
                    linked = False
                if not linked:
                    try:
                        context.scene.collection.objects.link(normal_obj)
                    except Exception:
                        pass
                created += 1
            else:
                updated += 1

            # Ensure *_Normal is mesh-linked to the Optimized mesh
            try:
                if getattr(normal_obj, 'data', None) is not obj.data:
                    normal_obj.data = obj.data
            except Exception:
                pass

            # Ensure Decimate modifier (Collapse) on *_Normal
            try:
                dec = normal_obj.modifiers.get("Decimate_Normal")
                if not dec:
                    dec = normal_obj.modifiers.new("Decimate_Normal", 'DECIMATE')
                try:
                    dec.decimate_type = 'COLLAPSE'
                except Exception:
                    pass
                dec.ratio = dec_ratio
            except Exception:
                skipped += 1
                continue

            # Ensure Data Transfer modifier on *_Optimized
            try:
                mod = obj.modifiers.get("DataTransfer_Normals")
                if not mod:
                    mod = obj.modifiers.new("DataTransfer_Normals", 'DATA_TRANSFER')
                mod.object = normal_obj
                mod.use_loop_data = True
                mod.data_types_loops = {'CUSTOM_NORMAL'}
                # Nearest Face Interpolated (instead of Projected Face Interpolated)
                mod.loop_mapping = 'POLYINTERP_NEAREST'
            except Exception:
                skipped += 1
                continue

        self.report({'INFO'}, f"Setup Normals Mesh complete: created {created}, updated {updated}, skipped {skipped}.")
        return {'FINISHED'}


class VIVID_OT_setup_color_grid(Operator):
    bl_idname = "vivid.setup_color_grid"
    bl_label = "Setup Color Grid"
    bl_description = "Remove materials from *_Optimized mesh(es) and assign a Grid material using ColorGrid.png"

    def execute(self, context):
        def _iter_optimized_targets():
            opt_coll = bpy.data.collections.get('Optimized')
            if opt_coll:
                for o in list(opt_coll.objects):
                    if o and o.type == 'MESH' and isinstance(o.name, str) and o.name.endswith('_Optimized'):
                        yield o
                return
            for o in bpy.data.objects:
                if o and o.type == 'MESH' and isinstance(o.name, str) and o.name.endswith('_Optimized'):
                    yield o

        targets = list(_iter_optimized_targets())
        if not targets:
            self.report({'ERROR'}, "No *_Optimized mesh objects found.")
            return {'CANCELLED'}

        img_path = str(utils.resource_or_legacy("ColorGrid.png"))
        if not os.path.isfile(img_path):
            self.report({'ERROR'}, f"Missing resource: {img_path}")
            return {'CANCELLED'}

        try:
            img = bpy.data.images.load(img_path, check_existing=True)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load ColorGrid.png: {e}")
            return {'CANCELLED'}

        mat = bpy.data.materials.get("Grid")
        if not mat:
            mat = bpy.data.materials.new("Grid")
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links
        for n in list(nodes):
            nodes.remove(n)
        out = nodes.new("ShaderNodeOutputMaterial")
        out.location = (300, 0)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-300, 0)
        tex.image = img
        links.new(tex.outputs.get("Color"), bsdf.inputs.get("Base Color"))
        links.new(bsdf.outputs.get("BSDF"), out.inputs.get("Surface"))

        updated = 0
        skipped = 0
        for obj in targets:
            me = getattr(obj, 'data', None)
            if not me:
                skipped += 1
                continue
            try:
                me.materials.clear()
                me.materials.append(mat)
                updated += 1
            except Exception:
                skipped += 1

        self.report({'INFO'}, f"Setup Color Grid complete: updated {updated}, skipped {skipped}.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_import_simplified)
    bpy.utils.register_class(VIVID_OT_setup_normals_mesh)
    bpy.utils.register_class(VIVID_OT_setup_color_grid)


def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_setup_color_grid)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(VIVID_OT_setup_normals_mesh)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(VIVID_OT_import_simplified)
    except Exception:
        pass
