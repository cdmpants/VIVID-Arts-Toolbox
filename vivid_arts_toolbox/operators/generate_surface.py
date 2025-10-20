import bpy
from bpy.props import FloatProperty


def _replace_final_suffix(name: str, new_suffix: str) -> str:
    """Replace the trailing _Suffix (after last underscore) with new_suffix.
    If no underscore is present, append new_suffix.
    new_suffix should include the leading underscore, e.g. '_Optimized'."""
    if '_' in name:
        base, _ = name.rsplit('_', 1)
        return f"{base}{new_suffix}"
    return f"{name}{new_suffix}"


class VIVID_OT_generate_surface(bpy.types.Operator):
    bl_idname = "vivid.generate_surface"
    bl_label = "Generate Surface"
    bl_description = "Create a plane at the 3D cursor with explicit X/Y dimensions, then add Subdivision + Shrinkwrap modifiers to conform it."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        target = context.active_object
        if not target or target.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object to generate the surface against.")
            return {'CANCELLED'}

        # Create plane at cursor
        cursor_loc = context.scene.cursor.location.copy()
        bpy.ops.mesh.primitive_plane_add(size=2.0, align='WORLD', location=cursor_loc)
        plane = context.active_object

        # Name the plane based on target name -> replace final suffix with _Optimized
        new_name = _replace_final_suffix(target.name, "_Optimized")
        plane.name = new_name
        plane.data.name = new_name

        # Scale plane to desired explicit dimensions (primitive plane is 2x2 by default)
        dim_x = float(getattr(self, 'dim_x', getattr(context.scene, 'vivid_surface_dim_x', 2.0)))
        dim_y = float(getattr(self, 'dim_y', getattr(context.scene, 'vivid_surface_dim_y', 2.0)))
        plane.scale.x = max(dim_x, 0.01) / 2.0
        plane.scale.y = max(dim_y, 0.01) / 2.0

        # Ensure it lives only in an 'Optimized' collection
        coll_name = "Optimized"
        # Always create a fresh 'Optimized' collection (Blender will uniquify the name if it exists)
        optimized_coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(optimized_coll)

        # Link and then unlink from any other collections including scene root
        optimized_coll.objects.link(plane)
        for c in list(plane.users_collection):
            if c != optimized_coll:
                try:
                    c.objects.unlink(plane)
                except Exception:
                    pass

        # Modifiers
        # 1) Subdivision (Simple) levels 3 viewport+render
        sub_simple = plane.modifiers.new("Subdivision_Simple", 'SUBSURF')
        sub_simple.subdivision_type = 'SIMPLE'
        sub_simple.levels = 3
        sub_simple.render_levels = 3

        # 2) Shrinkwrap Project On Surface along Z (both dirs), target=active
        sh = plane.modifiers.new("Shrinkwrap", 'SHRINKWRAP')
        sh.wrap_method = 'PROJECT'
        sh.target = target
        sh.use_project_x = False
        sh.use_project_y = False
        sh.use_project_z = True
        sh.use_negative_direction = True
        sh.use_positive_direction = True
        try:
            sh.cull_face = 'OFF'
        except Exception:
            pass

        # 3) Final Subdivision Catmull-Clark, levels 6, Keep Corners
        sub_final = plane.modifiers.new("Subdivision_Final", 'SUBSURF')
        sub_final.subdivision_type = 'CATMULL_CLARK'
        sub_final.levels = 6
        sub_final.render_levels = 6
        try:
            sub_final.boundary_smooth = 'PRESERVE_CORNERS'
        except Exception:
            # Older versions may not have this enum; ignore silently
            pass

        self.report({'INFO'}, f"Surface generated: {plane.name} -> Optimized collection")
        return {'FINISHED'}


def register():
    # Define operator properties via __annotations__ BEFORE registering the class,
    # so Blender's RNA system picks them up correctly.
    ann = getattr(VIVID_OT_generate_surface, "__annotations__", {})
    ann["dim_x"] = FloatProperty(
        name="Meters X",
        description="Width of the generated surface in meters",
        default=2.0,
        min=0.01,
        soft_max=1000.0,
    )
    ann["dim_y"] = FloatProperty(
        name="Meters Y",
        description="Height of the generated surface in meters",
        default=2.0,
        min=0.01,
        soft_max=1000.0,
    )
    VIVID_OT_generate_surface.__annotations__ = ann
    bpy.utils.register_class(VIVID_OT_generate_surface)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_generate_surface)
