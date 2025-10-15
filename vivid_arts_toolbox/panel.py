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


class VIVID_PT_generate_surface(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Generate Surface"
    bl_order      = 1
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row(align=True)
        row.prop(context.scene, "vivid_surface_margin", text="Margin")
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "generate_surface"):
            op = col.operator("vivid.generate_surface", text="Generate Surface", icon='MESH_GRID')
            op.margin = getattr(context.scene, "vivid_surface_margin", 1.0)
        else:
            col.label(text="Operator vivid.generate_surface not registered.", icon='ERROR')

class VIVID_PT_bake_textures(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Bake Textures"
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

# ShadowProxy Correction lives in operators/shadowproxy_correction.py (order ~40 above Export Asset)

class VIVID_PT_export_asset(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Export Asset"
    bl_order      = 50
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "export_asset"):
            col.operator("vivid.export_asset", text="Export Asset", icon='EXPORT')
        else:
            col.label(text="Operator vivid.export_asset not registered.", icon='ERROR')

# NEW — Export to Painter (default OPEN because we don't set DEFAULT_CLOSED)
class VIVID_PT_export_to_painter(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Export to Painter"
    bl_order      = 60
    def draw(self, context):
        layout = self.layout
        v = getattr(context.scene, "vivid_export_to_painter", None)

        box = layout.box()
        row = box.row(align=True)
        if v:
            row.prop(v, "texture_res", text="Texture Resolution")
            row = box.row(align=True)
            row.prop(v, "is_surface", text="Is Surface")
            row = box.row(align=True)
            row.prop(v, "open_after", text="Open Painter after export")
        else:
            box.label(text="Export-to-Painter props not found (scene.vivid_export_to_painter).", icon='INFO')

        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "export_to_painter"):
            col.operator("vivid.export_to_painter", text="Export to Painter", icon='EXPORT')
        else:
            col.label(text="Operator vivid.export_to_painter not registered.", icon='ERROR')


# --------- Panels moved from operators ---------

class VIVID_PT_light_removal(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Light Removal"
    bl_order      = 15

    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, "vivid_light_removal", None)
        box = layout.box()
        box.label(text="Settings", icon='PREFERENCES')
        if s:
            row = box.row(align=True); row.prop(s, "bake_resolution", text="Bake Resolution")
            row = box.row(align=True); row.prop(s, "engine",          text="Engine")
        else:
            box.label(text="Light Removal settings not found.", icon='INFO')
        col = layout.column(align=True)
        col.operator("vivid.bake_delit", text="Bake Delit Texture", icon='RENDER_STILL')


class VIEW3D_PT_shadowproxy_correction(Panel):
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category  = "VIVID Arts Toolbox"
    bl_parent_id = "VIVID_PT_main_panel"
    bl_label     = "ShadowProxy Correction"
    bl_order     = 40

    def draw(self,context):
        s=context.scene; layout=self.layout
        box=layout.box(); box.label(text="Solve Settings",icon='MOD_SHRINKWRAP')
        box.prop(s,"sp_margin")
        box.prop(s,"sp_grid")
        box.prop(s,"sp_edge_samples")
        row = box.row(align=True)
        row.prop(s,"sp_passes")
        row.prop(s,"sp_v_passes")
        box.prop(s,"sp_max_push")
        row=box.row(align=True); row.prop(s,"sp_token_lod"); row.prop(s,"sp_token_proxy")

        layout.separator()
        col=layout.column(align=True)
        op=col.operator("object.shadowproxy_fit_all_pairs",text="Fit Shadow Proxies",icon='MOD_SHRINKWRAP')
        op.margin=s.sp_margin; op.grid=s.sp_grid; op.edge_samples=s.sp_edge_samples
        op.passes=s.sp_passes; op.v_passes=s.sp_v_passes; op.max_push=s.sp_max_push
        op.only_selected=s.sp_only_selected_pairs
        col.prop(s,"sp_only_selected_pairs")
        col.operator("object.shadowproxy_list_pairs",text="List Pairs",icon='INFO')

_classes = (
    VIVID_PT_main_panel,
    VIVID_PT_generate_surface,
    VIVID_PT_bake_textures,
    VIVID_PT_generate_asset,
    VIVID_PT_setup_lods,
    VIVID_PT_export_asset,
    VIVID_PT_export_to_painter,  # NEW: added last so it appears at the bottom
    VIVID_PT_light_removal,
    VIEW3D_PT_shadowproxy_correction,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)
    # Simple scene prop to store default margin value
    if not hasattr(bpy.types.Scene, "vivid_surface_margin"):
        from bpy.props import FloatProperty
        bpy.types.Scene.vivid_surface_margin = FloatProperty(
            name="Surface Margin",
            description="Default margin used by Generate Surface",
            default=1.0,
            min=0.0,
            soft_max=100.0,
        )

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
    if hasattr(bpy.types.Scene, "vivid_surface_margin"):
        del bpy.types.Scene.vivid_surface_margin
