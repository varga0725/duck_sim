import mujoco
import os

xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml"
with open(xml_path, 'r') as f:
    xml_text = f.read()

# lift the boxes
xml_text = xml_text.replace('pos="1.0 0.3 0.15"', 'pos="1.0 0.3 0.5"')
xml_text = xml_text.replace('pos="1.5 -0.5 0.2"', 'pos="1.5 -0.5 0.5"')

with open(xml_path, 'w') as f:
    f.write(xml_text)

model = mujoco.MjModel.from_xml_path(xml_path)
data = mujoco.MjData(model)
home = model.keyframe("home")
data.qpos[:] = home.qpos
data.ctrl[:] = home.ctrl

for i in range(100):
    mujoco.mj_step(model, data)

print("Lifted Z position after 100 steps:", data.qpos[2])

