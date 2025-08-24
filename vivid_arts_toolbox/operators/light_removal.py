
import bpy, os, re
from bpy.types import Operator, PropertyGroup, Panel
from bpy.props import EnumProperty, PointerProperty

from ..bake_textures import _folders, _find_baked_textures_ex, _remove_suffix, _find_optimized_object

class VIVID_LightRemovalSettings(PropertyGroup):
    bake_resolution: EnumProperty(
        name="Bake Resolution",
        description="Resolution for Delit bake",
        items=[(str(v), f"{v}", "") for v in (256,512,1024,2048,4096,8192)],
        default="4096",
    )
    engine: EnumProperty(
        name="Engine",
        description="Use CPU or GPU for Cycles",
        items=[("CPU","CPU",""),("GPU","GPU","")],
        default="GPU",
    )

class VIVID_OT_bake_delit(Operator):
    bl_idname = "vivid.bake_delit"
    bl_label = "Bake Delit Texture"
    bl_description = "Cycles diffuse-color bake to a new image in the 'Delit' node"

    def execute(self, context):
        s = getattr(context.scene, "vivid_light_removal", None)
        if not s:
            self.report({'ERROR'}, "Light Removal settings not found on scene.")
            return {'CANCELLED'}

        scene = context.scene
        # Switch engine
        scene.render.engine = 'CYCLES'

        # Toggle device
        try:
            scene.cycles.device = s.engine
        except Exception:
            pass
        try:
            prefs = context.preferences.addons.get("cycles")
            if prefs and hasattr(prefs, "preferences"):
                prefs.preferences.compute_device_type = 'CUDA' if s.engine == 'GPU' else 'NONE'
        except Exception:
            pass

        # Disable denoise during bake (store + restore)
        prev_scene_denoise = getattr(scene.cycles, "use_denoising", None)
        prev_layer_denoise = None
        try:
            prev_layer_denoise = context.view_layer.cycles.use_denoising
        except Exception:
            pass
        try:
            if hasattr(scene.cycles, "use_denoising"):
                scene.cycles.use_denoising = False
            if hasattr(context.view_layer, "cycles") and hasattr(context.view_layer.cycles, "use_denoising"):
                context.view_layer.cycles.use_denoising = False
        except Exception:
            pass

        # Target object/material
        obj = _find_optimized_object()
        if not obj:
            self.report({'ERROR'}, "No *_Optimized object found in the scene.")
            # restore denoise
            if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
            if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
            return {'CANCELLED'}
        if obj.type != 'MESH':
            self.report({'ERROR'}, "Optimized object is not a mesh.")
            if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
            if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
            return {'CANCELLED'}

        base_name = _remove_suffix(obj.name, "_Optimized")
        mat = obj.active_material or (obj.material_slots[0].material if obj.material_slots else None)
        if not mat or not mat.use_nodes or not mat.node_tree:
            self.report({'ERROR'}, "Optimized object's material is missing or has no nodes.")
            if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
            if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
            return {'CANCELLED'}

        nt = mat.node_tree
        delit_node = nt.nodes.get("Delit")
        if not delit_node:
            delit_node = nt.nodes.new("ShaderNodeTexImage")
            delit_node.name = "Delit"
            delit_node.label = "Delit"
            delit_node.location = (-800, 300)
        # New image (always keep name "<base>_Delit", update existing to new resolution)
        res = int(s.bake_resolution)
        img_name = f"{base_name}_Delit"
        img = bpy.data.images.get(img_name)
        if img is None:
            img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)
        else:
            # If size changed, try scaling; if that fails, recreate but keep the same name
            try:
                if getattr(img, "size", None) and (img.size[0] != res or img.size[1] != res):
                    img.scale(res, res)
            except Exception:
                try:
                    bpy.data.images.remove(img)
                except Exception:
                    pass
                img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)

        # Prefer generated source for stable re-bakes regardless of file deletion on disk
        try:
            img.source = 'GENERATED'
        except Exception:
            pass
        img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)
        
        # Prefer generated source for stable re-bakes regardless of file deletion on disk
        try:
            img.source = 'GENERATED'
        except Exception:
            pass
        
        delit_node.image = img
        try:
            delit_node.image.colorspace_settings.name = "sRGB"
        except Exception:
            pass
        # Filename based on DLBC
        _, _, bake_tex = _folders()
        dlbc, _, _, _ = _find_baked_textures_ex(bake_tex)
        if dlbc:
            outfile = re.sub(r"(?i)_dlbc(\.[^\.]+)?$", "_Delit.png", dlbc)
            if outfile == dlbc:
                outfile = os.path.join(bake_tex, f"{base_name}_Delit.png")
        else:
            outfile = os.path.join(bake_tex, f"{base_name}_Delit.png")
        
        # Force visible/selectable, select object
        prev_hide = obj.hide_viewport
        prev_select = obj.select_get()
        try:
            obj.hide_set(False)
        except Exception:
            obj.hide_viewport = False
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        nt.nodes.active = delit_node
        
        # Bake diffuse color only
        try:
            scene.cycles.bake_type = 'DIFFUSE'
        except Exception:
            pass
        
        try:
            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='IMAGE_TEXTURES', use_clear=True)
        except Exception as e:
            # restore
            try:
                obj.select_set(prev_select)
                obj.hide_viewport = prev_hide
            except Exception:
                pass
            if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
            if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
            self.report({'ERROR'}, f"Bake failed: {e}")
            return {'CANCELLED'}
        
        # Save image
        os.makedirs(os.path.dirname(outfile), exist_ok=True)
        img.filepath_raw = outfile
        img.file_format = 'PNG'
        try:
            img.save()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save Delit image: {e}")
        
        # restore visibility and denoise
        try:
            obj.select_set(prev_select)
            obj.hide_viewport = prev_hide
        except Exception:
            pass
        if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
        if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
        
        self.report({'INFO'}, f"Delit baked → {outfile}")
        return {'FINISHED'}
        
class VIVID_PT_light_removal(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "VIVID Arts Toolbox"
    bl_parent_id  = "VIVID_PT_main_panel"
    bl_label      = "Light Removal"
    bl_order      = 15

    def draw(self, context):
        layout = self.layout
        s = getattr(context.scene, "vivid_light_removal", None)
        box = layout.box()
        box.label(text="Settings", icon='PREFERENCES')
        if s:
            row = box.row(align=True); row.prop(s, "bake_resolution", text="Bake Resolution")
            row = box.row(align=True); row.prop(s, "engine",          text="Engine")
        else:
            box.label(text="Light Removal settings not found.", icon='INFO')
        col = layout.column(align=True)
        col.operator("vivid.bake_delit", text="Bake Delit Texture", icon='RENDER_STILL')


CLASSES = (VIVID_LightRemovalSettings, VIVID_OT_bake_delit, VIVID_PT_light_removal)

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.vivid_light_removal = bpy.props.PointerProperty(type=VIVID_LightRemovalSettings)

def unregister():
    if hasattr(bpy.types.Scene, "vivid_light_removal"):
        del bpy.types.Scene.vivid_light_removal
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
