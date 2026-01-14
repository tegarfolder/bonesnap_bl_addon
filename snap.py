bl_info = {
    "name": "BoneSnap Addon",
    "author": "Putra Tegar",
    "version": (0, 5, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Tool Shelf > Anti Slide",
    "description": "Tools for snapping and unsnapping bones with constraints.",
    "warning": "",
    "wiki_url": "",
    "category": "Animation",
}

import bpy
from mathutils import Matrix

# Global properties for toggles in the panel
def update_follow_rotation(self, context):
    pass  # Placeholder for callback if needed

def update_add_constraints(self, context):
    pass  # Placeholder for callback if needed

# Define properties
bpy.types.Scene.bone_tool_follow_rotation = bpy.props.BoolProperty(
    name="Follow Bone Rotation",
    description="Make the empty follow the rotation of the selected bone",
    default=True,
    update=update_follow_rotation
)

bpy.types.Scene.bone_tool_add_constraints = bpy.props.BoolProperty(
    name="Add Constraints",
    description="Add Copy Location and Copy Rotation constraints to the selected bone targeting the new empty",
    default=True,
    update=update_add_constraints
)

bpy.types.Scene.bone_tool_keyframe_offset = bpy.props.IntProperty(
    name="Snap Smoothness",
    description="Number of frames before current frame to place the initial keyframe for snap",
    default=1,
    min=1,
    max=10,
    update=lambda self, context: None
)

bpy.types.Scene.bone_tool_unsnap_offset = bpy.props.IntProperty(
    name="Unsnap Smoothness",
    description="Number of frames after current frame to place the final keyframe for unsnap",
    default=5,
    min=1,
    max=10,
    update=lambda self, context: None
)

bpy.types.Scene.tweak_pose_set_inverse = bpy.props.BoolProperty(
    name="Set Inverse",
    description="Set inverse for the Child Of constraint",
    default=False
)

bpy.types.Scene.is_update_prepared = bpy.props.BoolProperty(default=False)
bpy.types.Scene.temp_target_empty_name = bpy.props.StringProperty()

# Define operators
class POSE_OT_add_empty_to_bone(bpy.types.Operator):
    """Add Empty Arrow to selected bone position with optional rotation and add constraints"""
    bl_idname = "pose.add_empty_to_bone"
    bl_label = "Add Empty to Selected Bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Only enable in pose mode with selected bones
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.selected_pose_bones)

    def execute(self, context):
        try:
            # Get the global toggle values
            follow_rotation = context.scene.bone_tool_follow_rotation
            add_constraints = context.scene.bone_tool_add_constraints

            # Store the original armature object
            original_armature = context.active_object
            # Store the selected pose bones (use active bone for rotation)
            selected_pose_bone = context.active_pose_bone or context.selected_pose_bones[0]
            
            if not selected_pose_bone:
                self.report({'WARNING'}, "No active or selected bone found")
                return {'CANCELLED'}
            
            # 1. 3D Cursor to selected bone (this handles position)
            bpy.ops.view3d.snap_cursor_to_selected()
            
            # Calculate the world matrix of the selected bone if needed
            bone_matrix_world = None
            if follow_rotation:
                arm_obj = original_armature
                bone = selected_pose_bone
                # Get the bone's matrix in world space
                bone_matrix_world = arm_obj.matrix_world @ bone.matrix
            
            # 2. Switch to Object Mode
            bpy.ops.object.mode_set(mode='OBJECT')
            
            # 3. Add Empty Arrows
            bpy.ops.object.empty_add(type='ARROWS')
            
            # Get the newly created empty object
            new_empty = context.active_object
            if new_empty:
                # Apply position from cursor
                new_empty.location = context.scene.cursor.location
                
                # Apply rotation if option is enabled
                if follow_rotation and bone_matrix_world:
                    # Extract only the rotation part (to avoid scaling issues)
                    rotation_matrix = bone_matrix_world.to_3x3().normalized().to_4x4()
                    new_empty.matrix_world = Matrix.Translation(bone_matrix_world.translation) @ rotation_matrix
                # If not following rotation, the empty will keep its default orientation
                
                # Set the display size
                new_empty.empty_display_size = 0.15
                new_empty.name = "SnapEmpty"
                
            # Switch back to pose mode to add constraints
            # We need to make sure the armature is active before switching modes
            context.view_layer.objects.active = original_armature
            original_armature.select_set(True)
            bpy.ops.object.mode_set(mode='POSE')
            
            # 4. Add constraints if option is enabled
            if add_constraints and new_empty:
                # Make sure we're operating on the correct armature and bone
                context.view_layer.objects.active = original_armature
                original_armature.select_set(True)
                
                # Find the same bone in the updated pose_bones collection
                target_bone = original_armature.pose.bones.get(selected_pose_bone.name)
                if target_bone:
                    initial_constraint_count = len(target_bone.constraints)
                    
                    # Add Copy Location constraint
                    copy_loc_constraint = target_bone.constraints.new(type='COPY_LOCATION')
                    copy_loc_constraint.target = new_empty
                    copy_loc_constraint.name = f"snapLoc: {new_empty.name}"
                    
                    # Add Copy Rotation constraint
                    copy_rot_constraint = target_bone.constraints.new(type='COPY_ROTATION')
                    copy_rot_constraint.target = new_empty
                    copy_rot_constraint.name = f"snapRot: {new_empty.name}"

                    final_constraint_count = len(target_bone.constraints)
                    self.report({'INFO'}, f"Added {final_constraint_count - initial_constraint_count} constraints to bone '{target_bone.name}'")

            # Re-select the original armature and ensure we're in pose mode
            context.view_layer.objects.active = original_armature
            original_armature.select_set(True)
            bpy.ops.object.mode_set(mode='POSE')
                
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Operation failed: {str(e)}")
            # Ensure we're back in pose mode if something went wrong
            try:
                if original_armature:
                    context.view_layer.objects.active = original_armature
                    original_armature.select_set(True)
                    bpy.ops.object.mode_set(mode='POSE')
            except:
                pass
            return {'CANCELLED'}


