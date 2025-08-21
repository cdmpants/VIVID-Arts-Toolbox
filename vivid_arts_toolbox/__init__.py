import bpy

# Import all modules that contain Blender classes to be registered
# We explicitly import the classes from the 'operators' sub-package's __init__.py
from . import preferences
from . import properties
from . import panel
from .operators import (
    VIVID_OT_warning_dialog,
    VIVID_OT_bake_designer_textures,
    VIVID_OT_generate_asset,
    VIVID_OT_setup_lods,
    VIVID_OT_export_asset
)

bl_info = {
    "name": "VIVID Arts Toolbox",
    "author": "Christopher/VIVID Arts",
    "version": (1, 17), # Current version, no new changes in this file for this query.
    "blender": (4, 3, 0),
    "location": "3D Viewport > N Panel > VIVID Arts Toolbox",
    "description": "Automates photogrammetry processing with Blender and Substance Designer.",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

# List of all classes to register
_classes = [
    preferences.VIVID_Arts_Toolbox_Preferences,
    properties.VIVID_PG_BakeProperties,
    properties.VIVID_PG_LODProperties,
    panel.VIVID_PT_main_panel,
    VIVID_OT_warning_dialog,
    VIVID_OT_bake_designer_textures,
    VIVID_OT_generate_asset,
    VIVID_OT_setup_lods,
    VIVID_OT_export_asset,
]

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    # Register scene properties
    bpy.types.Scene.vivid_bake_props = bpy.props.PointerProperty(type=properties.VIVID_PG_BakeProperties)
    bpy.types.Scene.vivid_lod_props = bpy.props.PointerProperty(type=properties.VIVID_PG_LODProperties)
    bpy.types.Scene.vivid_warning_confirmed = bpy.props.BoolProperty(name="Warning Confirmed", default=False)
    bpy.types.Scene.vivid_warning_callback_id = bpy.props.StringProperty(name="Warning Callback ID")

    print("VIVID Arts Toolbox Registered!")

def unregister():
    # Unregister scene properties first
    del bpy.types.Scene.vivid_bake_props
    del bpy.types.Scene.vivid_lod_props
    del bpy.types.Scene.vivid_warning_confirmed
    del bpy.types.Scene.vivid_warning_callback_id

    # Unregister all classes in reverse order
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    print("VIVID Arts Toolbox Unregistered!")

if __name__ == "__main__":
    register()

