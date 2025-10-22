import bpy
import os
import subprocess
import tempfile
import sys # Import sys to get the executable path of the current Blender instance
from pathlib import Path


def generate_lods_with_meshlabserver(operator, context, lod0_dae_filepath, lods_dir, lod0_obj, initial_face_count, ratios=None):
    """
    Generates LODs using meshlabserver.
    Requires MeshLab Server to be installed and path configured in preferences.
    """
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences

    try:
        meshlab_server_path = prefs.meshlab_executable_path
    except AttributeError:
        operator.report({'ERROR'}, "Addon preference 'meshlab_executable_path' not found. "
                                   "Please ensure your addon preferences define the MeshLab Server Path "
                                   "property with this exact name, or update utils.py with the correct name.")
        return False

    if not os.path.exists(meshlab_server_path) or not os.path.isfile(meshlab_server_path):
        operator.report({'ERROR'}, f"MeshLab Server not found at: {meshlab_server_path}. Please set the correct path in addon preferences.")
        return False

    # Define target face counts based on initial_face_count, including optional LOD0
    default_r = {0: 0.08, 1: 0.40, 2: 0.16, 3: 0.064}
    r = ratios or {1: 0.40, 2: 0.16, 3: 0.064}
    # Ensure all 0..3 keys have a value (fallback to defaults)
    r_full = {i: float(r.get(i, default_r[i])) for i in (0, 1, 2, 3)}
    lod_targets = {i: max(10, int(initial_face_count * r_full[i])) for i in (0, 1, 2, 3)}

    # Derive base name from input; if input is Cinema or variant, we will name outputs {base}_LOD{i}
    name = lod0_obj.name
    if name.endswith('_Cinema'):
        base_name = name.replace('_Cinema', '')
    else:
        base_name = name.replace('_LOD0', '')

    temp_filter_file = None
    try:
        # Produce LOD0..LOD3
        for i in (0, 1, 2, 3):
            target_face_count = lod_targets.get(i, max(10, int(initial_face_count * 0.1)))
            output_lod_name = f"{base_name}_LOD{i}.dae"
            output_filepath = os.path.join(lods_dir, output_lod_name)

            # Create a temporary MLX filter file with the dynamic target face count
            temp_filter_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".mlx")
            temp_filter_file.write(f"""<!DOCTYPE FilterScript>
<FilterScript>
 <filter name="Simplification: Quadric Edge Collapse Decimation (with texture)">
  <Param description="Target number of faces" value="{target_face_count}" type="RichInt" name="TargetFaceNum"/>
  <Param description="Quality threshold" value="0.5" type="RichFloat" name="QualityThr"/>
  <Param description="Texture Weight" value="100" type="RichFloat" isxmlparam="0" name="Extratcoordw"/>
  <Param description="Preserve Boundary of the mesh" value="true" type="RichBool" name="PreserveBoundary"/>
  <Param description="Optimal position of simplified vertices" value="true" type="RichBool" name="OptimalPlacement"/>
  <Param description="Preserve Normal" value="true" type="RichBool" name="PreserveNormal"/>
 </filter>
</FilterScript>""")
            temp_filter_file.close() # Close the file so MeshLab can read it

            meshlab_cmd = [
                meshlab_server_path,
                "-i", lod0_dae_filepath,
                "-o", output_filepath,
		"-m", "wt",
                "-s", temp_filter_file.name # Use the temporary filter script
            ]

            operator.report({'INFO'}, f"Running MeshLab server for {output_lod_name} with target faces: {target_face_count}")
            process = subprocess.run(meshlab_cmd, check=True, capture_output=True, text=True, cwd=lods_dir)
            operator.report({'INFO'}, f"MeshLab server output for {output_lod_name}:\n{process.stdout}")
            if process.stderr:
                operator.report({'WARNING'}, f"MeshLab server warnings/errors for {output_lod_name}:\n{process.stderr}")

        operator.report({'INFO'}, "MeshLab server processing completed for all LODs.")
        return True

    except FileNotFoundError:
        operator.report({'ERROR'}, f"MeshLab server not found at '{meshlab_server_path}'. Please ensure the path is correct.")
        operator.report({'ERROR'}, "You can set the MeshLab Server Path in the addon preferences (Edit > Preferences > Add-ons > VIVID Arts Toolbox).\nIf you are using Blender on Windows, the path should look like C:\\Program Files\\MeshLab\\meshlabserver.exe.")
        return False
    except subprocess.CalledProcessError as e:
        operator.report({'ERROR'}, f"MeshLab server processing failed: {e}")
        operator.report({'ERROR'}, f"MeshLab server Stdout: {e.stdout}")
        operator.report({'ERROR'}, f"MeshLab server Stderr: {e.stderr}")
        return False
    except Exception as e:
        operator.report({'ERROR'}, f"An unexpected error occurred during MeshLab server processing: {e}")
        return False
    finally:
        if temp_filter_file and os.path.exists(temp_filter_file.name):
            os.remove(temp_filter_file.name)


