# vivid_arts_toolbox/operators/export_to_painter.py
import bpy
from bpy.types import PropertyGroup, Operator
from bpy.props import EnumProperty, BoolProperty, PointerProperty
import os, json, subprocess
from pathlib import Path
from ..utils import resource_or_legacy

# Use NON-numeric IDs; map to ints in operator
_RES_ITEMS = [
    ("RES_256",  "256",  "256px"),
    ("RES_512",  "512",  "512px"),
    ("RES_1024", "1024", "1024px"),
    ("RES_2048", "2048", "2048px"),
    ("RES_4096", "4096", "4096px"),
    ("RES_8192", "8192", "8192px"),
]
_RES_MAP = {
    "RES_256": 256, "RES_512": 512, "RES_1024": 1024,
    "RES_2048": 2048, "RES_4096": 4096, "RES_8192": 8192,
}

class VIVID_PG_ExportToPainter(PropertyGroup):
    __annotations__ = {}
    __annotations__['texture_res'] = EnumProperty(
        name="Texture Resolution",
        description="Target texture size for Painter export",
        items=_RES_ITEMS,
        default="RES_4096",
    )
    __annotations__['is_surface'] = BoolProperty(
        name="Is Surface",
        description="Use VIVID_Arts_Surface export template instead of VIVID_Arts",
        default=False,
    )
    __annotations__['open_after'] = BoolProperty(
        name="Open Painter after export",
        description="Launch Substance 3D Painter after preparing the .spp",
        default=True,
    )

def _pkg_root() -> Path:
    # operators/ -> package root
    return Path(__file__).resolve().parent.parent

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
    src = resource_or_legacy("VIVID_Arts.spp")
    if not src.exists():
        raise RuntimeError("Starter SPP not found in add-on: VIVID_Arts.spp")
    dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(src, dst)

def _template_path(is_surface: bool) -> Path:
    fname = "VIVID_Arts_Surface.spexp" if is_surface else "VIVID_Arts.spexp"
    p = resource_or_legacy(fname)
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

def run_export(context,
               painter_exe: str = "",
               export_dir: str = "",
               texture_res: int = 4096,
               is_surface: bool = False,
               open_after: bool = True,
               texture_export_dir: str = None,
               **kwargs) -> str:
    """Prepare SPP/config for Painter export next to the .blend and optionally launch Painter.
    Compatibility signature retained; texture_export_dir is ignored except as alias for export_dir.
    """
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

    # Discover textures we use
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

    if open_after:
        if painter_exe and Path(painter_exe).exists():
            cmd = [str(Path(painter_exe)), "--mesh", str(fbx), str(spp)]
            try:
                subprocess.Popen(cmd, shell=False)
                return f"SPP prepared + config written. Launching Painter...\n{cfg_path}"
            except Exception as e:
                return f"SPP prepared + config written, but failed to launch Painter: {e}"
        else:
            return f"SPP prepared + config written. Painter EXE not set; open manually.\n{cfg_path}"

    return f"SPP prepared + config written:\n{cfg_path}"


class VIVID_OT_export_to_painter(Operator):
    bl_idname = "vivid.export_to_painter"
    bl_label = "Export to Painter"
    bl_description = "Prepare a standardized .spp next to the .blend and (optionally) open Substance 3D Painter"

    def execute(self, context):
        # Preferences
        try:
            addon_key = __package__.split('.')[0] if __package__ else "vivid_arts_toolbox"
            prefs = bpy.context.preferences.addons[addon_key].preferences
        except KeyError:
            self.report({'ERROR'}, "Addon preferences not found. Is the addon enabled?")
            return {'CANCELLED'}

        props = context.scene.vivid_export_to_painter

        try:
            res_px = _RES_MAP.get(props.texture_res, 4096)
            report = run_export(
                context=context,
                painter_exe=getattr(prefs, 'painter_exe_path', ''),
                texture_res=int(res_px),
                is_surface=props.is_surface,
                open_after=props.open_after,
            )
            self.report({'INFO'}, report)
        except Exception as e:
            self.report({'ERROR'}, f"Export to Painter failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

_classes = (
    VIVID_PG_ExportToPainter,
    VIVID_OT_export_to_painter,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.vivid_export_to_painter = PointerProperty(type=VIVID_PG_ExportToPainter)

def unregister():
    del bpy.types.Scene.vivid_export_to_painter
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
