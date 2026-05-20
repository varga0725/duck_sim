import mujoco
import mujoco.viewer

model = mujoco.MjModel.from_xml_string('<mujoco></mujoco>')
data = mujoco.MjData(model)

# Can't actually launch without mjpython on mac, but let's check the source of Handle
import inspect
print(inspect.getsource(mujoco.viewer.Handle))
