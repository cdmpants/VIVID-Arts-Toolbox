import math
import re

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from ..decimate import decimate_to_new_object


def _build_bvh_from_evaluated(obj: bpy.types.Object):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    bm = bmesh.new()
    try:
        bm.from_mesh(eval_mesh)
        bm.normal_update()
        return BVHTree.FromBMesh(bm)
    finally:
        bm.free()
        eval_obj.to_mesh_clear()


def _boundary_vert_indices(mesh: bpy.types.Mesh):
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        return {vert.index for vert in bm.verts if any(len(edge.link_faces) < 2 for edge in vert.link_edges)}
    finally:
        bm.free()


def _source_boundary_samples_world(obj: bpy.types.Object, spacing: float):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        samples = []
        matrix_world = obj.matrix_world
        step = max(spacing * 0.5, 1e-4)
        for edge in bm.edges:
            if len(edge.link_faces) >= 2:
                continue
            start = matrix_world @ edge.verts[0].co
            end = matrix_world @ edge.verts[1].co
            length = (end - start).length
            segments = max(1, int(math.ceil(length / step)))
            for index in range(segments + 1):
                factor = index / segments
                samples.append(start.lerp(end, factor))
        return samples
    finally:
        bm.free()


def _world_bounds(obj: bpy.types.Object):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = Vector((
        min(corner.x for corner in corners),
        min(corner.y for corner in corners),
        min(corner.z for corner in corners),
    ))
    maxs = Vector((
        max(corner.x for corner in corners),
        max(corner.y for corner in corners),
        max(corner.z for corner in corners),
    ))
    return mins, maxs


def _axis_samples(min_value: float, max_value: float, spacing: float):
    span = max_value - min_value
    if span <= 0.0:
        return [min_value]

    steps = max(1, int(math.ceil(span / spacing)))
    values = [min_value + min(index * spacing, span) for index in range(steps + 1)]
    if abs(values[-1] - max_value) > 1e-6:
        values.append(max_value)
    return values


def _base_cinema_source(context):
    active = context.active_object
    if active and active.type == 'MESH' and (active.name.endswith('_Cinema') or active.name == 'Cinema'):
        return active

    cinema = bpy.data.collections.get('Cinema')
    if cinema:
        for obj in cinema.objects:
            if obj.type == 'MESH' and (obj.name.endswith('_Cinema') or obj.name == 'Cinema'):
                return obj
    return None


def _base_label(src: bpy.types.Object) -> str:
    match = re.match(r'(.+)_Cinema$', src.name)
    if match:
        return match.group(1)
    if src.name == 'Cinema':
        return 'Cinema'
    raise RuntimeError(f"Unexpected Cinema name format: {src.name}")


