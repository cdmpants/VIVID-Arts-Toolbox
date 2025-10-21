# vivid_arts_toolbox/export_to_painter.py
import bpy
from bpy.types import PropertyGroup, Operator
from bpy.props import EnumProperty, BoolProperty, PointerProperty

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

class VIVID_OT_export_to_painter(Operator):
    bl_idname = "vivid.export_to_painter"
    bl_label = "Export to Painter"
    bl_description = "Prepare a standardized .spp next to the .blend and (optionally) open Substance 3D Painter"

    def execute(self, context):
        # Preferences
        try:
            prefs = bpy.context.preferences.addons[__package__].preferences
        except KeyError:
            self.report({'ERROR'}, "Addon preferences not found. Is the addon enabled?")
            return {'CANCELLED'}

        props = context.scene.vivid_export_to_painter

        # Delegate to the Painter logic module
        try:
            from . import vivid_painter_export as VPE
        except Exception as e:
            self.report({'ERROR'}, f"vivid_painter_export.py not found or failed to import: {e}")
            return {'CANCELLED'}

        try:
            res_px = _RES_MAP.get(props.texture_res, 4096)
            report = VPE.run_export(
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
