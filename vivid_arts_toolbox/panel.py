# vivid_arts_toolbox/panel.py
import bpy
from bpy.types import Panel

class VIVID_PT_main_panel(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        pass

class VIVID_PT_bake_textures(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Bake Textures"
    bl_options    = {'DEFAULT_CLOSED'}
    bl_order      = 10

    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, "vivid_designer_bake", None)

        box = layout.box()
        box.label(text="Settings", icon='PREFERENCES')

        if s:
            row = box.row(align=True); row.prop(s, "export_bake_meshes", text="Export Bake Meshes")
            row = box.row(align=True); row.prop(s, "setup_material",      text="Setup Material")
            row = box.row(align=True); row.prop(s, "bake_resolution",     text="Bake Resolution")
            row = box.row(align=True); row.prop(s, "engine",              text="Engine")
        else:
            box.label(text="Designer bake settings not found (scene.vivid_designer_bake).", icon='INFO')

        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "bake_designer"):
            col.operator("vivid.bake_designer", text="Bake Designer Textures", icon='RENDER_STILL')
        else:
            col.label(text="Operator vivid.bake_designer not registered.", icon='ERROR')

class VIVID_PT_generate_asset(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Generate Asset"
    bl_options    = {'DEFAULT_CLOSED'}
    bl_order      = 20

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "generate_asset"):
            col.operator("vivid.generate_asset", text="Generate Asset", icon='OUTLINER_OB_LIGHTPROBE')
        else:
            col.label(text="Operator vivid.generate_asset not registered.", icon='ERROR')

class VIVID_PT_setup_lods(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Setup LODs"
    bl_options    = {'DEFAULT_CLOSED'}
    bl_order      = 30

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="LOD Setup Settings", icon='OUTLINER_OB_MESH')

        s = getattr(context.scene, "vivid_lod_props", None)
        if s:
            box.prop(s, "generate_shadow_proxies")
            row = box.row(align=True)
            row.prop(s, "generate_collider")
            row.prop(s, "is_convex_collider")
        else:
            box.label(text="Scene LOD properties not found (scene.vivid_lod_props).", icon='INFO')

        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "setup_lods"):
            col.operator("vivid.setup_lods", text="Setup LODs", icon='MOD_DECIM')
        else:
            col.label(text="Operator vivid.setup_lods not registered.", icon='ERROR')

# ShadowProxy Correction lives in operators/shadowproxy_correction.py
# It uses bl_parent_id="VIVID_PT_main_panel" and bl_order=40 (above Export Asset)

class VIVID_PT_export_asset(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Export Asset"
    bl_options    = {'DEFAULT_CLOSED'}
    bl_order      = 50

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "export_asset"):
            col.operator("vivid.export_asset", text="Export Asset", icon='EXPORT')
        else:
            col.label(text="Operator vivid.export_asset not registered.", icon='ERROR')

_classes = (
    VIVID_PT_main_panel,
    VIVID_PT_bake_textures,
    VIVID_PT_generate_asset,
    VIVID_PT_setup_lods,
    VIVID_PT_export_asset,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)