class POSE_OT_snap_influence(bpy.types.Operator):
    """Add keyframes to influence of snapLoc and snapRot constraints"""
    bl_idname = "pose.snap_influence"
    bl_label = "Snap Influence"
    bl_description = "Add keyframes to snapLoc and snapRot constraint influences"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Enable if in pose mode, has active bone, and that bone has relevant constraints
        if (context.mode == 'POSE' and 
            context.active_object and 
            context.active_object.type == 'ARMATURE' and
            context.active_pose_bone and
            not context.scene.is_update_prepared):
            bone = context.active_pose_bone
            # Check for constraints with names starting with "snapLoc:" or "snapRot:"
            snap_cons = [c for c in bone.constraints if c.name.startswith(("snapLoc:", "snapRot:"))]
            return len(snap_cons) > 0
        return False

    def execute(self, context):
        try:
            # Get the global offset value
            offset = context.scene.bone_tool_keyframe_offset
            current_frame = context.scene.frame_current
            frame_before = current_frame - offset

            # Get the active bone
            target_bone = context.active_pose_bone
            if not target_bone:
                self.report({'WARNING'}, "No active pose bone found.")
                return {'CANCELLED'}

            # Find relevant constraints
            snap_loc_constraint = None
            snap_rot_constraint = None
            for c in target_bone.constraints:
                if c.name.startswith("snapLoc:"):
                    snap_loc_constraint = c
                elif c.name.startswith("snapRot:"):
                    snap_rot_constraint = c

            # Apply keyframes
            if snap_loc_constraint:
                # Keyframe 0.0 at frame_before
                snap_loc_constraint.influence = 0.0
                snap_loc_constraint.keyframe_insert(data_path="influence", frame=frame_before)
                # Keyframe 1.0 at current_frame
                snap_loc_constraint.influence = 1.0
                snap_loc_constraint.keyframe_insert(data_path="influence", frame=current_frame)
                self.report({'INFO'}, f"Keyframed snapLoc influence on bone '{target_bone.name}'")

            if snap_rot_constraint:
                # Keyframe 0.0 at frame_before
                snap_rot_constraint.influence = 0.0
                snap_rot_constraint.keyframe_insert(data_path="influence", frame=frame_before)
                # Keyframe 1.0 at current_frame
                snap_rot_constraint.influence = 1.0
                snap_rot_constraint.keyframe_insert(data_path="influence", frame=current_frame)
                self.report({'INFO'}, f"Keyframed snapRot influence on bone '{target_bone.name}'")

            if not snap_loc_constraint and not snap_rot_constraint:
                self.report({'WARNING'}, f"No 'snapLoc:' or 'snapRot:' constraints found on bone '{target_bone.name}'.")

            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Snap influence operation failed: {str(e)}")
            return {'CANCELLED'}


