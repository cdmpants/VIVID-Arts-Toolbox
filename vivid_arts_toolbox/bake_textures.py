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
    return False

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
    export_bake_meshes: BoolProperty(
        name="Export Bake Meshes",
        description="Export bake meshes before running the Designer baker",
        default=True
    )
    setup_material: BoolProperty(
        name="Setup Material",
        description="Create/assign a material on the _Optimized object using baked DLBC/Normal maps",
        default=True
    )
    bake_resolution: EnumProperty(
        name="Bake Resolution",
        description="Target output resolution for Designer bakers",
        items=_BAKE_RES_ITEMS,
        default="4096",
    )
    engine: EnumProperty(
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

    # Load baked texture paths (with bent-normal guard)
    dlbc, normal_path, dlao, dlbn = _find_baked_textures_ex(bake_tex_dir)

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

    # Make a unique copy per object, rename to base_name (or reuse if exists)
    mat = bpy.data.materials.get(base_name)
    if mat is None:
        try:
            mat = src_mat.copy()
            mat.name = base_name
            mat.use_fake_user = False
        except Exception as e:
            print(f"[Delighter] Copy/rename failed: {e}")
            mat = src_mat

    # Assign images into named nodes if they exist
    try:
        nt = mat.node_tree
        nodes = nt.nodes if nt else None
        def _set_img(node_name, img_path, cs_name):
            if not nodes or not img_path or not os.path.isfile(img_path):
                return
            node = nodes.get(node_name)
            if node and hasattr(node, "image"):
                try:
                    img = bpy.data.images.load(img_path, check_existing=True)
                except Exception:
                    img = None
                if img:
                    node.image = img
                    try:
                        node.image.colorspace_settings.name = cs_name
                    except Exception:
                        pass

        _set_img("DLBC", dlbc, "sRGB")
        _set_img("DLAO", dlao, "Non-Color")
        _set_img("DLBN", dlbn, "Non-Color")

        # Normals node: must use true *_Normal(s).* (NOT Bent_Normals)
        if normal_path and os.path.isfile(normal_path):
            node_normals = nodes.get("Normals") or nodes.get("Normal") or nodes.get("NormalTex")
            if node_normals and hasattr(node_normals, "image"):
                try:
                    img = bpy.data.images.load(normal_path, check_existing=True)
                except Exception:
                    img = None
                if img:
                    node_normals.image = img
                    try:
                        node_normals.image.colorspace_settings.name = "Non-Color"
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Delighter] Node setup error: {e}")

    # Replace object material slots with this material (keep slot count)
    try:
        slots = obj.data.materials
        if len(slots) == 0:
            slots.append(mat)
        else:
            for i in range(len(slots)):
                slots[i] = mat
        obj.active_material = mat
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

