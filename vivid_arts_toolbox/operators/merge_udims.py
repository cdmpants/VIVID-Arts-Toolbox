import bpy, os, re
from bpy.types import Operator
from pathlib import Path

from ..metadata import _release_mirror_dir

class VIVID_OT_merge_udims(Operator):
    bl_idname = "vivid.merge_udims"
    bl_label = "Merge UDIM Tiles"
    bl_description = "Merge baked UDIM tiles per LOD into a single square texture per map identifier (deletes tiles)."

    def execute(self, context):
        # Resolve Release/Textures/LOD directory
        try:
            release_dir = _release_mirror_dir(context)
        except Exception:
            blend_path = bpy.data.filepath
            if not blend_path:
                self.report({'ERROR'}, "Save your .blend file first.")
                return {'CANCELLED'}
            blend_dir = os.path.dirname(blend_path)
            release_dir = os.path.join(os.path.dirname(blend_dir), 'Release', os.path.basename(blend_dir))
        textures_root = os.path.join(release_dir, 'Textures')
        lod_root = os.path.join(textures_root, 'LOD')
        if not os.path.isdir(lod_root):
            self.report({'ERROR'}, f"Missing LOD textures directory: {lod_root}")
            return {'CANCELLED'}

        # For each LOD subfolder under Textures/LOD, merge tiles
        merged_any = False
        for sub in sorted(os.listdir(lod_root)):
            subdir = os.path.join(lod_root, sub)
            if not os.path.isdir(subdir):
                continue
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
        return
    import math
    grid_n = int(math.ceil(math.sqrt(max(1, len(udims_set)))))
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
    """Composite images into a grid using Blender's Compositor.
    udim_path_pairs: list of (udim, path) sorted by UDIM ascending.
    """
    # Create temp scene
    scene = bpy.data.scenes.new("VIVID_MERGE_UDIM")
    scene.use_nodes = True
    nt = scene.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    comp = nt.nodes.new('CompositorNodeComposite')
    comp.location = (600, 0)
    last = None
    # Set render size
    scene.render.resolution_x = grid_n * int(tile_w)
    scene.render.resolution_y = grid_n * int(tile_h)
    scene.render.resolution_percentage = 100
    # Determine file format
    fmt_map = {
        'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG', 'tif': 'TIFF', 'tiff': 'TIFF', 'exr': 'OPEN_EXR'
    }
    scene.render.image_settings.file_format = fmt_map.get(ext.lower(), 'PNG')
    # Ensure neutral view transform
    try:
        scene.view_settings.view_transform = 'Standard'
    except Exception:
        pass
    # Build nodes per tile
    for idx, (ud, path) in enumerate(udim_path_pairs):
        row = idx // grid_n
        col = idx % grid_n
        img = nt.nodes.new('CompositorNodeImage')
        try:
            img.image = bpy.data.images.load(path)
        except Exception:
            continue
        img.location = (-800, -200 * idx)
        sc = nt.nodes.new('CompositorNodeScale')
        sc.space = 'RELATIVE'
        sc.inputs['X'].default_value = 1.0 / grid_n
        sc.inputs['Y'].default_value = 1.0 / grid_n
        sc.location = (-400, -200 * idx)
        tr = nt.nodes.new('CompositorNodeTranslate')
        tr.location = (0, -200 * idx)
        tr.inputs['X'].default_value = col * tile_w
        tr.inputs['Y'].default_value = row * tile_h
        nt.links.new(img.outputs['Image'], sc.inputs['Image'])
        nt.links.new(sc.outputs['Image'], tr.inputs['Image'])
        if last is None:
            last = tr
        else:
            ao = nt.nodes.new('CompositorNodeAlphaOver')
            ao.location = (300, -200 * idx)
            nt.links.new(last.outputs['Image'], ao.inputs[1])
            nt.links.new(tr.outputs['Image'], ao.inputs[2])
            last = ao
    if last is None:
        bpy.data.scenes.remove(scene)
        return
    nt.links.new(last.outputs['Image'], comp.inputs['Image'])
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
        try:
            bpy.context.window.scene = orig_scene
        except Exception:
            pass
        try:
            for n in list(scene.node_tree.nodes):
                if n.bl_idname == 'CompositorNodeImage' and n.image:
                    try:
                        bpy.data.images.remove(n.image)
                    except Exception:
                        pass
        except Exception:
            pass
        bpy.data.scenes.remove(scene)


def register():
    bpy.utils.register_class(VIVID_OT_merge_udims)


def unregister():
    bpy.utils.unregister_class(VIVID_OT_merge_udims)
