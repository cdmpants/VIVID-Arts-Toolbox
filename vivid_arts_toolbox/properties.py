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

    __annotations__['generate_reflection_proxy'] = BoolProperty(
        name="Generate Reflection Proxy",
        default=False,
        description="After LOD processing, create a decimated _RefProxy from LOD3 and a _RefProxy_ShadowProxy from it."
    )

    __annotations__['refproxy_ratio'] = FloatProperty(
        name="RefProxy",
        default=0.25,
        min=0.0,
        max=1.0,
        precision=3,
        description="Decimate ratio applied to RefProxy, as a ratio of LOD3."
    )
    __annotations__['refproxy_sp_ratio'] = FloatProperty(
        name="RefProxy SP",
        default=0.20,
        min=0.0,
        max=1.0,
        precision=3,
        description="Decimate ratio applied to RefProxy ShadowProxy, as a ratio of RefProxy."
    )

    __annotations__['use_cinema_as_lod0'] = BoolProperty(
        name="Use Cinema as LOD0",
        default=True,
        description="Use a copy of the Cinema mesh as LOD0 and skip LOD0 reduction/generation."
    )
    __annotations__['generate_shadow_proxies'] = BoolProperty(
        name="Generate High ShadowProxies",
        default=True,
        description="Toggle creation of high-detail ShadowProxy meshes."
    )

    __annotations__['generate_low_shadow_proxies'] = BoolProperty(
        name="Generate Low ShadowProxies",
        default=True,
        description="Toggle creation of low-detail ShadowProxy meshes."
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
    __annotations__['sp_lod0_ratio'] = FloatProperty(name="SP High LOD0 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
    __annotations__['sp_lod1_ratio'] = FloatProperty(name="SP High LOD1 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
    __annotations__['sp_lod2_ratio'] = FloatProperty(name="SP High LOD2 Ratio", default=0.20, min=0.0, max=1.0, precision=3)
    __annotations__['sp_lod3_ratio'] = FloatProperty(name="SP High LOD3 Ratio", default=0.20, min=0.0, max=1.0, precision=3)

    __annotations__['sp_low_lod0_ratio'] = FloatProperty(name="SP Low LOD0 Ratio", default=0.01, min=0.0, max=1.0, precision=3)
    __annotations__['sp_low_lod1_ratio'] = FloatProperty(name="SP Low LOD1 Ratio", default=0.02, min=0.0, max=1.0, precision=3)
    __annotations__['sp_low_lod2_ratio'] = FloatProperty(name="SP Low LOD2 Ratio", default=0.04, min=0.0, max=1.0, precision=3)
    __annotations__['sp_low_lod3_ratio'] = FloatProperty(name="SP Low LOD3 Ratio", default=0.08, min=0.0, max=1.0, precision=3)

    # LOD Cage generation settings
    __annotations__['displace_cage_strength'] = FloatProperty(
        name="Displace Modifier Strength",
        description="Strength applied to Displace modifiers added to generated LOD cages.",
        default=1.0, soft_min=-10.0, soft_max=10.0, precision=3
    )

    # Per-LOD Displace strengths (override the global when set)
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

    # LOD bake scope
    __annotations__['bake_only_lod0'] = BoolProperty(
        name="Bake only LOD0",
        description="When enabled, only export and bake LOD0 (and its UDIMs/cage). Disable to bake all LODs.",
        default=False
    )

    # LOD baking scope for textures
    __annotations__['bake_only_essential_textures'] = BoolProperty(
        name="Bake only essential textures",
        description="When enabled, only bake Normal, BentNormal and Displacement; other bakers are disabled.",
        default=True
    )

    # Merge UDIMs after baking into a single square texture per map
    __annotations__['merge_udims'] = BoolProperty(
        name="Merge UDIMs",
        description="After baking, composite UDIM tiles into a single square texture per map and remove the original tiles.",
        default=True
    )
