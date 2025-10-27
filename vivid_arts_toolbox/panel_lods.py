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
            # Custom LODs toggle (always enabled)
            box.prop(s, "custom_lods")
            # Settings below are disabled when Custom LODs is enabled
            settings_col = box.column(align=True)
            settings_col.enabled = not bool(getattr(s, 'custom_lods', False))
            # Collider options and ratio
            row = settings_col.row(align=True)
            row.prop(s, "generate_collider")
            row = settings_col.row(align=True)
            row.prop(s, "collider_ratio", text="MeshCollider Ratio")
            # LOD targets: explicit LOD0 triangle count and ratios for LOD1–3 relative to LOD0
            col = settings_col.column(align=True)
            col.prop(s, "lod0_target_tris", text="LOD0 Target Tris")
            col.prop(s, "lod1_ratio", text="LOD1 Ratio (of LOD0)")
            col.prop(s, "lod2_ratio", text="LOD2 Ratio (of LOD0)")
            col.prop(s, "lod3_ratio", text="LOD3 Ratio (of LOD0)")
            # ShadowProxy toggle and per-LOD ratios (vertical)
            settings_col.prop(s, "generate_shadow_proxies")
            sp_box = settings_col.box()
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

class VIVID_PT_lod_textures(Panel):
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category  = "LOD"
    bl_parent_id = "VIVID_PT_main_panel_lods"
    bl_label     = "LOD Textures"
    bl_order     = 80

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        s = getattr(context.scene, 'vivid_lod_props', None)
        # Bake only LOD0 toggle at top
        if s and hasattr(s, 'bake_only_lod0'):
            col.prop(s, 'bake_only_lod0', text='Bake only LOD0')
        # Bake only essential textures toggle
        if s and hasattr(s, 'bake_only_essential_textures'):
            col.prop(s, 'bake_only_essential_textures', text='Bake only essential textures')
        # Slider for Displace strength used by LOD cage generation
        if s and hasattr(s, 'displace_cage_strength'):
            col.prop(s, 'displace_cage_strength', text='Displace Modifier Strength')
            # Per-LOD overrides (shown when available)
            has_per_lod = all(hasattr(s, attr) for attr in (
                'displace_cage_strength_lod1',
                'displace_cage_strength_lod2',
                'displace_cage_strength_lod3',
            ))
            # Hide overrides when baking only LOD0
            show_overrides = has_per_lod and (not bool(getattr(s, 'bake_only_lod0', False)))
            if show_overrides:
                box = col.box()
                box.label(text="Per-LOD Displace Overrides")
                bcol = box.column(align=True)
                bcol.prop(s, 'displace_cage_strength_lod1', text='LOD1 Displace Strength')
                bcol.prop(s, 'displace_cage_strength_lod2', text='LOD2 Displace Strength')
                bcol.prop(s, 'displace_cage_strength_lod3', text='LOD3 Displace Strength')
        # Generate LOD Cages (above Max Resolution)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "generate_lod_cages"):
            col.operator("vivid.generate_lod_cages", text="Generate LOD Cages", icon='MESH_GRID')
        else:
            col.label(text="Operator vivid.generate_lod_cages not registered.", icon='ERROR')
        # LOD bake max resolution selector (controls LOD0; others derive)
        if s and hasattr(s, 'lod_max_resolution'):
            col.prop(s, 'lod_max_resolution', text='Max Resolution')
        # Bake LOD Textures
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "bake_lod_textures"):
            col.operator("vivid.bake_lod_textures", text="Bake LOD Textures", icon='RENDER_STILL')
        else:
            col.label(text="Operator vivid.bake_lod_textures not registered.", icon='ERROR')

class VIVID_PT_export_lods(Panel):
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category  = "LOD"
    bl_parent_id = "VIVID_PT_main_panel_lods"
    bl_label     = "Export LODs"
    bl_order     = 100

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "export_lods"):
            col.operator("vivid.export_lods", text="Export LODs", icon='EXPORT')
        else:
            col.label(text="Operator vivid.export_lods not registered.", icon='ERROR')

_classes = (
    VIVID_PT_main_panel_lods,
    VIVID_PT_setup_lods,
    VIEW3D_PT_shadowproxy_correction,
    VIVID_PT_lod_textures,
    VIVID_PT_export_lods,
    # New panels for LOD Textures and Export at bottom
    
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
