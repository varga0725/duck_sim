import mujoco

xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml"
with open(xml_path, 'r') as f:
    xml_text = f.read()

# Remove freejoints to make obstacles static
xml_text_static = xml_text.replace('<freejoint/>', '')

with open('temp_static.xml', 'w') as f:
    f.write(xml_text_static)

model = mujoco.MjModel.from_xml_path('temp_static.xml')
data = mujoco.MjData(model)
home = model.keyframe("home")
data.qpos[:] = home.qpos
data.ctrl[:] = home.ctrl

for i in range(100):
    mujoco.mj_step(model, data)

print("Static Z position after 100 steps:", data.qpos[2])
