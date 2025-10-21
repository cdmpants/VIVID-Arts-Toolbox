import bpy, os, re
from bpy.types import Operator
from pathlib import Path

from ..metadata import _release_mirror_dir
from ..bake_textures import (
    _ensure_outdir,
    _udim_tiles_from_object,
    _load_and_patch_json,
    _apply_udim_to_json,
    _run_baker,
)
from ..utils import resource_or_legacy

class VIVID_OT_bake_lod_textures(Operator):
    bl_idname = "vivid.bake_lod_textures"
    bl_label = "Bake LOD Textures"
    bl_description = "Export LODs and cages to BakeMesh and run bakes using bakeLOD_preset.json; outputs go to Release"

    def execute(self, context):
        # Ensure saved blend
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Save your .blend file first.")
            return {'CANCELLED'}

        # Resolve directories
        root, bake_mesh, bake_tex = _ensure_outdir()
        try:
            release_dir = _release_mirror_dir(context)
        except Exception:
            release_dir = os.path.join(os.path.dirname(os.path.dirname(root)), 'Release', os.path.basename(os.path.normpath(root)))
        os.makedirs(release_dir, exist_ok=True)

        # Locate Cinema FBX in Release
        cinema_fbx = None
        try:
            for p in Path(release_dir).glob("*_Cinema.fbx"):
                cinema_fbx = str(p)
                break
        except Exception:
            cinema_fbx = None
        if not cinema_fbx:
            self.report({'ERROR'}, f"No *_Cinema.fbx found in Release folder: {release_dir}")
            return {'CANCELLED'}

        # Find LOD and LOD_Cage collections
        lod_coll = bpy.data.collections.get('LOD')
        if not lod_coll:
            self.report({'ERROR'}, "'LOD' collection not found.")
            return {'CANCELLED'}
        cage_coll = bpy.data.collections.get('LOD_Cage')

        # Gather base LODs (ignore proxies/colliders)
        base_lods = []
        for o in lod_coll.objects:
            if o.type != 'MESH':
                continue
            n = o.name
            if re.search(r"_LOD[0-3]$", n) and ('ShadowProxy' not in n) and ('Collider' not in n):
                base_lods.append(o)
        if not base_lods:
            self.report({'ERROR'}, "No base LODs (_LOD0.._LOD3) found in 'LOD'.")
            return {'CANCELLED'}

        # Export each base LOD and its cage (if present) to BakeMesh
        def _export_obj_to_fbx(obj, out_path):
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
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

        lod_pairs = []  # (lod_obj, lod_fbx, cage_obj, cage_fbx)
        for lod in base_lods:
            lod_fbx = os.path.join(bake_mesh, f"{lod.name}.fbx")
            try:
                _export_obj_to_fbx(lod, lod_fbx)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to export {lod.name}: {e}")
                return {'CANCELLED'}
            cage_obj, cage_fbx = None, None
            if cage_coll:
                cand = cage_coll.objects.get(f"{lod.name}_Cage") if hasattr(cage_coll.objects, 'get') else None
                if not cand:
                    cand = bpy.data.objects.get(f"{lod.name}_Cage")
                    if cand and cage_coll not in cand.users_collection:
                        cand = None
                if cand:
                    cage_obj = cand
                    cage_fbx = os.path.join(bake_mesh, f"{cage_obj.name}.fbx")
                    try:
                        _export_obj_to_fbx(cage_obj, cage_fbx)
                    except Exception as e:
                        self.report({'ERROR'}, f"Failed to export {cage_obj.name}: {e}")
                        return {'CANCELLED'}
            lod_pairs.append((lod, lod_fbx, cage_obj, cage_fbx))

        # Designer baker path and preset
        addon_key = __package__.split('.')[0] if __package__ else "vivid_arts_toolbox"
        prefs = context.preferences.addons.get(addon_key)
        baker_path_pref = getattr(prefs.preferences, "substance_baker_path", "") if prefs and hasattr(prefs, "preferences") else ""
        exe_path = baker_path_pref if (baker_path_pref and os.path.isfile(baker_path_pref)) else os.path.join("C:\\Program Files\\Adobe\\Adobe Substance 3D Designer", "substance3d_baker.exe")
        if not os.path.isfile(exe_path):
            self.report({'ERROR'}, f"Designer baker not found: {exe_path}")
            return {'CANCELLED'}
        preset_path = str(resource_or_legacy("bakeLOD_preset.json"))
        if not os.path.isfile(preset_path):
            self.report({'ERROR'}, f"Missing bakeLOD_preset.json: {preset_path}")
            return {'CANCELLED'}

        # Bake resolution and engine from Designer settings
        settings = getattr(context.scene, "vivid_designer_bake", None)
        try:
            res_px = int(settings.bake_resolution) if settings and settings.bake_resolution else 2048
        except Exception:
            res_px = 2048
        use_cpu = (settings.engine == "CPU") if settings else False

        # Run bakes per LOD
        total_rc = 0
        for lod_obj, lod_fbx, cage_obj, cage_fbx in lod_pairs:
            gen_json = os.path.join(bake_mesh, f"_generated_bakeLOD_{lod_obj.name}.json")
            log_path = os.path.join(bake_mesh, f"bakeLOD_{lod_obj.name}.log")
            files = {"low": lod_fbx, "high": cinema_fbx, "cage": cage_fbx}
            # Patch JSON
            _load_and_patch_json(preset_path, files, release_dir, gen_json, res_px)
            # UDIM awareness
            try:
                tiles = _udim_tiles_from_object(lod_obj)
                if tiles and (len(tiles) > 1 or tiles != [(0, 0)]):
                    _apply_udim_to_json(gen_json, tiles)
            except Exception:
                pass
            # Execute
            rc = _run_baker(exe_path, gen_json, log_path, cwd=bake_mesh, use_cpu=use_cpu)
            total_rc += (rc or 0)

        self.report({'INFO'}, f"LOD bakes finished. Output: {release_dir}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_bake_lod_textures)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_bake_lod_textures)
