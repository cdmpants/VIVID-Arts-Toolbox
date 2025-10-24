# vivid_arts_toolbox/bake_textures.py
import bpy
import os
import json
import math
import time
import subprocess
from pathlib import Path
from bpy.types import Operator, PropertyGroup
from bpy.props import BoolProperty, PointerProperty, EnumProperty, StringProperty, FloatProperty

# ------------------------------------------------------------
# Defaults & Paths
# ------------------------------------------------------------
def _default_baker_path():
    return r"C:\Program Files\Adobe\Adobe Substance 3D Designer\substance3d_baker.exe"

def _blend_dir():
    return bpy.path.abspath("//")

# _addon_dir was used for legacy resource lookup; no longer needed

def _folders():
    # Centralized via utils.project_dirs()
    from .utils import project_dirs
    try:
        root_p, bake_mesh_p, bake_tex_p = project_dirs()
        return str(root_p), str(bake_mesh_p), str(bake_tex_p)
    except Exception:
        # Fallback to // if unsaved; maintain previous behavior for unsaved scenarios
        root = _blend_dir()
        bake_mesh = os.path.join(root, "BakeMesh")
        bake_tex = os.path.join(root, "BakeTextures")
        return root, bake_mesh, bake_tex

def _ensure_outdir():
    root, bake_mesh, bake_tex = _folders()
    os.makedirs(bake_tex, exist_ok=True)
    return root, bake_mesh, bake_tex

# ------------------------------------------------------------
# File discovery
# ------------------------------------------------------------
def _glob_one(patterns, directory):
    cands = []
    pdir = Path(directory)
    for pat in patterns:
        cands.extend([p for p in pdir.glob(pat) if p.is_file()])
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(cands[0])

def _find_inputs(bake_mesh_dir):
    low  = _glob_one(["*_Optimized.fbx", "*_optimized.fbx"], bake_mesh_dir)
    high = _glob_one(["*_HighPoly.fbx", "*_highpoly.fbx", "*_HP.fbx"], bake_mesh_dir)
    cage = _glob_one(["*_Cage.fbx", "*_cage.fbx"], bake_mesh_dir)
    # TextureTransfer source texture: prefer common naming; include HighPoly.* as a robust fallback
    # Only consider image files for the TextureTransfer source (avoid matching FBX)
    diff = _glob_one([
        "*_u0_v0_diffuse.png", "*_u0_v0_diffuse.jpg", "*_u0_v0_diffuse.jpeg", "*_u0_v0_diffuse.tif", "*_u0_v0_diffuse.tiff", "*_u0_v0_diffuse.exr", "*_u0_v0_diffuse.tga",
        "*diffuse.png", "*diffuse.jpg", "*diffuse.jpeg", "*diffuse.tif", "*diffuse.tiff", "*diffuse.exr", "*diffuse.tga",
        "*_HighPoly.png", "*_HighPoly.jpg", "*_HighPoly.jpeg", "*_HighPoly.tif", "*_HighPoly.tiff", "*_HighPoly.exr", "*_HighPoly.tga",
        "*_highpoly.png", "*_highpoly.jpg", "*_highpoly.jpeg", "*_highpoly.tif", "*_highpoly.tiff", "*_highpoly.exr", "*_highpoly.tga",
    ], bake_mesh_dir)
    # Gather additional _Part#_HighPoly FBXs
    high_parts = []
    try:
        pdir = Path(bake_mesh_dir)
        import re
        for p in sorted(pdir.glob("*_Part*_HighPoly.fbx")):
            m = re.search(r"_Part(\d+)_HighPoly\\.fbx$", p.name, re.IGNORECASE)
            if m:
                high_parts.append((f"Part{m.group(1)}", str(p)))
    except Exception:
        pass
    return {"low": low, "high": high, "cage": cage, "diffuse": diff, "high_parts": high_parts}

# ------------------------------------------------------------
# JSON patching (paths + resolution)
# ------------------------------------------------------------
def _looks_like_path(s):
    if not isinstance(s, str):
        return False
    s2 = s.lower()
    return s2.endswith((".fbx", ".obj", ".png", ".tga", ".exr", ".jpg", ".jpeg", ".tif", ".tiff"))

def _set_if_present(dct, key, value):
    if isinstance(dct, dict) and key in dct and value:
        dct[key] = value

