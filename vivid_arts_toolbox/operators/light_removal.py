
import bpy, os, re, math
from bpy.types import Operator, PropertyGroup, Panel
from bpy.props import EnumProperty, PointerProperty, BoolProperty

from ..bake_textures import _folders, _find_baked_textures_ex, _remove_suffix, _find_optimized_object, _find_baked_textures_by_suffix_udim
from ..bake_textures import _udim_tiles_from_object

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

        # Helper retained only if needed later
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

        # Detect UDIM tiles from geometry instead of material names
        # Returns list of (u,v) offsets
        uv_tiles = []
        try:
            uv_tiles = _udim_tiles_from_object(obj)
        except Exception:
            uv_tiles = []
        udim_mode = len(uv_tiles) > 1 or (len(uv_tiles) == 1 and uv_tiles[0] != (0, 0))

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
        def bake_for_material(target_material: bpy.types.Material, out_dir: str, part_suffix: str = None):
            # Assign material to all slots temporarily
            original_mats = [sl.material for sl in obj.material_slots]
            try:
                if len(obj.material_slots) == 0:
                    obj.data.materials.append(target_material)
                else:
                    for i in range(len(obj.material_slots)):
                        obj.material_slots[i].material = target_material
                # Prepare image node on active material
                nt, tex_node = ensure_target_tex_node(target_material)
                if not (nt and tex_node):
                    return []
                baked = []
                # Determine tiles to bake
                tiles = uv_tiles if udim_mode else [(0,0)]
                me = obj.data
                uv_layer = me.uv_layers.active if hasattr(me, 'uv_layers') and me.uv_layers.active else None
                for (u_off, v_off) in tiles:
                    udim_num = 1001 + u_off + v_off*10
                    img_name = f"{base_name}_BaseColor_{udim_num}"
                    if part_suffix:
                        img_name = f"{base_name}_{part_suffix}_BaseColor_{udim_num}"
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

                    # Offset UVs for faces in this tile
                    saved_uvs = []
                    if uv_layer and me.polygons and me.loops:
                        try:
                            if obj.mode != 'OBJECT':
                                bpy.ops.object.mode_set(mode='OBJECT')
                        except Exception:
                            pass
                        try:
                            for poly in me.polygons:
                                for li in poly.loop_indices:
                                    luv = uv_layer.data[li].uv
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
                        try:
                            for li, ux, uy in saved_uvs:
                                uv_layer.data[li].uv.x = ux
                                uv_layer.data[li].uv.y = uy
                        except Exception:
                            pass
                        raise e
                    # Restore UVs
                    try:
                        for li, ux, uy in saved_uvs:
                            uv_layer.data[li].uv.x = ux
                            uv_layer.data[li].uv.y = uy
                    except Exception:
                        pass
                    # Save
                    udim_str = f"{udim_num}"
                    outfile = os.path.join(out_dir, f"{base_name}_BaseColor_{udim_str}.tif") if not part_suffix else os.path.join(out_dir, f"{base_name}_{part_suffix}_BaseColor_{udim_str}.tif")
                    os.makedirs(os.path.dirname(outfile), exist_ok=True)
                    img.filepath_raw = outfile
                    img.file_format = 'TIFF'
                    try:
                        img.save()
                    except Exception as e:
                        self.report({'ERROR'}, f"Failed to save BaseColor image ({udim_str}): {e}")
                    baked.append(outfile)
                return baked
            finally:
                # restore materials
                try:
                    if original_mats:
                        for i in range(min(len(obj.material_slots), len(original_mats))):
                            obj.material_slots[i].material = original_mats[i]
                except Exception:
                    pass

        # Main material on object
        baked_files.extend(bake_for_material(obj.active_material or (obj.material_slots[0].material if obj.material_slots else None), process_tex))

        # Alternate materials: base_name_Part# created by baking procedure
        import re
        alt_mats = []
        pat = re.compile(rf"^{re.escape(base_name)}_Part\d+$")
        for m in bpy.data.materials:
            if pat.match(m.name):
                alt_mats.append(m)
        for m in sorted(alt_mats, key=lambda x: x.name):
            part_token = m.name.split('_')[-1]  # PartX
            out_dir = os.path.join(process_tex, part_token)
            os.makedirs(out_dir, exist_ok=True)
            try:
                baked_files.extend(bake_for_material(m, out_dir, part_suffix=part_token))
            except Exception as e:
                self.report({'ERROR'}, f"Bake failed for {m.name}: {e}")
                if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
                if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
                return {'CANCELLED'}
        msg = ", ".join([os.path.basename(x) for x in baked_files]) if baked_files else "<none>"
        self.report({'INFO'}, f"BaseColor processed: {msg}")

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
