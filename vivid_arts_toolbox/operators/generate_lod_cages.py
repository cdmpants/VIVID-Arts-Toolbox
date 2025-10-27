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
            global_strength = float(getattr(sprops, 'displace_cage_strength', 1.0)) if sprops else 1.0
            # Read per-LOD overrides for LOD1–LOD3 only; LOD0 uses global
            lod_strengths = {0: global_strength}
            for idx in (1, 2, 3):
                attr = f"displace_cage_strength_lod{idx}"
                try:
                    lod_strengths[idx] = float(getattr(sprops, attr)) if sprops and hasattr(sprops, attr) else global_strength
                except Exception:
                    lod_strengths[idx] = global_strength
        except Exception:
            global_strength = 1.0
            lod_strengths = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0}
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
        # If 'Bake only LOD0' is enabled, restrict cages to only LOD0
        only_lod0 = True
        try:
            sprops = getattr(context.scene, 'vivid_lod_props', None)
            only_lod0 = bool(getattr(sprops, 'bake_only_lod0', True))
        except Exception:
            only_lod0 = True
        if only_lod0:
            candidates = [o for o in candidates if o.name.endswith('_LOD0')]
        if not candidates:
            msg = "No base LODs found in 'LOD'."
            if only_lod0:
                msg = "Bake only LOD0 is enabled but no _LOD0 found in 'LOD'."
            self.report({'WARNING'}, msg)
            return {'CANCELLED'}

        created = 0
        for src in candidates:
            cage_name = f"{src.name}_Cage"
            # Remove any existing with same name from cage collection
            _delete_obj_in_cage(cage_name)

            # Duplicate robustly without relying on operators
            try:
                dup = src.copy()
                dup.data = src.data.copy()
                dup.matrix_world = src.matrix_world.copy()
            except Exception as e:
                self.report({'ERROR'}, f"Duplicate failed for {src.name}: {e}")
                continue
            dup.name = cage_name
            dup.data.name = cage_name
            # Add a Displace modifier using configured strength (per-LOD override)
            try:
                mod = dup.modifiers.new("Displace", 'DISPLACE')
                try:
                    # Determine LOD index from name suffix _LOD0.._LOD3
                    lod_idx = None
                    m = re.search(r"_LOD([0-3])$", src.name)
                    if m:
                        lod_idx = int(m.group(1))
                    strength = lod_strengths.get(lod_idx, global_strength) if lod_idx is not None else global_strength
                    mod.strength = strength
                except Exception:
                    pass
            except Exception:
                pass
            # Link only to cage_coll (new copy has no collections yet)
            try:
                cage_coll.objects.link(dup)
            except Exception:
                # Fallback: ensure not left orphaned
                try:
                    context.scene.collection.objects.link(dup)
                except Exception:
                    pass
            created += 1

        self.report({'INFO'}, f"Generated {created} LOD cage(s) in 'LOD_Cage'.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_generate_lod_cages)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_generate_lod_cages)
