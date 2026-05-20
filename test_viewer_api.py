import mujoco
import mujoco.viewer

print("Viewer cam properties:")
for item in dir(mujoco.MjvCamera):
    if not item.startswith('_'):
        print(item)
print("\nmjCAMERA_FIXED:", mujoco.mjtCamera.mjCAMERA_FIXED)
