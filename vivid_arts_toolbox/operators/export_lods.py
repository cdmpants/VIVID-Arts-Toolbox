import bpy
import os


def _release_asset_dir(context):
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences
    release_root = getattr(prefs, 'release_directory', '') or ''
    blend_path = bpy.data.filepath
    if not blend_path:
        raise RuntimeError("Save your .blend file first.")
    blend_dir = os.path.dirname(blend_path)

    parts = os.path.normpath(blend_dir).split(os.sep)
    lower_parts = [p.lower() for p in parts]
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


class VIVID_OT_export_lods(bpy.types.Operator):
    bl_idname = "vivid.export_lods"
    bl_label = "Export LODs"
    bl_description = "Exports LOD FBXs (including variants and ShadowProxies) to the mirrored Release directory."

    def execute(self, context):
        try:
            release_dir = _release_asset_dir(context)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        # Tidy structure: export meshes into Release/Mesh
        mesh_dir = os.path.join(release_dir, "Mesh")
        os.makedirs(mesh_dir, exist_ok=True)

        # Collect LOD objects: any *_LOD0..3 and *_ShadowProxy[_LOD*] and colliders
        lod_candidates = []
        for o in bpy.data.objects:
            if o.type != 'MESH':
                continue
            n = o.name
            # Skip LOD Cages entirely (names like *_LOD#_Cage or in LOD_Cage collection)
            if "_Cage" in n or any(c.name == 'LOD_Cage' for c in getattr(o, 'users_collection', []) or []):
                continue
            if any(s in n for s in ["_LOD0", "_LOD1", "_LOD2", "_LOD3", "_ShadowProxy", "_MeshCollider", "_ConvexCollider"]):
                lod_candidates.append(o)

        if not lod_candidates:
            self.report({'ERROR'}, "No LODs/Proxies found to export.")
            return {'CANCELLED'}

        exported = 0
        for obj in lod_candidates:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            out_path = os.path.join(mesh_dir, f"{obj.name}.fbx")
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
                self.report({'ERROR'}, f"Failed exporting {obj.name}: {e}")

        if exported == 0:
            return {'CANCELLED'}
        self.report({'INFO'}, f"Exported {exported} LOD FBXs to: {mesh_dir}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_export_lods)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_export_lods)
