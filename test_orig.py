import mujoco
import os

xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/scene_flat_terrain.xml"
with open(xml_path, 'r') as f:
    current_xml = f.read()

orig_xml = """<mujoco model="scene">
    <include file="open_duck_mini_v2.xml"/>

    <visual>
        <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/>
        <rgba haze="0.15 0.25 0.35 1"/>
        <global azimuth="160" elevation="-20"/>
    </visual>

    <asset>
        <texture type="skybox" builtin="gradient" rgb1="1 1 1" rgb2="1 1 1" width="800" height="800"/>
        <texture type="2d" name="groundplane" builtin="checker" mark="edge" rgb1="1 1 1" rgb2="1 1 1" markrgb="0 0 0"
            width="300" height="300"/>
        <material name="groundplane" texture="groundplane" texuniform="true" texrepeat="5 5" reflectance="0"/>
    </asset>

    <worldbody>
        <body name="floor">
            <geom name="floor" size="0 0 0.01" type="plane" material="groundplane" contype="1" conaffinity="0"
                priority="1" friction="0.6" condim="3"/>
        </body>
    </worldbody>
    <keyframe>
        <key name="home"
            qpos="
    0 0 0.15
    1 0 0 0
      0.002
        0.053
        -0.63
        1.368
        -0.784
        0
        0
        0
        0
        -0.003
        -0.065
        0.635
        1.379
        -0.796
"
            ctrl="
          0.002
        0.053
        -0.63
        1.368
        -0.784
        0
        0
        0
        0
        -0.003
        -0.065
        0.635
        1.379
        -0.796
          "/>
    </keyframe>
</mujoco>
"""

with open(xml_path, "w") as f:
    f.write(orig_xml)

model = mujoco.MjModel.from_xml_path(xml_path)
data = mujoco.MjData(model)
home = model.keyframe("home")
data.qpos[:] = home.qpos
data.ctrl[:] = home.ctrl

for i in range(100):
    mujoco.mj_step(model, data)

print("Original Z position after 100 steps:", data.qpos[2])

# restore
with open(xml_path, "w") as f:
    f.write(current_xml)

