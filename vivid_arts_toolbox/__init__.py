# vivid_arts_toolbox/__init__.py
bl_info = {
    "name": "VIVID Arts Toolbox",
    "author": "Christopher/VIVID Arts",
    "version": (1, 0, 1),  # bumped
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

# Modules with their own register() functions
from .operators import shadowproxy_correction
from .operators import light_removal   # existing
# NEW: Export to Painter (self-registering like your other modules)
from . import export_to_painter
from .operators import generate_surface

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
    if not hasattr(bpy.types.Scene, "vivid_surface_margin"):
        from bpy.props import FloatProperty
        bpy.types.Scene.vivid_surface_margin = FloatProperty(
            name="Surface Margin",
            description="Default margin used by Generate Surface",
            default=1.0,
            min=0.0,
        )

    # Warning dialog flags (used by Setup LODs flow)
    if not hasattr(bpy.types.Scene, "vivid_warning_confirmed"):
        bpy.types.Scene.vivid_warning_confirmed = BoolProperty(default=False)
    if not hasattr(bpy.types.Scene, "vivid_warning_callback_id"):
        bpy.types.Scene.vivid_warning_callback_id = StringProperty(default="")

    # Bake Textures (creates scene.vivid_designer_bake and registers VIVID_OT_bake_designer)
    bake_textures.register_designer_bake()

    # Panels (UI foldouts)
    panel.register()

    # Modules with custom register()
    shadowproxy_correction.register()
    light_removal.register()
    generate_surface.register()

    # NEW: Export to Painter props/op (adds scene.vivid_export_to_painter and operator)
    export_to_painter.register()

    print("VIVID Arts Toolbox Registered!")

def unregister():
    # NEW: Export to Painter
    export_to_painter.unregister()

    # Unregister in reverse order
    light_removal.unregister()
    shadowproxy_correction.unregister()
    generate_surface.unregister()
    panel.unregister()

    # Remove Scene pointers/flags
    if hasattr(bpy.types.Scene, "vivid_lod_props"):
        del bpy.types.Scene.vivid_lod_props
    if hasattr(bpy.types.Scene, "vivid_surface_margin"):
        del bpy.types.Scene.vivid_surface_margin
    if hasattr(bpy.types.Scene, "vivid_warning_confirmed"):
        del bpy.types.Scene.vivid_warning_confirmed
    if hasattr(bpy.types.Scene, "vivid_warning_callback_id"):
        del bpy.types.Scene.vivid_warning_callback_id

    # Undo Designer bake registration
    bake_textures.unregister_designer_bake()

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)

    print("VIVID Arts Toolbox Unregistered!")

# Ensure Export to Painter module is loaded
try:
    from . import vivid_painter_export as _vpe
except Exception as _e:
    print('[VIVID] vivid_painter_export not loaded:', _e)
