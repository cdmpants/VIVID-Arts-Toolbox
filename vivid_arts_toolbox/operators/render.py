import bpy
import os
from math import radians, sin
from mathutils import Vector
from ..utils import resource_or_legacy
from bpy.types import Operator

BAKE_EXTS = (".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp")


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


def _find_optimized_obj() -> bpy.types.Object | None:
    o = bpy.context.active_object
    if o and o.type == 'MESH' and o.name.endswith('_Optimized'):
        return o
    for t in bpy.context.scene.objects:
        if t.type == 'MESH' and t.name.endswith('_Optimized'):
            return t
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


def _append_or_get_render_material(render_blend_path: str, template_name: str = "Render") -> bpy.types.Material | None:
    mat = bpy.data.materials.get(template_name)
    if mat:
        return mat
    if not (render_blend_path and os.path.isfile(render_blend_path)):
        return None
    try:
        with bpy.data.libraries.load(render_blend_path, link=False) as (data_from, data_to):
            if template_name in (data_from.materials or []):
                data_to.materials = [template_name]
        return bpy.data.materials.get(template_name)
    except Exception:
        return None


def _parse_udim_from_mat_name(name: str) -> str:
    try:
        parts = (name or "").split('_')
        for token in reversed(parts):
            if token.isdigit() and len(token) == 4 and int(token) >= 1001:
                return token
    except Exception:
        pass
    return '1001'


def _scan_release_textures(release_dir: str) -> list[str]:
    try:
        return [os.path.join(release_dir, f) for f in os.listdir(release_dir)
                if os.path.splitext(f)[1].lower() in BAKE_EXTS and os.path.isfile(os.path.join(release_dir, f))]
    except Exception:
        return []


def _pick_texture_for(node_suffix: str, udim: str, files: list[str], preferred_prefixes: list[str]) -> str | None:
    # Heuristic: prefer files whose stem starts with a preferred prefix (asset id, object), contains _UDIM_, and ends with suffix token
    cand = []
    low_suffix = node_suffix.lower()
    for p in files:
        stem = os.path.splitext(os.path.basename(p))[0]
        low = stem.lower()
        if f"_{udim}_" not in low:
            continue
        if not low.endswith(low_suffix) and not low.endswith(f"_{low_suffix}"):
            # also allow suffix separated by underscore
            continue
        score = 0
        for pref in preferred_prefixes:
            if pref and low.startswith(pref.lower() + "_"):
                score += 2
        # prefer exact suffix match at end
        if low.endswith(f"_{low_suffix}"):
            score += 1
        cand.append((score, p))
    if not cand:
        # fallback: accept any file with udim and suffix anywhere
        for p in files:
            low = os.path.splitext(os.path.basename(p))[0].lower()
            if f"_{udim}_" in low and low_suffix in low:
                cand.append((0, p))
    if not cand:
        return None
    cand.sort(key=lambda t: t[0], reverse=True)
    return cand[0][1]


_RENDER_COLORSPACE = {
    'BaseColor': 'sRGB',
}


