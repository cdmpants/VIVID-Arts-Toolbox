# vivid_arts_toolbox/panel_asset.py
import bpy
from bpy.types import Panel

class VIVID_PT_main_panel_asset(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Asset"
    bl_label      = "VIVID Arts Toolbox"
    bl_options    = {'HIDE_HEADER'}
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
    bl_label      = "Cinema Model"
    bl_order      = 20
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "generate_asset"):
            col.operator("vivid.generate_asset", text="Generate Cinema Model", icon='OUTLINER_OB_LIGHTPROBE')
        else:
            col.label(text="Operator vivid.generate_asset not registered.", icon='ERROR')
        # Create Variant button (requires operator implementation later)
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "create_cinema_variant"):
            col.operator("vivid.create_cinema_variant", text="Create Variant", icon='DUPLICATE')
        # Move Export Asset below here and rename
        if hasattr(bpy.ops, "vivid") and hasattr(bpy.ops.vivid, "export_asset"):
            col.operator("vivid.export_asset", text="Export Cinema Model", icon='EXPORT')

## Removed separate Export Asset panel; export button is now under Cinema Model

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
            row = box.row(align=True); row.prop(s, "de_light_with_lightmap", text="De-light with Lightmap")
            row = box.row(align=True); row.prop(s, "make_seamless", text="Make Seamless")
        else:
            box.label(text="Light Removal settings not found.", icon='INFO')
        col = layout.column(align=True)
        col.operator("vivid.bake_delit", text="Process Textures", icon='RENDER_STILL')

_classes = (
    VIVID_PT_main_panel_asset,
    VIVID_PT_surface,
    VIVID_PT_uv_mapping,
    VIVID_PT_bake_textures,
    VIVID_PT_generate_asset,
    VIVID_PT_export_to_painter,
    VIVID_PT_texture_processing,
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
