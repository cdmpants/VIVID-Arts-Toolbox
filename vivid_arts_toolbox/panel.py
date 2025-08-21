import bpy

class VIVID_PT_main_panel(bpy.types.Panel):
    bl_label = "VIVID Arts Toolbox"
    bl_idname = "VIVID_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'VIVID Arts Toolbox'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Baker and Resolution options
        box = layout.box()
        box.label(text="Baking Settings:", icon='RENDER_STILL')
        row = box.row(align=True)
        row.prop(scene.vivid_bake_props, "baker_type", expand=True)
        row = box.row()
        row.prop(scene.vivid_bake_props, "resolution", expand=True)

        layout.separator()

        # Bake Designer Textures Button
        col = layout.column(align=True)
        col.prop(scene.vivid_bake_props, "import_baked_textures")
        col.operator("vivid.bake_designer_textures")

        layout.separator()

        # Generate Asset Button
        col = layout.column(align=True)
        col.operator("vivid.generate_asset")

        layout.separator()

        # Setup LODs Section
        box = layout.box()
        box.label(text="LOD Setup Settings:", icon='MOD_DECIM')
        box.prop(scene.vivid_lod_props, "generate_shadow_proxies")
        
        # Generate Collider options
        row = box.row()
        row.prop(scene.vivid_lod_props, "generate_collider")
        if scene.vivid_lod_props.generate_collider:
            row.prop(scene.vivid_lod_props, "is_convex_collider", text="Is Convex")

        box.operator("vivid.setup_lods")

        layout.separator()

        # Export Asset Button
        col = layout.column(align=True)
        col.operator("vivid.export_asset")

