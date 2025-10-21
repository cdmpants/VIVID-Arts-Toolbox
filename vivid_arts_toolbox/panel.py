# vivid_arts_toolbox/panel.py
import bpy
from bpy.types import Panel

class VIVID_PT_main_panel_asset(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        pass


class VIVID_PT_surface(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
    bl_label      = "Surface"
    bl_order      = 1
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        # Dimensions controls stored on Scene for convenience
        row = col.row(align=True)
        row.prop(context.scene, "vivid_surface_dim_x", text="Meters X")
        row.prop(context.scene, "vivid_surface_dim_y", text="Meters Y")
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "generate_surface"):
            op = col.operator("vivid.generate_surface", text="Generate Surface", icon='MESH_GRID')
            op.dim_x = getattr(context.scene, "vivid_surface_dim_x", 2.0)
            op.dim_y = getattr(context.scene, "vivid_surface_dim_y", 2.0)
        else:
            col.label(text="Operator vivid.generate_surface not registered.", icon='ERROR')

class VIVID_PT_uv_mapping(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
    bl_label      = "UV Mapping"
    bl_order      = 2
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.prop(context.scene, "vivid_uv_udim_tiles", text="UDIM")
        col.prop(context.scene, "vivid_uv_pixel_margin", text="Pixel Margin")
        col.prop(context.scene, "vivid_uv_texture_res", text="Texture Resolution")
        col.operator("vivid.unwrap_uvs", text="Unwrap UVs", icon='UV')

class VIVID_PT_bake_textures(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
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
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
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

class VIVID_PT_export_asset(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
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
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
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

class VIVID_PT_texture_processing(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_parent_id  = "VIVID_PT_main_panel_asset"
    bl_label      = "Texture Processing"
    bl_order      = 15

    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, "vivid_light_removal", None)
        box = layout.box()
        box.label(text="Settings", icon='PREFERENCES')
        if s:
            row = box.row(align=True); row.prop(s, "bake_resolution", text="Bake Resolution")
            row = box.row(align=True); row.prop(s, "engine",          text="Engine")
            row = box.row(align=True); row.prop(s, "save_only_release", text="Save only to Release")
            row = box.row(align=True); row.prop(s, "sharpen", text="Sharpen")
            row = box.row(align=True); row.prop(s, "de_light_with_lightmap", text="Delight with Lightmap")
            row = box.row(align=True); row.prop(s, "make_seamless", text="Make Seamless")
        else:
            box.label(text="Light Removal settings not found.", icon='INFO')
        col = layout.column(align=True)
        col.operator("vivid.bake_delit", text="Process Textures", icon='RENDER_STILL')

class VIVID_PT_main_panel_lods(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "LOD"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}

    def draw(self, context):
        pass

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

        layout.separator()
        col=layout.column(align=True)
        op=col.operator("object.shadowproxy_fit_all_pairs",text="Fit Shadow Proxies",icon='MOD_SHRINKWRAP')
        op.margin=s.sp_margin; op.grid=s.sp_grid; op.edge_samples=s.sp_edge_samples
        op.passes=s.sp_passes; op.v_passes=s.sp_v_passes; op.max_push=s.sp_max_push
        op.only_selected=s.sp_only_selected_pairs
        col.prop(s,"sp_only_selected_pairs")
        layout.separator()
        box2 = layout.box(); box2.label(text="LOD Textures", icon='RENDER_STILL')
        box2.label(text="Bake LOD Textures (coming soon)", icon='RENDER_STILL')

class VIVID_PT_main_panel_meta(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Metadata"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}

    def draw(self, context):
        pass

class VIVID_PT_metadata(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Metadata"
    bl_parent_id  = "VIVID_PT_main_panel_meta"
    bl_label      = "Metadata"
    bl_order      = 10
    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, 'vivid_metadata', None)
        col = layout.column(align=True)
        # Buttons
        col.operator("vivid.export_metadata_json", text="Export Metadata JSON", icon='EXPORT')
        row = layout.row(align=True)
        row.operator("vivid.reload_local_json", text="Reload Local JSON", icon='FILE_REFRESH')
        sub = layout.column(align=True)
        sub.prop(context.scene, "vivid_metadata_reference_path", text="Reference JSON")
        sub.operator("vivid.load_reference_json", text="Load Reference JSON", icon='FILE_FOLDER')
        layout.separator()
        if s:
            box = layout.box(); box.label(text="Main", icon='INFO')
            col = box.column(align=True)
            col.prop(s, 'asset_id')
            col.prop(s, 'display_name')
            col.prop(s, 'asset_type')
            col.prop(s, 'size')
            col.prop(s, 'biome')
            col.prop(s, 'category')
            col.prop(s, 'country')
            col.prop(s, 'region')
            col.prop(s, 'location')
            col.prop(s, 'date_captured')
            col.prop(s, 'version')

            box = layout.box(); box.label(text="Polycounts", icon='MESH_DATA')
            col = box.column(align=True)
            col.prop(s, 'poly_cinema')
            col.prop(s, 'poly_lod0')
            col.prop(s, 'poly_lod1')
            col.prop(s, 'poly_lod2')
            col.prop(s, 'poly_lod3')

            box = layout.box(); box.label(text="Source", icon='CAMERA_DATA')
            col = box.column(align=True)
            col.prop(s, 'source_name')
            col.prop(s, 'capture_device')
            col.prop(s, 'source_notes')

            box = layout.box(); box.label(text="Importer", icon='IMPORT')
            col = box.column(align=True)
            col.prop(s, 'importer_allow_udim_merge')
            col.prop(s, 'importer_allow_tessellation')
            col.prop(s, 'importer_has_collision')
            col.prop(s, 'importer_static')

            box = layout.box(); box.label(text="Labels", icon='BOOKMARKS')
            box.prop(s, 'labels')
        else:
            layout.label(text="Metadata properties not found.", icon='ERROR')

_classes = (
    VIVID_PT_main_panel_asset,
    VIVID_PT_surface,
    VIVID_PT_uv_mapping,
    VIVID_PT_bake_textures,
    VIVID_PT_generate_asset,
    VIVID_PT_export_asset,
    VIVID_PT_export_to_painter,
    VIVID_PT_texture_processing,
    VIVID_PT_main_panel_lods,
    VIVID_PT_setup_lods,
    VIEW3D_PT_shadowproxy_correction,
    VIVID_PT_main_panel_meta,
    VIVID_PT_metadata,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)
    # Scene UI properties
    from bpy.props import FloatProperty, EnumProperty, StringProperty, IntProperty
    if not hasattr(bpy.types.Scene, "vivid_surface_dim_x"):
        bpy.types.Scene.vivid_surface_dim_x = FloatProperty(
            name="Meters X",
            description="Width of the generated surface in meters",
            default=2.0, min=0.01, soft_max=1000.0,
        )
    if not hasattr(bpy.types.Scene, "vivid_surface_dim_y"):
        bpy.types.Scene.vivid_surface_dim_y = FloatProperty(
            name="Meters Y",
            description="Height of the generated surface in meters",
            default=2.0, min=0.01, soft_max=1000.0,
        )
    if not hasattr(bpy.types.Scene, "vivid_uv_udim_tiles"):
        bpy.types.Scene.vivid_uv_udim_tiles = EnumProperty(
            name="UDIM",
            description="Number of UDIM tiles (None = 0). Not wired yet.",
            items=[('0','None',''),*[(str(i),str(i),'') for i in range(2,17)]],
            default='0'
        )
    if not hasattr(bpy.types.Scene, "vivid_uv_pixel_margin"):
        bpy.types.Scene.vivid_uv_pixel_margin = IntProperty(
            name="Pixel Margin",
            description="UV packing pixel margin. Packer will use 1/8 of selected Texture Resolution internally.",
            default=3, min=0, soft_max=128,
        )
    if not hasattr(bpy.types.Scene, "vivid_uv_texture_res"):
        bpy.types.Scene.vivid_uv_texture_res = EnumProperty(
            name="Texture Resolution",
            description="Target texel density for UV packing (internally 1/8 of this will be used).",
            items=[(str(v), f"{v}", "") for v in (256,512,1024,2048,4096,8192)],
            default='8192'
        )
    if not hasattr(bpy.types.Scene, "vivid_metadata_reference_path"):
        bpy.types.Scene.vivid_metadata_reference_path = StringProperty(
            name="Reference JSON",
            description="Path to a reference metadata JSON to load",
            subtype='FILE_PATH'
        )

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
    for attr in (
        "vivid_surface_dim_x","vivid_surface_dim_y",
        "vivid_uv_udim_tiles","vivid_uv_pixel_margin","vivid_uv_texture_res",
        "vivid_metadata_reference_path",
    ):
        if hasattr(bpy.types.Scene, attr):
            delattr(bpy.types.Scene, attr)
