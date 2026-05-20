import mujoco

xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml"
with open(xml_path, 'r') as f:
    xml_text = f.read()

# remove green wall
xml_text = xml_text.replace('<body name="obstacle_green_wall" pos="2.5 0 0.25">', '<!--')
xml_text = xml_text.replace('<geom type="box" size="0.1 1.5 0.25" rgba="0.2 0.8 0.2 1" contype="1" conaffinity="1"/>', '')
xml_text = xml_text.replace('</body>\n    </worldbody>', '-->\n    </worldbody>')

with open('temp_nowall.xml', 'w') as f:
    f.write(xml_text)

model = mujoco.MjModel.from_xml_path('temp_nowall.xml')
data = mujoco.MjData(model)
home = model.keyframe("home")
data.qpos[:] = home.qpos
data.ctrl[:] = home.ctrl

for i in range(100):
    mujoco.mj_step(model, data)

print("No wall Z position after 100 steps:", data.qpos[2])
