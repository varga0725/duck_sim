import os
import time
import math
import torch
import threading
from ultralytics import YOLO

class YOLODetector:
    """
    Singleton YOLO Object Detector.
    Lazily loads YOLO11 (defaults to yolo11n) or other models and runs inference on CPU/GPU.
    Supports mock detection outputs in simulation mock mode to ensure quick test feedback.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(YOLODetector, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
            
    def __init__(self, model_name: str = "yolo11n.pt", conf_threshold: float = 0.5, img_sz: int = 640):
        if self._initialized:
            return
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        self.img_sz = img_sz
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = None
        self._lock = threading.RLock()
        self._initialized = True
        
    def _load_model(self):
        with self._lock:
            if self._model is None:
                self._model = YOLO(self.model_name)
                self._model.to(self.device)
                
    def detect(self, frame) -> list:
        """Runs YOLO object detection on the provided RGB frame."""
        sim_mode = os.getenv("DUCK_SIM_MODE", "mock").lower()
        if sim_mode == "mock":
            return self._detect_mock()
            
        self._load_model()
        with self._lock:
            results = self._model(frame, conf=self.conf_threshold, imgsz=self.img_sz, device=self.device, verbose=False)
        detections = []
        if results:
            result = results[0]
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                label = result.names[cls_id]
                conf = float(box.conf[0])
                xyxy = box.xyxy[0].tolist()
                
                x1, y1, x2, y2 = xyxy
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0
                
                detections.append({
                    "label": label,
                    "confidence": round(conf, 4),
                    "bbox": [round(x, 1) for x in xyxy],
                    "center": [round(cx, 1), round(cy, 1)],
                    "tracking_id": -1
                })
                
        # If in real sim mode, augment with 3D projection of static/free objects in the scene
        if sim_mode == "real":
            projected = self._detect_real_projected(frame)
            detections.extend(projected)
            
        return detections

    def _detect_real_projected(self, frame) -> list:
        """Ground-truth project simulated geoms for target bodies in the MuJoCo scene."""
        detections = []
        try:
            from duck_agent_sim.simulator.instance import active_simulator
            import mujoco
            import numpy as np
            
            if not hasattr(active_simulator, "model") or not hasattr(active_simulator, "data"):
                return detections
                
            model = active_simulator.model
            data = active_simulator.data
            
            with active_simulator._lock:
                try:
                    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "fpv")
                except Exception:
                    # Fallback if name lookup fails
                    cam_id = 0
                    
                h, w, _ = frame.shape
                fovy = model.vis.global_.fovy
                f_y = h / (2.0 * math.tan(math.radians(fovy) / 2.0))
                f_x = f_y
                
                cam_pos = data.cam_xpos[cam_id]
                cam_mat = data.cam_xmat[cam_id].reshape(3, 3)
                
                for label in ["chair", "table", "sports_ball", "person"]:
                    try:
                        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, label)
                    except Exception:
                        continue
                        
                    geom_start = model.body_geomadr[body_id]
                    geom_count = model.body_geomnum[body_id]
                    
                    pts_cam = []
                    for i in range(geom_start, geom_start + geom_count):
                        g_type = model.geom_type[i]
                        g_pos = data.geom_xpos[i]
                        g_mat = data.geom_xmat[i].reshape(3, 3)
                        g_size = model.geom_size[i]
                        
                        local_verts = []
                        if g_type == mujoco.mjtGeom.mjGEOM_BOX:
                            dx, dy, dz = g_size
                            for sx in [-1, 1]:
                                for sy in [-1, 1]:
                                    for sz in [-1, 1]:
                                        local_verts.append(np.array([sx*dx, sy*dy, sz*dz]))
                        elif g_type == mujoco.mjtGeom.mjGEOM_SPHERE:
                            r = g_size[0]
                            for axis in range(3):
                                for sign in [-1, 1]:
                                    v = np.zeros(3)
                                    v[axis] = sign * r
                                    local_verts.append(v)
                        elif g_type in [mujoco.mjtGeom.mjGEOM_CAPSULE, mujoco.mjtGeom.mjGEOM_CYLINDER]:
                            r, hh = g_size[:2]
                            for sz in [-hh, hh]:
                                local_verts.append(np.array([0.0, 0.0, sz]))
                                for axis in [0, 1]:
                                    for sign in [-1, 1]:
                                        v = np.zeros(3)
                                        v[axis] = sign * r
                                        v[2] = sz
                                        local_verts.append(v)
                        else:
                            local_verts.append(np.zeros(3))
                            
                        for lv in local_verts:
                            w_vert = g_pos + g_mat @ lv
                            c_vert = cam_mat.T @ (w_vert - cam_pos)
                            pts_cam.append(c_vert)
                            
                    # Project to screen coordinates
                    pxs = []
                    pys = []
                    for pt in pts_cam:
                        depth = -pt[2]
                        if depth > 0.05:  # clip near plane
                            px = (pt[0] / depth) * f_x + (w / 2.0)
                            py = (h / 2.0) - (pt[1] / depth) * f_y
                            pxs.append(px)
                            pys.append(py)
                            
                    if not pxs:
                        continue
                        
                    xmin = max(0.0, min(pxs))
                    ymin = max(0.0, min(pys))
                    xmax = min(float(w), max(pxs))
                    ymax = min(float(h), max(pys))
                    
                    if xmax > xmin and ymax > ymin:
                        cx = (xmin + xmax) / 2.0
                        cy = (ymin + ymax) / 2.0
                        
                        detections.append({
                            "label": label,
                            "confidence": 0.99,
                            "bbox": [round(xmin, 1), round(ymin, 1), round(xmax, 1), round(ymax, 1)],
                            "center": [round(cx, 1), round(cy, 1)],
                            "tracking_id": -1
                        })
        except Exception as e:
            # Fallback if any unexpected exception occurs
            pass
        return detections

    def _detect_mock(self) -> list:
        """Generates dynamic mock detections by projecting static classroom landmarks based on the robot's pose."""
        try:
            from duck_agent_sim.simulator.instance import active_simulator
            state = active_simulator.get_state()
            robot_x = state.position[0]
            robot_y = state.position[1]
            robot_yaw_deg = state.orientation.yaw_deg
        except Exception:
            robot_x = 0.0
            robot_y = 0.0
            robot_yaw_deg = 0.0

        # Define static mock objects in world space: (label, x, y, real_height)
        static_objects = [
            ("chair", 1.5, 0.5, 0.6),
            ("sports_ball", 1.0, -0.3, 0.22),
            ("person", 2.5, 0.0, 1.7)
        ]

        detections = []
        img_w = 640
        img_h = 480
        
        # Camera model specs
        fovy = 45.0
        focal_length = img_h / (2.0 * math.tan(math.radians(fovy) / 2.0)) # ~579.4
        fov_x_rad = math.radians(60.0)
        fov_half = fov_x_rad / 2.0
        
        yaw_rad = math.radians(robot_yaw_deg)
        
        for label, obj_x, obj_y, real_h in static_objects:
            dx = obj_x - robot_x
            dy = obj_y - robot_y
            distance = math.hypot(dx, dy)
            
            # Skip if object is too close (behind near plane) or too far to detect
            if distance < 0.1 or distance > 5.0:
                continue
                
            # Angle of object in world frame
            angle_to_obj = math.atan2(dy, dx)
            
            # Bearing relative to robot's heading
            bearing = angle_to_obj - yaw_rad
            # Normalize bearing to [-pi, pi]
            bearing = (bearing + math.pi) % (2.0 * math.pi) - math.pi
            
            # Check if within horizontal FOV
            if abs(bearing) <= fov_half:
                # Calculate horizontal screen position
                cx = (img_w / 2.0) - (bearing / fov_half) * (img_w / 2.0)
                
                # Calculate vertical box size using pinhole height projection
                box_height = (focal_length * real_h) / distance
                
                # Estimate vertical screen center (closer objects sit lower in the frame)
                cy = 240.0 + (100.0 / distance)
                
                # Clamp vertical center to prevent box going completely off-screen
                cy = max(box_height / 2.0 + 10, min(img_h - box_height / 2.0 - 10, cy))
                
                # Assume a fixed aspect ratio of 0.8 for width/height
                box_width = box_height * 0.8
                
                x1 = cx - box_width / 2.0
                y1 = cy - box_height / 2.0
                x2 = cx + box_width / 2.0
                y2 = cy + box_height / 2.0
                
                # Clamp bounding boxes to image frame
                x1 = max(0.0, min(float(img_w), x1))
                y1 = max(0.0, min(float(img_h), y1))
                x2 = max(0.0, min(float(img_w), x2))
                y2 = max(0.0, min(float(img_h), y2))
                
                if x2 > x1 and y2 > y1:
                    detections.append({
                        "label": label,
                        "confidence": 0.90,
                        "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                        "center": [round(cx, 1), round(cy, 1)],
                        "tracking_id": -1
                    })
                    
        return detections

