import bpy
import os
import subprocess
import tempfile # Still needed for a temporary MLX to be written with specific target face count

def generate_lods_with_pymeshlab(context, lod0_dae_filepath, lods_dir, lod0_obj, initial_face_count):
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

    lod_target_percentages = {
        'LOD1': 0.4,
        'LOD2': 0.16,
        'LOD3': 0.064
    }
    
    original_base_name = lod0_obj.name.replace("_LOD0", "")

    for i in range(1, 4):
        lod_key = f"LOD{i}"
        lod_suffix = f"_{lod_key}"
        output_lod_name = f"{original_base_name}{lod_suffix}"
        output_dae_filepath = os.path.join(lods_dir, f"{output_lod_name}.dae")
        
        target_percentage = lod_target_percentages[lod_key]
        target_face_count = int(initial_face_count * target_percentage)
        
        if target_face_count < 10: 
            target_face_count = 10
        
        context.report({'INFO'}, f"Generating {output_lod_name} with target faces: {target_face_count}")

        ms_current_pass = ml.MeshSet()
        try:
            ms_current_pass.load_new_mesh(lod0_dae_filepath)
        except Exception as e:
            context.report({'ERROR'}, f"Failed to re-load LOD0.dae for {output_lod_name} processing: {e}")
            context.report({'ERROR'}, "Check if the DAE file is valid. Consult System Console.")
            return False

        try:
            ms_current_pass.apply_filter('meshing.decimation_quadric_edge_collapse',
                                          targetfacenum=target_face_count,
                                          preserve_boundary=True,
                                          preserve_uv=True,
                                          quality_idx=0.3)
            
            ms_current_pass.save_current_mesh(output_dae_filepath, 
                                             save_vertex_color=False, 
                                             save_face_color=False,
                                             save_vertex_normal=True,
                                             save_face_normal=True,
                                             save_texcoord=True)
            context.report({'INFO'}, f"Successfully generated and saved: {output_lod_name}.dae")

        except Exception as e:
            context.report({'ERROR'}, f"PyMeshLab processing failed for {output_lod_name}: {e}")
            context.report({'ERROR'}, "Please check the System Console for more details (Window > Toggle System Console).")
            return False
    
    context.report({'INFO'}, "PyMeshLab processing completed for all LODs.")
    return True


