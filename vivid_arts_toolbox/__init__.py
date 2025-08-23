# vivid_arts_toolbox/__init__.py
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
from bpy.props import PointerProperty, BoolProperty, StringProperty

# Core modules
from . import preferences
from . import properties
from . import panel
from . import bake_textures

# Operators (modules define operator classes; they don't register themselves)
from .operators.generate_asset import VIVID_OT_generate_asset
from .operators.setup_lods import VIVID_OT_setup_lods
from .operators.export_asset import VIVID_OT_export_asset
from .operators.warning_dialog import VIVID_OT_warning_dialog

# ShadowProxy Correction module (has its own register() that adds its panel + scene props)
from .operators import shadowproxy_correction

# Classes that need bpy.utils.register_class(...)
_classes = (
    preferences.VIVID_Arts_Toolbox_Preferences,
    properties.VIVID_PG_BakeProperties,
    VIVID_OT_warning_dialog,
    VIVID_OT_generate_asset,
    VIVID_OT_setup_lods,
    VIVID_OT_export_asset,
)

def register():
    # Register classes that don't self-register
    for cls in _classes:
        bpy.utils.register_class(cls)

    # Scene pointers & flags used across operators/panels
    bpy.types.Scene.vivid_lod_props = PointerProperty(type=properties.VIVID_PG_BakeProperties)

    # Warning dialog flags (used by Setup LODs flow)
    if not hasattr(bpy.types.Scene, "vivid_warning_confirmed"):
        bpy.types.Scene.vivid_warning_confirmed = BoolProperty(default=False)
    if not hasattr(bpy.types.Scene, "vivid_warning_callback_id"):
        bpy.types.Scene.vivid_warning_callback_id = StringProperty(default="")

    # Bake Textures (creates scene.vivid_designer_bake and registers VIVID_OT_bake_designer)
    # NOTE: bake_textures.py exposes custom functions, not register()
    bake_textures.register_designer_bake()

    # Panels (UI foldouts)
    panel.register()

    # ShadowProxy Correction (its module handles its own scene props + subpanel)
    shadowproxy_correction.register()

    print("VIVID Arts Toolbox Registered!")

def unregister():
    # Unregister in reverse order
    shadowproxy_correction.unregister()
    panel.unregister()

    # Remove Scene pointers/flags
    if hasattr(bpy.types.Scene, "vivid_lod_props"):
        del bpy.types.Scene.vivid_lod_props
    if hasattr(bpy.types.Scene, "vivid_warning_confirmed"):
        del bpy.types.Scene.vivid_warning_confirmed
    if hasattr(bpy.types.Scene, "vivid_warning_callback_id"):
        del bpy.types.Scene.vivid_warning_callback_id

    # Undo Designer bake registration (removes scene.vivid_designer_bake)
    bake_textures.unregister_designer_bake()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    print("VIVID Arts Toolbox Unregistered!")


