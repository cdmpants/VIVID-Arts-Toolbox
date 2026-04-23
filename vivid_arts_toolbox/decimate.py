"""Mesh decimation via meshoptimizer.

Supports multiple UV channels with per-channel quality weights and
mesh-boundary locking for photogrammetry LOD generation.

Requires: vivid_arts_toolbox/lib/meshoptimizer.dll
Build with: python build_meshopt.py <path_to_meshoptimizer_source>
"""

import ctypes
import numpy as np
from pathlib import Path

import bpy

MESHOPT_SIMPLIFY_LOCK_BORDER = 1 << 0

_lib = None


def _load_lib():
    """Load the meshoptimizer shared library."""
    global _lib
    if _lib is not None:
        return _lib

    dll_path = Path(__file__).parent / "lib" / "meshoptimizer.dll"
    if not dll_path.exists():
        raise RuntimeError(
            f"meshoptimizer.dll not found at {dll_path}.\n"
            "Run build_meshopt.py to compile it from meshoptimizer source."
        )

    _lib = ctypes.CDLL(str(dll_path))

    # meshopt_simplify — position-only decimation
    _lib.meshopt_simplify.restype = ctypes.c_size_t
    _lib.meshopt_simplify.argtypes = [
        ctypes.POINTER(ctypes.c_uint),   # destination
        ctypes.POINTER(ctypes.c_uint),   # indices
        ctypes.c_size_t,                 # index_count
        ctypes.POINTER(ctypes.c_float),  # vertex_positions
        ctypes.c_size_t,                 # vertex_count
        ctypes.c_size_t,                 # vertex_positions_stride
        ctypes.c_size_t,                 # target_index_count
        ctypes.c_float,                  # target_error
        ctypes.c_uint,                   # options
        ctypes.POINTER(ctypes.c_float),  # result_error (nullable)
    ]

    # meshopt_simplifyWithAttributes — attribute-aware decimation
    _lib.meshopt_simplifyWithAttributes.restype = ctypes.c_size_t
    _lib.meshopt_simplifyWithAttributes.argtypes = [
        ctypes.POINTER(ctypes.c_uint),   # destination
        ctypes.POINTER(ctypes.c_uint),   # indices
        ctypes.c_size_t,                 # index_count
        ctypes.POINTER(ctypes.c_float),  # vertex_positions
        ctypes.c_size_t,                 # vertex_count
        ctypes.c_size_t,                 # vertex_positions_stride
        ctypes.POINTER(ctypes.c_float),  # vertex_attributes
        ctypes.c_size_t,                 # vertex_attributes_stride
        ctypes.POINTER(ctypes.c_float),  # attribute_weights
        ctypes.c_size_t,                 # attribute_count
        ctypes.POINTER(ctypes.c_ubyte),  # vertex_lock (nullable)
        ctypes.c_size_t,                 # target_index_count
        ctypes.c_float,                  # target_error
        ctypes.c_uint,                   # options
        ctypes.POINTER(ctypes.c_float),  # result_error (nullable)
    ]

    return _lib


