# vivid_arts_toolbox/panel_lods.py
import bpy
from bpy.types import Panel

class VIVID_PT_main_panel_lods(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "LOD"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}
    def draw(self, context):
        pass

class VIVID_PT_setup_lods(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "LOD"
    bl_parent_id  = "VIVID_PT_main_panel_lods"
    bl_label      = "Generate LODs"
    bl_order      = 30
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="LOD Setup Settings", icon='OUTLINER_OB_MESH')
        s = getattr(context.scene, "vivid_lod_props", None)
        if s:
            # Custom LODs toggle
            box.prop(s, "custom_lods")
            # Collider options and ratio
            row = box.row(align=True)
            row.prop(s, "generate_collider")
            row = box.row(align=True)
            row.prop(s, "collider_ratio", text="MeshCollider Ratio")
            # LOD target ratios
            col = box.column(align=True)
            col.prop(s, "lod0_ratio", text="LOD0 Ratio")
            col.prop(s, "lod1_ratio", text="LOD1 Ratio")
            col.prop(s, "lod2_ratio", text="LOD2 Ratio")
            col.prop(s, "lod3_ratio", text="LOD3 Ratio")
            # ShadowProxy toggle and per-LOD ratios (vertical)
            box.prop(s, "generate_shadow_proxies")
            sp_box = box.box()
            sp_box.label(text="ShadowProxy Ratios")
            sp_col = sp_box.column(align=True)
            sp_col.prop(s, "sp_lod0_ratio", text="SP LOD0")
            sp_col.prop(s, "sp_lod1_ratio", text="SP LOD1")
            sp_col.prop(s, "sp_lod2_ratio", text="SP LOD2")
            sp_col.prop(s, "sp_lod3_ratio", text="SP LOD3")
        else:
            box.label(text="Scene LOD properties not found (scene.vivid_lod_props).", icon='INFO')
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "setup_lods"):
            row = col.row(align=True)
            row.enabled = not getattr(getattr(context.scene, 'vivid_lod_props', None), 'custom_lods', False)
            row.operator("vivid.setup_lods", text="Generate LODs", icon='MOD_DECIM')
        else:
            col.label(text="Operator vivid.setup_lods not registered.", icon='ERROR')

        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "export_lods"):
            col.operator("vivid.export_lods", text="Export LODs", icon='EXPORT')
        else:
            col.label(text="Operator vivid.export_lods not registered.", icon='ERROR')

class VIEW3D_PT_shadowproxy_correction(Panel):
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category  = "LOD"
    bl_parent_id = "VIVID_PT_main_panel_lods"
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
    # LOD/Proxy tokens are hardcoded now
        layout.separator()
        col=layout.column(align=True)
        op=col.operator("object.shadowproxy_fit_all_pairs",text="Fit Shadow Proxies",icon='MOD_SHRINKWRAP')
        op.margin=s.sp_margin; op.grid=s.sp_grid; op.edge_samples=s.sp_edge_samples
        op.passes=s.sp_passes; op.v_passes=s.sp_v_passes; op.max_push=s.sp_max_push
        op.only_selected=s.sp_only_selected_pairs
        col.prop(s,"sp_only_selected_pairs")
    # Removed List Pairs button
        layout.separator()
        box2 = layout.box(); box2.label(text="LOD Textures", icon='RENDER_STILL')
        box2.label(text="Bake LOD Textures (coming soon)", icon='RENDER_STILL')

_classes = (
    VIVID_PT_main_panel_lods,
    VIVID_PT_setup_lods,
    VIEW3D_PT_shadowproxy_correction,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
