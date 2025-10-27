
import bpy, os, re, math
from bpy.types import Operator, PropertyGroup, Panel
from bpy.props import EnumProperty, PointerProperty, BoolProperty, FloatProperty

from ..bake_textures import _folders, _find_optimized_object
from ..bake_textures import _clean_dir
from ..bake_textures import _udim_tiles_from_object
from ..metadata import _release_mirror_dir

def _remove_suffix(name: str, suffix: str):
    return name[:-len(suffix)] if name.endswith(suffix) else name

def _delighter_update(self, context):
    """Property update callback: apply delighter slider values live to materials."""
    try:
        apply_delighter_to_materials(self)
    except Exception:
        pass


class VIVID_LightRemovalSettings(PropertyGroup):
    __annotations__ = {}
    __annotations__['engine'] = EnumProperty(
        name="Engine",
        description="Use CPU or GPU for Cycles",
        items=[("CPU","CPU",""),("GPU","GPU","")],
        default="GPU",
    )
    __annotations__['save_only_release'] = BoolProperty(
        name="Save only to Release",
        description="Only save outputs to the Release folder alongside exported FBXs and metadata",
        default=False,
    )
    __annotations__['sharpen'] = BoolProperty(
        name="Sharpen",
        description="Apply sharpen filter to result (placeholder)",
        default=False,
    )
    __annotations__['de_light_with_lightmap'] = BoolProperty(
        name="Delight with Lightmap",
        description="Use lightmap to assist de-lighting (placeholder)",
        default=False,
        update=_delighter_update,
    )
    # Delighter UI
    __annotations__['show_delighter_options'] = BoolProperty(
        name="Show Delighter Options",
        description="Reveal the DelighterGroup sliders",
        default=True,
    )
    __annotations__['divide_ao'] = FloatProperty(name="Divide AO", default=0.3, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['divide_r'] = FloatProperty(name="Divide R", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['divide_g'] = FloatProperty(name="Divide G", default=1.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['divide_b'] = FloatProperty(name="Divide B", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['invert_r'] = FloatProperty(name="Invert R", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['invert_g'] = FloatProperty(name="Invert G", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['invert_b'] = FloatProperty(name="Invert B", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    # Lightmap-specific sliders
    __annotations__['divide_lightmap'] = FloatProperty(name="Divide Lightmap", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['lightmap_brightness'] = FloatProperty(name="Lightmap Brightness", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    __annotations__['lightmap_contrast'] = FloatProperty(name="Lightmap Contrast", default=0.0, min=0.0, max=1.0, update=_delighter_update)
    # Tiling controls
    __annotations__['tile_x'] = BoolProperty(
        name="Tile X",
        description="Enable seamless tiling in X (exposes sliders)",
        default=False,
    )
    __annotations__['tile_x_threshold'] = FloatProperty(name="Threshold", default=0.5, min=0.0, max=1.0)
    __annotations__['tile_x_smoothness'] = FloatProperty(name="Smoothness", default=0.5, min=0.0, max=1.0)
    __annotations__['tile_x_contrast'] = FloatProperty(name="Contrast", default=0.5, min=0.0, max=1.0)
    __annotations__['tile_y'] = BoolProperty(
        name="Tile Y",
        description="Enable seamless tiling in Y (exposes sliders)",
        default=False,
    )
    __annotations__['tile_y_threshold'] = FloatProperty(name="Threshold", default=0.5, min=0.0, max=1.0)
    __annotations__['tile_y_smoothness'] = FloatProperty(name="Smoothness", default=0.5, min=0.0, max=1.0)
    __annotations__['tile_y_contrast'] = FloatProperty(name="Contrast", default=0.5, min=0.0, max=1.0)

class VIVID_OT_bake_delit(Operator):
    bl_idname = "vivid.bake_delit"
    bl_label = "Process Textures"
    bl_description = "Process textures (de-lighting pipeline). Outputs will be saved under ProcessTextures."

    def execute(self, context):
        s = getattr(context.scene, "vivid_light_removal", None)
        if not s:
            self.report({'ERROR'}, "Light Removal settings not found on scene.")
            return {'CANCELLED'}

        # Clean ProcessTextures and local bake logs/settings before processing
        try:
            root, bake_mesh, _ = _folders()
            process_dir = os.path.join(root, "ProcessTextures")
            _clean_dir(process_dir)
            _clean_dir(os.path.join(bake_mesh, "bake_log"))
            _clean_dir(os.path.join(bake_mesh, "bake_settings"))
        except Exception:
            pass

        # Apply Delighter sliders to materials on Optimized object (Part1 only)
        try:
            apply_delighter_to_materials(s)
        except Exception:
            pass

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

        # Output directory: ProcessTextures next to the .blend OR Release mirror
        root = bpy.path.abspath("//") or os.getcwd()
        if bool(getattr(s, 'save_only_release', False)):
            try:
                release_dir = _release_mirror_dir(context)
            except Exception:
                release_dir = os.path.join(root, 'Release')
            base_out_dir = release_dir
        else:
            base_out_dir = os.path.join(root, "ProcessTextures")
        os.makedirs(base_out_dir, exist_ok=True)
        # Use Designer bake resolution for texture processing to keep settings unified
        try:
            ds = getattr(context.scene, 'vivid_designer_bake', None)
            res = int(ds.bake_resolution) if ds and getattr(ds, 'bake_resolution', None) else 4096
        except Exception:
            res = 4096

        def ensure_target_tex_node(mat):
            if not (mat and mat.use_nodes and mat.node_tree):
                return None, None
            nt = mat.node_tree
            # If "Delight with Lightmap" is enabled, bake to Lightmap node; else use BaseColor
            if getattr(s, 'de_light_with_lightmap', False):
                node = nt.nodes.get("Lightmap")
                if not node:
                    node = nt.nodes.new("ShaderNodeTexImage")
                    node.name = "Lightmap"
                    node.label = "Lightmap"
                    node.location = (-800, 100)
            else:
                node = nt.nodes.get("BaseColor") or nt.nodes.get("BaseColorOut") or nt.nodes.get("Delit")
            if not node:
                node = nt.nodes.new("ShaderNodeTexImage")
                if getattr(s, 'de_light_with_lightmap', False):
                    node.name = "Lightmap"; node.label = "Lightmap"
                else:
                    node.name = "BaseColor"; node.label = "BaseColor"
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
                    # Name images based on target node to avoid confusion
                    bake_target = 'Lightmap' if getattr(s, 'de_light_with_lightmap', False) else 'BaseColor'
                    img_name = f"{base_name}_{bake_target}_{udim_num}"
                    if part_suffix:
                        img_name = f"{base_name}_{part_suffix}_{bake_target}_{udim_num}"
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
                        if getattr(s, 'de_light_with_lightmap', False):
                            # Bake only Direct + Indirect, no color for Lightmap target
                            bpy.ops.object.bake(type='DIFFUSE', pass_filter={'DIRECT','INDIRECT'}, target='IMAGE_TEXTURES', use_clear=True)
                        else:
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
                    # Lightmap bake does not need saving externally according to requirements
                    if getattr(s, 'de_light_with_lightmap', False):
                        # Skip saving to disk for Lightmap target
                        baked.append(f"<baked:Lightmap:{udim_str}>")
                        continue
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
        baked_files.extend(bake_for_material(obj.active_material or (obj.material_slots[0].material if obj.material_slots else None), base_out_dir))

        # Alternate materials: base_name_Part# created by baking procedure
        import re
        alt_mats = []
        pat = re.compile(rf"^{re.escape(base_name)}_Part\d+$")
        for m in bpy.data.materials:
            if pat.match(m.name):
                alt_mats.append(m)
        for m in sorted(alt_mats, key=lambda x: x.name):
            part_token = m.name.split('_')[-1]  # PartX
            out_dir = os.path.join(base_out_dir, part_token)
            os.makedirs(out_dir, exist_ok=True)
            try:
                baked_files.extend(bake_for_material(m, out_dir, part_suffix=part_token))
            except Exception as e:
                self.report({'ERROR'}, f"Bake failed for {m.name}: {e}")
                if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
                if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
                return {'CANCELLED'}
        msg = ", ".join([os.path.basename(x) for x in baked_files]) if baked_files else "<none>"
        self.report({'INFO'}, f"Processed: {msg}")

        # restore visibility and denoise
        try:
            obj.select_set(prev_select)
            obj.hide_viewport = prev_hide
        except Exception:
            pass
        if prev_scene_denoise is not None: scene.cycles.use_denoising = prev_scene_denoise
        if prev_layer_denoise is not None: context.view_layer.cycles.use_denoising = prev_layer_denoise
        return {'FINISHED'}


def apply_delighter_to_materials(s):
    """Apply UI slider values to the DelighterGroup of eligible materials.
    Eligible = assigned materials on the Optimized object whose names are either:
      - <Object>_<UDIM>
      - <Object>_Part1_<UDIM> (include Part1)
      - Any material without a _Part# segment
    Exclude Part2 and above.
    """
    import re
    obj = _find_optimized_object()
    if not obj or obj.type != 'MESH':
        return
    mats = [sl.material for sl in obj.material_slots if sl.material]
    part_pat = re.compile(r"_Part(\d+)(?:_|$)")
    for m in mats:
        try:
            # Determine part index if present
            part_idx = None
            mt = part_pat.search(m.name)
            if mt:
                try:
                    part_idx = int(mt.group(1))
                except Exception:
                    part_idx = None
            # Skip Part >= 2; include None and Part1
            if part_idx is not None and part_idx >= 2:
                continue
            if not (m.use_nodes and m.node_tree):
                continue
            nt = m.node_tree
            # Find a group node named DelighterGroup
            target = None
            for n in nt.nodes:
                if getattr(n, 'type', '') == 'GROUP' and (n.name == 'DelighterGroup' or (getattr(n, 'node_tree', None) and getattr(n.node_tree, 'name', '') == 'DelighterGroup')):
                    target = n
                    break
            if not target:
                continue
            def set_input(name, val):
                try:
                    sock = target.inputs.get(name)
                    if sock is not None and hasattr(sock, 'default_value'):
                        sock.default_value = float(val)
                except Exception:
                    pass
            set_input('Divide AO', getattr(s, 'divide_ao', 0.3))
            set_input('Divide R', getattr(s, 'divide_r', 0.0))
            set_input('Divide G', getattr(s, 'divide_g', 1.0))
            set_input('Divide B', getattr(s, 'divide_b', 0.0))
            set_input('Invert R', getattr(s, 'invert_r', 0.0))
            set_input('Invert G', getattr(s, 'invert_g', 0.0))
            set_input('Invert B', getattr(s, 'invert_b', 0.0))
            if getattr(s, 'de_light_with_lightmap', False):
                set_input('Divide Lightmap', getattr(s, 'divide_lightmap', 0.0))
                set_input('Lightmap Brightness', getattr(s, 'lightmap_brightness', 0.0))
                set_input('Lightmap Contrast', getattr(s, 'lightmap_contrast', 0.0))
        except Exception:
            pass
        
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
