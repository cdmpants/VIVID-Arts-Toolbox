# vivid_arts_toolbox/panel_lods.py
import bpy
from bpy.types import Panel

class VIVID_PT_main_panel_lods(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "LODs"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}
    def draw(self, context):
        pass

class VIVID_PT_setup_lods(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "LODs"
    bl_parent_id  = "VIVID_PT_main_panel_lods"
    bl_label      = "Generate LODs"
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

class VIEW3D_PT_shadowproxy_correction(Panel):
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category  = "LODs"
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
        row=box.row(align=True); row.prop(s,"sp_token_lod"); row.prop(s,"sp_token_proxy")
        layout.separator()
        col=layout.column(align=True)
        op=col.operator("object.shadowproxy_fit_all_pairs",text="Fit Shadow Proxies",icon='MOD_SHRINKWRAP')
        op.margin=s.sp_margin; op.grid=s.sp_grid; op.edge_samples=s.sp_edge_samples
        op.passes=s.sp_passes; op.v_passes=s.sp_v_passes; op.max_push=s.sp_max_push
        op.only_selected=s.sp_only_selected_pairs
        col.prop(s,"sp_only_selected_pairs")
        col.operator("object.shadowproxy_list_pairs",text="List Pairs",icon='INFO')
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
