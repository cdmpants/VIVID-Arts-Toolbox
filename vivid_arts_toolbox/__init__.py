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
from . import panel_asset
from . import panel_lods
from . import panel_metadata
from . import bake_textures

# Operators (modules define operator classes; they don't register themselves)
from .operators.generate_asset import VIVID_OT_generate_asset
from .operators.setup_lods import VIVID_OT_setup_lods
from .operators.export_asset import VIVID_OT_export_asset
from .operators.warning_dialog import VIVID_OT_warning_dialog
from .operators.create_cinema_variant import VIVID_OT_create_cinema_variant
from .operators.export_lods import VIVID_OT_export_lods
from .operators.generate_lod_cages import VIVID_OT_generate_lod_cages
from .operators.bake_lod_textures import VIVID_OT_bake_lod_textures
from .operators.render import VIVID_OT_output_renders

# Modules with their own register() functions
from .operators import shadowproxy_correction
from .operators import light_removal   # existing
# NEW: Export to Painter under operators/
from .operators import export_to_painter
from .operators import generate_surface
from .operators import unwrap_uvs
from .operators import setup_materials
from .operators import udim_material_assignment
from . import metadata

# Classes that need bpy.utils.register_class(...)
_classes = (
    preferences.VIVID_Arts_Toolbox_Preferences,
    properties.VIVID_PG_BakeProperties,
    properties.VIVID_PG_LODProperties,
    VIVID_OT_warning_dialog,
    VIVID_OT_generate_asset,
    VIVID_OT_setup_lods,
    VIVID_OT_export_asset,
    VIVID_OT_create_cinema_variant,
    VIVID_OT_export_lods,
    VIVID_OT_generate_lod_cages,
    VIVID_OT_bake_lod_textures,
    VIVID_OT_output_renders,
)

def register():
    # Register classes that don't self-register
    for cls in _classes:
        bpy.utils.register_class(cls)

    # Scene pointers & flags used across operators/panels
    bpy.types.Scene.vivid_lod_props = PointerProperty(type=properties.VIVID_PG_LODProperties)
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

    # Proactively unregister any legacy monolithic panels (panel.py) if they linger from older sessions
    try:
        _legacy = [
            'VIVID_PT_main_panel_asset','VIVID_PT_surface','VIVID_PT_uv_mapping','VIVID_PT_bake_textures',
            'VIVID_PT_generate_asset','VIVID_PT_export_asset','VIVID_PT_export_to_painter','VIVID_PT_texture_processing',
            'VIVID_PT_main_panel_lods','VIVID_PT_setup_lods','VIEW3D_PT_shadowproxy_correction',
            'VIVID_PT_main_panel_meta','VIVID_PT_metadata'
        ]
        for _name in _legacy:
            cls = getattr(bpy.types, _name, None)
            if cls:
                try:
                    bpy.utils.unregister_class(cls)
                except Exception:
                    pass
    except Exception:
        pass

    # Panels (UI foldouts)
    panel_asset.register()
    panel_lods.register()
    panel_metadata.register()

    # Modules with custom register()
    shadowproxy_correction.register()
    light_removal.register()
    generate_surface.register()
    unwrap_uvs.register()
    metadata.register()
    setup_materials.register()
    udim_material_assignment.register()
    

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
    unwrap_uvs.unregister()
    metadata.unregister()
    try:
        udim_material_assignment.unregister()
    except Exception:
        pass
    try:
        setup_materials.unregister()
    except Exception:
        pass
    
    panel_metadata.unregister()
    panel_lods.unregister()
    panel_asset.unregister()

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

# vivid_painter_export is deprecated and no longer imported; export_to_painter contains the UI and backend
