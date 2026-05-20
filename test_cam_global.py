import mujoco
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
print("Camera forward vector (global):", data.cam_xmat[cam_id].reshape(3, 3)[:, 2] * -1)
print("Camera up vector (global):", data.cam_xmat[cam_id].reshape(3, 3)[:, 1])
print("Camera position (global):", data.cam_xpos[cam_id])
