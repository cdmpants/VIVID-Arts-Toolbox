import bpy
from bpy.props import EnumProperty, BoolProperty, FloatProperty, IntProperty

class VIVID_PG_BakeProperties(bpy.types.PropertyGroup):
    """
    Properties for Blender's internal Cycles baking.
    This replaces the previous Substance Designer specific bake properties.
    """
    bake_resolution: IntProperty(
        name="Bake Resolution",
        default=2048,
        min=256, max=8192,
        step=256,
        description="Resolution of the baked texture maps for Blender's internal baker."
    )
    bake_extrusion: FloatProperty(
        name="Bake Extrusion",
        default=0.1,
        min=0.0, max=1.0,
        step=0.01,
        precision=3,
        description="Distance to extrude rays during Blender's internal baking (cage extrusion)."
    )
    bake_normal_map: BoolProperty(name="Normal Map", default=True, description="Bake a Normal Map.")
    bake_ao_map: BoolProperty(name="Ambient Occlusion Map", default=True, description="Bake an Ambient Occlusion Map.")
    bake_diffuse_map: BoolProperty(name="Diffuse Color Map", default=True, description="Bake a Diffuse Color Map.")
    # Add other bake types here if needed (e.g., Emission, Roughness, Metallic, Combined)


class VIVID_PG_LODProperties(bpy.types.PropertyGroup):
    """
    Properties for LOD generation.
    """
    generate_shadow_proxies: BoolProperty(
        name="Generate ShadowProxies",
        default=True,
        description="Toggle creation of ShadowProxy meshes."
    )
    generate_collider: BoolProperty(
        name="Generate Collider",
        default=True,
        description="Toggle creation of collider meshes."
    )
    is_convex_collider: BoolProperty(
        name="Is Convex",
        default=False,
        description="If true, generates a _ConvexCollider; otherwise _MeshCollider."
    )
