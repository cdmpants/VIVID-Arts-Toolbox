import bpy
import os


def _release_asset_dir(context):
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences
    release_root = getattr(prefs, 'release_directory', '') or ''
    blend_path = bpy.data.filepath
    if not blend_path:
        raise RuntimeError("Save your .blend file first.")
    blend_dir = os.path.dirname(blend_path)

    # Find subpath after 'Production' (case-insensitive)
    parts = os.path.normpath(blend_dir).split(os.sep)
    lower_parts = [p.lower() for p in parts]
    sub_after = []
    if 'production' in lower_parts:
        idx = lower_parts.index('production')
        sub_after = parts[idx + 1:]
        # Prefer preference root; fallback to sibling replacement
        if release_root:
            return os.path.join(release_root, *sub_after)
        # Fallback: replace Production with Release in original path
        parts[idx] = 'Release'
        return os.path.join(*parts)
    # If 'Production' not found, mirror using prefs root + last folder name
    if release_root:
        return os.path.join(release_root, os.path.basename(blend_dir))
    # As a last resort, put next to .blend in 'Release' sibling
    return os.path.join(os.path.dirname(blend_dir), 'Release', os.path.basename(blend_dir))


class VIVID_OT_export_asset(bpy.types.Operator):
    bl_idname = "vivid.export_asset"
    bl_label = "Export Asset"
    bl_description = "Exports the _Cinema and any _Cinema_Var# objects to FBX files in the mirrored Release directory."

    def execute(self, context):
        self.report({'INFO'}, "Starting Export Cinema Model...")

        try:
            release_dir = _release_asset_dir(context)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        # Tidy structure: export cinema meshes into Release/Mesh
        mesh_dir = os.path.join(release_dir, "Mesh")
        os.makedirs(mesh_dir, exist_ok=True)

        # Gather base Cinema and variant objects
        targets = []
        cinema_coll = bpy.data.collections.get('Cinema')
        if cinema_coll:
            for o in cinema_coll.objects:
                if o.type == 'MESH' and o.name.endswith('_Cinema'):
                    targets.append(o)
        # Variants in Cinema_Var# collections
        for c in bpy.data.collections:
            if c.name.startswith('Cinema_Var'):
                for o in c.objects:
                    if o.type == 'MESH' and (o.name.endswith('_Cinema') or '_Cinema_Var' in o.name):
                        targets.append(o)

        if not targets:
            self.report({'ERROR'}, "No _Cinema or _Cinema_Var# objects found. Generate Cinema Model first.")
            return {'CANCELLED'}

        exported = 0
        for obj in targets:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            out_name = obj.name
            out_path = os.path.join(mesh_dir, f"{out_name}.fbx")
            try:
                bpy.ops.export_scene.fbx(
                    filepath=out_path,
                    use_selection=True,
                    object_types={'MESH'},
                    bake_space_transform=True,
                    use_mesh_modifiers=True,
                    mesh_smooth_type='FACE',
                    axis_forward='-Z',
                    axis_up='Y'
                )
                self.report({'INFO'}, f"Exported: {out_path}")
                exported += 1
            except Exception as e:
                self.report({'ERROR'}, f"Failed to export {obj.name}: {e}")

        if exported == 0:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Export Cinema Model complete. Files in: {mesh_dir}")
        return {'FINISHED'}

