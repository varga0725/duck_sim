import cv2
import numpy as np
import time
import math
import mujoco

from duck_agent_sim.simulator.duck_sim import RealDuckSimulator

print("Initializing RealDuckSimulator...")
sim = RealDuckSimulator(headless=True)
sim.reset()

model = sim.model
data = sim.data

# FPV camera ID
try:
    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
except Exception as e:
    cam_id = -1
    print(f"Could not find fpv camera: {e}")

print(f"FPV Camera ID: {cam_id}")

# Load the saved frame
frame = cv2.imread("fpv_test_frame.png")
height, width, _ = frame.shape
print(f"Frame size: {width}x{height}")

# Focal length calculations
fovy = model.vis.global_.fovy
f_y = height / (2.0 * math.tan(math.radians(fovy) / 2.0))
f_x = f_y
print(f"Camera FOVY: {fovy} degrees, Focal length: {f_y:.1f} pixels")

# Camera pose
cam_pos = data.cam_xpos[cam_id]
cam_mat = data.cam_xmat[cam_id].reshape(3, 3)

def get_body_bbox(body_name):
    try:
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
    except Exception:
        print(f"Body {body_name} not found")
        return None
        
    geom_start = model.body_geomadr[body_id]
    geom_count = model.body_geomnum[body_id]
    
    pts_cam = []
    
    for i in range(geom_start, geom_start + geom_count):
        g_type = model.geom_type[i]
        g_pos = data.geom_xpos[i]
        g_mat = data.geom_xmat[i].reshape(3, 3)
        g_size = model.geom_size[i]
        
        # We generate local vertices depending on the geom type
        local_verts = []
        if g_type == mujoco.mjtGeom.mjGEOM_BOX:
            dx, dy, dz = g_size
            for sx in [-1, 1]:
                for sy in [-1, 1]:
                    for sz in [-1, 1]:
                        local_verts.append(np.array([sx*dx, sy*dy, sz*dz]))
        elif g_type == mujoco.mjtGeom.mjGEOM_SPHERE:
            r = g_size[0]
            # Simple approximation of sphere with 6 cardinal vertices
            for axis in range(3):
                for sign in [-1, 1]:
                    v = np.zeros(3)
                    v[axis] = sign * r
                    local_verts.append(v)
        else:
            # Fallback to geom center
            local_verts.append(np.zeros(3))
            
        for lv in local_verts:
            w_vert = g_pos + g_mat @ lv
            c_vert = cam_mat.T @ (w_vert - cam_pos)
            pts_cam.append(c_vert)
            
    # Now project to screen
    pxs = []
    pys = []
    
    for pt in pts_cam:
        depth = -pt[2]
        if depth > 0.05:  # clip near plane
            px = (pt[0] / depth) * f_x + (width / 2.0)
            py = (height / 2.0) - (pt[1] / depth) * f_y
            pxs.append(px)
            pys.append(py)
            
    if not pxs:
        return None
        
    xmin = max(0.0, min(pxs))
    ymin = max(0.0, min(pys))
    xmax = min(float(width), max(pxs))
    ymax = min(float(height), max(pys))
    
    # Return bounding box if it overlaps with screen
    if xmax > xmin and ymax > ymin:
        return [xmin, ymin, xmax, ymax]
    return None

# Let's draw bounding boxes for chair, table, sports_ball
for label in ["chair", "table", "sports_ball"]:
    bbox = get_body_bbox(label)
    if bbox:
        x1, y1, x2, y2 = [int(val) for val in bbox]
        print(f"{label} bounding box: {[x1, y1, x2, y2]}")
        # Draw box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        # Put label
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

cv2.imwrite("projected_frame.png", frame)
print("Saved final visualization to projected_frame.png")

sim.close()