class VIVID_OT_generate_locomotion(bpy.types.Operator):
    bl_idname = "vivid.generate_locomotion"
    bl_label = "Generate Locomotion"
    bl_description = "Generate a locomotion collider from Cinema into the Locomotion collection."
    bl_options = {'REGISTER', 'UNDO'}

    confirm_overwrite: bpy.props.BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def _source(self, context) -> bpy.types.Object:
        src = _base_cinema_source(context)
        if not src:
            raise RuntimeError("No Cinema source found. Select the Cinema mesh or create a Cinema collection first.")
        return src

    def _target_name(self, src: bpy.types.Object) -> str:
        return f"{_base_label(src)}_Locomotion"

    def _ensure_collection(self, context) -> bpy.types.Collection:
        collection = bpy.data.collections.get('Locomotion')
        if not collection:
            collection = bpy.data.collections.new('Locomotion')
            context.scene.collection.children.link(collection)
        return collection

    def _find_existing_target(self, context, src: bpy.types.Object):
        collection = bpy.data.collections.get('Locomotion')
        if not collection:
            return None
        return collection.objects.get(self._target_name(src))

    def _delete_target(self, obj: bpy.types.Object):
        if not obj:
            return
        for collection in list(getattr(obj, 'users_collection', []) or []):
            try:
                collection.objects.unlink(obj)
            except Exception:
                pass
        bpy.data.objects.remove(obj, do_unlink=True)

    def _collect_seed_uv_weights(self, src: bpy.types.Object, props):
        weights = {}
        src_uvs = src.data.uv_layers
        if src_uvs:
            if len(src_uvs) >= 1:
                weights[src_uvs[0].name] = float(getattr(props, 'uv1_decimation_weight', 1.0) or 1.0)
            if len(src_uvs) >= 2:
                weights[src_uvs[1].name] = float(getattr(props, 'uv2_decimation_weight', 0.5) or 0.5)
        return weights

    def _conform_boundary_to_source(self, obj: bpy.types.Object, source_obj: bpy.types.Object, spacing: float):
        samples = _source_boundary_samples_world(source_obj, spacing)
        if not samples:
            return obj

        kd = KDTree(len(samples))
        for index, sample in enumerate(samples):
            kd.insert(Vector((sample.x, sample.y, 0.0)), index)
        kd.balance()

        boundary_verts = _boundary_vert_indices(obj.data)
        if not boundary_verts:
            return obj

        matrix_world = obj.matrix_world.copy()
        matrix_world_inv = matrix_world.inverted()
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            for vert_index in boundary_verts:
                vert = bm.verts[vert_index]
                world_co = matrix_world @ vert.co
                _, sample_index, _ = kd.find(Vector((world_co.x, world_co.y, 0.0)))
                sample = samples[sample_index]
                vert.co = matrix_world_inv @ sample
            bm.to_mesh(obj.data)
            obj.data.update()
            return obj
        finally:
            bm.free()

    def _apply_seed_smoothing(self, obj: bpy.types.Object, props, preserve_open_edges: bool):
        iterations = int(getattr(props, 'locomotion_smooth_iterations', 0) or 0)
        factor = float(getattr(props, 'locomotion_smooth_factor', 0.0) or 0.0)
        if iterations <= 0 or factor <= 0.0:
            return obj

        boundary_verts = _boundary_vert_indices(obj.data) if preserve_open_edges else set()
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            for _ in range(iterations):
                verts = [vert for vert in bm.verts if vert.index not in boundary_verts]
                if not verts:
                    break
                bmesh.ops.smooth_vert(
                    bm,
                    verts=verts,
                    factor=factor,
                    use_axis_x=True,
                    use_axis_y=True,
                    use_axis_z=True,
                )
            bm.to_mesh(obj.data)
            obj.data.update()
            return obj
        finally:
            bm.free()

    def _build_projected_mesh(self, src: bpy.types.Object, target_name: str, props):
        spacing = float(getattr(props, 'locomotion_voxel_size', 0.1) or 0.1)
        spacing = max(0.001, spacing)

        bvh = _build_bvh_from_evaluated(src)
        mins, maxs = _world_bounds(src)
        x_values = _axis_samples(mins.x, maxs.x, spacing)
        y_values = _axis_samples(mins.y, maxs.y, spacing)
        ray_start_z = maxs.z + max(spacing, 0.1)
        ray_distance = (maxs.z - mins.z) + max(spacing, 0.1) * 2.0
        local_from_world = src.matrix_world.inverted()

        bm = bmesh.new()
        try:
            verts = {}
            for y_index, y_value in enumerate(y_values):
                for x_index, x_value in enumerate(x_values):
                    origin = Vector((x_value, y_value, ray_start_z))
                    hit, _, _, _ = bvh.ray_cast(origin, Vector((0.0, 0.0, -1.0)), ray_distance)
                    if hit is None:
                        continue
                    verts[(x_index, y_index)] = bm.verts.new(local_from_world @ hit)

            bm.verts.ensure_lookup_table()
            face_count = 0
            for y_index in range(len(y_values) - 1):
                for x_index in range(len(x_values) - 1):
                    quad = [
                        verts.get((x_index, y_index)),
                        verts.get((x_index + 1, y_index)),
                        verts.get((x_index + 1, y_index + 1)),
                        verts.get((x_index, y_index + 1)),
                    ]
                    if any(vert is None for vert in quad):
                        continue
                    try:
                        bm.faces.new(quad)
                        face_count += 1
                    except ValueError:
                        pass

            if face_count == 0:
                raise RuntimeError("Top-down projection produced no locomotion faces. Try a smaller Sample Spacing.")

            mesh = bpy.data.meshes.new(target_name)
            bm.to_mesh(mesh)
            mesh.update()
            obj = bpy.data.objects.new(target_name, mesh)
            obj.matrix_world = src.matrix_world.copy()
            return obj
        finally:
            bm.free()

    def _apply_final_decimation(self, obj: bpy.types.Object, props, preserve_open_edges: bool):
        ratio = float(getattr(props, 'locomotion_ratio', 1.0) or 1.0)
        if ratio >= 1.0:
            return obj

        source_faces = len(obj.data.polygons)
        target_faces = max(8, int(source_faces * ratio))
        if target_faces >= source_faces:
            return obj

        reduced = decimate_to_new_object(
            obj,
            target_faces,
            obj.name,
            uv_weights=None,
            lock_boundary=preserve_open_edges,
        )
        bpy.data.objects.remove(obj, do_unlink=True)
        return reduced

    def _build_locomotion_mesh(self, context, src: bpy.types.Object, target_name: str, props) -> bpy.types.Object:
        preserve_open_edges = bool(getattr(props, 'locomotion_preserve_open_edges', True))
        spacing = float(getattr(props, 'locomotion_voxel_size', 0.1) or 0.1)
        locomotion = self._build_projected_mesh(src, target_name, props)
        context.scene.collection.objects.link(locomotion)
        if preserve_open_edges:
            self._conform_boundary_to_source(locomotion, src, spacing)
        locomotion = self._apply_seed_smoothing(locomotion, props, preserve_open_edges)
        if not preserve_open_edges:
            self._conform_boundary_to_source(locomotion, src, spacing)
        locomotion = self._apply_final_decimation(locomotion, props, preserve_open_edges)
        context.scene.collection.objects.link(locomotion)
        if preserve_open_edges:
            self._conform_boundary_to_source(locomotion, src, spacing)
        locomotion.name = target_name
        try:
            locomotion.data.name = target_name
            locomotion.data.materials.clear()
        except Exception:
            pass
        locomotion.display_type = 'TEXTURED'
        for polygon in locomotion.data.polygons:
            polygon.use_smooth = True
        locomotion.data.update()
        return locomotion

    def invoke(self, context, event):
        try:
            src = self._source(context)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        self.confirm_overwrite = bool(self._find_existing_target(context, src))
        if self.confirm_overwrite:
            return context.window_manager.invoke_props_dialog(self, width=420)
        return self.execute(context)

    def draw(self, context):
        if not self.confirm_overwrite:
            return
        layout = self.layout
        layout.label(text="Existing Locomotion mesh will be overwritten.", icon='ERROR')
        layout.label(text="Manual edits on the current locomotion mesh will be lost.")

    def execute(self, context):
        try:
            src = self._source(context)
            props = getattr(context.scene, 'vivid_lod_props', None)
            if not props:
                raise RuntimeError("Scene LOD properties are not available.")

            target_name = self._target_name(src)
            collection = self._ensure_collection(context)
            existing = collection.objects.get(target_name)
            if existing:
                self._delete_target(existing)

            locomotion = self._build_locomotion_mesh(context, src, target_name, props)
            try:
                collection.objects.link(locomotion)
            except Exception:
                pass
            for owner in list(getattr(locomotion, 'users_collection', []) or []):
                if owner is not collection:
                    try:
                        owner.objects.unlink(locomotion)
                    except Exception:
                        pass
            self.report({'INFO'}, f"Generated {locomotion.name} ({len(locomotion.data.polygons)} faces)")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}