import bpy
from bpy.props import StringProperty, BoolProperty

class VIVID_Arts_Toolbox_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    asset_destination_path: StringProperty(
        name="Asset Destination",
        subtype='DIR_PATH',
        default="//",
        description="Directory for final asset export."
    )
    designer_preset_filepath: StringProperty(
        name="Designer JSON Preset",
        subtype='FILE_PATH',
        description="Path to your Substance Designer JSON preset file."
    )
    meshlab_executable_path: StringProperty(
        name="MeshLab Server Path (Optional)",
        subtype='FILE_PATH',
        description="Full path to meshlabserver.exe. Used if PyMeshLab automation is disabled or fails.",
        default=""
    )
    enable_pymeshlab_automation: BoolProperty(
        name="Enable PyMeshLab Automation",
        default=True,
        description="Use PyMeshLab library for LOD generation (requires installation). Disable for manual MeshLab or meshlabserver.exe fallback."
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="VIVID Arts Toolbox Settings")
        layout.prop(self, "asset_destination_path")
        layout.prop(self, "designer_preset_filepath")
        
        layout.separator()
        layout.label(text="LOD Generation Options:", icon='INFO')
        layout.prop(self, "enable_pymeshlab_automation")
        
        if self.enable_pymeshlab_automation:
            layout.label(text="PyMeshLab is enabled. Ensure it's installed in Blender's Python.", icon='FILE_SCRIPT')
            box = layout.box()
            box.label(text="Installation Instructions for PyMeshLab:", icon='QUESTION')
            box.label(text="1. Open Blender's System Console (Window > Toggle System Console)")
            box.label(text="2. In console: import sys; print(sys.executable) to get Python path.")
            box.label(text="3. In Administrator PowerShell/CMD:")
            box.label(text="   & '<Blender_Python_Path>' -m pip install pymeshlab")
            box.label(text="4. Restart Blender.")
        else:
            layout.label(text="PyMeshLab automation is disabled.", icon='CHECKBOX_DEHLT')
            layout.prop(self, "meshlab_executable_path")
            layout.label(text="If 'MeshLab Server Path' is empty, manual MeshLab steps are required.", icon='INFO')