# ----------------------
# Resource path helpers
# ----------------------
def resources_dir() -> Path:
    """Return the path to the add-on's bundled resources directory.
    We keep non-Python assets (blend/json/spp) under 'resources/'.
    """
    return Path(__file__).resolve().parent / "resources"


def resource_path(name: str) -> Path:
    """Preferred path: vivid_arts_toolbox/resources/<name>"""
    return resources_dir() / name


def resource_or_legacy(name: str) -> Path:
    """Return the path to a resource under resources/ only.
    Fallback to legacy locations has been removed to keep the add-on tidy.
    """
    return resource_path(name)


# ----------------------
# Project directory helpers
# ----------------------
def project_dirs() -> tuple[Path, Path, Path]:
    """Return (root, BakeMesh, BakeTextures) based on the current .blend location.

    Root is the directory containing the current .blend file. This function does not
    create any directories; callers can create them as needed.

    Raises:
        RuntimeError: If the current .blend has not been saved yet.
    """
    blend_path = Path(bpy.data.filepath)
    if not blend_path:
        raise RuntimeError("Please save your .blend file first.")
    root = blend_path.parent
    return root, root / "BakeMesh", root / "BakeTextures"


# ----------------------
# Naming helpers (asset conventions)
# ----------------------
def is_optimized_name(name: str) -> bool:
    """True if name ends with '_Optimized' (case-sensitive)."""
    return isinstance(name, str) and name.endswith("_Optimized")


def base_from_optimized(name: str) -> str:
    """Strip '_Optimized' suffix if present; otherwise return name unchanged."""
    if is_optimized_name(name):
        return name[:-10]
    return name


def lod_suffix(index: int) -> str:
    """Return LOD suffix like '_LOD0' for index 0."""
    return f"_LOD{int(index)}"


def lod_name(base: str, index: int) -> str:
    """Return full LOD object name from base and index (e.g., 'Rock_LOD1')."""
    return f"{base}{lod_suffix(index)}"


def is_lod_name(name: str) -> bool:
    """True if name ends with a LOD suffix like _LOD0 … _LOD9."""
    if not isinstance(name, str):
        return False
    import re
    return re.search(r"_LOD\d+$", name) is not None


def generate_lods_with_pymeshlab(context, lod0_dae_filepath, lods_dir, lod0_obj, initial_face_count, ratios=None):
    """Helper function to encapsulate PyMeshLab logic."""
    try:
        import pymeshlab as ml
    except ImportError:
        context.report({'ERROR'}, "PyMeshLab not found. Please install it or disable PyMeshLab automation in addon preferences.")
        return False

    ms = ml.MeshSet()
    try:
        ms.load_new_mesh(lod0_dae_filepath)
    except Exception as e:
        context.report({'ERROR'}, f"Failed to load LOD0.dae into PyMeshLab: {e}")
        context.report({'ERROR'}, "Please check the System Console (Window > Toggle System Console) for more details.")
        return False

    if initial_face_count <= 0:
        context.report({'ERROR'}, "LOD0 has no faces. Cannot generate LODs.")
        return False

    # Include LOD0; fall back to sensible defaults if not provided
    lod_target_percentages = {
        'LOD0': (ratios.get(0) if ratios else 0.08),
        'LOD1': (ratios.get(1) if ratios else 0.4),
        'LOD2': (ratios.get(2) if ratios else 0.16),
        'LOD3': (ratios.get(3) if ratios else 0.064)
    }

    name = lod0_obj.name
    if name.endswith('_Cinema'):
        original_base_name = name.replace('_Cinema', '')
    else:
        original_base_name = name.replace('_LOD0', '')

    try:
        ms.set_current_mesh(0)

        for i in [0, 1, 2, 3]:
            lod_suffix = f"_LOD{i}"
            output_filename = f"{original_base_name}{lod_suffix}.dae"
            output_filepath = os.path.join(lods_dir, output_filename)
            target_percentage = lod_target_percentages[f'LOD{i}']
            target_faces = max(1, int(initial_face_count * target_percentage))

            ms.clone_current_mesh()
            ms.set_current_mesh(ms.number_meshes() - 1)

            ms.meshing_decimation_quadric_edge_collapse(
                targetfacenum=target_faces,
                qualitythr=0.5,
                preserveboundary=True,
                preservetopology=False,
                preservenormal=True,
                planarquadric=False,
                selected=False
            )
            # Save current mesh to output
            ms.save_current_mesh(output_filepath)

            context.report({'INFO'}, f"Generated {output_filename} with target faces: {target_faces}")

            ms.delete_current_mesh()
        
        context.report({'INFO'}, "PyMeshLab processing completed for all LODs.")
        return True

    except Exception as e:
        context.report({'ERROR'}, f"An error occurred during PyMeshLab LOD generation: {e}")
        return False


