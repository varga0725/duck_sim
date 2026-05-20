import mujoco
import mujoco.viewer
import time
import os

os.chdir("external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls")
model = mujoco.MjModel.from_xml_path("scene_flat_terrain.xml")
data = mujoco.MjData(model)

# Set home keyframe
home = model.keyframe("home")
data.qpos[:] = home.qpos
data.ctrl[:] = home.ctrl
mujoco.mj_step(model, data)

viewer = mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False)
cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
if cam_id >= 0:
    print(f"Locking viewer to fpv camera (id={cam_id})")
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = cam_id
else:
    print("Could not find fpv camera!")

viewer.sync()
time.sleep(1)
viewer.close()
print("Viewer test completed.")
