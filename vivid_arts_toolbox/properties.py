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
    __annotations__['custom_lods'] = BoolProperty(
        name="Custom LODs",
        default=False,
        description="Disable built-in LOD generation; you will manage LODs manually."
    )
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
    # LOD0 explicit target triangle count (reduced directly from Cinema)
    __annotations__['lod0_target_tris'] = IntProperty(
        name="LOD0 Target Tris",
        description="Target triangle count for LOD0 reduced directly from the Cinema mesh.",
        default=10000, min=100, soft_max=2000000
    )
    # Deprecated legacy ratio (kept for backward compatibility; not shown in UI)
    __annotations__['lod0_ratio'] = FloatProperty(
        name="LOD0 Reduction (Legacy)",
        description="Legacy: target face ratio for LOD0 (fraction of Cinema).",
        default=0.08, min=0.0, max=1.0, precision=4
    )
    __annotations__['lod1_ratio'] = FloatProperty(
        name="LOD1 Ratio (of LOD0)",
        description="LOD1 target is this fraction of LOD0 triangle count.",
        default=0.40, min=0.0, max=1.0, precision=4
    )
    __annotations__['lod2_ratio'] = FloatProperty(
        name="LOD2 Ratio (of LOD0)",
        description="LOD2 target is this fraction of LOD0 triangle count.",
        default=0.16, min=0.0, max=1.0, precision=4
    )
    __annotations__['lod3_ratio'] = FloatProperty(
        name="LOD3 Ratio (of LOD0)",
        description="LOD3 target is this fraction of LOD0 triangle count.",
        default=0.064, min=0.0, max=1.0, precision=4
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

    # LOD Cage generation settings
    __annotations__['displace_cage_strength'] = FloatProperty(
        name="Displace Modifier Strength",
        description="Strength applied to Displace modifiers added to generated LOD cages.",
        default=1.0, soft_min=-10.0, soft_max=10.0, precision=3
    )

    # Per-LOD Displace strengths (override the global when set)
    __annotations__['displace_cage_strength_lod0'] = FloatProperty(
        name="LOD0 Displace Strength",
        description="Displace modifier strength for LOD0 cages.",
        default=1.0, soft_min=-10.0, soft_max=10.0, precision=3
    )
    __annotations__['displace_cage_strength_lod1'] = FloatProperty(
        name="LOD1 Displace Strength",
        description="Displace modifier strength for LOD1 cages.",
        default=1.0, soft_min=-10.0, soft_max=10.0, precision=3
    )
    __annotations__['displace_cage_strength_lod2'] = FloatProperty(
        name="LOD2 Displace Strength",
        description="Displace modifier strength for LOD2 cages.",
        default=1.0, soft_min=-10.0, soft_max=10.0, precision=3
    )
    __annotations__['displace_cage_strength_lod3'] = FloatProperty(
        name="LOD3 Displace Strength",
        description="Displace modifier strength for LOD3 cages.",
        default=1.0, soft_min=-10.0, soft_max=10.0, precision=3
    )

    # LOD bake max resolution (controls LOD0; LOD1/2/3 bake at 1/2, 1/4, 1/8)
    __annotations__['lod_max_resolution'] = EnumProperty(
        name="Max Resolution",
        description="Maximum resolution for LOD bakes (applied to LOD0; LOD1=1/2, LOD2=1/4, LOD3=1/8)",
        items=[
            ("256",  "256",  "256 x 256"),
            ("512",  "512",  "512 x 512"),
            ("1024", "1024", "1024 x 1024"),
            ("2048", "2048", "2048 x 2048"),
            ("4096", "4096", "4096 x 4096"),
            ("8192", "8192", "8192 x 8192"),
        ],
        default="4096",
    )