class POSE_OT_unsnap_influence(bpy.types.Operator):
    """Add keyframes to influence of snapLoc and snapRot constraints for unsnap"""
    bl_idname = "pose.unsnap_influence"
    bl_label = "Unsnap Influence"
    bl_description = "Add keyframes to snapLoc and snapRot constraint influences"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Enable if in pose mode, has active bone, and that bone has relevant constraints
        if (context.mode == 'POSE' and 
            context.active_object and 
            context.active_object.type == 'ARMATURE' and
            context.active_pose_bone and
            not context.scene.is_update_prepared):
            bone = context.active_pose_bone
            # Check for constraints with names starting with "snapLoc:" or "snapRot:"
            snap_cons = [c for c in bone.constraints if c.name.startswith(("snapLoc:", "snapRot:"))]
            return len(snap_cons) > 0
        return False

    def execute(self, context):
        try:
            # Get the global offset value
            offset = context.scene.bone_tool_unsnap_offset
            current_frame = context.scene.frame_current
            frame_after = current_frame + offset

            # Get the active bone
            target_bone = context.active_pose_bone
            if not target_bone:
                self.report({'WARNING'}, "No active pose bone found.")
                return {'CANCELLED'}

            # Find relevant constraints
            snap_loc_constraint = None
            snap_rot_constraint = None
            for c in target_bone.constraints:
                if c.name.startswith("snapLoc:"):
                    snap_loc_constraint = c
                elif c.name.startswith("snapRot:"):
                    snap_rot_constraint = c

            # Apply keyframes
            if snap_loc_constraint:
                # Keyframe 1.0 at current_frame
                snap_loc_constraint.influence = 1.0
                snap_loc_constraint.keyframe_insert(data_path="influence", frame=current_frame)
                # Keyframe 0.0 at frame_after
                snap_loc_constraint.influence = 0.0
                snap_loc_constraint.keyframe_insert(data_path="influence", frame=frame_after)
                self.report({'INFO'}, f"Keyframed unsnapLoc influence on bone '{target_bone.name}'")

            if snap_rot_constraint:
                # Keyframe 1.0 at current_frame
                snap_rot_constraint.influence = 1.0
                snap_rot_constraint.keyframe_insert(data_path="influence", frame=current_frame)
                # Keyframe 0.0 at frame_after
                snap_rot_constraint.influence = 0.0
                snap_rot_constraint.keyframe_insert(data_path="influence", frame=frame_after)
                self.report({'INFO'}, f"Keyframed unsnapRot influence on bone '{target_bone.name}'")

            if not snap_loc_constraint and not snap_rot_constraint:
                self.report({'WARNING'}, f"No 'snapLoc:' or 'snapRot:' constraints found on bone '{target_bone.name}'.")

            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Unsnap influence operation failed: {str(e)}")
            return {'CANCELLED'}


