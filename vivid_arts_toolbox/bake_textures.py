# vivid_arts_toolbox/bake_textures.py
import bpy
import os
import json
import math
import time
import subprocess
from pathlib import Path
from bpy.types import Operator, PropertyGroup
from bpy.props import BoolProperty, PointerProperty, EnumProperty

# ------------------------------------------------------------
# Defaults & Paths
# ------------------------------------------------------------
def _default_baker_path():
    return r"C:\Program Files\Adobe\Adobe Substance 3D Designer\substance3d_baker.exe"

def _blend_dir():
    return bpy.path.abspath("//")

def _addon_dir():
    # Folder where this file lives (the vivid_arts_toolbox package directory)
    return os.path.dirname(os.path.abspath(__file__))

def _folders():
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
    diff = _glob_one(["*_u0_v0_diffuse.png", "*_u0_v0_diffuse.*", "*diffuse.*"], bake_mesh_dir)
    return {"low": low, "high": high, "cage": cage, "diffuse": diff}

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
        if files_map.get("high"):
            cp["high_scene_paths"] = [files_map["high"]]
        _set_if_present(cp, "cage_scene_path", files_map.get("cage"))

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
                    elif "high" in lk and files_map.get("high"):
                        params[k] = files_map["high"]
                    elif "cage" in lk and files_map.get("cage"):
                        params[k] = files_map["cage"]

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

