import mujoco
import numpy as np
import sys
import os

sys.path.append("external/Open_Duck_Playground")
from playground.open_duck_mini_v2 import base
from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML

xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()

axes = [
    [1, 0, 0], [-1, 0, 0],
    [0, 1, 0], [0, -1, 0],
    [0, 0, 1], [0, 0, -1]
]

best_xyaxes = None
best_score = -999

for x_ax in axes:
    for y_ax in axes:
        # X and Y must be orthogonal
        if np.dot(x_ax, y_ax) == 0:
            xyaxes = f"{x_ax[0]} {x_ax[1]} {x_ax[2]} {y_ax[0]} {y_ax[1]} {y_ax[2]}"
            
            import re
            mod_xml = re.sub(r'xyaxes="[^"]+"', f'xyaxes="{xyaxes}"', xml_text)
            
            model = mujoco.MjModel.from_xml_string(mod_xml, assets=base.get_assets())
            data = mujoco.MjData(model)
            
            # Step physics 10 times to let home keyframe settle
            for _ in range(10):
                mujoco.mj_step(model, data)
            
            cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
            fwd = data.cam_xmat[cam_id].reshape(3, 3)[:, 2] * -1
            up = data.cam_xmat[cam_id].reshape(3, 3)[:, 1]
            
            # Score: we want fwd to be close to [1,0,0] and up to be close to [0,0,1]
            score = np.dot(fwd, [1, 0, 0]) + np.dot(up, [0, 0, 1])
            if score > best_score:
                best_score = score
                best_xyaxes = xyaxes
                print(f"New best: {xyaxes} | Fwd: {fwd} | Up: {up} | Score: {score}")

print("FINAL BEST:", best_xyaxes)