class POSE_OT_update_empty(bpy.types.Operator):
    """Update the target empty of snap constraints by moving it to the current bone position and keyframing."""
    bl_idname = "pose.update_empty"
    bl_label = "Update Empty Target"
    bl_description = "Move the target empty to the current bone position and add keyframes for its transform"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Enable if in pose mode, has active bone, and that bone has relevant constraints
        if (context.mode == 'POSE' and 
            context.active_object and 
            context.active_object.type == 'ARMATURE' and
            context.active_pose_bone and
            not context.scene.is_update_prepared):
            bone = context.active_pose_bone
            # Check for constraints with names starting with "snapLoc:" or "snapRot:"
            snap_cons = [c for c in bone.constraints if c.name.startswith(("snapLoc:", "snapRot:"))]
            return len(snap_cons) > 0
        return False

    def execute(self, context):
        try:
            # Get the global offset value for the 'before' frame
            snap_offset = context.scene.bone_tool_keyframe_offset
            current_frame = context.scene.frame_current
            frame_before = current_frame - snap_offset - 1
            temp_frame = frame_before + 1

            # Get the active bone
            target_bone = context.active_pose_bone
            if not target_bone:
                self.report({'WARNING'}, "No active pose bone found.")
                return {'CANCELLED'}

            # Find the target empty from the snap constraints
            snap_loc_constraint = None
            snap_rot_constraint = None
            for c in target_bone.constraints:
                if c.name.startswith("snapLoc:"):
                    snap_loc_constraint = c
                elif c.name.startswith("snapRot:"):
                    snap_rot_constraint = c

            target_empty = None
            if snap_loc_constraint and snap_loc_constraint.target:
                target_empty = snap_loc_constraint.target
            elif snap_rot_constraint and snap_rot_constraint.target:
                target_empty = snap_rot_constraint.target

            if not target_empty:
                self.report({'ERROR'}, f"Could not find target empty for constraints on bone '{target_bone.name}'.")
                return {'CANCELLED'}

            # Store the original armature object to switch back to later
            original_armature = target_bone.id_data

            # 1. (Pose mode) 3D Cursor to selected bone
            # We are still in pose mode here
            bpy.ops.view3d.snap_cursor_to_selected()

            # 2. Pindah ke Object mode (on the original armature)
            bpy.ops.object.mode_set(mode='OBJECT')

            # 3. Select the target empty (and deselect others)
            bpy.ops.object.select_all(action='DESELECT')
            target_empty.select_set(True)
            context.view_layer.objects.active = target_empty

            # 4. Add keyframe pada empty (Position, Rotation) di frame 'before' (menggunakan offset)
            target_empty.keyframe_insert(data_path="location", frame=frame_before)
            target_empty.keyframe_insert(data_path="rotation_euler", frame=frame_before) # Using euler for simplicity

            # --- Penanganan Auto Keying ---
            auto_key_state = context.scene.tool_settings.use_keyframe_insert_auto
            if auto_key_state:
                context.scene.tool_settings.use_keyframe_insert_auto = False
            # ----------------------------

            # 5. Pindah object ke 3D cursor (yg sudah dipindahkan ke posisi baru)
            # Sekarang tidak akan menambah keyframe jika auto keying aktif
            target_empty.location = context.scene.cursor.location
            # For rotation, we might want to get the bone's rotation in world space
            # Similar logic as in add_empty_to_bone
            # We already have original_armature and target_bone
            bone_matrix_world = original_armature.matrix_world @ target_bone.matrix
            # Extract rotation
            rotation_matrix = bone_matrix_world.to_3x3().normalized().to_4x4()
            target_empty.rotation_euler = rotation_matrix.to_euler(target_empty.rotation_mode)

            # --- Kembalikan Auto Keying ---
            if auto_key_state:
                context.scene.tool_settings.use_keyframe_insert_auto = True
            # ------------------------------

            # 6. (Tidak ada keyframe di current_frame di sini)

            # Switch back to the original armature object and enter pose mode
            bpy.ops.object.select_all(action='DESELECT')
            original_armature.select_set(True)
            context.view_layer.objects.active = original_armature
            bpy.ops.object.mode_set(mode='POSE')
            
            # Snapping cuy
            
            if snap_loc_constraint:
                # Keyframe 0.0 at frame_before
                snap_loc_constraint.influence = 0.0
                snap_loc_constraint.keyframe_insert(data_path="influence", frame=frame_before + 1)
                # Keyframe 1.0 at current_frame
                snap_loc_constraint.influence = 1.0
                snap_loc_constraint.keyframe_insert(data_path="influence", frame=current_frame)
                self.report({'INFO'}, f"Keyframed snapLoc influence on bone '{target_bone.name}'")

            if snap_rot_constraint:
                # Keyframe 0.0 at frame_before
                snap_rot_constraint.influence = 0.0
                snap_rot_constraint.keyframe_insert(data_path="influence", frame=frame_before + 1)
                # Keyframe 1.0 at current_frame
                snap_rot_constraint.influence = 1.0
                snap_rot_constraint.keyframe_insert(data_path="influence", frame=current_frame)
                self.report({'INFO'}, f"Keyframed snapRot influence on bone '{target_bone.name}'")

            if not snap_loc_constraint and not snap_rot_constraint:
                self.report({'WARNING'}, f"No 'snapLoc:' or 'snapRot:' constraints found on bone '{target_bone.name}'.")
            