def _update_json_paths(data, files_map, output_dir):
    """
    Patch this Substance 3D Designer preset schema:
      - Top-level: output_path, low_scene_path
      - CommonProjection: high_scene_paths (list), cage_scene_path
      - Per-baker: source_texture_path (explicit), keep all other params as-is
      - Force any nested output dirs to BakeTextures
      NOTE: We do NOT touch 'is_selected' anywhere.
    """
    # ---- Top-level overrides ----
    _set_if_present(data, "output_path", output_dir)
    _set_if_present(data, "low_scene_path", files_map.get("low"))

    # CommonProjection dictionary
    cp = data.get("CommonProjection")
    if isinstance(cp, dict):
        # High poly: require explicit replacement; otherwise blank to avoid stale template paths
        if files_map.get("high"):
            cp["high_scene_paths"] = [files_map["high"]]
        elif "high_scene_paths" in cp:
            cp["high_scene_paths"] = []
        # Cage: optional; blank if not provided to avoid stale template paths
        if files_map.get("cage"):
            cp["cage_scene_path"] = files_map["cage"]
        elif "cage_scene_path" in cp:
            cp["cage_scene_path"] = ""
        # Toggle cage usage based on presence of a valid cage file
        try:
            use_cage = bool(files_map.get("cage") and os.path.isfile(files_map.get("cage", "")))
        except Exception:
            use_cage = False
        cp["use_cage"] = use_cage

    # Optional 'output' block normalization
    out = data.get("output")
    if isinstance(out, dict):
        for k in list(out.keys()):
            lk = k.lower()
            if lk in {"directory", "path"} or ("output" in lk and "path" in lk):
                out[k] = output_dir

    # Sweep through bakers to enforce output paths and source texture path
    def force_outputs_on_baker(baker_node):
        params = baker_node.get("parameters", {})
        for k in list(params.keys()):
            lk = k.lower()
            if lk in {"outputpath", "outputdirectory"} or ("output" in lk and "path" in lk):
                params[k] = output_dir
        cop = baker_node.get("commonOutputParameters")
        if isinstance(cop, dict):
            for k in list(cop.keys()):
                lk = k.lower()
                if lk in {"outputpath", "outputdirectory"} or ("output" in lk and "path" in lk):
                    cop[k] = output_dir

    def patch_params(params):
        # Only fix file-path params; never touch booleans like is_selected.
        if "source_texture_path" in params and files_map.get("diffuse"):
            params["source_texture_path"] = files_map["diffuse"]
        # Correct any explicit FBX path fields safely
        for k, v in list(params.items()):
            if isinstance(v, str) and _looks_like_path(v):
                lk = k.lower()
                if v.lower().endswith(".fbx"):
                    if "low" in lk and files_map.get("low"):
                        params[k] = files_map["low"]
                    elif "high" in lk:
                        params[k] = files_map.get("high", "")
                    elif "cage" in lk:
                        params[k] = files_map.get("cage", "")

    for baker in data.get("bakers", []):
        if not isinstance(baker, dict):
            continue
        force_outputs_on_baker(baker)
        params = baker.get("parameters")
        if isinstance(params, dict):
            patch_params(params)

    return data

def _apply_resolution_anywhere(mapping: dict, res_px: int):
    if not isinstance(mapping, dict):
        return
    log2 = int(round(math.log(res_px, 2)))

    # Common patterns
    if "output_size" in mapping and isinstance(mapping["output_size"], (list, tuple)) and len(mapping["output_size"]) == 2:
        mapping["output_size"] = [res_px, res_px]
    if "outputSize" in mapping and isinstance(mapping["outputSize"], (list, tuple)) and len(mapping["outputSize"]) == 2:
        mapping["outputSize"] = [log2, log2]

    for w_key, h_key in [("width", "height"), ("outputWidth", "outputHeight"), ("outWidth", "outHeight")]:
        if w_key in mapping: mapping[w_key] = res_px
        if h_key in mapping: mapping[h_key] = res_px

    for k in ["resolution", "textureSize", "size"]:
        if k in mapping:
            mapping[k] = res_px

def _apply_resolution(data, res_px):
    # Top-level Common often carries output_size referenced via "Value from Common/output_size"
    common = data.get("Common")
    if isinstance(common, dict):
        _apply_resolution_anywhere(common, res_px)
    out = data.get("output")
    if isinstance(out, dict):
        _apply_resolution_anywhere(out, res_px)
    for baker in data.get("bakers", []):
        if isinstance(baker, dict):
            _apply_resolution_anywhere(baker, res_px)
            if isinstance(baker.get("parameters"), dict):
                _apply_resolution_anywhere(baker["parameters"], res_px)
            if isinstance(baker.get("commonOutputParameters"), dict):
                _apply_resolution_anywhere(baker["commonOutputParameters"], res_px)

