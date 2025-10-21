import bpy
import os
from math import radians, sin
from mathutils import Vector
from bpy.types import Operator


def _addon_dir():
    import pathlib
    return str(pathlib.Path(__file__).resolve().parent.parent)


def _release_asset_dir(context):
    # Reuse logic from export_asset without importing to avoid circulars
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences
    release_root = getattr(prefs, 'release_directory', '') or ''
    blend_path = bpy.data.filepath
    if not blend_path:
        raise RuntimeError("Save your .blend file first.")
    blend_dir = os.path.dirname(blend_path)

    parts = os.path.normpath(blend_dir).split(os.sep)
    lower_parts = [p.lower() for p in parts]
    sub_after = []
    if 'production' in lower_parts:
        idx = lower_parts.index('production')
        sub_after = parts[idx + 1:]
        if release_root:
            return os.path.join(release_root, *sub_after)
        parts[idx] = 'Release'
        return os.path.join(*parts)
    if release_root:
        return os.path.join(release_root, os.path.basename(blend_dir))
    return os.path.join(os.path.dirname(blend_dir), 'Release', os.path.basename(blend_dir))


def _find_camera(scene: bpy.types.Scene) -> bpy.types.Object | None:
    cam = scene.camera
    if cam:
        return cam
    for o in scene.objects:
        if o.type == 'CAMERA':
            return o
    return None


def _set_camera_offsets(scene: bpy.types.Scene, z_angle_rad: float, x_angle_rad: float):
    co_z = scene.objects.get('CameraOffset_Z')
    co_x = scene.objects.get('CameraOffset_X')
    if co_z:
        co_z.rotation_mode = 'XYZ'
        co_z.rotation_euler.z = z_angle_rad
    if co_x:
        co_x.rotation_mode = 'XYZ'
        co_x.rotation_euler.x = x_angle_rad


def _bbox_world(o: bpy.types.Object):
    # Returns world-space bbox corners, center, and radius
    mat = o.matrix_world
    corners = [mat @ Vector(corner) for corner in o.bound_box]
    center = sum(corners, Vector((0, 0, 0))) / 8.0
    radius = max((corner - center).length for corner in corners)
    return corners, center, radius