#            bpy.ops.pose.snap_influence()

            # --- Set Status Update ---
            context.scene.is_update_prepared = True
            context.scene.temp_target_empty_name = target_empty.name
            # -----------------------
            
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            target_empty.select_set(True)
            context.view_layer.objects.active = target_empty
            
            self.report({'INFO'}, f"Updated and keyframed target empty '{target_empty.name}' for bone '{target_bone.name}' using snap offset ({snap_offset} frames before current).")

            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Update empty operation failed: {str(e)}")
            # Ensure we're back in pose mode on the armature if something went wrong
            try:
                current_obj = context.view_layer.objects.active
                if current_obj and current_obj.type == 'ARMATURE':
                    if context.mode != 'POSE':
                        bpy.ops.object.mode_set(mode='POSE')
                else:
                    arm_obj = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
                    if arm_obj:
                        bpy.ops.object.select_all(action='DESELECT')
                        arm_obj.select_set(True)
                        context.view_layer.objects.active = arm_obj
                        if context.mode != 'OBJECT':
                            bpy.ops.object.mode_set(mode='OBJECT')
                        bpy.ops.object.mode_set(mode='POSE')
            except:
                 print("Could not return to Pose mode after error.")
            # --- Reset Status Update jika terjadi error ---
            context.scene.is_update_prepared = False
            context.scene.temp_target_empty_name = ""
            # --------------------------------------------
            return {'CANCELLED'}
        
class POSE_OT_continue_update_empty(bpy.types.Operator):
    """Apply final keyframes to the target empty after manual adjustment."""
    bl_idname = "pose.continue_update_empty"
    bl_label = "Continue Update Empty"
    bl_description = "Add keyframes to the empty at temp_frame and return to pose mode."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Enable if in object mode and the active object is an empty
        # (Assuming the empty is still selected from the previous step)
        return (context.mode == 'OBJECT' and 
                context.active_object and 
                context.active_object.type == 'EMPTY' and
                context.scene.is_update_prepared and
                context.active_object.name == context.scene.temp_target_empty_name)

    def execute(self, context):
        try:
            # Get the global offset value for the 'before' frame
            snap_offset = context.scene.bone_tool_keyframe_offset
            current_frame = context.scene.frame_current
            frame_before = current_frame - snap_offset - 1
            temp_frame = frame_before + 1 # Ini adalah frame tujuan untuk keyframe final

            # Ambil empty yang aktif (harusnya empty yang disesuaikan pengguna)
            target_empty = context.active_object
            if not target_empty or target_empty.type != 'EMPTY':
                 self.report({'ERROR'}, "Active object is not an Empty.")
                 return {'CANCELLED'}

            # Ambil bone dan constraint yang terkait dengan empty ini
            target_bone = None
            original_armature = None
            snap_loc_constraint = None
            snap_rot_constraint = None

            for obj in bpy.data.objects:
                if obj.type == 'ARMATURE':
                    for bone in obj.pose.bones:
                        for constraint in bone.constraints:
                             if constraint.name.startswith(("snapLoc:", "snapRot:")) and constraint.target == target_empty:
                                 target_bone = bone
                                 original_armature = obj
                                 if constraint.name.startswith("snapLoc:"):
                                     snap_loc_constraint = constraint
                                 elif constraint.name.startswith("snapRot:"):
                                     snap_rot_constraint = constraint
                                 break # Cukup temukan satu
                        if target_bone:
                            break
                if target_bone:
                    break

            if not target_bone or not original_armature:
                 self.report({'ERROR'}, f"Could not find associated bone or armature for empty '{target_empty.name}'.")
                 return {'CANCELLED'}

            # 1. Insert keyframe empty di temp_frame (dengan nilai transform saat ini, yaitu hasil penyesuaian user)
            target_empty.keyframe_insert(data_path="location", frame=temp_frame)
            target_empty.keyframe_insert(data_path="rotation_euler", frame=temp_frame)

            # Switch back to the original armature object and enter pose mode
            bpy.ops.object.select_all(action='DESELECT')
            original_armature.select_set(True)
            context.view_layer.objects.active = original_armature
            bpy.ops.object.mode_set(mode='POSE')
            
            # --- Reset Status Update ---
            context.scene.is_update_prepared = False
            context.scene.temp_target_empty_name = ""
            # ---------------------------

            self.report({'INFO'}, f"Applied final keyframe to empty '{target_empty.name}' at frame {temp_frame}. Returned to Pose Mode.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Continue update operation failed: {str(e)}")
            # Coba kembali ke Pose Mode jika error
            try:
                if context.mode == 'OBJECT':
                    arm_obj = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
                    if arm_obj:
                        bpy.ops.object.select_all(action='DESELECT')
                        arm_obj.select_set(True)
                        context.view_layer.objects.active = arm_obj
                        bpy.ops.object.mode_set(mode='POSE')
            except:
                 print("Could not return to Pose mode after error in continue_update.")
            return {'CANCELLED'}
        
