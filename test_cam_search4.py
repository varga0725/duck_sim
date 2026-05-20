import mujoco
import numpy as np
import sys
import os

sys.path.append("external/Open_Duck_Playground")
from playground.open_duck_mini_v2 import base
from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML

xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()
duck_xml_path = "external/Open_Duck_Playground/playground/open_duck_mini_v2/xmls/open_duck_mini_v2.xml"

with open(duck_xml_path, 'r') as f:
    orig_duck_xml = f.read()

axes = [
    [1, 0, 0], [-1, 0, 0],
    [0, 1, 0], [0, -1, 0],
    [0, 0, 1], [0, 0, -1]
]

best_score = -999
best_xyaxes = None

for x_ax in axes:
    for y_ax in axes:
        if np.dot(x_ax, y_ax) == 0:
            xyaxes = f"{x_ax[0]} {x_ax[1]} {x_ax[2]} {y_ax[0]} {y_ax[1]} {y_ax[2]}"
            
            import re
            mod_duck_xml = re.sub(r'<camera name="fpv"[^>]+>', f'<camera name="fpv" pos="0.08 0 0.05" xyaxes="{xyaxes}" mode="fixed"/>', orig_duck_xml)
            
            with open(duck_xml_path, 'w') as f:
                f.write(mod_duck_xml)
            
            model = mujoco.MjModel.from_xml_string(xml_text, assets=base.get_assets())
            data = mujoco.MjData(model)
            
            for _ in range(10):
                mujoco.mj_step(model, data)
                
            cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
            fwd = data.cam_xmat[cam_id].reshape(3, 3)[:, 2] * -1
            up = data.cam_xmat[cam_id].reshape(3, 3)[:, 1]
            
            score = np.dot(fwd, [1, 0, 0]) + np.dot(up, [0, 0, 1])
            if score > best_score:
                best_score = score
                best_xyaxes = xyaxes
                print(f"New best: {xyaxes} | Fwd: [{fwd[0]:.1f}, {fwd[1]:.1f}, {fwd[2]:.1f}], Up: [{up[0]:.1f}, {up[1]:.1f}, {up[2]:.1f}] | Score: {score:.1f}")

with open(duck_xml_path, 'w') as f:
    f.write(orig_duck_xml)
