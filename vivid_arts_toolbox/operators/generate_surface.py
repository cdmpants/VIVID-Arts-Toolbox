import bpy
import bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree
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

        # Read desired plane dimensions
        dim_x = float(getattr(self, 'dim_x', getattr(context.scene, 'vivid_surface_dim_x', 2.0)))
        dim_y = float(getattr(self, 'dim_y', getattr(context.scene, 'vivid_surface_dim_y', 2.0)))

        # Sample normals near the 3D cursor using a KDTree for speed
        cursor_loc = context.scene.cursor.location.copy()
        try:
            depsgraph = context.evaluated_depsgraph_get()
            eobj = target.evaluated_get(depsgraph)
            emesh = eobj.to_mesh()
        except Exception:
            emesh = target.data
            eobj = target

        # Build bmesh to ensure normals, then KDTree in world-space
        bm = bmesh.new(); bm.from_mesh(emesh); bm.normal_update()
        world = eobj.matrix_world
        nverts = len(bm.verts)
        kd = KDTree(nverts) if nverts > 0 else None
        if kd:
            for i, v in enumerate(bm.verts):
                kd.insert(world @ v.co, i)
            kd.balance()
        # Radius approximates the requested area (0.8 of the larger dimension), treated as a disk
        radius = 0.4 * max(dim_x, dim_y)
        avg_n = Vector((0.0, 0.0, 1.0))
        if kd and nverts:
            M_n = world.to_3x3().inverted().transposed()
            # Ensure bmesh lookup table is up-to-date for indexed access
            try:
                bm.verts.ensure_lookup_table()
            except Exception:
                pass
            hits = kd.find_range(cursor_loc, radius)
            if hits:
                s = Vector((0,0,0))
                for (_, index, _) in hits:
                    vn = M_n @ bm.verts[index].normal
                    try:
                        vn.normalize()
                    except Exception:
                        pass
                    s += vn
                if s.length > 0.0:
                    s.normalize()
                    avg_n = s
        try:
            # Free evaluated mesh if allocated
            if hasattr(eobj, 'to_mesh_clear'):
                eobj.to_mesh_clear()
        except Exception:
            pass
        bm.free()

        # Create plane at cursor
        bpy.ops.mesh.primitive_plane_add(size=2.0, align='WORLD', location=cursor_loc)
        plane = context.active_object

        # Name the plane based on target name -> replace final suffix with _Optimized
        new_name = _replace_final_suffix(target.name, "_Optimized")
        plane.name = new_name
        plane.data.name = new_name

        # Scale plane to desired explicit dimensions (primitive plane is 2x2 by default)
        plane.scale.x = max(dim_x, 0.01) / 2.0
        plane.scale.y = max(dim_y, 0.01) / 2.0

        # Orient plane so its local +Z aligns with the averaged surface normal
        try:
            q = Vector((0,0,1)).rotation_difference(avg_n)
            plane.rotation_mode = 'QUATERNION'
            plane.rotation_quaternion = q
        except Exception:
            pass

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

        # Offset plane along its local +Z after orientation so it sits slightly above the surface
        try:
            z_offset = 0.5 * ((dim_x + dim_y) * 0.5)
            # Move along local Z in world space using the plane's quaternion
            offset_world = plane.rotation_quaternion @ Vector((0, 0, z_offset))
            plane.location = plane.location + offset_world
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