class POSE_OT_tweak_pose(bpy.types.Operator):
    """Tweak pose by constraining the selected bone to an empty."""
    bl_idname = "pose.tweak_pose"
    bl_label = "Tweak Pose"
    bl_description = "Create an empty, constrain the selected bone to it, and optionally set inverse."
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Enable if in pose mode and has an active bone selected
        return (context.mode == 'POSE' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and
                context.active_pose_bone)

    def execute(self, context):
        try:
            # Get the selected pose bone
            target_bone = context.active_pose_bone
            if not target_bone:
                self.report({'ERROR'}, "No active pose bone selected.")
                return {'CANCELLED'}

            # Get the original armature object
            original_armature = target_bone.id_data

            # 1. Spawn Empty "CUBE" with size 0.2 at the selected bone's world head location
            # Switch to Object Mode temporarily to add the empty
            initial_mode = context.mode
            if initial_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            # Store selection to restore later
            selected_objects_before = context.selected_objects[:]
            active_object_before = context.view_layer.objects.active

            # Deselect everything
            bpy.ops.object.select_all(action='DESELECT')

            # Add the empty
            # Gunakan world-space head location dari bone
            world_head_location = original_armature.matrix_world @ target_bone.head
            bpy.ops.object.empty_add(type='CUBE', location=world_head_location) # Gunakan world_head_location
            new_empty = context.active_object
            new_empty.empty_display_size = 0.2
            new_empty.name = f"Tweak_Empty_{target_bone.name}"

            # Restore previous selection and active object
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selected_objects_before:
                if obj.name in context.scene.objects: # Check if object still exists
                    obj.select_set(True)
            context.view_layer.objects.active = active_object_before

            # Switch back to Pose Mode
            bpy.ops.object.mode_set(mode='POSE')

            # 2. Add "Child Of" constraint to the selected bone
            child_of_constraint = target_bone.constraints.new(type='CHILD_OF')
            child_of_constraint.name = f"Tweak_ChildOf_{target_bone.name}"
            child_of_constraint.target = new_empty

            # 3. Set inverse if the boolean property is True
            if context.scene.tweak_pose_set_inverse:
                # Calculate and set the inverse matrix manually
                # This replicates what "Set Inverse" does
                bone_matrix_world = original_armature.matrix_world @ target_bone.matrix
                empty_matrix_world = new_empty.matrix_world
                child_of_constraint.inverse_matrix = empty_matrix_world.inverted() @ bone_matrix_world

            self.report({'INFO'}, f"Created tweak empty '{new_empty.name}' and added Child Of constraint to bone '{target_bone.name}'.")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Tweak pose operation failed: {str(e)}")
            # Ensure we're back in pose mode if something went wrong
            try:
                if context.mode == 'OBJECT':
                    # Find the original armature if we were in object mode
                    arm_obj = next((obj for obj in context.selected_objects if obj.type == 'ARMATURE'), None)
                    if not arm_obj:
                         # If not selected, try to find it by association with the bone
                         # This is tricky without storing the original armature name
                         # For now, assume the active object might be the armature if it's selected
                         if context.active_object and context.active_object.type == 'ARMATURE':
                              arm_obj = context.active_object
                    if arm_obj:
                        bpy.ops.object.select_all(action='DESELECT')
                        arm_obj.select_set(True)
                        context.view_layer.objects.active = arm_obj
                        bpy.ops.object.mode_set(mode='POSE')
                elif context.mode.startswith('EDIT'):
                    bpy.ops.object.mode_set(mode='POSE')
            except:
                print("Could not return to Pose mode after error in tweak_pose.")
            return {'CANCELLED'}