def _mesh_to_buffers(mesh, uv_names):
    """Extract indexed buffers from a Blender Mesh, splitting vertices at UV seams.

    Returns (positions, indices, attributes):
        positions:  (V, 3)  float32
        indices:    (T*3,)  uint32
        attributes: (V, A)  float32  where A = 2 * len(uv_names), or None
    """
    mesh.calc_loop_triangles()
    n_loops = len(mesh.loops)
    n_tris = len(mesh.loop_triangles)
    n_verts = len(mesh.vertices)

    if n_tris == 0:
        raise RuntimeError("Mesh has no geometry to decimate")

    # Vertex positions
    co = np.empty(n_verts * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)

    # Triangle loop / vertex indices
    tri_loops = np.empty(n_tris * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", tri_loops)
    tri_verts = np.empty(n_tris * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", tri_verts)

    if not uv_names:
        return co, tri_verts.astype(np.uint32), None

    # Per-loop vertex indices (for the entire mesh, not just triangles)
    loop_vi = np.empty(n_loops, dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_vi)

    # Read UV data per layer
    uv_arrays = []
    for name in uv_names:
        layer = mesh.uv_layers.get(name)
        if not layer:
            raise RuntimeError(f"UV layer '{name}' not found on mesh")
        buf = np.empty(n_loops * 2, dtype=np.float32)
        layer.data.foreach_get("uv", buf)
        uv_arrays.append(buf.reshape(-1, 2))

    # Build unique (vert_idx, quantised-UV…) keys for triangle loops
    parts = [loop_vi[tri_loops].reshape(-1, 1)]
    for uv in uv_arrays:
        parts.append(np.round(uv[tri_loops] * 1e5).astype(np.int64))
    keys = np.ascontiguousarray(np.hstack(parts))
    kv = keys.view(np.dtype((np.void, keys.dtype.itemsize * keys.shape[1]))).ravel()
    _, first, inv = np.unique(kv, return_index=True, return_inverse=True)
    inv = inv.ravel()

    # Split-vertex positions from original vert index in column 0
    split_pos = co[keys[first, 0].astype(np.int32)].copy()

    # Split-vertex UV attributes (actual float values from first occurrence)
    src_loops = tri_loops[first]
    split_attr = np.hstack([uv[src_loops] for uv in uv_arrays]).astype(np.float32)

    return split_pos, inv.astype(np.uint32), split_attr


def _buffers_to_mesh(positions, new_idx, attributes, uv_names, name):
    """Reconstruct a Blender Mesh from decimated buffers.

    Vertices that share the same world position are merged back into single
    Blender vertices; per-loop UVs are written from the split-vertex attributes.
    """
    # Identify surviving split-vertices
    used = np.unique(new_idx)
    used_pos = positions[used]

    # Merge split verts at the same position
    pq = np.ascontiguousarray(np.round(used_pos * 1e6).astype(np.int64))
    pv = pq.view(np.dtype((np.void, pq.dtype.itemsize * pq.shape[1]))).ravel()
    _, pf, pi = np.unique(pv, return_index=True, return_inverse=True)
    pi = pi.ravel()

    merged_pos = used_pos[pf]

    remap = np.full(len(positions), -1, dtype=np.int32)
    remap[used] = pi

    faces = remap[new_idx].reshape(-1, 3)

    new_mesh = bpy.data.meshes.new(name)
    new_mesh.from_pydata(merged_pos.tolist(), [], faces.tolist())
    new_mesh.update()

    # Write per-loop UVs
    if attributes is not None and uv_names:
        off = 0
        for uv_name in uv_names:
            layer = new_mesh.uv_layers.new(name=uv_name)
            loop_uv = attributes[new_idx, off:off + 2].flatten()
            layer.data.foreach_set("uv", loop_uv.tolist())
            off += 2
        new_mesh.update()

    new_mesh.validate(clean_customdata=False)
    return new_mesh


def decimate_to_new_object(source_obj, target_faces, new_name,
                           uv_weights=None, lock_boundary=True):
    """Create a decimated copy of a Blender mesh object using meshoptimizer.

    Args:
        source_obj:    Source bpy.types.Object (MESH type).
        target_faces:  Target triangle count.
        new_name:      Name for the new Object and Mesh datablock.
        uv_weights:    Dict {uv_layer_name: float_weight}.
                       None or {} for position-only decimation (fast, no UV awareness).
                       Higher weights = stricter UV preservation.
        lock_boundary: Lock open mesh boundary edges (never collapsed).

    Returns:
        New bpy.types.Object (not linked to any collection — caller must link it).
    """
    lib = _load_lib()

    if source_obj.type != 'MESH':
        raise RuntimeError(f"{source_obj.name} is not a mesh object")

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = source_obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()

    uv_names = list(uv_weights.keys()) if uv_weights else []
    positions, indices, attributes = _mesh_to_buffers(mesh, uv_names)
    eval_obj.to_mesh_clear()

    n_verts = len(positions)
    n_idx = len(indices)
    target_idx = max(3, int(target_faces) * 3)
    options = MESHOPT_SIMPLIFY_LOCK_BORDER if lock_boundary else 0

    dest = np.empty(n_idx, dtype=np.uint32)
    err = ctypes.c_float(0.0)

    if uv_weights and attributes is not None:
        n_attr = attributes.shape[1]
        weights = np.array(
            [uv_weights[n] for n in uv_names for _ in range(2)],
            dtype=np.float32,
        )
        out_n = lib.meshopt_simplifyWithAttributes(
            dest.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)),
            indices.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)),
            ctypes.c_size_t(n_idx),
            positions.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_size_t(n_verts),
            ctypes.c_size_t(12),  # 3 floats × 4 bytes
            attributes.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_size_t(n_attr * 4),
            weights.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_size_t(n_attr),
            None,  # vertex_lock — rely on LockBorder option
            ctypes.c_size_t(target_idx),
            ctypes.c_float(1e-1),
            ctypes.c_uint(options),
            ctypes.byref(err),
        )
    else:
        out_n = lib.meshopt_simplify(
            dest.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)),
            indices.ctypes.data_as(ctypes.POINTER(ctypes.c_uint)),
            ctypes.c_size_t(n_idx),
            positions.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_size_t(n_verts),
            ctypes.c_size_t(12),
            ctypes.c_size_t(target_idx),
            ctypes.c_float(1e-1),
            ctypes.c_uint(options),
            ctypes.byref(err),
        )

    new_indices = dest[:out_n]
    new_mesh = _buffers_to_mesh(positions, new_indices, attributes, uv_names, new_name)
    new_obj = bpy.data.objects.new(new_name, new_mesh)
    new_obj.matrix_world = source_obj.matrix_world.copy()

    return new_obj
