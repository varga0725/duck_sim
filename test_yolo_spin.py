import os
import sys
import cv2
import numpy as np
import time
import mujoco

os.environ["DUCK_SIM_MODE"] = "real"
sys.path.append("external/Open_Duck_Playground")

from duck_agent_sim.simulator.duck_sim import RealDuckSimulator
from duck_agent_sim.vision.yolo_detector import YOLODetector
from duck_agent_sim.vision.camera import CameraDevice

print("Initializing RealDuckSimulator (headless=True)...")
sim = RealDuckSimulator(headless=True)
sim.reset()
time.sleep(0.5)

camera = CameraDevice(sim)
detector = YOLODetector(conf_threshold=0.1)

# We want to rotate the robot's base yaw in qpos
# Root joint qpos indices:
# 0, 1, 2: 3D position (x, y, z)
# 3, 4, 5, 6: quaternion (w, x, y, z)

for angle_deg in range(0, 360, 20):
    angle_rad = np.deg2rad(angle_deg)
    
    # Calculate quaternion for yaw rotation
    qw = np.cos(angle_rad / 2.0)
    qx = 0.0
    qy = 0.0
    qz = np.sin(angle_rad / 2.0)
    
    with sim._lock:
        # Set yaw
        sim.data.qpos[3:7] = [qw, qx, qy, qz]
        # Clear velocities to keep it stable
        sim.data.qvel[:] = 0.0
        # Step physics to update render positions
        mujoco.mj_forward(sim.model, sim.data)
        
    # Capture and detect
    frame = camera.capture_frame()
    detections = detector.detect(frame)
    
    if len(detections) > 0:
        print(f"--- Angle {angle_deg} degrees ---")
        for i, d in enumerate(detections):
            print(f"  [{i}] Label: {d['label']}, Confidence: {d['confidence']:.4f}, Center: {d['center']}")
        # Save a sample detection frame
        cv2.imwrite(f"detected_{angle_deg}.png", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

print("Scan complete.")
sim.close()
