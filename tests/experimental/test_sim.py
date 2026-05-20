import mujoco
from pathlib import Path
xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml"
with open(xml_path, 'r') as f:
    original_xml = f.read()

# Try without the boxes
clean_xml = original_xml.split('<!-- Akadályok')[0] + '</worldbody>\n<keyframe>\n' + original_xml.split('<keyframe>\n')[1]

model = mujoco.MjModel.from_xml_string(clean_xml)
data = mujoco.MjData(model)
home = model.keyframe("home")
data.qpos[:] = home.qpos
data.ctrl[:] = home.ctrl

for i in range(100):
    mujoco.mj_step(model, data)

print("Duck z position without boxes:", data.qpos[2])
