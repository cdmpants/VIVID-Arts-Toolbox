# vivid_arts_toolbox/panel_metadata.py
import bpy
from bpy.types import Panel, UIList


class VIVID_UL_labels(UIList):
    bl_idname = "VIVID_UL_labels"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        # item is a VIVID_LabelItem
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(text=getattr(item, 'value', ''), icon='BOOKMARKS')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="")

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
            row = col.row(align=True)
            row.enabled = False
            row.prop(s, 'asset_id')
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
            # Display-only like AssetID
            row = col.row(align=True); row.enabled = False; row.prop(s, 'poly_cinema')
            row = col.row(align=True); row.enabled = False; row.prop(s, 'poly_lod0')
            row = col.row(align=True); row.enabled = False; row.prop(s, 'poly_lod1')
            row = col.row(align=True); row.enabled = False; row.prop(s, 'poly_lod2')
            row = col.row(align=True); row.enabled = False; row.prop(s, 'poly_lod3')

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
            row = box.row()
            row.template_list("VIVID_UL_labels", "", s, "labels_coll", s, "labels_index", rows=3)
            col_right = row.column(align=True)
            col_right.operator("vivid.label_add", text="", icon='ADD')
            col_right.operator("vivid.label_remove", text="", icon='REMOVE')
            # Draw the active item's dropdown below
            if 0 <= s.labels_index < len(s.labels_coll):
                it = s.labels_coll[s.labels_index]
                sub = box.column(align=True)
                sub.prop(it, 'value', text="Label")
            # Legacy string UI for backward compatibility
            box.prop(s, 'labels')
        else:
            layout.label(text="Metadata properties not found.", icon='ERROR')

_classes = (
    VIVID_UL_labels,
    VIVID_PT_main_panel_meta,
    VIVID_PT_metadata,
)

def register():
    for c in _classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
