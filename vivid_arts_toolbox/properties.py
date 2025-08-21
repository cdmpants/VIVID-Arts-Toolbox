import bpy
from bpy.props import EnumProperty, BoolProperty, FloatProperty

class VIVID_PG_BakeProperties(bpy.types.PropertyGroup):
    baker_type: EnumProperty(
        name="Baker",
        items=[
            ('CPU', "CPU", "Use CPU for baking"),
            ('GPU', "GPU", "Use GPU for baking")
        ],
        default='GPU'
    )
    resolution: EnumProperty(
        name="Resolution",
        items=[
            ('256', "256", "256x256 pixels"),
            ('512', "512", "512x512 pixels"),
            ('1024', "1024", "1024x1024 pixels"),
            ('2048', "2048", "2048x2048 pixels"),
            ('4096', "4096", "4096x4096 pixels"),
            ('8192', "8192", "8192x8192 pixels")
        ],
        default='2048'
    )
    import_baked_textures: BoolProperty(
        name="Import Baked Textures",
        default=True,
        description="Imports generated textures back into Blender for preview."
    )

class VIVID_PG_LODProperties(bpy.types.PropertyGroup):
    generate_shadow_proxies: BoolProperty(
        name="Generate ShadowProxies",
        default=True,
        description="Toggle creation of ShadowProxy meshes. Ticked on by default."
    )
    generate_collider: BoolProperty(
        name="Generate Collider",
        default=True,
        description="Toggle creation of collider meshes. Ticked on by default."
    )
    is_convex_collider: BoolProperty(
        name="Is Convex",
        default=False,
        description="If true, generates a _ConvexCollider; otherwise _MeshCollider."
    )