def _load_and_patch_json(src_json, files_map, output_dir, dest_json, res_px, settings=None):
    with open(src_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Paths
    data = _update_json_paths(data, files_map, output_dir)

    # Resolution
    if res_px:
        _apply_resolution(data, res_px)

    # Apply baker selections and AO params when provided
    if settings is not None:
        try:
            toggles = {
                'Displacement': bool(getattr(settings, 'enable_displacement', True)),
                'AOWide':       bool(getattr(settings, 'enable_aowide', True)),
                'NormalOS':     bool(getattr(settings, 'enable_normalos', True)),
                'Thickness':    bool(getattr(settings, 'enable_thickness', False)),
                'Curvature':    bool(getattr(settings, 'enable_curvature', False)),
                'BentNormalOS': bool(getattr(settings, 'enable_bentnormalos', False)),
                'Position':     bool(getattr(settings, 'enable_position', False)),
            }
            ao_max = float(getattr(settings, 'ao_secondary_max_distance', 0.04))
        except Exception:
            toggles = {}
            ao_max = None

        for baker in data.get('bakers', []) or []:
            if not isinstance(baker, dict):
                continue
            ident = baker.get('identifier') or ''
            params = baker.get('parameters')
            if not isinstance(params, dict):
                continue
            # Toggle known optional bakers; force others on
            if ident in toggles:
                params['is_selected'] = bool(toggles[ident])
            else:
                # Always keep required/default bakers on
                params['is_selected'] = True
            # AO slider override
            if ident == 'AO' and ao_max is not None:
                params['secondary.max_distance'] = ao_max

    # Save generated JSON
    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return dest_json

def _apply_udim_to_json(json_path, udim_tiles):
    """Patch an already-generated JSON to include UDIM tiles and flags.
    - udim_tiles: list of (u, v) ints; if empty or [(0,0)] only, no-op.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return json_path

    def set_if_key_present(container, key, value):
        if isinstance(container, dict) and key in container:
            container[key] = value

    # Determine if UDIM mode should be enabled
    tiles = sorted({(int(u), int(v)) for (u, v) in (udim_tiles or []) if int(u) >= 0 and int(v) >= 0})
    is_udim = False
    if tiles:
        # If any tile beyond (0,0), treat as UDIM; or more than one tile
        is_udim = len(tiles) > 1 or tiles != [(0, 0)]

    if is_udim:
        # Top-level defaults match Designer's "Bakers default values -> UV tiles: All"
        data["uv_tiles"] = [[u, v] for (u, v) in tiles]
        # Mirror uv_tiles into common sections if keys exist (no is_udim flags)
        for key in ("Common", "CommonProjection", "output"):
            sec = data.get(key)
            if isinstance(sec, dict):
                set_if_key_present(sec, "uv_tiles", [[u, v] for (u, v) in tiles])
        # Per-baker settings if the schema exposes these fields
        for baker in data.get("bakers", []) or []:
            if isinstance(baker, dict):
                for subkey in ("parameters", "commonOutputParameters"):
                    sub = baker.get(subkey)
                    if isinstance(sub, dict):
                        set_if_key_present(sub, "uv_tiles", [[u, v] for (u, v) in tiles])

    # Write back
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
    return json_path

    # Save generated JSON
    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return dest_json

# ------------------------------------------------------------
# Multi-highpoly helpers
# ------------------------------------------------------------
def _rename_bake_outputs_with_part(output_dir, part_token):
    """
    Normalize Part# filenames to the new convention:
      (objectname)_(Part#)_(udim)_(bakername)

    Handles these cases generically (no hard-coded baker names):
    - Old style: (objectname)_(udim)_(Part#)_(bakername)  → move Part# before UDIM
    - No part token: (objectname)_(udim)_(bakername)      → insert Part# before UDIM
    - Part token already in object segment (anywhere)     → ensure exactly one Part# right before UDIM
    """
    try:
        if not os.path.isdir(output_dir):
            return

        def is_udim(tok: str) -> bool:
            return tok.isdigit() and len(tok) == 4 and int(tok) >= 1001

        for fn in os.listdir(output_dir):
            src = os.path.join(output_dir, fn)
            if not os.path.isfile(src):
                continue
            name, ext = os.path.splitext(fn)
            parts = name.split('_')
            if len(parts) < 3:
                continue

            # Case A: ... _ <udim> _ <baker>
            if is_udim(parts[-2]):
                baker = parts[-1]
                udim = parts[-2]
                obj_tokens = parts[:-2]
                # Remove any existing part token in obj tokens
                obj_tokens = [t for t in obj_tokens if t != part_token]
                new_parts = obj_tokens + [part_token, udim, baker]
                new_name = '_'.join(new_parts) + ext
            # Case B: ... _ <Part#> _ <baker> with udim at -3 (legacy)
            elif len(parts) >= 4 and parts[-2] == part_token and is_udim(parts[-3]):
                baker = parts[-1]
                udim = parts[-3]
                obj_tokens = parts[:-3]
                obj_tokens = [t for t in obj_tokens if t != part_token]
                new_parts = obj_tokens + [part_token, udim, baker]
                new_name = '_'.join(new_parts) + ext
            else:
                # Unrecognized; skip
                continue

            if new_name != fn:
                dst = os.path.join(output_dir, new_name)
                try:
                    os.replace(src, dst)
                except Exception:
                    pass
    except Exception:
        pass

# (Delighter material setup moved to operators/setup_materials.py)

# ------------------------------------------------------------
# Running the baker
# ------------------------------------------------------------
def _run_baker(exe_path, json_path, log_path, cwd, use_cpu=False):
    cmd = [exe_path, "run", "--json", json_path, "--verbose"]
    if use_cpu:
        cmd.append("--cpu")  # force CPU (GPU = no flag)
    with open(log_path, "a", encoding="utf-8") as log:
        log.write("\n=== Running: {} ===\n".format(" ".join(cmd)))
        p = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=log, shell=False)
        log.write("\nReturn code: {}\n".format(p.returncode))
        return p.returncode

# ------------------------------------------------------------
# Export scope (only bake exports)
# ------------------------------------------------------------
def _try_export_bake_meshes_only():
    """Export only bake meshes (Optimized, Cage, HighPoly, Part#_HighPoly) to BakeMesh.

    We intentionally do NOT call the Cinema export operator here. Baking should not
    trigger Cinema exports. If a dedicated 'vivid.export_for_designer' operator is
    introduced in the future, we can prefer that here; until then, we always use
    the local FBX export routine.
    """
    try:
        root, bake_mesh, bake_tex = _folders()
        return _export_bake_meshes_local(bake_mesh)
    except Exception:
        return False


def _export_bake_meshes_local(bake_mesh_dir):
    """
    Export *_Optimized and *_Cage mesh objects to BakeMesh as FBX.
    - Create BakeMesh if missing
    - Temporarily unhide the objects and their collections to allow export
    - Use FBX options: FBX All + Apply Transform (bake_space_transform + apply_unit_scale + FBX_SCALE_ALL)
    - Restore prior visibility state after export
    """
    # Find targets
    opt = None; cage = None; highs = []
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        if o.name.endswith('_Optimized') and not opt:
            opt = o
        elif o.name.endswith('_Cage') and not cage:
            cage = o
        elif o.name.endswith('_HighPoly'):
            highs.append(o)
        else:
            try:
                import re
                if re.search(r"_Part\d+_HighPoly$", o.name):
                    highs.append(o)
            except Exception:
                pass

    if not opt:
        return False

    # Ensure BakeMesh exists
    os.makedirs(bake_mesh_dir, exist_ok=True)

    base = opt.name[:-10] if opt.name.endswith('_Optimized') else opt.name
    items = [(opt, os.path.join(bake_mesh_dir, f"{base}_Optimized.fbx"))]
    if cage:
        items.append((cage, os.path.join(bake_mesh_dir, f"{base}_Cage.fbx")))
    # Export all highpoly candidates
    for hp in highs:
        items.append((hp, os.path.join(bake_mesh_dir, f"{hp.name}.fbx")))

    # Helper: find the LayerCollection that maps to a given collection
    root_lc = bpy.context.view_layer.layer_collection
    def _find_layer_collection(lc, coll):
        if lc.collection == coll:
            return lc
        for child in getattr(lc, 'children', []):
            found = _find_layer_collection(child, coll)
            if found:
                return found
        return None

    prev_active = bpy.context.view_layer.objects.active
    obj_prev = {}
    lc_prev = {}
    try:
        for obj, out_path in items:
            # Record previous object visibility
            # Record previous visibility flags (including hide_get if available)
            prev = {
                'hide_viewport': getattr(obj, 'hide_viewport', None),
                'hide_render': getattr(obj, 'hide_render', None),
            }
            try:
                if hasattr(obj, 'hide_get'):
                    prev['hide'] = obj.hide_get()
            except Exception:
                prev['hide'] = None
            obj_prev[obj.name] = prev

            # Record and unhide layer collections
            for coll in getattr(obj, 'users_collection', []) or []:
                lc = _find_layer_collection(root_lc, coll)
                if lc and lc not in lc_prev:
                    lc_prev[lc] = getattr(lc, 'hide_viewport', None)
                    try:
                        cur = lc
                        while cur:
                            cur.hide_viewport = False
                            cur = getattr(cur, 'parent', None)
                    except Exception:
                        pass

            # Unhide object for export
            try:
                if hasattr(obj, 'hide_set'):
                    obj.hide_set(False)
            except Exception:
                pass
            try:
                if hasattr(obj, 'hide_viewport'):
                    obj.hide_viewport = False
            except Exception:
                pass
            try:
                if hasattr(obj, 'hide_render'):
                    obj.hide_render = False
            except Exception:
                pass

            # Export only this object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            kwargs = dict(
                filepath=out_path,
                use_selection=True,
                object_types={'MESH'},
                use_mesh_modifiers=True,
                mesh_smooth_type='FACE',
                axis_forward='-Z',
                axis_up='Y',
                bake_space_transform=True,
            )
            # Apply scale options akin to FBX All + Apply Transform
            try:
                kwargs['apply_unit_scale'] = True
                kwargs['apply_scale_options'] = 'FBX_SCALE_ALL'
            except Exception:
                pass
            bpy.ops.export_scene.fbx(**kwargs)

    finally:
        # Restore selection
        try:
            bpy.ops.object.select_all(action='DESELECT')
            if prev_active:
                prev_active.select_set(True)
                bpy.context.view_layer.objects.active = prev_active
        except Exception:
            pass

        # Restore collections
        for lc, prev in lc_prev.items():
            try:
                if prev is not None:
                    lc.hide_viewport = prev
            except Exception:
                pass

        # Restore object visibility
        for name, prev in obj_prev.items():
            o = bpy.data.objects.get(name)
            if not o:
                continue
            try:
                if prev.get('hide_viewport') is not None:
                    o.hide_viewport = prev['hide_viewport']
            except Exception:
                pass
            try:
                if prev.get('hide_render') is not None:
                    o.hide_render = prev['hide_render']
            except Exception:
                pass
            try:
                # Restore generic hide (object mode visibility) last
                if 'hide' in prev and prev['hide'] is not None and hasattr(o, 'hide_set'):
                    o.hide_set(prev['hide'])
            except Exception:
                pass

    return True

"""Material setup helpers removed; see operators/setup_materials.py"""

# Minimal helper retained for UDIM detection below
def _find_optimized_object():
    obj = bpy.context.active_object
    if obj and obj.type == 'MESH' and obj.name.endswith("_Optimized"):
        return obj
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.endswith("_Optimized"):
            return o
    return None

# ------------------------------------------------------------
# UDIM helpers
# ------------------------------------------------------------
def _udim_tiles_from_object(obj) -> list:
    """Return sorted unique (u, v) UDIM tile coordinates used by the object's active UV map.
    Returns [] if no UVs found.
    """
    tiles = set()
    try:
        me = getattr(obj, 'data', None)
        if not me or not getattr(me, 'uv_layers', None) or len(me.uv_layers) == 0:
            return []
        uv_layer = me.uv_layers.active or me.uv_layers[0]
        EPS = 1e-6
        def _tile_index(x: float) -> int:
            """Map UV coordinate to UDIM tile index along one axis.
            Treat exact positive-integer boundaries (>=1) within a tiny epsilon as belonging to the
            previous tile so faces on the 0-1 edge don't incorrectly spill into the next UDIM tile.
            Example: x == 1.0 -> tile 0; x == 2.0 -> tile 1; x == 0.0 stays tile 0.
            """
            n = math.floor(x)
            # Only adjust when we're at (or extremely close to) a positive integer boundary >= 1
            if x >= 0.0 and n >= 1 and (x - n) >= 0.0 and (x - n) < EPS:
                x = x - EPS
            return int(math.floor(x))
        for luv in uv_layer.data:
            u = _tile_index(float(luv.uv.x))
            v = _tile_index(float(luv.uv.y))
            tiles.add((u, v))
    except Exception:
        return []
    try:
        return sorted(tiles)
    except Exception:
        return list(tiles)

# ------------------------------------------------------------
# Properties (match panel.py)
# ------------------------------------------------------------
_BAKE_RES_ITEMS = [
    ("256",  "256",  "256 x 256"),
    ("512",  "512",  "512 x 512"),
    ("1024", "1024", "1024 x 1024"),
    ("2048", "2048", "2048 x 2048"),
    ("4096", "4096", "4096 x 4096"),
    ("8192", "8192", "8192 x 8192"),
]
_ENGINE_ITEMS = [
    ("GPU", "GPU", "Use GPU (no flag)"),
    ("CPU", "CPU", "Force CPU (--cpu)"),
]

class VIVID_DesignerBakeSettings(PropertyGroup):
    # Use explicit __annotations__ to keep Blender property registration
    __annotations__ = {}
    __annotations__['export_bake_meshes'] = BoolProperty(
        name="Export Bake Meshes",
        description="Export bake meshes before running the Designer baker",
        default=True
    )
    __annotations__['setup_material'] = BoolProperty(
        name="Setup Material",
        description="Create/assign a Delighter-based material on the _Optimized object using baked textures",
        default=True
    )
    __annotations__['ao_secondary_max_distance'] = FloatProperty(
        name="AO Max Distance",
        description="Controls AO baker secondary.max_distance in meters",
        default=0.04, min=0.0, soft_max=1.0, step=0.01, precision=4
    )
    __annotations__['bake_resolution'] = EnumProperty(
        name="Bake Resolution",
        description="Target output resolution for Designer bakers",
        items=_BAKE_RES_ITEMS,
        default="4096",
    )
    __annotations__['engine'] = EnumProperty(
        name="Engine",
        description="CPU (adds --cpu) or GPU (no flag) for Substance baker",
        items=_ENGINE_ITEMS,
        default="CPU",
    )
    __annotations__['custom_highpoly_dir'] = StringProperty(
        name="Custom HighPoly",
        description="Optional folder to look for HighPoly FBX and textures instead of //BakeMesh",
        subtype='DIR_PATH',
        default=""
    )
    # Additional bakers UI toggle
    __annotations__['show_additional_bakers'] = BoolProperty(
        name="Show Additional Bakers",
        description="Reveal additional optional bakers to include/exclude",
        default=False
    )
    # Per-baker enable flags
    __annotations__['enable_displacement'] = BoolProperty(
        name="Displacement",
        description="Enable Displacement baker",
        default=True
    )
    __annotations__['enable_aowide'] = BoolProperty(
        name="AOWide",
        description="Enable AOWide baker",
        default=True
    )
    __annotations__['enable_normalos'] = BoolProperty(
        name="NormalOS",
        description="Enable world-space NormalOS baker",
        default=True
    )
    __annotations__['enable_thickness'] = BoolProperty(
        name="Thickness",
        description="Enable Thickness baker",
        default=False
    )
    __annotations__['enable_curvature'] = BoolProperty(
        name="Curvature",
        description="Enable Curvature baker",
        default=False
    )
    __annotations__['enable_bentnormalos'] = BoolProperty(
        name="BentNormalOS",
        description="Enable world-space BentNormalOS baker",
        default=False
    )
    __annotations__['enable_position'] = BoolProperty(
        name="Position",
        description="Enable Position baker",
        default=False
    )

# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------
class VIVID_OT_bake_designer(Operator):
    bl_idname = "vivid.bake_designer"
    bl_label = "Bake Designer Textures"
    bl_description = "Run Designer headless using //BakeMesh → //BakeTextures; optionally build material on _Optimized"

    def execute(self, context):
        addon_key = __package__.split('.')[0] if __package__ else "vivid_arts_toolbox"
        prefs = context.preferences.addons.get(addon_key)
        baker_path_pref = getattr(prefs.preferences, "substance_baker_path", "") if prefs and hasattr(prefs, "preferences") else ""
        exe_path = baker_path_pref or _default_baker_path()
        if not os.path.isfile(exe_path):
            self.report({'ERROR'}, f"Designer baker not found: {exe_path}")
            return {'CANCELLED'}

        settings = getattr(context.scene, "vivid_designer_bake", None)
        if settings and settings.export_bake_meshes:
            _try_export_bake_meshes_only()

        root, bake_mesh, bake_tex = _ensure_outdir()
        if not os.path.isdir(bake_mesh):
            self.report({'ERROR'}, f"Missing BakeMesh folder: {bake_mesh}")
            return {'CANCELLED'}

        # Allow overriding HighPoly search directory via custom_highpoly_dir
        high_src_dir = bake_mesh
        if settings and getattr(settings, 'custom_highpoly_dir', ''):
            cand = bpy.path.abspath(getattr(settings, 'custom_highpoly_dir', '')).strip()
            if cand and os.path.isdir(cand):
                high_src_dir = cand
        files = _find_inputs(high_src_dir)
        # Always keep low/high/cage from local BakeMesh if not found in override dir
        if not files.get('low') or not os.path.isfile(files.get('low', '')):
            files['low'] = _glob_one(["*_Optimized.fbx", "*_optimized.fbx"], bake_mesh)
        if not files.get('high') or not os.path.isfile(files.get('high', '')):
            files['high'] = _glob_one(["*_HighPoly.fbx", "*_highpoly.fbx", "*_HP.fbx"], bake_mesh)
        if not files.get('cage') or not os.path.isfile(files.get('cage', '')):
            files['cage'] = _glob_one(["*_Cage.fbx", "*_cage.fbx"], bake_mesh)
        if not files.get('diffuse') or not os.path.isfile(files.get('diffuse', '')):
            files['diffuse'] = _glob_one([
                "*_u0_v0_diffuse.png", "*_u0_v0_diffuse.jpg", "*_u0_v0_diffuse.jpeg", "*_u0_v0_diffuse.tif", "*_u0_v0_diffuse.tiff", "*_u0_v0_diffuse.exr", "*_u0_v0_diffuse.tga",
                "*diffuse.png", "*diffuse.jpg", "*diffuse.jpeg", "*diffuse.tif", "*diffuse.tiff", "*diffuse.exr", "*diffuse.tga",
                "*_HighPoly.png", "*_HighPoly.jpg", "*_HighPoly.jpeg", "*_HighPoly.tif", "*_HighPoly.tiff", "*_HighPoly.exr", "*_HighPoly.tga",
                "*_highpoly.png", "*_highpoly.jpg", "*_highpoly.jpeg", "*_highpoly.tif", "*_highpoly.tiff", "*_highpoly.exr", "*_highpoly.tga",
            ], bake_mesh)
        if not files.get("low"):
            self.report({'ERROR'}, "Missing required low mesh (e.g. *_Optimized.fbx) in BakeMesh.")
            return {'CANCELLED'}
        if not files.get("high"):
            self.report({'ERROR'}, "Missing required high mesh (e.g. *_HighPoly.fbx) in BakeMesh or override directory.")
            return {'CANCELLED'}

        # Always use the master preset shipped with the addon (resources only)
        from .utils import resource_or_legacy
        main_json = str(resource_or_legacy("bake_preset.json"))
        if not os.path.isfile(main_json):
            self.report({'ERROR'}, "Missing bake_preset.json in add-on resources.")
            return {'CANCELLED'}

        # Resolution + engine
        try:
            res_px = int(settings.bake_resolution) if settings and settings.bake_resolution else 2048
        except ValueError:
            res_px = 2048
        use_cpu = (settings.engine == "CPU") if settings else False

        # --- Start timer ---
        start_time = time.time()

        # Multi-highpoly: if _Part#_HighPoly FBXs exist, bake each into a subfolder
        parts = files.get("high_parts") or []
        base_name = None
        try:
            opt_obj = _find_optimized_object()
            if opt_obj:
                nm = opt_obj.name
                base_name = nm[:-10] if nm.endswith('_Optimized') else nm
        except Exception:
            base_name = None

        rc_total = 0
        # Ensure a dedicated log directory under BakeMesh
        log_dir = os.path.join(bake_mesh, "bake_log")
        os.makedirs(log_dir, exist_ok=True)
        # Ensure a dedicated settings directory under BakeMesh for generated JSONs
        settings_dir = os.path.join(bake_mesh, "bake_settings")
        os.makedirs(settings_dir, exist_ok=True)
        if parts:
            for part_token, hp in parts:
                out_dir = os.path.join(bake_tex, part_token)
                os.makedirs(out_dir, exist_ok=True)
                files_local = dict(files)
                files_local['high'] = hp
                log_path = os.path.join(log_dir, f"bake_{part_token}.log")
                gen_json = os.path.join(settings_dir, f"_generated_bake_{part_token}.json")
                _load_and_patch_json(main_json, files_local, out_dir, gen_json, res_px, settings=settings)
                try:
                    udim_tiles = _udim_tiles_from_object(opt_obj) if opt_obj else []
                    if udim_tiles and (len(udim_tiles) > 1 or udim_tiles != [(0, 0)]):
                        _apply_udim_to_json(gen_json, udim_tiles)
                except Exception:
                    pass
                rc = _run_baker(exe_path, gen_json, log_path, cwd=bake_mesh, use_cpu=use_cpu)
                rc_total = rc_total or rc
                _rename_bake_outputs_with_part(out_dir, part_token)
        else:
            # Always bake into Part1 subfolder and include Part1 in filenames
            # Patch + run a single JSON
            part_dir = os.path.join(bake_tex, "Part1")
            os.makedirs(part_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "bake_designer.log")
            gen_main = os.path.join(settings_dir, "_generated_bake_preset.json")
            _load_and_patch_json(main_json, files, part_dir, gen_main, res_px, settings=settings)

            # UDIM detection from active *_Optimized object and JSON patching (uv_tiles, is_udim)
            try:
                opt_obj = _find_optimized_object()
                udim_tiles = _udim_tiles_from_object(opt_obj) if opt_obj else []
                if udim_tiles and (len(udim_tiles) > 1 or udim_tiles != [(0, 0)]):
                    _apply_udim_to_json(gen_main, udim_tiles)
            except Exception:
                pass
            rc_total = _run_baker(exe_path, gen_main, log_path, cwd=bake_mesh, use_cpu=use_cpu)
            # Normalize filenames to (object)_(Part1)_(udim)_(baker)
            _rename_bake_outputs_with_part(part_dir, "Part1")

        # --- Stop timer ---
        duration = time.time() - start_time

        
        # Optional material setup: call the dedicated operator (decoupled from this module)
        if settings and settings.setup_material:
            try:
                bpy.ops.vivid.setup_materials()
            except Exception:
                self.report({'WARNING'}, "Failed to run material setup operator.")

        if parts:
            self.report({'INFO'}, f"Designer baking complete for {len(parts)} highpoly parts in {duration:.1f}s → {bake_tex}\\Part#")
        else:
            if rc_total != 0:
                self.report({'WARNING'}, f"Designer baking finished with warnings/errors in {duration:.1f}s. See log: {log_path}")
            else:
                self.report({'INFO'}, f"Designer baking complete in {duration:.1f}s → {bake_tex}")

        # Attempt to switch active 3D View(s) to Material Preview and Diffuse Color pass
        # (Safe no-op in background/headless mode or if properties unavailable.)
        try:
            wm = bpy.context.window_manager
            if wm:
                for window in wm.windows:
                    scr = window.screen
                    if not scr:
                        continue
                    for area in scr.areas:
                        if area.type == 'VIEW_3D':
                            for space in area.spaces:
                                if space.type == 'VIEW_3D':
                                    shading = getattr(space, 'shading', None)
                                    if shading:
                                        # Set viewport shading mode
                                        try:
                                            shading.type = 'MATERIAL'
                                        except Exception:
                                            pass
                                        # Set render pass if supported (usually affects Rendered / Material preview overlays)
                                        if hasattr(shading, 'render_pass'):
                                            try:
                                                shading.render_pass = 'DIFFUSE_COLOR'
                                            except Exception:
                                                pass
                            # We only need to modify the first VIEW_3D we encounter per window
                            break
        except Exception:
            pass
        return {'FINISHED'}





# (Delighter material import and assignment moved to operators/setup_materials.py)

# ------------------------------------------------------------
# Registration (no panel here — your main panel draws the UI)
# ------------------------------------------------------------
CLASSES = (
    VIVID_DesignerBakeSettings,
    VIVID_OT_bake_designer,
)

def register_designer_bake():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.vivid_designer_bake = PointerProperty(type=VIVID_DesignerBakeSettings)

def unregister_designer_bake():
    if hasattr(bpy.types.Scene, "vivid_designer_bake"):
        del bpy.types.Scene.vivid_designer_bake
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)

# ------------------------------------------------------------
# Extended baked texture finder (fix for Light Removal)
# ------------------------------------------------------------
"""Extended baked texture finder removed with material setup decoupling."""