def bake_textures_headless_blender(operator, high_poly_filepath, low_poly_filepath, base_asset_name, output_dir, bake_types, resolution=2048, extrusion=0.1, cage_filepath=None):
    """
    Bakes textures from a high-poly object to a low-poly object using a headless Blender instance.

    Args:
        operator: The Blender operator calling this function (for reporting).
        high_poly_filepath (str): Full path to the high-poly FBX file.
        low_poly_filepath (str): Full path to the low-poly FBX file.
        base_asset_name (str): Base name for the output texture files.
        output_dir (str): Directory to save the baked textures.
        bake_types (list): List of bake types to perform (e.g., ['NORMAL', 'AO', 'DIFFUSE']).
        resolution (int): Resolution of the baked textures (e.g., 2048).
        extrusion (float): Cage extrusion distance for baking.
        cage_filepath (str, optional): Full path to the cage FBX file.
                                       If provided, this object will be used as the cage.
                                       Otherwise, cage extrusion will be used.

    Returns:
        bool: True if baking was successful, False otherwise.
    """
    # Determine the Blender executable path
    blender_python_executable = sys.executable # This is python.exe within Blender's installation

    blender_exec_path = None

    # Heuristic for Blender executable path:
    if sys.platform == "win32":
        # On Windows, sys.executable is usually blender_install_dir\VERSION\python\bin\python.exe
        # We need blender_install_dir\blender.exe
        # Go up 4 levels: bin -> python -> VERSION -> Blender_Base_Folder
        blender_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(blender_python_executable))))
        blender_exec_path = os.path.join(blender_base_dir, "blender.exe")
    elif sys.platform.startswith("linux") or sys.platform == "darwin":
        # On Linux/macOS, sys.executable might point to the Python interpreter inside the app bundle.
        # We need to find the main 'blender' executable.
        current_dir = os.path.dirname(blender_python_executable) # /.../python/bin
        # Traverse up to find the main Blender executable.
        # This heuristic is an educated guess and might need adjustment for specific Blender distributions.
        for _ in range(4): # Check up to 4 levels up
            # Look for a 'blender' executable in common locations (e.g., peer to 'python' dir, or within 'MacOS' on Darwin)
            candidate_blender_path_linux = os.path.join(current_dir, 'blender')
            candidate_blender_path_mac_app = os.path.join(current_dir, '..', '..', 'MacOS', 'Blender') # Common for macOS .app bundles

            if os.path.exists(candidate_blender_path_linux) and os.path.isfile(candidate_blender_path_linux) and os.access(candidate_blender_path_linux, os.X_OK):
                blender_exec_path = candidate_blender_path_linux
                break
            if os.path.exists(candidate_blender_path_mac_app) and os.path.isfile(candidate_blender_path_mac_app) and os.access(candidate_blender_path_mac_app, os.X_OK):
                blender_exec_path = candidate_blender_path_mac_app
                break
            
            # Move up one directory
            current_dir = os.path.dirname(current_dir)
            if current_dir == os.path.dirname(current_dir): # Reached root or cannot go further
                break
        
        if not blender_exec_path:
            # As a last resort, try using sys.executable directly if it happens to be the main binary
            if os.path.exists(blender_python_executable) and os.path.isfile(blender_python_executable) and os.access(blender_python_executable, os.X_OK) and 'blender' in os.path.basename(blender_python_executable).lower():
                blender_exec_path = blender_python_executable


    if not blender_exec_path or not os.path.exists(blender_exec_path):
        operator.report({'ERROR'}, f"Blender executable not found. Derived path: '{blender_exec_path}'. Please verify your Blender installation and permissions.")
        return False

    # Create the temporary baking script that the headless Blender will run
    # This script still needs to be temporary as it's generated for execution.
    temp_script_path = os.path.join(tempfile.gettempdir(), "blender_bake_script.py")

    # Define the baking script content as a regular triple-quoted string
    # All f-string curly braces inside this content need to be escaped by doubling them
    baking_script_content = """
import bpy
import os
import sys

# Get arguments passed from the main script via '--'
try:
    args_index = sys.argv.index("--")
    high_poly_file = sys.argv[args_index + 1]
    low_poly_file = sys.argv[args_index + 2]
    output_folder = sys.argv[args_index + 3] # This is now the permanent output folder
    base_name = sys.argv[args_index + 4]
    bake_types_str = sys.argv[args_index + 5]
    resolution = int(sys.argv[args_index + 6])
    extrusion = float(sys.argv[args_index + 7])
    # Check if cage_file argument exists and is not "None"
    cage_file = sys.argv[args_index + 8] if len(sys.argv) > args_index + 8 and sys.argv[args_index + 8] != "None" else None

    bake_types = bake_types_str.split(',')
except (ValueError, IndexError) as e:
    print(f"ERROR: Missing or invalid arguments for baking script: {{e}}")
    sys.stdout.flush()
    sys.exit(1)

# Clear default scene to ensure a clean slate for import
bpy.ops.wm.read_factory_settings(use_empty=True)
sys.stdout.flush()

print(f"INFO: Baking process started in headless Blender...")
sys.stdout.flush()
print(f"INFO: High poly file argument: {{high_poly_file}}")
sys.stdout.flush()
print(f"INFO: Low poly file argument: {{low_poly_file}}")
sys.stdout.flush()
print(f"INFO: Output folder (permanent): {{output_folder}}")
sys.stdout.flush()
print(f"INFO: Base name: {{base_name}}")
sys.stdout.flush()
print(f"INFO: Bake types: {{bake_types}}")
sys.stdout.flush()
print(f"INFO: Resolution: {{resolution}}")
sys.stdout.flush()
print(f"INFO: Extrusion: {{extrusion}}")
sys.stdout.flush()
print(f"INFO: Cage file argument: {{cage_file}}")
sys.stdout.flush()


high_poly_obj = None
low_poly_obj = None
cage_obj = None

try:
    # Import High Poly object
    print(f"INFO: Checking if high poly file exists: {{high_poly_file}}")
    sys.stdout.flush()
    if not os.path.exists(high_poly_file):
        print(f"ERROR: High poly file not found: {{high_poly_file}}")
        sys.stdout.flush()
        sys.exit(1)
    try:
        print(f"INFO: Importing high poly FBX: {{high_poly_file}}")
        sys.stdout.flush()
        bpy.ops.import_scene.fbx(filepath=high_poly_file)
        sys.stdout.flush()
        
        imported_high_poly_meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.name.startswith(os.path.basename(high_poly_file).split('.')[0])]
        if imported_high_poly_meshes:
            high_poly_obj = imported_high_poly_meshes[0]
            high_poly_obj.hide_set(True) # Hide from viewport
            high_poly_obj.hide_render = False # Ensure it's rendered for baking
            print(f"INFO: Imported high poly object: {{high_poly_obj.name}}")
            sys.stdout.flush()
        else:
            print(f"ERROR: High poly object not found in scene after import from {{high_poly_file}}. Check if the FBX file contains mesh data or if the naming convention is unexpected.")
            sys.stdout.flush()
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to import high poly FBX '{{high_poly_file}}': {{e}}")
        sys.stdout.flush()
        sys.exit(1)


    # Import Low Poly object
    print(f"INFO: Checking if low poly file exists: {{low_poly_file}}")
    sys.stdout.flush()
    if not os.path.exists(low_poly_file):
        print(f"ERROR: Low poly file not found: {{low_poly_file}}")
        sys.stdout.flush()
        sys.exit(1)
    try:
        print(f"INFO: Importing low poly FBX: {{low_poly_file}}")
        sys.stdout.flush()
        bpy.ops.import_scene.fbx(filepath=low_poly_file)
        sys.stdout.flush()
        imported_low_poly_meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.name.startswith(os.path.basename(low_poly_file).split('.')[0])]
        if imported_low_poly_meshes:
            low_poly_obj = imported_low_poly_meshes[0]
            print(f"INFO: Imported low poly object: {{low_poly_obj.name}}")
            sys.stdout.flush()
        else:
            print(f"ERROR: Low poly object not found in scene after import from {{low_poly_file}}. Check if the FBX file contains mesh data or if the naming convention is unexpected.")
            sys.stdout.flush()
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to import low poly FBX '{{low_poly_file}}': {{e}}")
        sys.stdout.flush()
        sys.exit(1)


    # Import Cage Mesh if specified
    if cage_file:
        print(f"INFO: Checking if cage file exists: {{cage_file}}")
        sys.stdout.flush()
        if not os.path.exists(cage_file):
            print(f"WARNING: Specified cage file does not exist: {{cage_file}}. Skipping cage import and using extrusion distance only.")
            sys.stdout.flush()
        else:
            try:
                print(f"INFO: Importing cage FBX: {{cage_file}}")
                sys.stdout.flush()
                bpy.ops.import_scene.fbx(filepath=cage_file)
                sys.stdout.flush()
                imported_cage_meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.name.startswith(os.path.basename(cage_file).split('.')[0])]
                if imported_cage_meshes:
                    cage_obj = imported_cage_meshes[0]
                    cage_obj.hide_set(True) # Hide from viewport
                    cage_obj.hide_render = False # Ensure it's rendered for baking
                    print(f"INFO: Imported cage mesh object: {{cage_obj.name}}")
                    sys.stdout.flush()
                else:
                    print(f"WARNING: Cage object not found in scene after import from {{cage_file}}. Ensure FBX contains mesh data or naming convention is expected.")
                    sys.stdout.flush()
            except Exception as e:
                print(f"WARNING: Failed to import cage FBX '{{cage_file}}': {{e}}. Proceeding without cage object.")
                sys.stdout.flush()
    else:
        print(f"INFO: No cage file specified. Baking will proceed using only extrusion distance.")
        sys.stdout.flush()


    # Set up low poly for baking
    print(f"INFO: Setting up low poly object '{{low_poly_obj.name}}' for baking...")
    sys.stdout.flush()
    bpy.context.view_layer.objects.active = low_poly_obj
    low_poly_obj.select_set(True)
    sys.stdout.flush()

    # Ensure low-poly has a UV map, create one if not present
    if not low_poly_obj.data.uv_layers:
        low_poly_obj.data.uv_layers.new(name="BakeUV")
        print("INFO: Created new UV layer 'BakeUV' for low poly object.")
        sys.stdout.flush()
    else:
        print(f"INFO: Low poly object already has UV layers. Using active UV layer: {{low_poly_obj.data.uv_layers.active.name}}")
        sys.stdout.flush()


    # Create or get a material for the low poly object
    if not low_poly_obj.data.materials:
        mat = bpy.data.materials.new(name="Bake_Material")
        low_poly_obj.data.materials.append(mat)
        print("INFO: Created new material 'Bake_Material' for low poly object.")
        sys.stdout.flush()
    else:
        mat = low_poly_obj.data.materials[0]
        print(f"INFO: Using existing material '{{mat.name}}' for low poly object.")
        sys.stdout.flush()

    # Ensure material uses nodes for baking
    if not mat.node_tree:
        mat.use_nodes = True
        print("INFO: Enabled node tree for material.")
        sys.stdout.flush()
    else:
        print("INFO: Material already uses nodes.")
        sys.stdout.flush()

    # Ensure Cycles is the render engine for baking
    bpy.context.scene.render.engine = 'CYCLES'
    print("INFO: Render engine set to Cycles.")
    sys.stdout.flush()
    try:
        # Prefer GPU if available for faster baking
        bpy.context.scene.cycles.device = 'GPU'
        print("INFO: Cycles device set to GPU.")
        sys.stdout.flush()
    except RuntimeError:
        print("WARNING: GPU device not available for Cycles, falling back to CPU.")
        bpy.context.scene.cycles.device = 'CPU' # Explicitly set to CPU if GPU fails
        sys.stdout.flush()
    
    # Set common bake settings
    bpy.context.scene.cycles.bake_selected_to_active = True
    bpy.context.scene.cycles.bake_cage_extrusion = extrusion
    if cage_obj:
        bpy.context.scene.cycles.bake_cage_object = cage_obj
        print(f"INFO: Using cage object: {{cage_obj.name}} for baking.")
        sys.stdout.flush()
    else:
        bpy.context.scene.cycles.bake_cage_object = None
        print(f"INFO: Using cage extrusion: {{extrusion}} for baking.")
        sys.stdout.flush()

    # Select both high and low poly for baking (high poly first for 'selected to active')
    bpy.ops.object.select_all(action='DESELECT')
    high_poly_obj.select_set(True) # Source object
    low_poly_obj.select_set(True) # Target object (also selected)
    bpy.context.view_layer.objects.active = low_poly_obj # Active object must be the target
    print(f"INFO: High poly ('{{high_poly_obj.name}}') and low poly ('{{low_poly_obj.name}}') selected, low poly is active.")
    sys.stdout.flush()


    # Loop through bake types and perform baking
    for bake_type in bake_types:
        print(f"INFO: Baking type: {{bake_type}}...")
        sys.stdout.flush()
        
        # Consistent image name based on base_name and bake_type
        img_name = f"{{base_name}}_{{bake_type.lower()}}"
        # Output directly to the specified output_folder (BakeTextures)
        output_image_filepath = os.path.join(output_folder, f"{{img_name}}.png")

        print(f"INFO: Creating image: {{img_name}} at resolution {{resolution}}x{{resolution}}.")
        sys.stdout.flush()
        # Blender's image data block should reference the *final* output path
        img = bpy.data.images.new(img_name, width=resolution, height=resolution)
        img.filepath_raw = output_image_filepath
        img.file_format = 'PNG'
        img.alpha_mode = 'NONE' # Most bake types don't need alpha for output
        sys.stdout.flush()

        # Remove any previously created bake image nodes in the material to ensure clean state for current bake
        nodes = mat.node_tree.nodes
        for node in nodes:
            if node.type == 'TEX_IMAGE' and node.image and node.image.name.startswith(base_name):
                print(f"INFO: Removing old texture node: {{node.name}}")
                nodes.remove(node)
        sys.stdout.flush()

        texture_node = nodes.new('ShaderNodeTexImage')
        texture_node.image = img
        texture_node.location = 0, 0 # Arbitrary location for the node
        print(f"INFO: Created new image texture node: {{texture_node.name}}.")
        sys.stdout.flush()
        
        # Critically, this node MUST be selected and active for bpy.ops.object.bake() to know where to bake
        # Re-ensure selection and active object state
        bpy.ops.object.select_all(action='DESELECT')
        low_poly_obj.select_set(True)
        high_poly_obj.select_set(True)
        bpy.context.view_layer.objects.active = low_poly_obj
        
        texture_node.select = True
        mat.node_tree.nodes.active = texture_node # Make the image texture node active for baking
        print(f"INFO: Image texture node '{{texture_node.name}}' is selected and active for material '{{mat.name}}'.")
        sys.stdout.flush()

        bpy.context.scene.cycles.bake_type = bake_type
        print(f"INFO: Cycles bake type set to '{{bake_type}}'.")
        sys.stdout.flush()

        # Specific settings per bake type
        if bake_type == 'NORMAL':
            bpy.context.scene.cycles.bake_normal_space = 'TANGENT' 
            bpy.context.scene.cycles.bake_normal_map_type = 'NORMAL_MAP' 
            print("INFO: Normal bake settings applied (Tangent Space, Normal Map type).")
        elif bake_type == 'AO':
            bpy.context.scene.cycles.bake_ao_samples = 64
            print("INFO: AO bake settings applied (64 samples).")
        elif bake_type == 'DIFFUSE':
            bpy.context.scene.cycles.bake_diffuse_direct = False # Only bake color, not lighting
            bpy.context.scene.cycles.bake_diffuse_indirect = False
            bpy.context.scene.cycles.bake_diffuse_color = True
            img.colorspace_settings.name = 'sRGB' # For color maps
            print("INFO: Diffuse bake settings applied (Color only, sRGB colorspace).")
        elif bake_type == 'EMISSION':
            bpy.context.scene.cycles.bake_emission = True
            print("INFO: Emission bake settings applied.")
        elif bake_type == 'ROUGHNESS':
            bpy.context.scene.cycles.bake_direct = False
            bpy.context.scene.cycles.bake_indirect = False
            bpy.context.scene.cycles.bake_color = False
            bpy.context.scene.cycles.bake_glossy = True # Capture glossy component for roughness
            print("INFO: Roughness bake settings applied (Glossy only).")
        elif bake_type == 'METALLIC':
            bpy.context.scene.cycles.bake_direct = False
            bpy.context.scene.cycles.bake_indirect = False
            bpy.context.scene.cycles.bake_color = False
            bpy.context.scene.cycles.bake_metallic = True # Capture metallic component
            print("INFO: Metallic bake settings applied.")
        elif bake_type == 'OPACITY':
            bpy.context.scene.cycles.bake_direct = False
            bpy.context.scene.cycles.bake_indirect = False
            bpy.context.scene.cycles.bake_color = False
            bpy.context.scene.cycles.bake_alpha = True # Capture alpha/opacity
            print("INFO: Opacity bake settings applied.")
        elif bake_type == 'COMBINED':
            print("INFO: Combined bake type selected.")
        sys.stdout.flush()

        try:
            print(f"INFO: Attempting to bake '{{bake_type}}'...")
            sys.stdout.flush()
            bpy.ops.object.bake(type=bake_type)
            # CRITICAL FIX: Save the image after baking
            img.save() 
            print(f"INFO: Successfully baked and saved '{{bake_type}}' to '{{img.filepath_raw}}'")
            sys.stdout.flush()
        except RuntimeError as e:
            print(f"ERROR: Error during '{{bake_type}}' bake: {{e}}")
            sys.stdout.flush()
            sys.exit(1)

    print("INFO: Baking process finished successfully in headless Blender.")
    sys.stdout.flush()
    sys.exit(0)

except Exception as e:
    print(f"CRITICAL ERROR: An unexpected error occurred in the baking script: {{e}}")
    sys.stdout.flush()
    sys.exit(1)
"""
    # Now, assign the baking script content directly, as all internal f-strings are escaped
    formatted_baking_script = baking_script_content 

    with open(temp_script_path, "w") as f:
        f.write(formatted_baking_script)

    command = [
        blender_exec_path,
        "--background", # Run Blender in background mode without GUI
        "--python", temp_script_path, # Execute the temporary Python script
        "--", # Separator for arguments to be passed to the Python script
        high_poly_filepath,
        low_poly_filepath,
        output_dir, # This is the permanent output_dir (BakeTextures)
        base_asset_name,
        ",".join(bake_types),
        str(resolution),
        str(extrusion),
        cage_filepath if cage_filepath else "None" # Pass "None" string if no cage
    ]

    operator.report({'INFO'}, f"Executing Blender headless command: {' '.join(command)}")

    try:
        process = subprocess.run(command, check=True, capture_output=True, text=True, cwd=output_dir)
        operator.report({'INFO'}, f"Blender headless output:\n{process.stdout}")
        if process.stderr:
            operator.report({'WARNING'}, f"Blender headless warnings/errors:\n{process.stderr}")
        operator.report({'INFO'}, "Texture baking completed successfully.")
        return True
    except FileNotFoundError:
        operator.report({'ERROR'}, f"Blender executable not found at '{blender_exec_path}'. "
                                   f"This is unexpected. Please report this issue.")
        return False
    except subprocess.CalledProcessError as e:
        operator.report({'ERROR'}, f"Blender headless baking failed with exit code {e.returncode}: {e}")
        operator.report({'ERROR'}, f"Blender Stdout: {e.stdout}")
        operator.report({'ERROR'}, f"Blender Stderr: {e.stderr}")
        return False
    except Exception as e:
        operator.report({'ERROR'}, f"An unexpected error occurred during Blender headless baking: {e}")
        return False
    finally:
        # The temporary script itself still needs to be cleaned up
        if os.path.exists(temp_script_path):
            os.remove(temp_script_path)

