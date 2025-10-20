
import bpy, os, re, math
from bpy.types import Operator, PropertyGroup, Panel
from bpy.props import EnumProperty, PointerProperty, BoolProperty

from ..bake_textures import _folders, _find_baked_textures_ex, _remove_suffix, _find_optimized_object, _find_baked_textures_by_suffix_udim

class VIVID_LightRemovalSettings(PropertyGroup):
    __annotations__ = {}
    __annotations__['bake_resolution'] = EnumProperty(
        name="Bake Resolution",
        description="Resolution for Delit bake",
        items=[(str(v), f"{v}", "") for v in (256,512,1024,2048,4096,8192)],
        default="4096",
    )
    __annotations__['engine'] = EnumProperty(
        name="Engine",
        description="Use CPU or GPU for Cycles",
        items=[("CPU","CPU",""),("GPU","GPU","")],
        default="GPU",
    )
    __annotations__['save_only_release'] = BoolProperty(
        name="Save only to Release",
        description="Only save outputs to the Release folder (placeholder)",
        default=False,
    )
    __annotations__['sharpen'] = BoolProperty(
        name="Sharpen",
        description="Apply sharpen filter to result (placeholder)",
        default=False,
    )
    __annotations__['de_light_with_lightmap'] = BoolProperty(
        name="De-light with Lightmap",
        description="Use lightmap to assist de-lighting (placeholder)",
        default=False,
    )
    __annotations__['make_seamless'] = BoolProperty(
        name="Make Seamless",
        description="Attempt to make BaseColor seamless (placeholder)",
        default=False,
    )

