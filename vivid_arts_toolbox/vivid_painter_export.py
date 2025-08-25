
# vivid_arts_toolbox/vivid_painter_export.py
# Export to Painter (file-driven): copy starter SPP, write config JSON, open Painter.
# SPP wiring happens in Painter via VIVID_Configure_From_JSON.py.

import os
import json
import subprocess
from pathlib import Path
import bpy
from bpy.types import Operator, Panel
from bpy.props import BoolProperty, EnumProperty

PACKAGE = __package__ or "vivid_arts_toolbox"

# ---------- helpers ----------

def _addon_dir() -> Path:
    return Path(__file__).resolve().parent

def _find_optimized_obj(context) -> bpy.types.Object:
    o = context.active_object
    if o and o.type == 'MESH' and o.name.endswith("_Optimized"):
        return o
    for t in context.scene.objects:
        if t.type == 'MESH' and t.name.endswith("_Optimized"):
            return t
    raise RuntimeError("No *_Optimized mesh found in the scene.")

def _base_name(o: bpy.types.Object) -> str:
    return o.name[:-10] if o.name.endswith("_Optimized") else o.name

def _proj_dirs():
    blend = Path(bpy.data.filepath)
    if not blend:
        raise RuntimeError("Please save your .blend file first.")
    root = blend.parent
    return root, root / "BakeMesh", root / "BakeTextures"

def _expect_file(p: Path, what: str):
    if not p.exists():
        raise RuntimeError(f"Couldn't find {what}: {p}")

def _copy_starter_spp(dst: Path):
    src = _addon_dir() / "VIVID_Arts.spp"
    if not src.exists():
        raise RuntimeError("Starter SPP not found in add-on: VIVID_Arts.spp")
    dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(src, dst)

def _template_path(is_surface: bool) -> Path:
    fname = "VIVID_Arts_Surface.spexp" if is_surface else "VIVID_Arts.spexp"
    p = _addon_dir() / fname
    if not p.exists():
        raise RuntimeError(f"Export template missing in add-on: {fname}")
    return p

def _find_tex(base: str, tex_dir: Path, suffixes):
    if not tex_dir.exists():
        return ""
    if isinstance(suffixes, str):
        suffixes = [suffixes]
    exts = (".png",".tga",".tif",".tiff",".exr",".jpg",".jpeg")
    for suf in suffixes:
        for ext in exts:
            p = tex_dir / f"{base}{suf}{ext}"
            if p.exists():
                return str(p)
    return ""

# -------- core action (returns status string) --------
def run_export(context,
               painter_exe: str = "",
               export_dir: str = "",
               texture_res: int = 4096,
               is_surface: bool = False,
               open_after: bool = True,
               texture_export_dir: str = None,
               **kwargs) -> str:
    """Compatibility signature: accepts either export_dir=... or texture_export_dir=....
    Any extra kwargs are ignored so older callers don't crash."""
    # Prefer explicit export_dir, fall back to texture_export_dir alias
    if (not export_dir) and texture_export_dir:
        export_dir = texture_export_dir

    opt = _find_optimized_obj(context)
    base = _base_name(opt)
    root, bake_mesh, bake_tex = _proj_dirs()

    fbx = bake_mesh / f"{base}_Optimized.fbx"
    _expect_file(fbx, "Optimized FBX in BakeMesh")

    # Prepare project SPP next to blend
    spp = root / f"{base}.spp"
    _copy_starter_spp(spp)

    # Discover ONLY requested textures
    tex = {
        "DLBC":         _find_tex(base, bake_tex, "_DLBC"),
        "Delit":        _find_tex(base, bake_tex, "_Delit"),
        "DLAO":         _find_tex(base, bake_tex, "_DLAO"),
        "Occlusion":    _find_tex(base, bake_tex, "_Occlusion"),
        "Bent_Normals": _find_tex(base, bake_tex, ["_Bent_Normals","_Bent_Normal"]),
        "Heightmap":    _find_tex(base, bake_tex, "_Heightmap"),
        "Normals":      _find_tex(base, bake_tex, ["_Normals","_Normal"]),
    }

    # Write config JSON next to the project
    cfg = {
        "base_name": base,
        "project_path": str(spp),
        "fbx_path": str(fbx),
        "bake_textures_dir": str(bake_tex),
        "textures": tex,
        "export_template": str(_template_path(is_surface)),
        "export_dir": str(Path(export_dir) if export_dir else (root / "PainterExports")),
        "texture_size": int(texture_res)
    }
    cfg_path = root / "vivid_painter_config.json"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    # Optionally open Painter with the SPP & Mesh
    if open_after:
        if painter_exe and Path(painter_exe).exists():
            cmd = [str(Path(painter_exe)), "--mesh", str(fbx), str(spp)]
            try:
                subprocess.Popen(cmd, shell=False)
            except Exception as e:
                return f"SPP prepared + config written, but failed to launch Painter: {e}"
        else:
            return f"SPP prepared + config written. Painter EXE not set; open manually.\n{cfg_path}"

    return f"SPP prepared + config written:\n{cfg_path}"

