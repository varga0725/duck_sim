import mujoco
from pathlib import Path
xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml"
model = mujoco.MjModel.from_xml_path(xml_path)
home = model.keyframe("home")
print("qpos length:", len(home.qpos))
print("qpos:", home.qpos)
