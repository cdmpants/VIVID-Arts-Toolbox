import bpy
import os
from bpy.props import StringProperty, BoolProperty

# Get the directory of the current script (preferences.py)
addon_dir = os.path.dirname(__file__)

def _default_release_dir():
    # Prefer network path if reachable; otherwise empty
    p = "\\\\TheArchive_2049\\VIVID Arts Library\\Release"
    return p if os.path.isdir(p) else ""

class VIVID_Arts_Toolbox_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    __annotations__ = {}
    __annotations__['designer_preset_filepath'] = StringProperty(
        name="Designer JSON Preset",
        subtype='FILE_PATH',
        default=os.path.join(addon_dir, "SDesigner_Photogrammetry.json"),
        description="Path to your Substance Designer JSON preset file. Defaults to local addon file."
    )
    __annotations__['substance_baker_path'] = StringProperty(
        name="Substance Baker (substance3d_baker.exe)",
        description="Path to Adobe Substance 3D Designer's headless baker executable",
        subtype='FILE_PATH',
        default=""
    )
    # NEW — Painter integration
    __annotations__['painter_exe_path'] = StringProperty(
        name="Substance Painter (Adobe Substance 3D Painter.exe)",
        subtype='FILE_PATH',
        description="Path to Substance 3D Painter executable (e.g. Substance 3D Painter.exe)",
        default=""
    )
    __annotations__['release_directory'] = StringProperty(
        name="Release Directory",
        subtype='DIR_PATH',
        description="Root of Release tree where final FBX/Textures are stored and LOD-specific bakes are saved.",
        default=_default_release_dir()
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="VIVID Arts Toolbox Settings")

        # Primary export/config paths (ordered for workflow)
        # Auto-fill executables if empty and default locations exist
        try:
            if not self.substance_baker_path:
                cand = r"C:\\Program Files\\Adobe\\Adobe Substance 3D Designer\\substance3d_baker.exe"
                if os.path.isfile(cand):
                    self.substance_baker_path = cand
        except Exception:
            pass
        try:
            if not self.painter_exe_path:
                cand = r"C:\\Program Files\\Adobe\\Adobe Substance 3D Painter\\Adobe Substance 3D Painter.exe"
                if os.path.isfile(cand):
                    self.painter_exe_path = cand
        except Exception:
            pass

        layout.prop(self, "release_directory")
        layout.prop(self, "substance_baker_path")
        layout.prop(self, "painter_exe_path")

