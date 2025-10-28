import bpy, os, re
from bpy.types import Operator
from pathlib import Path

from ..metadata import _release_mirror_dir

class VIVID_OT_merge_udims(Operator):
    bl_idname = "vivid.merge_udims"
    bl_label = "Merge UDIM Tiles"
    bl_description = "Merge baked UDIM tiles per LOD into a single square texture per map identifier (deletes tiles)."

    def execute(self, context):
        # Resolve Release/Game/Textures directory (which contains LOD# subfolders)
        try:
            release_dir = _release_mirror_dir(context)
        except Exception:
            blend_path = bpy.data.filepath
            if not blend_path:
                self.report({'ERROR'}, "Save your .blend file first.")
                return {'CANCELLED'}
            blend_dir = os.path.dirname(blend_path)
            release_dir = os.path.join(os.path.dirname(blend_dir), 'Release', os.path.basename(blend_dir))
        textures_root = os.path.join(release_dir, 'Game', 'Textures')
        lod_root = textures_root
        if not os.path.isdir(lod_root):
            self.report({'ERROR'}, f"Missing LOD textures directory: {lod_root}")
            return {'CANCELLED'}

        # For each LOD# subfolder under Game/Textures, merge tiles
        print(f"[UDIM-MERGE] Root: {lod_root}")
        merged_any = False
        for sub in sorted(os.listdir(lod_root)):
            subdir = os.path.join(lod_root, sub)
            if not os.path.isdir(subdir):
                continue
            if not sub.lower().startswith('lod'):
                continue
            print(f"[UDIM-MERGE] Processing LOD folder: {subdir}")
            try:
                _merge_udims_for_lod(subdir)
                merged_any = True
            except Exception as e:
                self.report({'WARNING'}, f"UDIM merge failed in {sub}: {e}")
        if not merged_any:
            self.report({'INFO'}, "No UDIM tiles found to merge.")
        else:
            self.report({'INFO'}, f"UDIM merge complete under {lod_root}")
        return {'FINISHED'}


def _merge_udims_for_lod(lod_out_dir: str):
    """Merge UDIM tiles per baker identifier inside a LOD's output directory.
    Expects files named like: <prefix>_UDIM_<identifier>.<ext>
    Produces merged files named: <prefix>_Merged_<identifier>.<ext> (prefix inferred from first match).
    Deletes the original UDIM files after merge.
    """
    from collections import defaultdict
    p = Path(lod_out_dir)
    if not p.exists():
        return
    groups = defaultdict(list)  # ident -> [(udim, path, ext, prefix)]
    rx = re.compile(r"^(?P<prefix>.+)_(?P<udim>\d{4})_(?P<ident>[^.]+)\.(?P<ext>png|tif|tiff|exr|jpg|jpeg)$", re.IGNORECASE)
    udims_set = set()
    for f in p.iterdir():
        if not f.is_file():
            continue
        m = rx.match(f.name)
        if not m:
            continue
        ud = int(m.group('udim'))
        ident = m.group('ident')
        groups[ident].append((ud, str(f), m.group('ext').lower(), m.group('prefix')))
        udims_set.add(ud)
    if not groups:
        print(f"[UDIM-MERGE] No matching UDIM tiles in: {lod_out_dir}")
        return
    import math
    grid_n = int(math.ceil(math.sqrt(max(1, len(udims_set)))))
    print(f"[UDIM-MERGE] LOD dir: {lod_out_dir}")
    print(f"[UDIM-MERGE] UDIMs: {sorted(udims_set)}  grid_n: {grid_n}")
    print(f"[UDIM-MERGE] Map identifiers: {list(groups.keys())}")
    for ident, entries in groups.items():
        entries.sort(key=lambda t: t[0])
        if not entries:
            continue
        ext = entries[0][2]
        # Determine prefix from UDIM tile filenames (derived from textures)
        prefixes = [pref for (_, _, _, pref) in entries]
        # Prefer unanimous prefix; else most frequent
        prefix = prefixes[0]
        try:
            if not all(p == prefix for p in prefixes):
                from collections import Counter
                prefix = Counter(prefixes).most_common(1)[0][0]
        except Exception:
            pass
        # Load first image to get tile size
        first_img = bpy.data.images.load(entries[0][1])
        tile_w, tile_h = first_img.size
        print(f"[UDIM-MERGE] Map: {ident}  tiles: {len(entries)}  ext: {ext}")
        print(f"[UDIM-MERGE] Prefix: {prefix}")
        print(f"[UDIM-MERGE] Tile size: {tile_w}x{tile_h}  Output size: {grid_n*tile_w}x{grid_n*tile_h}")
        # Naming derived from UDIM textures: <BaseName>_LOD#_<TextureType>
        out_name = f"{prefix}_{ident}.{ext}"
        out_path = str(p / out_name)
        _compose_images_grid([(ud, path) for (ud, path, _, _) in entries], grid_n, tile_w, tile_h, out_path, ext)
        try:
            bpy.data.images.remove(first_img)
        except Exception:
            pass
        # Delete original tiles
        for _, path, _, _ in entries:
            try:
                os.remove(path)
            except Exception:
                pass


