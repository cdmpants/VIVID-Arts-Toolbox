import bpy
import os
import subprocess
import json

from bpy.props import StringProperty, EnumProperty, BoolProperty

class VIVID_OT_bake_designer_textures(bpy.types.Operator):
    bl_idname = "vivid.bake_designer_textures"
    bl_label = "Bake Designer Textures"
    bl_description = "Exports models, runs Substance Designer baking, and imports textures."

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

    def execute(self, context):
        self.report({'INFO'}, "Starting Bake Designer Textures process...")

        prefs = context.preferences.addons[__package__.split('.')[0]].preferences
        blend_filepath = bpy.data.filepath
        if not blend_filepath:
            self.report({'ERROR'}, "Save your .blend file first!")
            return {'CANCELLED'}

        blend_dir = os.path.dirname(blend_filepath)
        designer_output_dir = os.path.join(blend_dir, "Designer")
        os.makedirs(designer_output_dir, exist_ok=True)

        self.report({'INFO'}, "Step 1: Exporting _Optimized and _Cage FBX models...")
        optimized_collection = bpy.data.collections.get("Optimized")
        
        optimized_mesh_obj = None
        cage_mesh_obj = None
        high_poly_obj = None

        if optimized_collection:
            for obj in optimized_collection.objects:
                if obj.type == 'MESH':
                    if obj.name.endswith("_Optimized"):
                        optimized_mesh_obj = obj
                    elif obj.name.endswith("_Cage"):
                        cage_mesh_obj = obj
                    elif obj.name.endswith("_HighPoly"):
                        high_poly_obj = obj
                if optimized_mesh_obj and cage_mesh_obj and high_poly_obj:
                    break
        
        if not optimized_mesh_obj:
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.name.endswith("_Optimized"):
                    optimized_mesh_obj = obj
                    break
        if not cage_mesh_obj:
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.name.endswith("_Cage"):
                    cage_mesh_obj = obj
                    break
        if not high_poly_obj:
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.name.endswith("_HighPoly"):
                    high_poly_obj = obj
                    break


        if not optimized_mesh_obj:
            self.report({'ERROR'}, "No object ending with '_Optimized' found in scene.")
            return {'CANCELLED'}
        if not cage_mesh_obj:
            self.report({'ERROR'}, "No object ending with '_Cage' found in scene.")
            return {'CANCELLED'}

        for obj_to_export in [optimized_mesh_obj, cage_mesh_obj]:
            bpy.ops.object.select_all(action='DESELECT')
            obj_to_export.select_set(True)
            export_filepath = os.path.join(blend_dir, f"{obj_to_export.name}.fbx")
            bpy.ops.export_scene.fbx(
                filepath=export_filepath,
                use_selection=True,
                object_types={'MESH'},
                bake_space_transform=True,
                # Removed 'apply_scale' as it's unrecognized in Blender 4.3+
            )
            self.report({'INFO'}, f"Exported: {export_filepath}")

        high_poly_texture_path = ""
        if high_poly_obj:
            for mat_slot in high_poly_obj.data.materials:
                if mat_slot.material:
                    for node in mat_slot.material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            if "_HighPoly_u0_v0_diffuse.png" in node.image.filepath or "_HighPoly_u0_v0_diffuse.exr" in node.image.filepath:
                                high_poly_texture_path = bpy.path.abspath(node.image.filepath)
                                self.report({'INFO'}, f"Found HighPoly texture: {high_poly_texture_path}")
                                break
                        if high_poly_texture_path:
                            break
                if high_poly_texture_path:
                    break
        
            if not high_poly_texture_path:
                self.report({'WARNING'}, "No diffuse texture found for '_HighPoly' object. BaseColor_Transfer_DLBC baker might not work as expected.")
        else:
            self.report({'WARNING'}, "No '_HighPoly' object found. BaseColor_Transfer_DLBC baker might not work as expected.")

        self.report({'INFO'}, "Step 2: Running Substance Designer Baker...")
        designer_preset = prefs.designer_preset_filepath
        if not os.path.exists(designer_preset):
            self.report({'ERROR'}, f"Designer JSON preset not found: {designer_preset}")
            return {'CANCELLED'}

        optimized_fbx_path = os.path.join(blend_dir, f"{optimized_mesh_obj.name}.fbx")
        cage_fbx_path = os.path.join(blend_dir, f"{cage_mesh_obj.name}.fbx")

        sbsbaker_cmd = [
            'sbsbaker',
            '--inputs',
            optimized_fbx_path,
            cage_fbx_path,
            *([] if not high_poly_obj else [os.path.join(blend_dir, f"{high_poly_obj.name}.fbx")]),
            '--presets', designer_preset,
            '--output-path', designer_output_dir,
            '--output-format', 'png',
            '--baker-settings',
            json.dumps({
                "global_settings": {
                    "output_width": self.resolution,
                    "output_height": self.resolution,
                    "use_gpu": (self.baker_type == 'GPU')
                },
                "bakers": {
                    "BaseColor_Transfer_DLBC": {
                        "source": high_poly_texture_path
                    }
                }
            }),
            '--bake'
        ]

        try:
            subprocess.run(sbsbaker_cmd, check=True, capture_output=True, text=True)
            self.report({'INFO'}, "Substance Designer baking completed successfully.")
        except FileNotFoundError:
            self.report({'ERROR'}, "sbsbaker not found. Please ensure Substance Automation Toolkit is installed and 'sbsbaker.exe' is in your system PATH.")
            return {'CANCELLED'}
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Substance Designer baking failed: {e}")
            self.report({'ERROR'}, f"Substance Baker Stdout: {e.stdout}")
            self.report({'ERROR'}, f"Substance Baker Stderr: {e.stderr}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"An unexpected error occurred during Designer baking: {e}")
            return {'CANCELLED'}


        if self.import_baked_textures:
            self.report({'INFO'}, "Step 3: Importing baked textures and setting up material...")

            base_color_tex_path = os.path.join(designer_output_dir, f"{optimized_mesh_obj.name}_BaseColor_Transfer_DLBC.png")
            normals_tex_path = os.path.join(designer_output_dir, f"{optimized_mesh_obj.name}_Normals.png")

            if not os.path.exists(base_color_tex_path):
                self.report({'ERROR'}, f"Base Color texture not found: {base_color_tex_path}")
                return {'CANCELLED'}
            if not os.path.exists(normals_tex_path):
                self.report({'ERROR'}, f"Normals texture not found: {normals_tex_path}")
                return {'CANCELLED'}

            if optimized_mesh_obj.data.materials:
                num_materials = len(optimized_mesh_obj.data.materials)
                msg = (
                    f"The '{optimized_mesh_obj.name}' object has {num_materials} existing material(s). "
                    "They will be removed." if num_materials > 1 else
                    f"The '{optimized_mesh_obj.name}' object has an existing material. It will be removed."
                )
                bpy.context.scene.vivid_warning_confirmed = False
                bpy.context.scene.vivid_warning_callback_id = "BakeTexturesMaterialRemoval"
                bpy.ops.vivid.warning_dialog('INVOKE_DEFAULT', message=msg, callback_id="BakeTexturesMaterialRemoval")

                self.report({'INFO'}, f"Removing {num_materials} existing materials from {optimized_mesh_obj.name}.")
                optimized_mesh_obj.data.materials.clear()

            material_name = optimized_mesh_obj.name.replace("_Optimized", "")
            if material_name in bpy.data.materials:
                new_mat = bpy.data.materials[material_name]
            else:
                new_mat = bpy.data.materials.new(name=material_name)
            new_mat.use_nodes = True
            optimized_mesh_obj.data.materials.append(new_mat)

            nodes = new_mat.node_tree.nodes
            links = new_mat.node_tree.links

            for node in nodes:
                nodes.remove(node)

            principled_node = nodes.new(type='ShaderNodeBsdfPrincipled')
            principled_node.location = (0, 0)
            principled_node.inputs['Roughness'].default_value = 0.9
            material_output_node = nodes.new(type='ShaderNodeOutputMaterial')
            material_output_node.location = (400, 0)
            links.new(principled_node.outputs['BSDF'], material_output_node.inputs['Surface'])

            base_color_node = nodes.new(type='ShaderNodeTexImage')
            base_color_node.location = (-400, 200)
            try:
                base_color_node.image = bpy.data.images.load(base_color_tex_path, check_existing=True)
            except RuntimeError as e:
                self.report({'ERROR'}, f"Could not load Base Color image: {e}")
                return {'CANCELLED'}
            links.new(base_color_node.outputs['Color'], principled_node.inputs['Base Color'])

            normals_node = nodes.new(type='ShaderNodeTexImage')
            normals_node.location = (-400, -200)
            try:
                normals_node.image = bpy.data.images.load(normals_tex_path, check_existing=True)
            except RuntimeError as e:
                self.report({'ERROR'}, f"Could not load Normals image: {e}")
                return {'CANCELLED'}
            normals_node.image.colorspace_settings.name = 'Non-Color'

            normal_map_node = nodes.new(type='ShaderNodeNormalMap')
            normal_map_node.location = (-100, -200)
            links.new(normals_node.outputs['Color'], normal_map_node.inputs['Color'])
            links.new(normal_map_node.outputs['Normal'], principled_node.inputs['Normal'])

            self.report({'INFO'}, "Material and textures set up successfully.")
        else:
            self.report({'INFO'}, "Skipping texture import as requested.")

        self.report({'INFO'}, "Bake Designer Textures process completed.")
        return {'FINISHED'}