# ---------- UI (panel & operator) ----------

def _ensure_wm_props():
    WM = bpy.types.WindowManager
    if not hasattr(WM, "vivid_ep_open_after"):
        WM.vivid_ep_open_after = BoolProperty(name="Open Painter after export", default=True)
    if not hasattr(WM, "vivid_ep_is_surface"):
        WM.vivid_ep_is_surface = BoolProperty(name="Is Surface", default=False)
    if not hasattr(WM, "vivid_ep_res"):
        WM.vivid_ep_res = EnumProperty(
            name="Texture Resolution",
            items=[(str(v), f"{v}", f"{v} x {v}") for v in (256,512,1024,2048,4096,8192)],
            default="4096"
        )
    if not hasattr(WM, "vivid_ep_foldout"):
        WM.vivid_ep_foldout = BoolProperty(name="Export to Painter", default=True)

class VIVID_PT_export_to_painter(Panel):
    bl_label = "Export to Painter"
    bl_idname = "VIVID_PT_export_to_painter"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "VIVID Arts Toolbox"
    bl_order = 9999  # keep at bottom

    def draw(self, context):
        _ensure_wm_props()
        wm = context.window_manager
        box = self.layout.box()
        row = box.row()
        row.prop(wm, "vivid_ep_foldout", icon="TRIA_DOWN" if wm.vivid_ep_foldout else "TRIA_RIGHT", emboss=False)
        row.label(text="Export to Painter")
        if not wm.vivid_ep_foldout:
            return
        col = box.column(align=True)
        col.prop(wm, "vivid_ep_res")
        col.prop(wm, "vivid_ep_is_surface")
        col.prop(wm, "vivid_ep_open_after")
        col.separator()
        col.operator("vivid.export_to_painter", icon='EXPORT')

class VIVID_OT_export_to_painter(Operator):
    bl_idname = "vivid.export_to_painter"
    bl_label = "Export to Painter"
    bl_options = {'REGISTER','INTERNAL'}

    def execute(self, context):
        try:
            addon = bpy.context.preferences.addons.get(PACKAGE)
            prefs = addon.preferences if addon else None
            painter_exe = getattr(prefs, "painter_exe_path", "") if prefs else ""
            export_dir  = getattr(prefs, "texture_export_dir", "") if prefs else ""
            size        = int(context.window_manager.vivid_ep_res)
            is_surface  = bool(context.window_manager.vivid_ep_is_surface)
            open_after  = bool(context.window_manager.vivid_ep_open_after)

            msg = run_export(context,
                             painter_exe=painter_exe,
                             export_dir=export_dir,
                             texture_res=size,
                             is_surface=is_surface,
                             open_after=open_after)
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export to Painter failed: {e}")
            return {'CANCELLED'}

def register():
    _ensure_wm_props()
    bpy.utils.register_class(VIVID_PT_export_to_painter)
    bpy.utils.register_class(VIVID_OT_export_to_painter)

def unregister():
    for cls in (VIVID_OT_export_to_painter, VIVID_PT_export_to_painter):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
