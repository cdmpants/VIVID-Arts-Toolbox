bl_info = {
    "name": "VIVID Arts Toolbox",
    "author": "Christopher/VIVID Arts",
    "version": (1, 0, 0),
    "blender": (4, 3, 0),
    "location": "3D Viewport > N Panel > VIVID Arts Toolbox",
    "description": "Automates photogrammetry processing for video games with Blender, MeshLab, and Substance Designer.",
    "category": "Import-Export",
}

import bpy

from . import preferences
from . import properties
from . import panel
from . import bake_textures
from .operators import (
    VIVID_OT_warning_dialog,
    VIVID_OT_generate_asset,
    VIVID_OT_setup_lods,
    VIVID_OT_export_asset,
)

_classes = [
    preferences.VIVID_Arts_Toolbox_Preferences,
    properties.VIVID_PG_LODProperties,
    panel.VIVID_PT_main_panel,
    VIVID_OT_warning_dialog,
    VIVID_OT_generate_asset,
    VIVID_OT_setup_lods,
    VIVID_OT_export_asset,
]

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    # Register old LOD property group
    bpy.types.Scene.vivid_lod_props = bpy.props.PointerProperty(type=properties.VIVID_PG_LODProperties)
    bpy.types.Scene.vivid_warning_confirmed = bpy.props.BoolProperty(name="Warning Confirmed", default=False)
    bpy.types.Scene.vivid_warning_callback_id = bpy.props.StringProperty(name="Warning Callback ID")

    # Register new Designer bake props & operator
    bake_textures.register_designer_bake()

    print("VIVID Arts Toolbox Registered!")

def unregister():
    # Remove properties
    del bpy.types.Scene.vivid_lod_props
    del bpy.types.Scene.vivid_warning_confirmed
    del bpy.types.Scene.vivid_warning_callback_id

    # Unregister new Designer bake props & operator
    bake_textures.unregister_designer_bake()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    print("VIVID Arts Toolbox Unregistered!")
