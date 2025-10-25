import bpy
import re

class VIVID_OT_generate_lod_cages(bpy.types.Operator):
    bl_idname = "vivid.generate_lod_cages"
    bl_label = "Generate LOD Cages"
    bl_description = "Duplicate base LODs from 'LOD' into 'LOD_Cage' as *_Cage, replacing existing"

    def execute(self, context):
        # Read desired Displace strength from scene properties (default 1.0)
        try:
            sprops = getattr(context.scene, 'vivid_lod_props', None)
            disp_strength = float(getattr(sprops, 'displace_cage_strength', 1.0)) if sprops else 1.0
        except Exception:
            disp_strength = 1.0
        lod_coll = bpy.data.collections.get('LOD')
        if not lod_coll:
            self.report({'ERROR'}, "'LOD' collection not found.")
            return {'CANCELLED'}
        # Ensure destination collection
        cage_coll = bpy.data.collections.get('LOD_Cage')
        if not cage_coll:
            cage_coll = bpy.data.collections.new('LOD_Cage')
            context.scene.collection.children.link(cage_coll)

        # Helper: delete object by name in cage collection if exists
        def _delete_obj_in_cage(name):
            obj = bpy.data.objects.get(name)
            if obj and any(c is cage_coll for c in obj.users_collection):
                # Unlink from all collections, then remove datablock
                for c in list(obj.users_collection):
                    c.objects.unlink(obj)
                try:
                    bpy.data.objects.remove(obj, do_unlink=True)
                except Exception:
                    pass

        # Source LODs: names ending in _LOD0.._LOD3, exclude proxies/colliders
        base_lod_rx = re.compile(r"_LOD[0-3]$")
        candidates = [o for o in lod_coll.objects if o.type == 'MESH' and base_lod_rx.search(o.name) and ('ShadowProxy' not in o.name) and ('Collider' not in o.name)]
        if not candidates:
            self.report({'WARNING'}, "No base LODs found in 'LOD'.")
            return {'CANCELLED'}

        created = 0
        for src in candidates:
            cage_name = f"{src.name}_Cage"
            # Remove any existing with same name from cage collection
            _delete_obj_in_cage(cage_name)

            # Duplicate
            bpy.ops.object.select_all(action='DESELECT')
            src.select_set(True)
            context.view_layer.objects.active = src
            try:
                bpy.ops.object.duplicate_move()
            except Exception as e:
                self.report({'ERROR'}, f"Duplicate failed for {src.name}: {e}")
                continue
            dup = context.active_object
            dup.name = cage_name
            dup.data.name = cage_name
            # Add a Displace modifier using configured strength
            try:
                mod = dup.modifiers.new("Displace", 'DISPLACE')
                try:
                    mod.strength = disp_strength
                except Exception:
                    pass
            except Exception:
                pass
            # Unlink from all current collections, link only to cage_coll
            for c in list(dup.users_collection):
                c.objects.unlink(dup)
            cage_coll.objects.link(dup)
            created += 1

        self.report({'INFO'}, f"Generated {created} LOD cage(s) in 'LOD_Cage'.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_generate_lod_cages)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_generate_lod_cages)
