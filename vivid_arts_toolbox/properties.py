import bpy
from bpy.props import EnumProperty, BoolProperty, FloatProperty, IntProperty


class VIVID_PG_BakeProperties(bpy.types.PropertyGroup):
    """Properties for Blender's internal baking."""
    __annotations__ = {}
    __annotations__['bake_resolution'] = IntProperty(
        name="Bake Resolution",
        default=2048,
        min=256, max=8192,
        step=256,
        description="Resolution of the baked texture maps for Blender's internal baker."
    )
    __annotations__['bake_extrusion'] = FloatProperty(
        name="Bake Extrusion",
        default=0.1,
        min=0.0, max=1.0,
        step=0.01,
        precision=3,
        description="Distance to extrude rays during Blender's internal baking (cage extrusion)."
    )
    __annotations__['bake_normal_map'] = BoolProperty(name="Normal Map", default=True, description="Bake a Normal Map.")
    __annotations__['bake_ao_map'] = BoolProperty(name="Ambient Occlusion Map", default=True, description="Bake an Ambient Occlusion Map.")
    __annotations__['bake_diffuse_map'] = BoolProperty(name="Diffuse Color Map", default=True, description="Bake a Diffuse Color Map.")


class VIVID_PG_LODProperties(bpy.types.PropertyGroup):
    """Properties for LOD generation and exports."""
    __annotations__ = {}
    __annotations__['generate_shadow_proxies'] = BoolProperty(
        name="Generate ShadowProxies",
        default=True,
        description="Toggle creation of ShadowProxy meshes."
    )
    __annotations__['generate_collider'] = BoolProperty(
        name="Generate Collider",
        default=True,
        description="Toggle creation of collider meshes."
    )
    # Reduction ratios
    __annotations__['lod0_ratio'] = FloatProperty(
        name="LOD0 Reduction",
        description="Target face ratio for LOD0 (reduced from Cinema).",
        default=0.08, min=0.0, max=1.0, precision=3
    )
    __annotations__['lod1_ratio'] = FloatProperty(
        name="LOD1 Reduction",
        description="Target face ratio for LOD1 (fraction of LOD0 faces).",
        default=0.40, min=0.0, max=1.0, precision=3
    )
    __annotations__['lod2_ratio'] = FloatProperty(
        name="LOD2 Reduction",
        description="Target face ratio for LOD2 (fraction of LOD0 faces).",
        default=0.16, min=0.0, max=1.0, precision=3
    )
    __annotations__['lod3_ratio'] = FloatProperty(
        name="LOD3 Reduction",
        description="Target face ratio for LOD3 (fraction of LOD0 faces).",
        default=0.064, min=0.0, max=1.0, precision=3
    )
    __annotations__['collider_ratio'] = FloatProperty(
        name="MeshCollider Reduction",
        description="Decimate ratio for MeshCollider generation from LOD0.",
        default=0.05, min=0.0, max=1.0, precision=3
    )
    # Per-LOD ShadowProxy ratios
    __annotations__['sp_lod0_ratio'] = FloatProperty(name="SP LOD0 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
    __annotations__['sp_lod1_ratio'] = FloatProperty(name="SP LOD1 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
    __annotations__['sp_lod2_ratio'] = FloatProperty(name="SP LOD2 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
    __annotations__['sp_lod3_ratio'] = FloatProperty(name="SP LOD3 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