def _load_and_patch_json(src_json, files_map, output_dir, dest_json, res_px):
    with open(src_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Paths
    data = _update_json_paths(data, files_map, output_dir)

    # Resolution
    if res_px:
        _apply_resolution(data, res_px)

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
    for ns, op in [("vivid", "export_for_designer"), ("vivid", "export_asset")]:
        try:
            ns_ops = getattr(bpy.ops, ns, None)
            if ns_ops:
                fn = getattr(ns_ops, op, None)
                if fn and fn.poll():
                    fn()
                    return True
        except Exception:
            pass
    # Fallback: export Optimized and Cage locally into BakeMesh
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
    opt = None; cage = None
    for o in bpy.data.objects:
        if o.type != 'MESH':
            continue
        if o.name.endswith('_Optimized') and not opt:
            opt = o
        elif o.name.endswith('_Cage') and not cage:
            cage = o
        if opt and cage:
            break

    if not opt:
        return False

    # Ensure BakeMesh exists
    os.makedirs(bake_mesh_dir, exist_ok=True)

    base = opt.name[:-10] if opt.name.endswith('_Optimized') else opt.name
    items = [(opt, os.path.join(bake_mesh_dir, f"{base}_Optimized.fbx"))]
    if cage:
        items.append((cage, os.path.join(bake_mesh_dir, f"{base}_Cage.fbx")))

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

# ------------------------------------------------------------
# Material Setup
# ------------------------------------------------------------
def _find_optimized_object():
    obj = bpy.context.active_object
    if obj and obj.type == 'MESH' and obj.name.endswith("_Optimized"):
        return obj
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.endswith("_Optimized"):
            return o
    return None

def _remove_suffix(name: str, suffix: str):
    return name[:-len(suffix)] if name.endswith(suffix) else name

def _find_baked_textures(bake_tex_dir):
    # BaseColor transfer (DLBC) and Normal maps from BakeTextures
    img_norm = _glob_one(["*_Normal.*", "*_Normals.*"], bake_tex_dir)
    img_dlbc = _glob_one(["*DLBC*.*", "*BaseColor*.*"], bake_tex_dir)
    return img_dlbc, img_norm

def _find_baked_textures_by_suffix(bake_tex_dir, base_name: str = None):
    """Find baked textures by suffix only (basename flexible):
    - DLBC    -> *_DLBC.*
    - DLBN    -> *_DLBN.*
    - DLAO    -> *_DLAO.*
    - Normals -> *_Normal(s).* (excludes Bent_Normals)
    Prefers files whose name contains the current base_name (case-insensitive),
    but will fall back to any match. Returns newest per category.
    """
    if not os.path.isdir(bake_tex_dir):
        return None, None, None, None

    exts = (".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp")
    base_tokens = []
    if base_name:
        b = base_name.lower()
        base_tokens = [b, b.replace(" ", "_")]

    # Track preferred (contains base) and fallback (any) candidates separately
    picked = {
        "dlbc": {"pref": (None, -1), "any": (None, -1)},
        "dlao": {"pref": (None, -1), "any": (None, -1)},
        "dlbn": {"pref": (None, -1), "any": (None, -1)},
        "normal": {"pref": (None, -1), "any": (None, -1)},
    }

    for fn in os.listdir(bake_tex_dir):
        full = os.path.join(bake_tex_dir, fn)
        lower = fn.lower()
        if not lower.endswith(exts) or not os.path.isfile(full):
            continue
        name_no_ext, _ = os.path.splitext(lower)

        try:
            ts = os.stat(full).st_mtime
        except Exception:
            ts = 0

        contains_base = any(bt in name_no_ext for bt in base_tokens) if base_tokens else False

        def choose(cat: str, path: str, ts_val: float, prefer: bool):
            key = "pref" if prefer else "any"
            cur_path, cur_ts = picked[cat][key]
            if ts_val > cur_ts:
                picked[cat][key] = (path, ts_val)

        if name_no_ext.endswith("_dlbc"):
            choose("dlbc", full, ts, contains_base)
        elif name_no_ext.endswith("_dlao"):
            choose("dlao", full, ts, contains_base)
        elif name_no_ext.endswith("_dlbn"):
            choose("dlbn", full, ts, contains_base)
        elif name_no_ext.endswith("_normal") or name_no_ext.endswith("_normals"):
            # For normal map only, exclude bent normals
            if not ("bent" in name_no_ext and "normal" in name_no_ext):
                choose("normal", full, ts, contains_base)

    def resolve(cat: str):
        pref_path, pref_ts = picked[cat]["pref"]
        any_path, any_ts = picked[cat]["any"]
        return pref_path if pref_path else any_path

    dlbc = resolve("dlbc")
    dlao = resolve("dlao")
    dlbn = resolve("dlbn")
    normal = resolve("normal")
    return dlbc, normal, dlao, dlbn

def _extract_udim_token(text: str):
    """Extract a UDIM numeric token like _1001, _1002 from a string; returns '1001' etc or None.
    Only accepts values >= 1001.
    """
    try:
        import re
        m = re.search(r"_(\d{4})(?:\D|$)", text or "")
        if m:
            val = int(m.group(1))
            if val >= 1001:
                return str(val)
    except Exception:
        pass
    return None

def _find_baked_textures_by_suffix_udim(bake_tex_dir, base_name: str = None):
    """Discover baked textures grouped by UDIM token per category.
    Returns a dict: { udim: { 'dlbc': path or None, 'normal':..., 'dlao':..., 'dlbn':... } }
    Prefers files containing base_name but will fall back to any; picks newest per (udim, category).
    If no UDIM token found in a file, it is grouped under '1001' to support non-UDIM flows with {udim}=1001.
    """
    out = {}
    if not os.path.isdir(bake_tex_dir):
        return out
    exts = (".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp")
    base_tokens = []
    if base_name:
        b = base_name.lower()
        base_tokens = [b, b.replace(" ", "_")]

    def ensure_key(u):
        if u not in out:
            out[u] = {
                'dlbc': (None, -1, False),
                'dlao': (None, -1, False),
                'dlbn': (None, -1, False),
                'normal': (None, -1, False),
            }

    def consider(u, cat, path, ts, prefer):
        cur_p, cur_t, cur_pref = out[u][cat]
        # Prefer base-matching files; if equal preference, pick newest
        if prefer and not cur_pref:
            out[u][cat] = (path, ts, True)
        elif prefer == cur_pref and ts > cur_t:
            out[u][cat] = (path, ts, cur_pref)
        elif not cur_p:
            out[u][cat] = (path, ts, cur_pref)

    for fn in os.listdir(bake_tex_dir):
        full = os.path.join(bake_tex_dir, fn)
        lower = fn.lower()
        if not lower.endswith(exts) or not os.path.isfile(full):
            continue
        name_no_ext, _ = os.path.splitext(lower)
        udim = _extract_udim_token(name_no_ext) or '1001'
        contains_base = any(bt in name_no_ext for bt in base_tokens) if base_tokens else False
        try:
            ts = os.stat(full).st_mtime
        except Exception:
            ts = 0
        ensure_key(udim)
        if name_no_ext.endswith("_dlbc"):
            consider(udim, 'dlbc', full, ts, contains_base)
        elif name_no_ext.endswith("_dlao"):
            consider(udim, 'dlao', full, ts, contains_base)
        elif name_no_ext.endswith("_dlbn"):
            consider(udim, 'dlbn', full, ts, contains_base)
        elif name_no_ext.endswith("_normal") or name_no_ext.endswith("_normals"):
            if not ("bent" in name_no_ext and "normal" in name_no_ext):
                consider(udim, 'normal', full, ts, contains_base)

    # Strip timestamps/prefer flags
    simplified = {}
    for u, cats in out.items():
        simplified[u] = {k: v[0] for k, v in cats.items()}
    return simplified

def _ensure_material(obj, base_name, dlbc_path, normal_path):
    mat_name = base_name
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree; nodes = nt.nodes; links = nt.links
    for n in list(nodes): nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (400, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (0, 0)
    bsdf.inputs["Roughness"].default_value = 0.9
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if dlbc_path and os.path.isfile(dlbc_path):
        img_node = nodes.new("ShaderNodeTexImage"); img_node.location = (-400, 100)
        try: img_node.image = bpy.data.images.load(dlbc_path, check_existing=True)
        except Exception: img_node.image = None
        if img_node.image:
            img_node.image.colorspace_settings.name = "sRGB"
            links.new(img_node.outputs["Color"], bsdf.inputs["Base Color"])

    if normal_path and os.path.isfile(normal_path):
        nrm_img = nodes.new("ShaderNodeTexImage"); nrm_img.location = (-600, -200)
        try: nrm_img.image = bpy.data.images.load(normal_path, check_existing=True)
        except Exception: nrm_img.image = None
        if nrm_img.image:
            nrm_img.image.colorspace_settings.name = "Non-Color"
        nrm = nodes.new("ShaderNodeNormalMap"); nrm.location = (-200, -200)
        links.new(nrm_img.outputs["Color"], nrm.inputs["Color"])
        links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return mat

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
        for luv in uv_layer.data:
            u = int(math.floor(luv.uv.x))
            v = int(math.floor(luv.uv.y))
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
        description="Create/assign a material on the _Optimized object using baked DLBC/Normal maps",
        default=True
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

        files = _find_inputs(bake_mesh)
        if not files.get("low"):
            self.report({'ERROR'}, "Missing required low mesh (e.g. *_Optimized.fbx) in BakeMesh.")
            return {'CANCELLED'}

        # Always use the master preset shipped with the addon
        addon_json = os.path.join(_addon_dir(), "bake_preset.json")
        if os.path.isfile(addon_json):
            main_json = addon_json
        else:
            # Fallback to project-local if addon copy is missing
            main_json = os.path.join(bake_mesh, "bake_preset.json")

        if not os.path.isfile(main_json):
            self.report({'ERROR'}, "Missing bake_preset.json (expected in addon folder or BakeMesh).")
            return {'CANCELLED'}

        # Resolution + engine
        try:
            res_px = int(settings.bake_resolution) if settings and settings.bake_resolution else 2048
        except ValueError:
            res_px = 2048
        use_cpu = (settings.engine == "CPU") if settings else False

        # --- Start timer ---
        start_time = time.time()

        # Patch + run a single JSON
        log_path = os.path.join(bake_mesh, "bake_designer.log")
        gen_main = os.path.join(bake_mesh, "_generated_bake_preset.json")
        _load_and_patch_json(main_json, files, bake_tex, gen_main, res_px)

        # UDIM detection from active *_Optimized object and JSON patching (uv_tiles, is_udim)
        try:
            opt_obj = _find_optimized_object()
            udim_tiles = _udim_tiles_from_object(opt_obj) if opt_obj else []
            if udim_tiles and (len(udim_tiles) > 1 or udim_tiles != [(0, 0)]):
                _apply_udim_to_json(gen_main, udim_tiles)
        except Exception:
            pass
        rc_total = _run_baker(exe_path, gen_main, log_path, cwd=bake_mesh, use_cpu=use_cpu)

        # --- Stop timer ---
        duration = time.time() - start_time

        
        # Optional material setup (Delighter only)
        if settings and settings.setup_material:
            opt_obj = _find_optimized_object()
            if opt_obj:
                _append_delighter_material(opt_obj, bake_tex)
            else:
                self.report({'WARNING'}, "No *_Optimized object found to assign material.")

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





# ------------------------------------------------------------
# Delighter material import + setup (must run after baking)
# ------------------------------------------------------------

def _append_delighter_material(obj, bake_tex_dir):
    """
    Appends 'Delighter' material from Delighter.blend (bundled with addon)
    and assigns baked textures:
      - Node 'DLBC'      -> *_DLBC.*     (sRGB)
      - Node 'DLAO'      -> *_DLAO.*     (Non-Color)
      - Node 'DLBN'      -> *_DLBN.*     (Non-Color)
      - Node 'Normals'   -> *_Normal(s).* (Non-Color, excludes Bent_Normals)
    Replaces existing material slots with this material (keeps the same number of slots).
    If the object has no slots, adds one. The material is copied and renamed to the object's
    base name (object name without the "_Optimized" suffix).
    """
    if not obj or obj.type != 'MESH':
        return

    # Resolve base name from object (strip _Optimized suffix if present)
    base_name = obj.name
    if base_name.endswith("_Optimized"):
        base_name = base_name[:-10]

    # Resolve path to Delighter.blend next to this module
    try:
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        pkg_dir = os.path.dirname(__file__)
    blend_path = os.path.join(pkg_dir, "Delighter.blend")
    if not os.path.isfile(blend_path):
        print("[Delighter] Missing Delighter.blend")
        return

    # Discover textures, supporting UDIM groupings
    udim_map = _find_baked_textures_by_suffix_udim(bake_tex_dir, base_name)
    # Also compute single fallback set (non-UDIM)
    dlbc_single, normal_single, dlao_single, dlbn_single = _find_baked_textures_by_suffix(bake_tex_dir, base_name)

    # Append the material (re-use if already present)
    src_name = "Delighter"
    src_mat = bpy.data.materials.get(src_name)
    if src_mat is None:
        try:
            with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
                if src_name in (data_from.materials or []):
                    data_to.materials = [src_name]
            src_mat = bpy.data.materials.get(src_name)
        except Exception as e:
            print(f"[Delighter] Append failed: {e}")
            return
    if src_mat is None:
        print("[Delighter] Could not get appended material")
        return

    def _norm_path(p: str) -> str:
        try:
            return bpy.path.abspath(os.path.normpath(p)).replace('\\', '/')
        except Exception:
            return p

    def _find_existing_image_by_path(abs_path: str):
        try:
            target = os.path.normcase(bpy.path.abspath(abs_path))
            for im in bpy.data.images:
                try:
                    cur = os.path.normcase(bpy.path.abspath(im.filepath or im.filepath_raw))
                except Exception:
                    cur = (im.filepath or im.filepath_raw or "")
                if cur and cur == target:
                    return im
        except Exception:
            pass
        return None

    def _overwrite_material_with_template(dst_mat: bpy.types.Material, template_mat: bpy.types.Material):
        try:
            dst_mat.use_nodes = True
            dst_nt = dst_mat.node_tree
            src_nt = template_mat.node_tree
            if not (dst_nt and src_nt):
                return
            # Clear dst nodes
            for n in list(dst_nt.nodes):
                dst_nt.nodes.remove(n)
            # Copy nodes
            node_map = {}
            for n in src_nt.nodes:
                nn = dst_nt.nodes.new(type=n.bl_idname)
                try:
                    nn.name = n.name
                except Exception:
                    pass
                nn.label = getattr(n, 'label', nn.label)
                nn.location = getattr(n, 'location', (0, 0))
                nn.width = getattr(n, 'width', nn.width)
                nn.height = getattr(n, 'height', nn.height)
                nn.hide = getattr(n, 'hide', False)
                # Preserve node tree for Group nodes
                try:
                    if hasattr(nn, 'node_tree') and hasattr(n, 'node_tree'):
                        nn.node_tree = n.node_tree
                except Exception:
                    pass
                node_map[n] = nn
            # Copy links
            def _socket_index(list_sockets, sock):
                try:
                    return list_sockets[:].index(sock)
                except ValueError:
                    try:
                        names = [s.name for s in list_sockets]
                        return names.index(getattr(sock, 'name', ''))
                    except Exception:
                        return -1
            for lk in src_nt.links:
                from_n = node_map.get(lk.from_node)
                to_n = node_map.get(lk.to_node)
                if not (from_n and to_n):
                    continue
                try:
                    fi = _socket_index(lk.from_node.outputs, lk.from_socket)
                    ti = _socket_index(lk.to_node.inputs, lk.to_socket)
                    if fi >= 0 and ti >= 0:
                        dst_nt.links.new(from_n.outputs[fi], to_n.inputs[ti])
                except Exception:
                    pass
        except Exception as e:
            print(f"[Delighter] Overwrite material template error: {e}")

    def _set_images_on_material(dst_mat: bpy.types.Material, dlbc, normal_path, dlao, dlbn):
        try:
            nt = dst_mat.node_tree
            nodes = nt.nodes if nt else None
            def _set_img(node_name, img_path, cs_name):
                if not nodes:
                    return
                node = nodes.get(node_name)
                if not (node and hasattr(node, "image")):
                    return
                node.image = None
                if not img_path or not os.path.isfile(img_path):
                    return
                img = None
                try:
                    np = _norm_path(img_path)
                    img = _find_existing_image_by_path(np)
                    if img is None:
                        img = bpy.data.images.load(np, check_existing=True)
                    try:
                        if getattr(img, 'packed_file', None):
                            img.unpack(method='USE_ORIGINAL')
                    except Exception:
                        pass
                except Exception:
                    img = None
                if img:
                    try:
                        img.reload()
                    except Exception:
                        pass
                    node.image = img
                    try:
                        node.image.colorspace_settings.name = cs_name
                    except Exception:
                        pass
            _set_img("DLBC", dlbc, "sRGB")
            _set_img("DLAO", dlao, "Non-Color")
            _set_img("DLBN", dlbn, "Non-Color")
            if normal_path and os.path.isfile(normal_path):
                node_normals = (
                    nodes.get("Normals") or
                    nodes.get("Normal") or
                    nodes.get("NormalTex")
                )
                if not node_normals:
                    for cand in nodes:
                        try:
                            if cand.bl_idname == 'ShaderNodeTexImage':
                                nm = (cand.name or "").lower()
                                if ("normal" in nm) and ("bent" not in nm):
                                    node_normals = cand
                                    break
                        except Exception:
                            pass
                if node_normals and hasattr(node_normals, "image"):
                    node_normals.image = None
                    img = None
                    try:
                        np = _norm_path(normal_path)
                        img = _find_existing_image_by_path(np)
                        if img is None:
                            img = bpy.data.images.load(np, check_existing=True)
                        try:
                            if getattr(img, 'packed_file', None):
                                img.unpack(method='USE_ORIGINAL')
                        except Exception:
                            pass
                    except Exception:
                        img = None
                    if img:
                        try:
                            img.reload()
                        except Exception:
                            pass
                        node_normals.image = img
                        try:
                            node_normals.image.colorspace_settings.name = "Non-Color"
                        except Exception:
                            pass
        except Exception as e:
            print(f"[Delighter] Node setup error: {e}")

    # Decide if UDIM-style multi-material assignment is needed
    slots = obj.data.materials
    has_udim_mats = False
    try:
        for m in slots:
            if m and _extract_udim_token(m.name):
                has_udim_mats = True
                break
    except Exception:
        has_udim_mats = False

    try:
        if has_udim_mats or (len(udim_map.keys()) > 1):
            # Per-slot assignment based on material UDIM; overwrite slot materials in place
            for i in range(len(slots)):
                m_old = slots[i]
                target_name = m_old.name if m_old and m_old.name else f"{base_name}_1001"
                udim = _extract_udim_token(target_name) or '1001'
                tex = udim_map.get(udim) or udim_map.get('1001') or {
                    'dlbc': dlbc_single,
                    'normal': normal_single,
                    'dlao': dlao_single,
                    'dlbn': dlbn_single,
                }
                if m_old is None:
                    m_old = bpy.data.materials.new(target_name)
                    slots[i] = m_old
                _overwrite_material_with_template(m_old, src_mat)
                _set_images_on_material(m_old, tex.get('dlbc'), tex.get('normal'), tex.get('dlao'), tex.get('dlbn'))
            obj.active_material = slots[0] if len(slots) > 0 else None
        else:
            # Single material applied to all slots; overwrite each slot's material contents
            tex = udim_map.get('1001') or {
                'dlbc': dlbc_single,
                'normal': normal_single,
                'dlao': dlao_single,
                'dlbn': dlbn_single,
            }
            if len(slots) == 0:
                m = bpy.data.materials.new(base_name)
                slots.append(m)
            for i in range(len(slots)):
                m = slots[i]
                if m is None:
                    m = bpy.data.materials.new(base_name)
                    slots[i] = m
                _overwrite_material_with_template(m, src_mat)
                _set_images_on_material(m, tex.get('dlbc'), tex.get('normal'), tex.get('dlao'), tex.get('dlbn'))
            obj.active_material = slots[0]
    except Exception as e:
        print(f"[Delighter] Assign error: {e}")

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
def _find_baked_textures_ex(bake_tex_dir):
    """
    Returns (dlbc_path, normal_path, dlao_path, dlbn_path).
    - Normal path excludes Bent_Normals on purpose.
    """
    if not os.path.isdir(bake_tex_dir):
        return None, None, None, None

    normal_path = None
    for fn in sorted(os.listdir(bake_tex_dir)):
        lower = fn.lower()
        if lower.endswith((".png",".tga",".jpg",".jpeg",".exr",".tif",".tiff",".bmp",".webp")):
            if "bent" in lower and "normal" in lower:
                continue
            if "_normal" in lower or "_normals" in lower:
                normal_path = os.path.join(bake_tex_dir, fn)
                break

    dlbc = None; dlao = None; dlbn = None
    for fn in sorted(os.listdir(bake_tex_dir)):
        lower = fn.lower()
        full = os.path.join(bake_tex_dir, fn)
        if any(k in lower for k in ["_dlbc","basecolor","base_color","albedo"]):
            dlbc = dlbc or full
        if "_dlao" in lower or (("ao" in lower) and ("dl" in lower)):
            dlao = dlao or full
        if "_dlbn" in lower or ("bent" in lower and "normal" in lower):
            dlbn = dlbn or full
    return dlbc, normal_path, dlao, dlbn