class VIEW3D_PT_bone_empty_panel(bpy.types.Panel):
    """Creates a panel in the 3D Viewport"""
    bl_label = "Anti Slide"
    bl_idname = "VIEW3D_PT_bone_empty_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Anti Slide"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        box1 = layout.box()
        box2 = layout.box()
        
        # Check if in pose mode with an armature selected
        is_pose_mode_armature = (context.mode == 'POSE' and 
                                 context.active_object and 
                                 context.active_object.type == 'ARMATURE')

        # Check for relevant constraints on the active bone (if applicable)
        # Only valid if in pose mode
        active_bone = context.active_pose_bone if is_pose_mode_armature else None
        has_snap_constraints = False
        if active_bone:
            snap_cons = [c for c in active_bone.constraints if c.name.startswith(("snapLoc:", "snapRot:"))]
            has_snap_constraints = len(snap_cons) > 0

        # Check if update is prepared
        is_prepared = context.scene.is_update_prepared

        # Disable the entire layout if not in the correct context (when not prepared)
        if not is_pose_mode_armature and not is_prepared:
            col.label(text="Select IK armature in Pose Mode", icon='INFO')
            box1.active = False
            box2.active = False # <-- Baris ini yang menonaktifkan semua elemen di bawahnya
            # Tidak perlu label tambahan karena elemen-elemen di bawah ini sudah tidak aktif

        # Show the toggles (always present in layout, but disabled if context is wrong and not prepared)
        row = box1.row()
        row.prop(context.scene, "bone_tool_follow_rotation", text="Follow Rotation")
        
        # Main button (disabled if update is prepared)
        row = box1.row()
        row.enabled = not is_prepared
        row.operator("pose.add_empty_to_bone", text="Prepare Snap", icon='EMPTY_ARROWS')
        
        # Show indicator if constraints exist
        row = box2.row()
        if not is_prepared:
            if has_snap_constraints and not is_prepared:
                row.label(text="Snap Constraints Found", icon='CHECKMARK')
            else:
                row.label(text="Constraints Not Found", icon='ERROR')
        else:
            row.label(text="Adjust Empty, then Apply", icon='INFO')
        
        # Update Empty Button - Tampilkan berdasarkan status
        row = box2.row(align=True)
        if is_prepared:
            # Jika update disiapkan, tampilkan hanya tombol Apply
            row.operator("pose.continue_update_empty", text="Apply", icon='CHECKMARK')
        else:
            # Jika tidak disiapkan, tampilkan tombol Update Empty
            row.operator("pose.update_empty", text="Update Empty", icon='FILE_REFRESH')
        
        # Layout for snap offset, snap button, unsnap button, unsnap offset
        # Sembunyikan jika sedang dalam proses update
        if not is_prepared:
            row = box2.row()
            row.scale_y = 1.0
            col1 = row.column(align=True)
            col1.prop(context.scene, "bone_tool_keyframe_offset", text="")
            c1 = col1.column(align=True)
            c1.scale_y = 1.5
            c1.operator("pose.snap_influence", text="Snap", icon='SNAP_ON')
            
            col2 = row.column(align=True)
            col2.prop(context.scene, "bone_tool_unsnap_offset", text="")
            c2 = col2.column(align=True)
            c2.scale_y = 1.5
            c2.operator("pose.unsnap_influence", text="Unsnap", icon='SNAP_OFF')
            
            box2.separator()
            coli = box2.column(align=True)
            coli.prop(context.scene, "tweak_pose_set_inverse", text="Set Inverse")
            coli.operator("pose.tweak_pose", text="Tweak", icon="POSE_HLT")
#        else:
#            # Opsional: beri indikasi bahwa kontrol lain dinonaktifkan
#            row = box.row()
#            row.label(text="Adjust Empty, then Apply", icon='INFO')
            # Tombol-tombol lain tidak muncul karena row-nya disembunyikan


# Registration
classes = (
    POSE_OT_add_empty_to_bone,
    POSE_OT_snap_influence,
    POSE_OT_unsnap_influence,
    POSE_OT_update_empty,
    POSE_OT_continue_update_empty,
    POSE_OT_tweak_pose,
    VIEW3D_PT_bone_empty_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    # Unregister the scene properties
    del bpy.types.Scene.bone_tool_follow_rotation
    del bpy.types.Scene.bone_tool_add_constraints
    del bpy.types.Scene.bone_tool_keyframe_offset
    del bpy.types.Scene.bone_tool_unsnap_offset
    del bpy.types.Scene.tweak_pose_set_inverse
    del bpy.types.Scene.is_update_prepared
    del bpy.types.Scene.temp_target_empty_name

if __name__ == "__main__":
    register()