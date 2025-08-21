import bpy
from bpy.props import StringProperty

class VIVID_OT_warning_dialog(bpy.types.Operator):
    bl_idname = "vivid.warning_dialog"
    bl_label = "Warning: Existing Materials Found!"
    bl_options = {'REGISTER', 'INTERNAL'}

    message: StringProperty(name="Message", default="Continue?")
    callback_id: StringProperty(name="Callback ID")

    def execute(self, context):
        bpy.context.scene.vivid_warning_confirmed = True
        bpy.context.scene.vivid_warning_callback_id = self.callback_id
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.label(text=self.message, icon='INFO')
        layout.label(text="Click 'OK' to remove them and continue.")

