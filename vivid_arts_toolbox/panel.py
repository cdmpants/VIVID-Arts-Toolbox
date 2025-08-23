# vivid_arts_toolbox/panel.py
import bpy
from bpy.types import Panel

def draw_designer_bake_ui(layout, context):
    s = getattr(context.scene, "vivid_designer_bake", None)
    if not s:
        layout.label(text="Designer bake settings not available", icon='ERROR')
        return

    box = layout.box()
    box.label(text="Substance Designer Bake", icon='RENDER_STILL')

    row = box.row(align=True)
    row.prop(s, "export_bake_meshes", text="Export Bake Meshes")

    row = box.row(align=True)
    row.prop(s, "setup_material", text="Setup Material")

    row = box.row(align=True)
    row.prop(s, "bake_resolution", text="Bake Resolution")

    row = box.row(align=True)
    row.prop(s, "engine", text="Engine")  # NEW

    box.operator("vivid.bake_designer", text="Bake Designer Textures", icon="RENDER_STILL")


class VIVID_PT_main_panel(Panel):
    bl_label = "VIVID Arts Toolbox"
    bl_idname = "VIVID_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'VIVID Arts Toolbox'  # single tab

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # --- Debugging Section Start ---
        layout.label(text="VIVID Arts Toolbox Status:", icon='INFO')

        if hasattr(scene, 'vivid_designer_bake') and scene.vivid_designer_bake:
            layout.label(text="Designer Bake Properties: OK", icon='CHECKMARK')
        else:
            layout.label(text="Designer Bake Properties: NOT INITIALIZED", icon='CANCEL')

        if hasattr(scene, 'vivid_lod_props') and scene.vivid_lod_props:
            layout.label(text="LOD Properties: OK", icon='CHECKMARK')
        else:
            layout.label(text="LOD Properties: NOT INITIALIZED", icon='CANCEL')

        layout.separator()
        # --- Debugging Section End ---

        # Designer Bake Section
        draw_designer_bake_ui(layout, context)
        layout.separator()

        # Generate Asset
        col = layout.column(align=True)
        if hasattr(bpy.ops, 'vivid') and hasattr(bpy.ops.vivid, 'generate_asset') and bpy.ops.vivid.generate_asset.poll():
            col.operator("vivid.generate_asset")
        else:
            col.label(text="Generate Asset (Operator Missing)", icon='INFO')

        layout.separator()

        # Setup LODs
        box = layout.box()
        box.label(text="LOD Setup Settings:", icon='MOD_DECIM')
        try:
            if hasattr(scene, 'vivid_lod_props') and scene.vivid_lod_props:
                box.prop(scene.vivid_lod_props, "generate_shadow_proxies")

                row = box.row()
                row.prop(scene.vivid_lod_props, "generate_collider")
                if scene.vivid_lod_props.generate_collider:
                    row.prop(scene.vivid_lod_props, "is_convex_collider", text="Is Convex")
            else:
                box.label(text="LOD Properties are not accessible.", icon='ERROR')
        except AttributeError as e:
            box.label(text=f"Error accessing LOD Props: {e}", icon='ERROR')
        except Exception as e:
            box.label(text=f"Unexpected error in LOD Props UI: {e}", icon='ERROR')

        col = layout.column(align=True)
        if hasattr(bpy.ops, 'vivid') and hasattr(bpy.ops.vivid, 'setup_lods') and bpy.ops.vivid.setup_lods.poll():
            col.operator("vivid.setup_lods")
        else:
            col.label(text="Setup LODs (Operator Missing)", icon='INFO')

        layout.separator()

        # Export Asset
        col = layout.column(align=True)
        if hasattr(bpy.ops, 'vivid') and hasattr(bpy.ops.vivid, 'export_asset') and bpy.ops.vivid.export_asset.poll():
            col.operator("vivid.export_asset")
        else:
            col.label(text="Export Asset (Operator Missing)", icon='INFO')


def register():
    bpy.utils.register_class(VIVID_PT_main_panel)

def unregister():
    bpy.utils.unregister_class(VIVID_PT_main_panel)
