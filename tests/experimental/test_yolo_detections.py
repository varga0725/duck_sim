import os
import sys
import cv2
import numpy as np
import time

os.environ["DUCK_SIM_MODE"] = "real"
sys.path.append("external/Open_Duck_Playground")

from duck_agent_sim.simulator.duck_sim import RealDuckSimulator
from duck_agent_sim.vision.yolo_detector import YOLODetector
from duck_agent_sim.vision.camera import CameraDevice

print("Initializing RealDuckSimulator (headless=True)...")
sim = RealDuckSimulator(headless=True)
sim.reset()

# Wait a second for background physics thread to start and stabilize
time.sleep(1.0)

camera = CameraDevice(sim)
detector = YOLODetector(conf_threshold=0.1)

print("Capturing frame...")
frame = camera.capture_frame()

print("Running YOLO detection...")
detections = detector.detect(frame)

print(f"Total detections: {len(detections)}")
for i, d in enumerate(detections):
    print(f"[{i}] Label: {d['label']}, Confidence: {d['confidence']:.4f}, Center: {d['center']}")

# Save the frame
cv2.imwrite("fpv_test_frame.png", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
print("Saved FPV frame to fpv_test_frame.png")

sim.close()
