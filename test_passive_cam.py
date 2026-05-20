import mujoco
import mujoco.viewer
import time
import sys
import os

sys.path.append("external/Open_Duck_Playground")
from playground.open_duck_mini_v2 import base
from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML

xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()
model = mujoco.MjModel.from_xml_string(xml_text, assets=base.get_assets())
data = mujoco.MjData(model)
mujoco.mj_step(model, data)

cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
print("FPV Cam ID:", cam_id)

viewer = mujoco.viewer.launch_passive(model, data)
with viewer.lock():
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = cam_id

time.sleep(2)
viewer.close()
