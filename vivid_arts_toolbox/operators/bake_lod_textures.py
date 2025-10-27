import bpy, os, re, json
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
from ..bake_textures import _clean_dir
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
        # Organize under Release/Textures and Release/Mesh
        textures_root = os.path.join(release_dir, 'Textures')
        textures_dir = os.path.join(textures_root, 'LOD')  # LOD outputs go under Textures/LOD
        mesh_dir = os.path.join(release_dir, 'Mesh')
        os.makedirs(textures_root, exist_ok=True)
        os.makedirs(textures_dir, exist_ok=True)
        # Wipe LOD subfolder only (leave other textures intact)
        try:
            _clean_dir(textures_dir)
        except Exception:
            pass
        os.makedirs(mesh_dir, exist_ok=True)

        # Locate Cinema FBX in Release/Mesh (fallback to Release root for backward compatibility)
        cinema_fbx = None
        try:
            for p in Path(mesh_dir).glob("*_Cinema.fbx"):
                cinema_fbx = str(p)
                break
        except Exception:
            cinema_fbx = None
        if not cinema_fbx:
            # Backward-compat search in Release root
            try:
                for p in Path(release_dir).glob("*_Cinema.fbx"):
                    cinema_fbx = str(p)
                    break
            except Exception:
                cinema_fbx = None
        if not cinema_fbx:
            self.report({'ERROR'}, f"No *_Cinema.fbx found in Release/Mesh: {mesh_dir}")
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

        # Bake resolution: prefer LOD-specific Max Resolution, fallback to Designer bake resolution
        settings = getattr(context.scene, "vivid_designer_bake", None)
        sprops = getattr(context.scene, 'vivid_lod_props', None)
        try:
            max_res_px = int(getattr(sprops, 'lod_max_resolution', '') or 0) or int(settings.bake_resolution) if settings and getattr(settings, 'bake_resolution', None) else 2048
        except Exception:
            max_res_px = 2048
        use_cpu = (settings.engine == "CPU") if settings else False

    # Run bakes per LOD
        # Helper: patch multiple TextureTransfer bakers in-place based on available sources
        def _patch_transfer_bakers(json_path: str, udim: int, get_map_for_kind):
            """get_map_for_kind(kind:str)->dict(udim->path). Mutates JSON to set source_texture_path and is_selected.
            Enforces hard requirements for 'Normal' and 'BaseColor' (must exist for this UDIM), others are optional.
            Returns (ok: bool, warnings: list[str]).
            """
            warnings = []
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                return False, warnings
            bakers = data.get('bakers', []) or []
            for baker in bakers:
                if not isinstance(baker, dict):
                    continue
                if str(baker.get('baker', '')).startswith('TextureTransfer'):
                    ident = str(baker.get('identifier', '') or '')
                    params = baker.get('parameters') or {}
                    if not isinstance(params, dict):
                        continue
                    # Determine source
                    m = get_map_for_kind(ident)
                    src = m.get(udim) if isinstance(m, dict) else None
                    hard = ident in ('Normal', 'BaseColor')
                    if src:
                        params['source_texture_path'] = src
                        params['is_selected'] = True
                    else:
                        if hard:
                            # Hard requirement missing
                            return False, warnings
                        # Soft requirement: disable this baker
                        try:
                            params['is_selected'] = False
                        except Exception:
                            pass
                        if ident == 'BentNormal':
                            warnings.append(f"Missing Cinema BentNormal texture for UDIM {udim}; continuing without it.")
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception:
                return False, warnings
            return True, warnings

        # Helper: ensure AO baker receives the Cinema Normal map via normal_map_path
        def _patch_ao_normal(json_path: str, ao_normal_path: str):
            if not ao_normal_path:
                return
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                return
            try:
                for baker in data.get('bakers', []) or []:
                    if isinstance(baker, dict) and baker.get('identifier') == 'AO':
                        params = baker.get('parameters') or {}
                        if isinstance(params, dict):
                            params['normal_map_path'] = ao_normal_path
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception:
                return

        # Helper: discover Cinema texture(s) in Release/Textures by UDIM for a given map kind ('Normal' or 'BentNormal')
        def _cinema_maps_by_udim(textures_root_dir: str, base_name: str, map_kind: str):
            """Return {udim:int -> path} mapping for files like: Base_UDIM_MapKind.ext in Release/Textures.
            Example: KAT_Cliff_Short_01_1001_Normal.tif
            """
            mapping = {}
            try:
                p = Path(textures_root_dir)
                if not p.exists():
                    return mapping
                import re as _re
                rx = _re.compile(rf"^{_re.escape(base_name)}_(\d{{4}})_{_re.escape(map_kind)}\.(png|tif|tiff|exr|jpg|jpeg)$", _re.IGNORECASE)
                for file in p.iterdir():
                    if not file.is_file():
                        continue
                    m = rx.match(file.name)
                    if not m:
                        continue
                    try:
                        ud = int(m.group(1))
                        if ud >= 1001:
                            mapping[ud] = str(file)
                    except Exception:
                        continue
            except Exception:
                return mapping
            return mapping

        total_rc = 0
        # Ensure logs go under BakeMesh/bake_log and JSONs under BakeMesh/bake_settings
        log_dir = os.path.join(bake_mesh, "bake_log")
        settings_dir = os.path.join(bake_mesh, "bake_settings")
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(settings_dir, exist_ok=True)
        for lod_obj, lod_fbx, cage_obj, cage_fbx in lod_pairs:
            gen_base = os.path.join(settings_dir, f"_generated_bakeLOD_{lod_obj.name}")
            log_base = os.path.join(log_dir, f"bakeLOD_{lod_obj.name}")
            files = {"low": lod_fbx, "high": cinema_fbx, "cage": cage_fbx}
            # Determine UDIM tiles on LOD and matching Cinema normals in Textures
            tiles = []
            try:
                tiles = _udim_tiles_from_object(lod_obj)
            except Exception:
                tiles = []
            base_name = lod_obj.name.split('_LOD')[0]
            normals_by_udim    = _cinema_maps_by_udim(textures_root, base_name, 'Normal')
            basecolor_by_udim  = _cinema_maps_by_udim(textures_root, base_name, 'BaseColor')
            bent_by_udim       = _cinema_maps_by_udim(textures_root, base_name, 'BentNormal')

            # Convert tiles to UDIM numbers
            udim_list = []
            for (u, v) in (tiles or []):
                udim_list.append(1001 + int(u) + int(v) * 10)
            # If no UDIMs detected on mesh, still bake once
            if not udim_list:
                udim_list = [1001]

            # Require a Normal and BaseColor map for every UDIM we intend to bake; BentNormal is optional (warn only)
            missing_normals = [ud for ud in udim_list if ud not in normals_by_udim]
            if missing_normals:
                self.report({'ERROR'}, f"Missing Cinema Normal textures for UDIMs: {missing_normals} in {textures_root}")
                return {'CANCELLED'}
            missing_base = [ud for ud in udim_list if ud not in basecolor_by_udim]
            if missing_base:
                self.report({'ERROR'}, f"Missing Cinema BaseColor textures for UDIMs: {missing_base} in {textures_root}")
                return {'CANCELLED'}

            # Bake per UDIM with matching source texture and single uv_tile
            # Determine LOD index to derive per-LOD resolution
            m = re.search(r"_LOD([0-3])$", lod_obj.name)
            try:
                lod_idx = int(m.group(1)) if m else 0
            except Exception:
                lod_idx = 0
            lod_res_px = max(1, int(max_res_px // (2 ** lod_idx)))

            for ud in udim_list:
                gen_json = f"{gen_base}_{ud}.json"
                log_path = f"{log_base}_{ud}.log"
                _load_and_patch_json(preset_path, files, textures_dir, gen_json, lod_res_px)
                # Apply single-tile UDIM for this run
                try:
                    # Convert UDIM back to (u, v)
                    val = ud - 1001
                    u = val % 10
                    v = val // 10
                    _apply_udim_to_json(gen_json, [(u, v)])
                except Exception:
                    pass
                # Patch TextureTransfer bakers (Normal/BaseColor hard; others soft)
                # Build a cache for map kinds to avoid rescanning
                cache = {
                    'Normal': normals_by_udim,
                    'BaseColor': basecolor_by_udim,
                    'BentNormal': bent_by_udim,
                }
                def _get_map_for_kind(kind: str):
                    if kind in cache:
                        return cache[kind]
                    # Lazily resolve any additional TextureTransfer identifiers
                    cache[kind] = _cinema_maps_by_udim(textures_root, base_name, kind)
                    return cache[kind]
                ok, warns = _patch_transfer_bakers(gen_json, ud, _get_map_for_kind)
                if not ok:
                    # Determine which hard requirement is missing for better messaging
                    msg = []
                    if ud not in normals_by_udim:
                        msg.append('Normal')
                    if ud not in basecolor_by_udim:
                        msg.append('BaseColor')
                    if not msg:
                        msg.append('required texture')
                    self.report({'ERROR'}, f"Missing Cinema {' & '.join(msg)} for UDIM {ud}")
                    return {'CANCELLED'}
                for w in (warns or []):
                    self.report({'WARNING'}, w)
                # Ensure AO baker uses the Cinema Normal map as normal_map_path
                _patch_ao_normal(gen_json, normals_by_udim.get(ud))
                rc = _run_baker(exe_path, gen_json, log_path, cwd=bake_mesh, use_cpu=use_cpu)
                total_rc += (rc or 0)

        self.report({'INFO'}, f"LOD bakes finished. Output: {textures_dir}")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(VIVID_OT_bake_lod_textures)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_bake_lod_textures)