def _fit_camera_to_object(scene: bpy.types.Scene, cam_obj: bpy.types.Object, obj: bpy.types.Object, margin: float = 1.1):
    # Fit perspective camera to bound sphere with margin, keeping current orientation
    if not cam_obj or cam_obj.type != 'CAMERA':
        return
    data = cam_obj.data
    # Only handle perspective; orthographic just sets ortho_scale
    _, center, radius = _bbox_world(obj)
    if data.type == 'ORTHO':
        data.ortho_scale = max(data.ortho_scale, radius * 2 * margin)
        cam_dir = (cam_obj.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
        cam_obj.location = center - cam_dir * 10.0  # arbitrary distance
        return

    # Perspective: compute needed distance based on FOV
    try:
        ang_x = getattr(data, 'angle_x', None)
        ang_y = getattr(data, 'angle_y', None)
        if not ang_x or not ang_y:
            # Fallback to single angle (vertical)
            fov_y = data.angle
            req_y = (radius * margin) / max(1e-6, sin(fov_y * 0.5))
            req = req_y
        else:
            req_x = (radius * margin) / max(1e-6, sin(ang_x * 0.5))
            req_y = (radius * margin) / max(1e-6, sin(ang_y * 0.5))
            req = max(req_x, req_y)
    except Exception:
        req = radius * 3.0  # conservative fallback

    cam_dir = (cam_obj.matrix_world.to_quaternion() @ Vector((0, 0, -1))).normalized()
    cam_obj.location = center - cam_dir * req


def _set_node_switch(material: bpy.types.Material, node_name: str, value: float):
    if not material or not material.use_nodes:
        return
    nt = material.node_tree
    if not nt:
        return
    for n in nt.nodes:
        if n.name == node_name:
            # Try outputs first (e.g., Value node)
            try:
                if hasattr(n, 'outputs') and len(n.outputs) > 0 and hasattr(n.outputs[0], 'default_value'):
                    n.outputs[0].default_value = value
                    continue
            except Exception:
                pass
            # Try inputs
            try:
                if hasattr(n, 'inputs') and len(n.inputs) > 0 and hasattr(n.inputs[0], 'default_value'):
                    n.inputs[0].default_value = value
            except Exception:
                pass


def _set_switch_for_object(obj: bpy.types.Object, node_name: str, value: float):
    if not obj or obj.type != 'MESH':
        return
    for slot in obj.material_slots:
        _set_node_switch(slot.material, node_name, value)


def _collect_cinema_targets():
    targets = []
    cinema = bpy.data.collections.get('Cinema')
    if cinema:
        for o in cinema.objects:
            if o.type == 'MESH' and (o.name.endswith('_Cinema') or '_Cinema_Var' in o.name):
                targets.append(o)
    # Also scan top-level for robustness
    for o in bpy.data.objects:
        if o.type == 'MESH' and (o.name.endswith('_Cinema') or '_Cinema_Var' in o.name):
            if o not in targets:
                targets.append(o)
    return targets


def _lod0_name_for(cinema_name: str) -> str:
    # cinema_name: Base_Cinema or Base_Cinema_VarN -> Base[_VarN]_LOD0
    name = cinema_name
    if name.endswith('_Cinema'):
        base = name[:-7]
        return f"{base}_LOD0"
    if '_Cinema_Var' in name:
        base = name.replace('_Cinema', '')
        return f"{base}_LOD0"
    return name.replace('_Cinema', '_LOD0')


class VIVID_OT_output_renders(Operator):
    bl_idname = "vivid.output_renders"
    bl_label = "Output Renders"
    bl_description = "Append a render scene and output Beauty, Clay, and Wireframe renders for Cinema and variants."

    def execute(self, context):
        # Resolve Render.blend path
        addon = _addon_dir()
        render_blend = os.path.join(addon, 'Render.blend')
        if not os.path.isfile(render_blend):
            # Fallback for environments where .blend1 is versioned
            alt = os.path.join(addon, 'Render.blend1')
            if os.path.isfile(alt):
                render_blend = alt
            else:
                self.report({'ERROR'}, f"Render.blend not found in addon: {render_blend}")
                return {'CANCELLED'}

        # Choose scene name by biome (fallback Generic)
        s = getattr(context.scene, 'vivid_metadata', None)
        biome_name = getattr(s, 'biome', 'Generic') if s else 'Generic'

        # Append scene
        before = set(sc.name for sc in bpy.data.scenes)
        want_name = biome_name
        chosen_name = None
        import bpy
        try:
            with bpy.data.libraries.load(render_blend, link=False) as (data_from, data_to):
                names = list(data_from.scenes)
                if want_name in names:
                    data_to.scenes = [want_name]
                    chosen_name = want_name
                elif 'Generic' in names:
                    data_to.scenes = ['Generic']
                    chosen_name = 'Generic'
                else:
                    # Append first available if none match
                    data_to.scenes = [names[0]] if names else []
                    chosen_name = names[0] if names else None
        except Exception as e:
            self.report({'ERROR'}, f"Failed to append scene from Render.blend: {e}")
            return {'CANCELLED'}

        if not chosen_name:
            self.report({'ERROR'}, "No scenes found in Render.blend")
            return {'CANCELLED'}

        # Resolve the newly appended scene (account for name suffix)
        after = {sc.name for sc in bpy.data.scenes}
        new_names = list(after - before)
        render_scene = bpy.data.scenes.get(chosen_name)
        if not render_scene and new_names:
            render_scene = bpy.data.scenes.get(new_names[0])
        if not render_scene:
            self.report({'ERROR'}, "Appended render scene not found")
            return {'CANCELLED'}

        # Switch to appended scene
        prev_scene = context.window.scene
        context.window.scene = render_scene

        # Set camera offsets from Scene sliders (stored in radians)
        z_angle = getattr(context.scene, 'vivid_camera_offset_z', 0.0)
        x_angle = getattr(context.scene, 'vivid_camera_offset_x', 0.0)
        _set_camera_offsets(render_scene, z_angle, x_angle)

        # Prepare render settings
        try:
            out_dir = _release_asset_dir(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            context.window.scene = prev_scene
            return {'CANCELLED'}
        os.makedirs(out_dir, exist_ok=True)

        cam_obj = _find_camera(render_scene)
        if not cam_obj:
            self.report({'ERROR'}, "No camera found in appended scene")
            context.window.scene = prev_scene
            return {'CANCELLED'}

        # Gather Cinema and variants
        targets = _collect_cinema_targets()
        if not targets:
            self.report({'ERROR'}, "No Cinema or variant meshes found.")
            context.window.scene = prev_scene
            return {'CANCELLED'}

        # Base render config
        orig_fp = render_scene.render.filepath
        orig_fmt = render_scene.render.image_settings.file_format
        orig_col = render_scene.render.image_settings.color_mode
        orig_transp = render_scene.render.film_transparent
        render_scene.render.image_settings.file_format = 'PNG'
        render_scene.render.image_settings.color_mode = 'RGBA'
        render_scene.render.film_transparent = True

        def do_render(path_no_ext: str):
            render_scene.render.filepath = path_no_ext
            bpy.ops.render.render(write_still=True)

        try:
            for obj in targets:
                # Link Cinema/variant into render scene
                if obj.name not in render_scene.collection.objects:
                    try:
                        render_scene.collection.objects.link(obj)
                    except RuntimeError:
                        pass  # already linked elsewhere

                # Align camera once per Cinema/variant
                _fit_camera_to_object(render_scene, cam_obj, obj, margin=1.08)

                # Base name without suffixes
                base = obj.name
                if base.endswith('_Cinema'):
                    base = base[:-7]
                base = base.replace('_Cinema_Var', '_Var')

                # Beauty
                _set_switch_for_object(obj, 'Switch_Clay', 0.0)
                out_path = os.path.join(out_dir, f"{base}_BeautyRender.png")
                do_render(out_path)

                # Clay
                _set_switch_for_object(obj, 'Switch_Clay', 1.0)
                out_path = os.path.join(out_dir, f"{base}_ClayRender.png")
                do_render(out_path)
                _set_switch_for_object(obj, 'Switch_Clay', 0.0)

                # Wireframe: swap to LOD0 corresponding
                lod0_name = _lod0_name_for(obj.name)
                lod0 = bpy.data.objects.get(lod0_name)
                # Remove Cinema from scene for wireframe view
                try:
                    if obj.name in render_scene.collection.objects:
                        render_scene.collection.objects.unlink(obj)
                except Exception:
                    pass
                if lod0 and lod0.type == 'MESH':
                    if lod0.name not in render_scene.collection.objects:
                        try:
                            render_scene.collection.objects.link(lod0)
                        except RuntimeError:
                            pass
                    _set_switch_for_object(lod0, 'Switch_Wireframe', 1.0)
                    out_path = os.path.join(out_dir, f"{base}_WireframeRender.png")
                    do_render(out_path)
                    _set_switch_for_object(lod0, 'Switch_Wireframe', 0.0)
                    # Unlink LOD0 after
                    try:
                        render_scene.collection.objects.unlink(lod0)
                    except Exception:
                        pass
                # Relink Cinema for next steps and cleanup
                try:
                    if obj.name not in render_scene.collection.objects:
                        render_scene.collection.objects.link(obj)
                    # Remove it so next variant starts clean
                    render_scene.collection.objects.unlink(obj)
                except Exception:
                    pass

        finally:
            # Restore render settings
            render_scene.render.filepath = orig_fp
            render_scene.render.image_settings.file_format = orig_fmt
            render_scene.render.image_settings.color_mode = orig_col
            render_scene.render.film_transparent = orig_transp

            # Restore previous scene and remove appended
            try:
                context.window.scene = prev_scene
            except Exception:
                pass
            try:
                bpy.data.scenes.remove(render_scene, do_unlink=True)
            except Exception:
                pass

        self.report({'INFO'}, f"Renders saved to: {out_dir}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_output_renders)


def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_output_renders)
    except Exception:
        pass