def _wire_render_material_images(mat: bpy.types.Material, udim: str, release_dir: str, preferred_prefixes: list[str], report_fn=None):
    if not mat or not mat.use_nodes:
        return
    files = _scan_release_textures(release_dir)
    if not files:
        return
    nt = mat.node_tree
    wired = []
    for n in nt.nodes:
        # Only consider image texture nodes; use node name as suffix key
        if getattr(n, 'bl_idname', '') != 'ShaderNodeTexImage':
            continue
        suffix = n.name or n.label or ''
        if not suffix:
            continue
        path = _pick_texture_for(suffix, udim, files, preferred_prefixes)
        if not path:
            continue
        try:
            img = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
            try:
                if getattr(img, 'packed_file', None):
                    img.unpack(method='USE_ORIGINAL')
            except Exception:
                pass
            n.image = img
            cs = _RENDER_COLORSPACE.get(suffix, 'Non-Color')
            try:
                n.image.colorspace_settings.name = cs
            except Exception:
                pass
            wired.append((suffix, os.path.basename(path)))
        except Exception:
            pass
    if report_fn and wired:
        msg = ", ".join([f"{suf} -> {fn}" for suf, fn in wired])
        report_fn({'INFO'}, f"Render material '{mat.name}': wired {len(wired)} textures: {msg}")


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
        render_blend = str(resource_or_legacy('Render.blend'))
        if not os.path.isfile(render_blend):
            self.report({'ERROR'}, f"Render.blend not found in add-on resources: {render_blend}")
            return {'CANCELLED'}

        # Prepare output folder (Release/Renders)
        try:
            release_dir = _release_asset_dir(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        renders_dir = os.path.join(release_dir, 'Renders')
        os.makedirs(renders_dir, exist_ok=True)

        # Determine asset type from metadata
        md = getattr(context.scene, 'vivid_metadata', None)
        asset_type = getattr(md, 'asset_type', 'Model') if md else 'Model'

        if asset_type == 'Surface':
            # Surface flow: TextureBall and TexturePlane, no camera offsets or fitting
            asset_id = getattr(md, 'asset_id', '') if md else ''
            if not asset_id:
                # fallback to folder name
                blend_dir = os.path.dirname(bpy.data.filepath)
                asset_id = os.path.basename(blend_dir)
            # Ensure Render material template
            render_mat_template = _append_or_get_render_material(render_blend, template_name="Render")
            if not render_mat_template:
                self.report({'ERROR'}, "Missing 'Render' material in Render.blend")
                return {'CANCELLED'}

            def render_surface_scene(scene_name: str, suffix: str):
                # Append requested scene
                before = set(sc.name for sc in bpy.data.scenes)
                chosen_name = None
                try:
                    with bpy.data.libraries.load(render_blend, link=False) as (data_from, data_to):
                        names = list(data_from.scenes)
                        if scene_name in names:
                            data_to.scenes = [scene_name]
                            chosen_name = scene_name
                        else:
                            raise RuntimeError(f"Scene '{scene_name}' not found in Render.blend")
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to append {scene_name} scene: {e}")
                    return False
                after = {sc.name for sc in bpy.data.scenes}
                new_names = list(after - before)
                scn = bpy.data.scenes.get(chosen_name)
                if not scn and new_names:
                    scn = bpy.data.scenes.get(new_names[0])
                if not scn:
                    self.report({'ERROR'}, f"Appended {scene_name} scene not found")
                    return False

                prev_scene = context.window.scene
                context.window.scene = scn

                # Assign temporary Render materials to named object in the appended scene
                obj = None
                for o in scn.objects:
                    if o.name == scene_name and o.type == 'MESH':
                        obj = o
                        break
                if not obj:
                    # fallback first mesh in scene
                    for o in scn.objects:
                        if o.type == 'MESH':
                            obj = o
                            break
                # Build preferred prefixes for filename matching
                preferred = [asset_id, obj.name]
                # Snapshot original materials
                original_mats = [slot.material for slot in (obj.material_slots or [])]
                created = []
                try:
                    # For each existing material slot, create a copy of Render template and wire images per UDIM
                    if obj:
                        if not obj.data.materials:
                            obj.data.materials.append(None)
                        for i, orig in enumerate(original_mats or [None]):
                            udim = _parse_udim_from_mat_name(orig.name if orig else obj.name)
                            new_mat = render_mat_template.copy()
                            new_mat.name = f"{(orig.name if orig else obj.name)}_Render"
                            _wire_render_material_images(new_mat, udim, release_dir, preferred, report_fn=self.report)
                            if i < len(obj.data.materials):
                                obj.data.materials[i] = new_mat
                            else:
                                obj.data.materials.append(new_mat)
                            created.append(new_mat)
                except Exception:
                    pass

                # Setup render output
                orig_fp = scn.render.filepath
                orig_fmt = scn.render.image_settings.file_format
                orig_col = scn.render.image_settings.color_mode
                orig_transp = scn.render.film_transparent
                scn.render.image_settings.file_format = 'PNG'
                scn.render.image_settings.color_mode = 'RGBA'
                scn.render.film_transparent = True

                out_path = os.path.join(renders_dir, f"{asset_id}_{suffix}.png")
                try:
                    scn.render.filepath = out_path
                    bpy.ops.render.render(write_still=True)
                finally:
                    scn.render.filepath = orig_fp
                    scn.render.image_settings.file_format = orig_fmt
                    scn.render.image_settings.color_mode = orig_col
                    scn.render.film_transparent = orig_transp
                    # Restore original materials and cleanup
                    try:
                        if obj:
                            for i, m in enumerate(original_mats):
                                if i < len(obj.data.materials):
                                    obj.data.materials[i] = m
                            # Trim extra slots if any
                            while len(obj.data.materials) > len(original_mats):
                                obj.data.materials.pop(index=len(obj.data.materials)-1)
                    except Exception:
                        pass
                    for m in created:
                        try:
                            bpy.data.materials.remove(m, do_unlink=True)
                        except Exception:
                            pass
                    try:
                        context.window.scene = prev_scene
                    except Exception:
                        pass
                    try:
                        bpy.data.scenes.remove(scn, do_unlink=True)
                    except Exception:
                        pass
                return True

            ok1 = render_surface_scene('TextureBall', 'Ball_BeautyRender')
            ok2 = render_surface_scene('TexturePlane', 'Plane_BeautyRender')

            # Downscale release textures to 1024 JPG into Renders folder
            self._downscale_release_textures_to_jpg(context, release_dir, renders_dir)

            if not (ok1 and ok2):
                return {'CANCELLED'}
            self.report({'INFO'}, f"Surface renders saved to: {renders_dir}")
            return {'FINISHED'}

        # Model flow (existing), but save into Renders subfolder
        # Choose biome scene (fallback to Generic)
        s = md
        biome_name = getattr(s, 'biome', 'Generic') if s else 'Generic'

        # Append scene
        before = set(sc.name for sc in bpy.data.scenes)
        want_name = biome_name
        chosen_name = None
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
                    data_to.scenes = [names[0]] if names else []
                    chosen_name = names[0] if names else None
        except Exception as e:
            self.report({'ERROR'}, f"Failed to append scene from Render.blend: {e}")
            return {'CANCELLED'}

        if not chosen_name:
            self.report({'ERROR'}, "No scenes found in Render.blend")
            return {'CANCELLED'}

        after = {sc.name for sc in bpy.data.scenes}
        new_names = list(after - before)
        render_scene = bpy.data.scenes.get(chosen_name)
        if not render_scene and new_names:
            render_scene = bpy.data.scenes.get(new_names[0])
        if not render_scene:
            self.report({'ERROR'}, "Appended render scene not found")
            return {'CANCELLED'}

        prev_scene = context.window.scene
        context.window.scene = render_scene

        # Camera offsets
        z_angle = getattr(context.scene, 'vivid_camera_offset_z', 0.0)
        x_angle = getattr(context.scene, 'vivid_camera_offset_x', 0.0)
        _set_camera_offsets(render_scene, z_angle, x_angle)

        cam_obj = _find_camera(render_scene)
        if not cam_obj:
            self.report({'ERROR'}, "No camera found in appended scene")
            context.window.scene = prev_scene
            return {'CANCELLED'}

        targets = _collect_cinema_targets()
        if not targets:
            self.report({'ERROR'}, "No Cinema or variant meshes found.")
            context.window.scene = prev_scene
            return {'CANCELLED'}

        # Ensure Render material template
        render_mat_template = _append_or_get_render_material(render_blend, template_name="Render")
        if not render_mat_template:
            self.report({'ERROR'}, "Missing 'Render' material in Render.blend")
            context.window.scene = prev_scene
            return {'CANCELLED'}

        # Render settings
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
                if obj.name not in render_scene.collection.objects:
                    try:
                        render_scene.collection.objects.link(obj)
                    except RuntimeError:
                        pass
                _fit_camera_to_object(render_scene, cam_obj, obj, margin=1.08)

                base = obj.name
                if base.endswith('_Cinema'):
                    base = base[:-7]
                base = base.replace('_Cinema_Var', '_Var')

                # Build preferred prefixes
                md = getattr(context.scene, 'vivid_metadata', None)
                asset_id = getattr(md, 'asset_id', '') if md else ''
                if not asset_id:
                    blend_dir = os.path.dirname(bpy.data.filepath)
                    asset_id = os.path.basename(blend_dir)
                preferred = [asset_id, obj.name]

                # Apply temporary Render materials on the target object
                original_mats = [slot.material for slot in (obj.material_slots or [])]
                created = []
                try:
                    if not obj.data.materials:
                        obj.data.materials.append(None)
                    for i, orig in enumerate(original_mats or [None]):
                        udim = _parse_udim_from_mat_name(orig.name if orig else obj.name)
                        new_mat = render_mat_template.copy()
                        new_mat.name = f"{(orig.name if orig else obj.name)}_Render"
                        _wire_render_material_images(new_mat, udim, release_dir, preferred, report_fn=self.report)
                        if i < len(obj.data.materials):
                            obj.data.materials[i] = new_mat
                        else:
                            obj.data.materials.append(new_mat)
                        created.append(new_mat)
                except Exception:
                    pass

                _set_switch_for_object(obj, 'Switch_Clay', 0.0)
                out_path = os.path.join(renders_dir, f"{base}_BeautyRender.png")
                do_render(out_path)

                _set_switch_for_object(obj, 'Switch_Clay', 1.0)
                out_path = os.path.join(renders_dir, f"{base}_ClayRender.png")
                do_render(out_path)
                _set_switch_for_object(obj, 'Switch_Clay', 0.0)

                lod0_name = _lod0_name_for(obj.name)
                lod0 = bpy.data.objects.get(lod0_name)
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
                    # Apply temporary Render materials to LOD0 for wireframe pass too
                    lod0_original = [slot.material for slot in (lod0.material_slots or [])]
                    lod0_created = []
                    try:
                        if not lod0.data.materials:
                            lod0.data.materials.append(None)
                        for i, orig in enumerate(lod0_original or [None]):
                            udim = _parse_udim_from_mat_name(orig.name if orig else lod0.name)
                            new_mat = render_mat_template.copy()
                            new_mat.name = f"{(orig.name if orig else lod0.name)}_Render"
                            _wire_render_material_images(new_mat, udim, release_dir, preferred, report_fn=None)
                            if i < len(lod0.data.materials):
                                lod0.data.materials[i] = new_mat
                            else:
                                lod0.data.materials.append(new_mat)
                            lod0_created.append(new_mat)
                    except Exception:
                        pass
                    _set_switch_for_object(lod0, 'Switch_Wireframe', 1.0)
                    out_path = os.path.join(renders_dir, f"{base}_WireframeRender.png")
                    do_render(out_path)
                    _set_switch_for_object(lod0, 'Switch_Wireframe', 0.0)
                    # Restore and cleanup for LOD0
                    try:
                        for i, m in enumerate(lod0_original):
                            if i < len(lod0.data.materials):
                                lod0.data.materials[i] = m
                        while len(lod0.data.materials) > len(lod0_original):
                            lod0.data.materials.pop(index=len(lod0.data.materials)-1)
                    except Exception:
                        pass
                    for m in lod0_created:
                        try:
                            bpy.data.materials.remove(m, do_unlink=True)
                        except Exception:
                            pass
                    try:
                        render_scene.collection.objects.unlink(lod0)
                    except Exception:
                        pass
                # Restore and cleanup for main object
                try:
                    for i, m in enumerate(original_mats):
                        if i < len(obj.data.materials):
                            obj.data.materials[i] = m
                    while len(obj.data.materials) > len(original_mats):
                        obj.data.materials.pop(index=len(obj.data.materials)-1)
                except Exception:
                    pass
                for m in created:
                    try:
                        bpy.data.materials.remove(m, do_unlink=True)
                    except Exception:
                        pass
                try:
                    if obj.name not in render_scene.collection.objects:
                        render_scene.collection.objects.link(obj)
                    render_scene.collection.objects.unlink(obj)
                except Exception:
                    pass

        finally:
            render_scene.render.filepath = orig_fp
            render_scene.render.image_settings.file_format = orig_fmt
            render_scene.render.image_settings.color_mode = orig_col
            render_scene.render.film_transparent = orig_transp
            try:
                context.window.scene = prev_scene
            except Exception:
                pass
            try:
                bpy.data.scenes.remove(render_scene, do_unlink=True)
            except Exception:
                pass

        # Downscale release textures to 1024 JPG into Renders folder (best-effort)
        self._downscale_release_textures_to_jpg(context, release_dir, renders_dir)

        self.report({'INFO'}, f"Renders saved to: {renders_dir}")
        return {'FINISHED'}

    def _downscale_release_textures_to_jpg(self, context, release_dir: str, renders_dir: str):
        # Best-effort: iterate images in release root (non-recursive), scale to 1024x1024 and save as JPG in Renders
        exts = {'.png', '.tga', '.tif', '.tiff', '.exr', '.jpg', '.jpeg'}
        files = []
        try:
            files = [f for f in os.listdir(release_dir) if os.path.splitext(f)[1].lower() in exts]
        except Exception:
            return
        if not files:
            return
        scene = context.scene
        # Save original settings
        orig_fmt = scene.render.image_settings.file_format
        orig_col = scene.render.image_settings.color_mode
        orig_fp = scene.render.filepath
        try:
            scene.render.image_settings.file_format = 'JPEG'
            scene.render.image_settings.color_mode = 'RGB'
            for f in files:
                src_path = os.path.join(release_dir, f)
                stem, _ = os.path.splitext(f)
                dst_path = os.path.join(renders_dir, f"{stem}_1024.jpg")
                try:
                    img = bpy.data.images.load(src_path, check_existing=True)
                except Exception:
                    continue
                try:
                    # Ensure loaded
                    if img.size[0] != 0 and img.size[1] != 0:
                        img.scale(1024, 1024)
                    img.save_render(dst_path, scene=scene)
                except Exception:
                    pass
                finally:
                    try:
                        bpy.data.images.remove(img, do_unlink=True)
                    except Exception:
                        pass
        finally:
            scene.render.image_settings.file_format = orig_fmt
            scene.render.image_settings.color_mode = orig_col
            scene.render.filepath = orig_fp


def register():
    bpy.utils.register_class(VIVID_OT_output_renders)


def unregister():
    try:
        bpy.utils.unregister_class(VIVID_OT_output_renders)
    except Exception:
        pass