def _compose_images_grid(udim_path_pairs, grid_n, tile_w, tile_h, out_path, ext):
    """Build the atlas via a temporary orthographic render (GPU), not the compositor,
    enforcing neutral color management and Non-Color sampling to avoid color transforms.
    udim_path_pairs: list of (udim, path) sorted by UDIM ascending.
    """
    import math
    from mathutils import Vector
    # Create temp scene
    scene = bpy.data.scenes.new("VIVID_ATLAS_UDIM")
    scene.render.resolution_x = grid_n * int(tile_w)
    scene.render.resolution_y = grid_n * int(tile_h)
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
    except Exception:
        pass
    fmt_map = {'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG', 'tif': 'TIFF', 'tiff': 'TIFF', 'exr': 'OPEN_EXR'}
    scene.render.image_settings.file_format = fmt_map.get(ext.lower(), 'PNG')
    # Set sensible color depths
    try:
        if ext.lower() in ('tif','tiff'):
            scene.render.image_settings.color_depth = '16'
        elif ext.lower() in ('png',):
            scene.render.image_settings.color_depth = '8'
    except Exception:
        pass

    # Camera: orthographic framing [0..grid_n] x [0..grid_n]
    cam_data = bpy.data.cameras.new("VIVID_ATLAS_CAM")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = float(grid_n)
    cam = bpy.data.objects.new("VIVID_ATLAS_CAM", cam_data)
    cam.location = (grid_n/2.0, grid_n/2.0, 10.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    mats_to_remove = []
    imgs_to_remove = []
    objs_to_remove = []

    def make_plane_with_image(img_path: str, x: float, y: float):
        # Load image
        try:
            img = bpy.data.images.load(img_path)
            imgs_to_remove.append(img)
        except Exception:
            return None
        # Ensure image is treated as data to avoid color conversion
        try:
            img.colorspace_settings.name = 'Non-Color'
        except Exception:
            pass
        # Material with Emission -> Output
        mat = bpy.data.materials.new(name="VIVID_ATLAS_TILE")
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        n_img = nt.nodes.new('ShaderNodeTexImage')
        n_img.image = img
        try:
            n_img.image.colorspace_settings.name = 'Non-Color'
            n_img.interpolation = 'Closest'
        except Exception:
            pass
        n_em  = nt.nodes.new('ShaderNodeEmission')
        n_out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(n_img.outputs['Color'], n_em.inputs['Color'])
        nt.links.new(n_em.outputs['Emission'], n_out.inputs['Surface'])
        mats_to_remove.append(mat)

        # Create a unit plane centered at origin with UVs
        me = bpy.data.meshes.new("VIVID_ATLAS_TILE")
        verts = [(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)]
        faces = [(0,1,2,3)]
        me.from_pydata(verts, [], faces)
        me.update()
        # UVs
        uv = me.uv_layers.new(name="UVMap")
        loops = uv.data
        loops[0].uv = (0.0, 0.0)
        loops[1].uv = (1.0, 0.0)
        loops[2].uv = (1.0, 1.0)
        loops[3].uv = (0.0, 1.0)
        ob = bpy.data.objects.new("VIVID_ATLAS_TILE", me)
        ob.location = (x, y, 0.0)
        # Scale plane to 1x1 cell
        ob.scale = (1.0, 1.0, 1.0)
        scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        objs_to_remove.append(ob)
        return ob

    # Create a plane per tile in cell center at (col+0.5, row+0.5)
    for idx, (ud, path) in enumerate(udim_path_pairs):
        row = idx // grid_n
        col = idx % grid_n
        cx = col + 0.5
        cy = row + 0.5
        make_plane_with_image(path, cx, cy)

    # Render
    orig_scene = bpy.context.scene
    try:
        scene.render.filepath = out_path
        try:
            bpy.context.window.scene = scene
        except Exception:
            pass
        bpy.ops.render.render(write_still=True)
    finally:
        # Restore previous scene
        try:
            bpy.context.window.scene = orig_scene
        except Exception:
            pass
        # Cleanup temporary objects/materials/images and the scene
        try:
            for ob in objs_to_remove:
                try:
                    bpy.data.meshes.remove(ob.data)
                except Exception:
                    pass
                try:
                    bpy.data.objects.remove(ob)
                except Exception:
                    pass
            for mat in mats_to_remove:
                try:
                    bpy.data.materials.remove(mat)
                except Exception:
                    pass
            for im in imgs_to_remove:
                try:
                    bpy.data.images.remove(im)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            bpy.data.scenes.remove(scene)
        except Exception:
            pass


def register():
    bpy.utils.register_class(VIVID_OT_merge_udims)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_merge_udims)