class VIVID_OT_bake_delit(Operator):
    bl_idname = "vivid.bake_delit"
    bl_label = "Process Textures"
    bl_description = "Process textures (de-lighting pipeline). Outputs will be saved under ProcessTextures."

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

        # UDIM detection from material names
        def _extract_udim(name: str):
            m = re.search(r"_(\d{4})(?:\D|$)", name or "")
            if m:
                try:
                    v = int(m.group(1))
                    if v >= 1001:
                        return m.group(1)
                except Exception:
                    return None
            return None

        slots = obj.material_slots
        udims = []
        for sl in slots:
            m = getattr(sl, 'material', None)
            u = _extract_udim(m.name) if m and getattr(m, 'name', None) else None
            if u:
                udims.append(u)
        udim_mode = len(set(udims)) >= 1

        # Common pre-bake selection/visibility handling
        prev_hide = obj.hide_viewport
        prev_select = obj.select_get()
        try:
            obj.hide_set(False)
        except Exception:
            obj.hide_viewport = False
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        try:
            scene.cycles.bake_type = 'DIFFUSE'
        except Exception:
            pass

        # Output directory: ProcessTextures next to the .blend
        root = bpy.path.abspath("//") or os.getcwd()
        process_tex = os.path.join(root, "ProcessTextures")
        os.makedirs(process_tex, exist_ok=True)
        res = int(s.bake_resolution)

        def ensure_target_tex_node(mat):
            if not (mat and mat.use_nodes and mat.node_tree):
                return None, None
            nt = mat.node_tree
            node = nt.nodes.get("BaseColor") or nt.nodes.get("BaseColorOut") or nt.nodes.get("Delit")
            if not node:
                node = nt.nodes.new("ShaderNodeTexImage")
                node.name = "BaseColor"
                node.label = "BaseColor"
                node.location = (-800, 300)
            return nt, node

        baked_files = []
        if udim_mode and len(slots) > 0:
            # Per-slot bake
            for i, sl in enumerate(slots):
                mat = sl.material
                nt, tex_node = ensure_target_tex_node(mat)
                if not (nt and tex_node):
                    continue
                udim = _extract_udim(mat.name) if mat and getattr(mat, 'name', None) else '1001'
                # Compute UDIM tile offsets (1001 = (0,0), 1002 = (1,0), 1011 = (0,1), etc.)
                try:
                    udim_val = int(udim)
                    t = udim_val - 1001
                    u_off = t % 10
                    v_off = t // 10
                except Exception:
                    u_off = 0; v_off = 0
                img_name = f"{base_name}_BaseColor_{udim}"
                img = bpy.data.images.get(img_name)
                if img is None:
                    img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)
                else:
                    try:
                        if getattr(img, "size", None) and (img.size[0] != res or img.size[1] != res):
                            img.scale(res, res)
                    except Exception:
                        try:
                            bpy.data.images.remove(img)
                        except Exception:
                            pass
                        img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)
                try:
                    img.source = 'GENERATED'
                except Exception:
                    pass
                tex_node.image = img
                try:
                    tex_node.image.colorspace_settings.name = "sRGB"
                except Exception:
                    pass
                # Make material active to ensure correct node context
                obj.active_material_index = i
                nt.nodes.active = tex_node

                # Temporarily offset UVs for faces in this material slot that live in this UDIM tile
                me = obj.data
                uv_layer = me.uv_layers.active if hasattr(me, 'uv_layers') and me.uv_layers.active else None
                saved_uvs = []
                if uv_layer and me.polygons and me.loops:
                    # Ensure object mode for direct UV edits
                    try:
                        if obj.mode != 'OBJECT':
                            bpy.ops.object.mode_set(mode='OBJECT')
                    except Exception:
                        pass
                    try:
                        for poly in me.polygons:
                            if poly.material_index != i:
                                continue
                            for li in poly.loop_indices:
                                luv = uv_layer.data[li].uv
                                # Only offset loops that are in the UDIM tile
                                if int(math.floor(luv.x)) == u_off and int(math.floor(luv.y)) == v_off:
                                    saved_uvs.append((li, luv.x, luv.y))
                                    uv_layer.data[li].uv.x = luv.x - u_off
                                    uv_layer.data[li].uv.y = luv.y - v_off
                    except Exception:
                        saved_uvs = []

                # Bake
                try:
                    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='IMAGE_TEXTURES', use_clear=True)
                except Exception as e:
                    # Restore UVs on failure
                    try:
                        for li, ux, uy in saved_uvs:
                            uv_layer.data[li].uv.x = ux
                            uv_layer.data[li].uv.y = uy
                    except Exception:
                        pass
                    if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
                    if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
                    self.report({'ERROR'}, f"Bake failed (UDIM {udim}): {e}")
                    return {'CANCELLED'}

                # Restore UVs after bake
                try:
                    for li, ux, uy in saved_uvs:
                        uv_layer.data[li].uv.x = ux
                        uv_layer.data[li].uv.y = uy
                except Exception:
                    pass

                # Save per-UDIM image to ProcessTextures as TIFF
                outfile = os.path.join(process_tex, f"{base_name}_BaseColor_{udim}.tif")
                os.makedirs(os.path.dirname(outfile), exist_ok=True)
                img.filepath_raw = outfile
                img.file_format = 'TIFF'
                try:
                    img.save()
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to save BaseColor image ({udim}): {e}")
                baked_files.append(outfile)
            msg = ", ".join([os.path.basename(x) for x in baked_files]) if baked_files else "<none>"
            self.report({'INFO'}, f"BaseColor processed (UDIM): {msg}")
        else:
            # Single bake
            mat = obj.active_material or (obj.material_slots[0].material if obj.material_slots else None)
            if not mat or not mat.use_nodes or not mat.node_tree:
                self.report({'ERROR'}, "Optimized object's material is missing or has no nodes.")
                if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
                if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
                return {'CANCELLED'}
            nt = mat.node_tree
            tex_node = nt.nodes.get("BaseColor") or nt.nodes.get("BaseColorOut") or nt.nodes.get("Delit")
            if not tex_node:
                tex_node = nt.nodes.new("ShaderNodeTexImage")
                tex_node.name = "BaseColor"
                tex_node.label = "BaseColor"
                tex_node.location = (-800, 300)
            img_name = f"{base_name}_BaseColor"
            img = bpy.data.images.get(img_name)
            if img is None:
                img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)
            else:
                try:
                    if getattr(img, "size", None) and (img.size[0] != res or img.size[1] != res):
                        img.scale(res, res)
                except Exception:
                    try:
                        bpy.data.images.remove(img)
                    except Exception:
                        pass
                    img = bpy.data.images.new(img_name, width=res, height=res, alpha=True, float_buffer=False)
            try:
                img.source = 'GENERATED'
            except Exception:
                pass
            tex_node.image = img
            try:
                tex_node.image.colorspace_settings.name = "sRGB"
            except Exception:
                pass
            nt.nodes.active = tex_node
            try:
                bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, target='IMAGE_TEXTURES', use_clear=True)
            except Exception as e:
                if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
                if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
                self.report({'ERROR'}, f"Bake failed: {e}")
                return {'CANCELLED'}
            # Save single image to ProcessTextures as TIFF
            outfile = os.path.join(process_tex, f"{base_name}_BaseColor.tif")
            os.makedirs(os.path.dirname(outfile), exist_ok=True)
            img.filepath_raw = outfile
            img.file_format = 'TIFF'
            try:
                img.save()
            except Exception as e:
                self.report({'ERROR'}, f"Failed to save BaseColor image: {e}")
            self.report({'INFO'}, f"BaseColor processed → {outfile}")

        # restore visibility and denoise
        try:
            obj.select_set(prev_select)
            obj.hide_viewport = prev_hide
        except Exception:
            pass
        if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
        if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
        return {'FINISHED'}
        
CLASSES = (VIVID_LightRemovalSettings, VIVID_OT_bake_delit)

def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.vivid_light_removal = bpy.props.PointerProperty(type=VIVID_LightRemovalSettings)

def unregister():
    if hasattr(bpy.types.Scene, "vivid_light_removal"):
        del bpy.types.Scene.vivid_light_removal
    for c in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
