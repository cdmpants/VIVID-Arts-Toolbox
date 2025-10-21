import bpy
import re


class VIVID_OT_create_cinema_variant(bpy.types.Operator):
    bl_idname = "vivid.create_cinema_variant"
    bl_label = "Create Cinema Variant"
    bl_description = "Duplicates the 'Cinema' collection to the next available variant (Cinema_Var#) and renames the _Cinema object accordingly."

    def execute(self, context):
        cinema_coll = bpy.data.collections.get("Cinema")
        if not cinema_coll:
            self.report({'ERROR'}, "Collection 'Cinema' not found. Generate Cinema Model first.")
            return {'CANCELLED'}

        # Determine next variant index
        existing = [c.name for c in bpy.data.collections if c.name.startswith("Cinema_Var")]
        next_idx = 1
        pat = re.compile(r"Cinema_Var(\d+)")
        for name in existing:
            m = pat.fullmatch(name)
            if m:
                next_idx = max(next_idx, int(m.group(1)) + 1)

        var_name = f"Cinema_Var{next_idx}"
        new_coll = bpy.data.collections.new(var_name)
        context.scene.collection.children.link(new_coll)

        # Duplicate contents of Cinema collection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in cinema_coll.objects:
            obj.select_set(True)
        if not cinema_coll.objects:
            self.report({'ERROR'}, "Cinema collection is empty.")
            return {'CANCELLED'}

        context.view_layer.objects.active = cinema_coll.objects[0]
        bpy.ops.object.duplicate_move()
        dup_objs = [o for o in context.selected_objects]

        # Link duplicates to new collection and unlink elsewhere
        for o in dup_objs:
            for col in list(o.users_collection):
                col.objects.unlink(o)
            new_coll.objects.link(o)

        # Rename the _Cinema object to _Cinema_Var# and data as well
        for o in dup_objs:
            if o.type == 'MESH' and o.name.endswith("_Cinema"):
                base = o.name[:-len("_Cinema")]
                new_name = f"{base}_Cinema_Var{next_idx}"
                o.name = new_name
                o.data.name = new_name

        self.report({'INFO'}, f"Created variant collection '{var_name}'.")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_create_cinema_variant)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_create_cinema_variant)
