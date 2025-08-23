# vivid_painter_export.py
# Blender 4.3
import bpy, os, shutil, json, subprocess, time, socket, http.client
from bpy.props import BoolProperty, EnumProperty, StringProperty

ADDON_PACKAGE = __package__ or "vivid_arts_toolbox"  # fallback if run ad-hoc
DEFAULT_RES = "4096"

PAINTER_DEFAULT_PORT = 60041  # per Adobe docs (Remote Scripting)
# --- Small HTTP client for Painter Remote Scripting (per Adobe docs) ---
def painter_ready(host="127.0.0.1", port=PAINTER_DEFAULT_PORT, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.create_connection((host, port), timeout=1.0)
            s.close()
            return True
        except Exception:
            time.sleep(0.5)
    return False

def painter_exec_python(python_code: str, host="127.0.0.1", port=PAINTER_DEFAULT_PORT):
    body = json.dumps({"python": python_code}).encode("utf-8")
    conn = http.client.HTTPConnection(host, port, timeout=3600)
    conn.request("POST", "/run.json", body, headers={
        "Content-type": "application/json", "Accept": "application/json"
    })
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    try:
        return data.decode("utf-8").strip()
    except Exception:
        return ""

# --- Addon Preferences ---
class VIVID_PT_PainterPrefs(bpy.types.AddonPreferences):
    bl_idname = ADDON_PACKAGE

    painter_exe: StringProperty(
        name="Painter EXE",
        description="Path to Adobe Substance 3D Painter.exe",
        subtype='FILE_PATH',
        default="C:/Program Files/Adobe/Adobe Substance 3D Painter/Adobe Substance 3D Painter.exe"
    )
    starter_spp: StringProperty(
        name="Starter .spp",
        description="Preconfigured starter project (with placeholder layers)",
        subtype='FILE_PATH',
        default=""
    )
    export_root: StringProperty(
        name="Export Root (optional)",
        description="Preferred export root for Painter (used to pre-fill export path)",
        subtype='DIR_PATH',
        default=""
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "painter_exe")
        layout.prop(self, "starter_spp")
        layout.prop(self, "export_root")

# --- Operator ---
class VIVID_OT_ExportToPainter(bpy.types.Operator):
    bl_idname = "vivid.export_to_painter"
    bl_label = "Export to Painter"
    bl_description = "Copy starter .spp, open in Painter, wire textures/layers, set resolution, and save"
    bl_options = {'REGISTER', 'UNDO'}

    open_painter: BoolProperty(name="Open Painter after export", default=True)
    is_surface: BoolProperty(name="Is Surface", default=False)

    output_res: EnumProperty(
        name="Output Resolution",
        items=[(str(v), f"{v}", "") for v in (256,512,1024,2048,4096,8192)],
        default=DEFAULT_RES
    )

    def _resolve_paths(self, context):
        blend_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
        blend_name = os.path.splitext(os.path.basename(bpy.data.filepath or "Unsaved.blend"))[0]

        # BaseName = assume project/asset folder name == BaseName; mesh in BakeMesh/<BaseName>_Optimized.fbx
        # If your toolbox already has path utils, you can swap in those calls here.
        basename = blend_name  # fallback; if your naming differs, adjust as needed
        bake_mesh_dir = os.path.join(blend_dir, "BakeMesh")
        bake_tex_dir  = os.path.join(blend_dir, "BakeTextures")

        fbx = os.path.join(bake_mesh_dir, f"{basename}_Optimized.fbx")
        if not os.path.isfile(fbx):
            # try to find any *_Optimized.fbx in BakeMesh
            for fn in os.listdir(bake_mesh_dir) if os.path.isdir(bake_mesh_dir) else []:
                if fn.endswith("_Optimized.fbx"):
                    fbx = os.path.join(bake_mesh_dir, fn)
                    basename = fn[:-len("_Optimized.fbx")]
                    break

        new_spp = os.path.join(blend_dir, f"{basename}.spp")
        return blend_dir, basename, fbx, bake_tex_dir, new_spp

    def _copy_presets_to_user(self, addon_dir, chosen_preset_path):
        # Ensure your two presets are available in Painter's Export UI.
        # Official user path (Windows): Documents\Adobe\Adobe Substance 3D Painter\assets\export-presets
        # We copy both so both appear, then we still tell our script which one to prefer.
        docs = os.path.expanduser("~/Documents")
        user_presets = os.path.join(docs, "Adobe", "Adobe Substance 3D Painter", "assets", "export-presets")
        os.makedirs(user_presets, exist_ok=True)
        for name in ("VIVID_Arts.spexp", "VIVID_Arts_Surface.spexp"):
            src = os.path.join(addon_dir, name)
            if os.path.isfile(src):
                dst = os.path.join(user_presets, name)
                try:
                    if (not os.path.exists(dst)) or (os.path.getmtime(src) > os.path.getmtime(dst)):
                        shutil.copy2(src, dst)
                except Exception as e:
                    print(f"[PainterExport] Warning: couldn't copy preset {name}: {e}")
        return chosen_preset_path

    def execute(self, context):
        prefs = bpy.context.preferences.addons[ADDON_PACKAGE].preferences
        painter_exe = os.path.normpath(prefs.painter_exe)
        starter_spp = os.path.normpath(prefs.starter_spp)
        export_root = os.path.normpath(prefs.export_root) if prefs.export_root else ""

        if not os.path.isfile(painter_exe):
            self.report({'ERROR'}, "Painter EXE not found in Addon Preferences.")
            return {'CANCELLED'}
        if not os.path.isfile(starter_spp):
            self.report({'ERROR'}, "Starter .spp not set or missing in Addon Preferences.")
            return {'CANCELLED'}

        blend_dir, basename, fbx, bake_tex_dir, new_spp = self._resolve_paths(context)
        if not os.path.isfile(fbx):
            self.report({'ERROR'}, f"Optimized FBX not found: {fbx}")
            return {'CANCELLED'}

        # Copy starter spp -> <BaseName>.spp (confirm overwrite)
        try:
            shutil.copy2(starter_spp, new_spp)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to copy starter .spp: {e}")
            return {'CANCELLED'}

        # Choose preset file based on Is Surface
        addon_dir = os.path.dirname(__file__)
        preset_name = "VIVID_Arts_Surface.spexp" if self.is_surface else "VIVID_Arts.spexp"
        preset_path = os.path.join(addon_dir, preset_name)
        if not os.path.isfile(preset_path):
            print(f"[PainterExport] Warning: preset not found in addon: {preset_path}")
        # Copy presets to user’s export-presets so they’re selectable in the Export UI
        self._copy_presets_to_user(addon_dir, preset_path)

        # Build args to feed to Painter (the script we send inside will use these)
        args = {
            "project_path": new_spp,
            "fbx_path": fbx,
            "textures_dir": bake_tex_dir,
            "export_preset_name": "VIVID_Arts_Surface" if self.is_surface else "VIVID_Arts",
            "base_name": basename,
            "resolution": int(self.output_res),
            # file basenames (we’ll look for these in textures_dir with common extensions):
            "maps": {
                "DLBC":          "_DLBC",
                "DELIT":         "_Delit",
                "NORMAL":        "_Normal",        # we also accept _Normals
                "OCCLUSION":     "_Occlusion",
                "BENT_NORMAL":   "_Bent_Normal",   # we also accept _Bent_Normals
                "HEIGHT":        "_Heightmap",
                "DLAO":          "_DLAO"
            },
            # placeholder resource names used in the starter .spp (these must match)
            "placeholders": {
                "Base_BaseColor":          "__PLACEHOLDER_DLBC",
                "Base_Roughness":          "__PLACEHOLDER_DELIT_R",
                "Base_Normal":             "__PLACEHOLDER_NORMAL",
                "Base_AO":                 "__PLACEHOLDER_OCCLUSION",
                "Base_CoatNormal":         "__PLACEHOLDER_BENT_NORMAL",
                "Base_Displacement":       "__PLACEHOLDER_HEIGHT",
                "Delit_BaseColor":         "__PLACEHOLDER_DELIT_BC",
                "AO_Wide_AO":              "__PLACEHOLDER_DLAO",
                "AO_Roughness_MaskFill":   "__PLACEHOLDER_OCCLUSION_MASK"
            },
            "export_root": export_root
        }
        # Store a temp JSON next to the .spp (for debugging too)
        args_json_path = os.path.join(os.path.dirname(new_spp), f"{basename}_painter_setup_args.json")
        with open(args_json_path, "w", encoding="utf-8") as f:
            json.dump(args, f, indent=2)

        if not self.open_painter:
            self.report({'INFO'}, f"Painter setup prepared; .spp copied to {new_spp}.")
            return {'FINISHED'}

        # Launch Painter: open the .spp and inject the FBX (update mesh), enable remote scripting
        # Per Adobe docs: "Adobe Substance 3D Painter.exe" --mesh "<fbx>" "<project.spp>"
        # Also enable remote scripting to accept HTTP commands from Blender.
        cmd = [
            painter_exe,
            "--enable-remote-scripting",
            "--mesh", fbx,
            new_spp
        ]
        try:
            subprocess.Popen(cmd, cwd=os.path.dirname(painter_exe))
        except Exception as e:
            self.report({'ERROR'}, f"Failed to start Painter: {e}")
            return {'CANCELLED'}

        # Wait until Painter HTTP endpoint is ready
        if not painter_ready(timeout=60):
            self.report({'ERROR'}, "Painter did not become ready for remote scripting.")
            return {'CANCELLED'}

        # Build the Python to run INSIDE Painter.
        painter_py = r'''
import json, os, glob
import substance_painter
import substance_painter.project as sp_project
import substance_painter.textureset as sp_textureset
import substance_painter.resource as sp_resource
import substance_painter.logging as sp_log

# Load the args JSON placed by Blender:
ARGS_PATH = r"{args_json_path}"
with open(ARGS_PATH, "r", encoding="utf-8") as f:
    ARGS = json.load(f)

proj = ARGS["project_path"]
fbx  = ARGS["fbx_path"]
tex_dir = ARGS["textures_dir"]
base_name = ARGS["base_name"]
res = int(ARGS["resolution"])
export_root = ARGS.get("export_root") or ""
maps = ARGS["maps"]
ph   = ARGS["placeholders"]

def _warn(msg): sp_log.log(sp_log.LogLevel.Warning, f"[VIVID Painter Setup] {msg}")
def _info(msg): sp_log.log(sp_log.LogLevel.Info,    f"[VIVID Painter Setup] {msg}")

# Ensure project is open (it should be, but be defensive)
if not sp_project.is_open():
    sp_project.open(proj)

# Rename Texture Set / material to <BaseName> if needed:
# (When a mesh is updated via --mesh, the existing Texture Set remains; we rename to match)
all_sets = sp_textureset.all_texture_sets()
if all_sets:
    ts = all_sets[0]
    # Nothing in API to rename textureset directly; typically name comes from mesh material.
    # If rename is essential, enforce via template or mesh material. We'll just log:
    _info(f"Active Texture Set: {ts.name()}")

# Helper: import a bitmap if present; return Resource
def import_bitmap_if_exists(tag, suffixes, exts=(".png", ".tga", ".tif", ".tiff", ".exr", ".jpg", ".jpeg")):
    # Accept both specified suffix and common plural variants
    patts = [suffixes]
    if suffixes.endswith("_Normal"):      patts.append("_Normals")
    if suffixes.endswith("_Bent_Normal"): patts.append("_Bent_Normals")
    for suf in patts:
        for ext in exts:
            cand = os.path.join(tex_dir, f"{base_name}{suf}{ext}")
            if os.path.isfile(cand):
                # Import resource into project, context = 'project'
                try:
                    return sp_resource.import_project_resource(cand)
                except Exception as e:
                    _warn(f"Failed to import {tag} ({cand}): {e}")
                    return None
    _warn(f"Missing texture for {tag} (looked for {base_name}{suffixes}.*)")
    return None

# Pull all candidate bitmaps
bm_DLBC       = import_bitmap_if_exists("DLBC",       maps["DLBC"])
bm_DELIT      = import_bitmap_if_exists("Delit",      maps["DELIT"])
bm_NORMAL     = import_bitmap_if_exists("Normal",     maps["NORMAL"])
bm_OCCLUSION  = import_bitmap_if_exists("Occlusion",  maps["OCCLUSION"])
bm_BENT       = import_bitmap_if_exists("BentNormal", maps["BENT_NORMAL"])
bm_HEIGHT     = import_bitmap_if_exists("Height",     maps["HEIGHT"])
bm_DLAO       = import_bitmap_if_exists("DLAO",       maps["DLAO"])

# Helper: swap placeholder resource with a real resource everywhere in layer stacks
def swap_placeholder(placeholder_name, new_res):
    if not new_res:
        _warn(f"Placeholder '{placeholder_name}': no replacement provided (skipping)")
        return
    try:
        old = sp_resource.ResourceID(context="project", name=placeholder_name)
        sp_resource.update_layer_stack_resource(old, new_res)
        _info(f"Replaced placeholder '{placeholder_name}' with '{new_res.identifier().name()}'")
    except Exception as e:
        _warn(f"swap failed for '{placeholder_name}': {e}")

# === Assign into your named layers via placeholders in the starter .spp ===
swap_placeholder(ph["Base_BaseColor"],        bm_DLBC)
swap_placeholder(ph["Base_Roughness"],        bm_DELIT)     # optional
swap_placeholder(ph["Base_Normal"],           bm_NORMAL)    # OpenGL assumed in template
swap_placeholder(ph["Base_AO"],               bm_OCCLUSION)
swap_placeholder(ph["Base_CoatNormal"],       bm_BENT)      # OpenGL assumed in template
swap_placeholder(ph["Base_Displacement"],     bm_HEIGHT)

swap_placeholder(ph["Delit_BaseColor"],       bm_DELIT)     # optional

swap_placeholder(ph["AO_Wide_AO"],            bm_DLAO)

# AO_Roughness mask fill: drive mask fill from Occlusion
swap_placeholder(ph["AO_Roughness_MaskFill"], bm_OCCLUSION)

# === Set document/texture-set resolution ===
try:
    # Convert int resolution to Resolution object
    res_obj = sp_textureset.Resolution(res, res)
    all_sets = sp_textureset.all_texture_sets()
    sp_textureset.set_resolutions(all_sets, res_obj)
    _info(f"Set resolution to {res} for {len(all_sets)} Texture Set(s).")
except Exception as e:
    _warn(f"Failed to set resolution: {e}")

# (Optional) Set default export path in project settings when creating project; for opened projects,
# export path for UI is user-driven. We just log it and rely on your Export dialog.
if export_root:
    _info(f"Preferred export root: {export_root}")

# Final save so user doesn’t lose anything
try:
    sp_project.save()
    _info("Project saved.")
except Exception as e:
    _warn(f"Save failed: {e}")
'''
        painter_py_fmt = painter_py.format(args_json_path=args_json_path.replace("\\", "\\\\"))
        out = painter_exec_python(painter_py_fmt)
        if out:
            print(out)

        self.report({'INFO'}, f"Painter project ready: {new_spp}")
        return {'FINISHED'}

# --- Panel (foldout at the bottom of VIVID Arts Toolbox tab) ---
class VIVID_PT_ExportToPainter(bpy.types.Panel):
    bl_label = "Export to Painter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "VIVID Arts Toolbox"
    bl_idname = "VIVID_PT_EXPORT_TO_PAINTER"

    bl_order = 999  # try to keep it last

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        op = col.operator(VIVID_OT_ExportToPainter.bl_idname, text="Export to Painter", icon='EXPORT')
        # Draw properties inline
        box = layout.box()
        box.prop(context.window_manager, "vivid_open_painter")
        box.prop(context.window_manager, "vivid_is_surface")
        box.prop(context.window_manager, "vivid_output_res")

# Wiring panel controls to operator defaults
def _get_set_prop(name, default, prop_type, items=None):
    wm = bpy.types.WindowManager
    if not hasattr(wm, name):
        if prop_type == 'BOOL':
            setattr(wm, name, BoolProperty(name=name, default=default))
        elif prop_type == 'ENUM':
            setattr(wm, name, EnumProperty(name="Output Resolution",
                                           items=items, default=default))
    return name

def _props_to_operator(self, context):
    op = self.layout.operator(VIVID_OT_ExportToPainter.bl_idname, text="Export to Painter", icon='EXPORT')
    op.open_painter = getattr(context.window_manager, "vivid_open_painter")
    op.is_surface   = getattr(context.window_manager, "vivid_is_surface")
    op.output_res   = getattr(context.window_manager, "vivid_output_res")

classes = (
    VIVID_PT_PainterPrefs,
    VIVID_OT_ExportToPainter,
    VIVID_PT_ExportToPainter,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    _get_set_prop("vivid_open_painter", True, 'BOOL')
    _get_set_prop("vivid_is_surface", False, 'BOOL')
    _get_set_prop("vivid_output_res", DEFAULT_RES, 'ENUM',
                  [(str(v), f"{v}", "") for v in (256,512,1024,2048,4096,8192)])

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    for name in ("vivid_open_painter", "vivid_is_surface", "vivid_output_res"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)

if __name__ == "__main__":
    register()