def generate_lods_with_meshlabserver(operator, context, lod0_dae_filepath, lods_dir, lod0_obj, initial_face_count):
    """Helper function to encapsulate meshlabserver.exe logic."""
    prefs = context.preferences.addons[__package__.split('.')[0]].preferences
    meshlab_exec_path = prefs.meshlab_executable_path
    
    if not meshlab_exec_path or not os.path.exists(meshlab_exec_path):
        operator.report({'ERROR'}, f"MeshLab server not found at '{meshlab_exec_path}'.")
        operator.report({'ERROR'}, "Please set the MeshLab Server Path in addon preferences or enable PyMeshLab automation.")
        return False

    operator.report({'INFO'}, "Step 3: Automating LOD generation using meshlabserver.exe...")

    lod_reductions = {
        'LOD1': 0.4,
        'LOD2': 0.16,
        'LOD3': 0.064
    }

    original_base_name = lod0_obj.name.replace("_LOD0", "")

    # Define the MLX filter content directly within the script
    # This replaces the need for an external decimate_filter.mlx file
    filter_template_content = """<!DOCTYPE FilterScript>
<FilterScript>
 <filter name="Simplification: Quadric Edge Collapse Decimation (with texture)">
  <Param description="Target number of faces" value="{TARGET_FACE_COUNT}" type="RichInt" tooltip="" isxmlparam="0" name="TargetFaceNum"/>
  <Param description="Percentage reduction (0..1)" value="0.4" type="RichFloat" tooltip="If non zero, this parameter specifies the desired final size of the mesh as a percentage of the initial mesh." isxmlparam="0" name="TargetPerc"/>
  <Param description="Quality threshold" value="0.3" type="RichFloat" tooltip="Quality threshold for penalizing bad shaped faces.&lt;br>The value is in the range [0..1]&#xa; 0 accept any kind of face (no penalties),&#xa; 0.5  penalize faces with quality &lt; 0.5, proportionally to their shape&#xa;" isxmlparam="0" name="QualityThr"/>
  <Param description="Texture Weight" value="10" type="RichFloat" tooltip="Additional weight for each extra Texture Coordinates for every (selected) vertex" isxmlparam="0" name="Extratcoordw"/>
  <Param description="Preserve Boundary of the mesh" value="true" type="RichBool" tooltip="The simplification process tries not to destroy mesh boundaries" isxmlparam="0" name="PreserveBoundary"/>
  <Param description="Boundary Preserving Weight" value="1" type="RichFloat" tooltip="The importance of the boundary during simplification. Default (1.0) means that the boundary has the same importance of the rest. Values greater than 1.0 raise boundary importance and has the effect of removing less vertices on the border. Admitted range of values (0,+inf). " isxmlparam="0" name="BoundaryWeight"/>
  <Param description="Optimal position of simplified vertices" value="true" type="RichBool" tooltip="Each collapsed vertex is placed in the position minimizing the quadric error.&#xa; It can fail (creating bad spikes) in case of very flat areas. &#xa;If disabled edges are collapsed onto one of the two original vertices and the final mesh is composed by a subset of the original vertices. " isxmlparam="0" name="OptimalPlacement"/>
  <Param description="Preserve Normal" value="false" type="RichBool" tooltip="Try to avoid face flipping effects and try to preserve the original orientation of the surface" isxmlparam="0" name="PreserveNormal"/>
  <Param description="Planar Simplification" value="false" type="RichBool" tooltip="Add additional simplification constraints that improves the quality of the simplification of the planar portion of the mesh." isxmlparam="0" name="PlanarQuadric"/>
  <Param description="Simplify only selected faces" value="false" type="RichBool" tooltip="The simplification is applied only to the selected set of faces.&#xa; Take care of the target number of faces!" isxmlparam="0" name="Selected"/>
 </filter>
</FilterScript>
"""

    for i in range(1, 4):
        lod_key = f"LOD{i}"
        lod_suffix = f"_{lod_key}"
        output_lod_name = f"{original_base_name}{lod_suffix}"
        output_dae_filepath = os.path.join(lods_dir, f"{output_lod_name}.dae")
        
        target_percent = lod_reductions[lod_key]
        target_face_count = int(initial_face_count * target_percent)
        
        if target_face_count < 10: 
            target_face_count = 10 
        
        # Replace the placeholder with the actual target face count for this LOD
        # A temporary MLX file is still needed because the targetfacenum parameter changes per LOD
        specific_filter_content = filter_template_content.replace("{TARGET_FACE_COUNT}", str(target_face_count))
        
        temp_filter_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.mlx', delete=False) as tf:
                tf.write(specific_filter_content)
                temp_filter_file = tf.name
            
            meshlab_cmd = [
                meshlab_exec_path,
                '-i', lod0_dae_filepath,
                '-o', output_dae_filepath,
                '-m', 'wt', # Only 'wt' for wedge texture coordinates (UVs)
                '-s', temp_filter_file,
            ]

            operator.report({'INFO'}, f"Running MeshLab server for {output_lod_name} with target faces: {target_face_count}")
            process = subprocess.run(meshlab_cmd, check=True, capture_output=True, text=True, cwd=lods_dir)
            operator.report({'INFO'}, f"MeshLab server output for {output_lod_name}:\n{process.stdout}")
            if process.stderr:
                operator.report({'WARNING'}, f"MeshLab server warnings/errors for {output_lod_name}:\n{process.stderr}")

        except FileNotFoundError:
            operator.report({'ERROR'}, f"MeshLab server not found at '{meshlab_exec_path}'. Please ensure the path is correct.")
            operator.report({'ERROR'}, "You can set the MeshLab Server Path in the addon preferences (Edit > Preferences > Add-ons > VIVID Arts Toolbox).")
            return False
        except subprocess.CalledProcessError as e:
            operator.report({'ERROR'}, f"MeshLab server processing failed for {output_lod_name}: {e}")
            operator.report({'ERROR'}, f"MeshLab server Stdout: {e.stdout}")
            operator.report({'ERROR'}, f"MeshLab server Stderr: {e.stderr}")
            return False
        except Exception as e:
            operator.report({'ERROR'}, f"An unexpected error occurred during MeshLab server processing for {output_lod_name}: {e}")
            return False
        finally:
            if temp_filter_file and os.path.exists(temp_filter_file):
                os.remove(temp_filter_file)

    operator.report({'INFO'}, "MeshLab server processing completed for all LODs.")
    return True
