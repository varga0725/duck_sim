import math
import time
import logging
from typing import Dict, List, Tuple, Any

logger = logging.getLogger("duck-spatial-world-model")

class SpatialWorldModel:
    """
    Lightweight 2D Occupancy Grid and Semantic Landmark Map.
    Optimized for CPU usage on a Raspberry Pi.
    
    Grid:
    - Default size: 8m x 8m (represented by 80x80 cells)
    - Grid resolution: 0.1m per cell
    - Coordinate origin (0.0, 0.0) is mapped to grid cell (40, 40)
    - Cell values: 0 = Unknown, 1 = Free, 2 = Occupied
    """
    
    def __init__(self, size_m: float = 8.0, resolution: float = 0.1):
        self.size_m = size_m
        self.resolution = resolution
        self.grid_size = int(size_m / resolution)
        self.half_grid = self.grid_size // 2
        
        # Initialize grid (0 = Unknown)
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        
        # Landmarks: label -> {x, y, confidence, last_updated}
        self.landmarks: Dict[str, Dict[str, Any]] = {}
        
        # Real heights of objects in meters to estimate distance from camera bounding box
        self.REAL_HEIGHTS = {
            "chair": 0.6,
            "table": 0.75,
            "sports_ball": 0.22,
            "person": 1.7,
            "ball": 0.22,
        }
        
        # Camera focal length proxy (vertical)
        # Based on H = 480 and fovy = 45 degrees
        self.focal_length = 480.0 / (2.0 * math.tan(math.radians(45.0) / 2.0)) # ~579 pixels
        self.fov_x_rad = math.radians(60.0) # Assume 60 deg horizontal FOV

    def reset(self):
        """Resets the occupancy grid and semantic landmarks."""
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.landmarks.clear()
        logger.info("Spatial World Model reset.")

    def world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Converts world coordinates (x, y) in meters to grid indices (gx, gy)."""
        gx = int(x / self.resolution) + self.half_grid
        gy = int(y / self.resolution) + self.half_grid
        # Clamp to grid bounds
        gx = max(0, min(self.grid_size - 1, gx))
        gy = max(0, min(self.grid_size - 1, gy))
        return gx, gy

    def grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        """Converts grid indices (gx, gy) to world coordinates (x, y) in meters."""
        x = (gx - self.half_grid) * self.resolution + (self.resolution / 2.0)
        y = (gy - self.half_grid) * self.resolution + (self.resolution / 2.0)
        return x, y

    def update(self, robot_x: float, robot_y: float, robot_yaw_deg: float, detections: List[Dict[str, Any]], img_w: int = 640, img_h: int = 480):
        """
        Updates grid occupancy and landmark memory using robot pose and YOLO detections.
        """
        # 1. Update robot cell as free
        rgx, rgy = self.world_to_grid(robot_x, robot_y)
        self.grid[rgy][rgx] = 1 # Mark robot spot as free
        
        # 2. Process each detection
        for det in detections:
            label = det.get("label", "").lower()
            conf = det.get("confidence", 0.0)
            bbox = det.get("bbox", [0, 0, 0, 0])
            center = det.get("center", [0, 0])
            
            # Avoid processing if confidence is too low
            if conf < 0.4:
                continue
                
            # Skip if we don't have a height model for the label
            real_h = self.REAL_HEIGHTS.get(label)
            if not real_h:
                # Use default object height if unknown
                real_h = 0.5
                
            x1, y1, x2, y2 = bbox
            box_height = max(1.0, y2 - y1)
            cx, cy = center
            
            # Estimate distance d (meters)
            distance = (self.focal_length * real_h) / box_height
            
            # Estimate relative bearing angle (radians)
            ex = cx - (img_w / 2.0)
            bearing_rad = - (ex / (img_w / 2.0)) * (self.fov_x_rad / 2.0)
            
            # Global yaw of the robot
            yaw_rad = math.radians(robot_yaw_deg)
            total_angle = yaw_rad + bearing_rad
            
            # Global coordinate calculation
            x_obj = robot_x + distance * math.cos(total_angle)
            y_obj = robot_y + distance * math.sin(total_angle)
            
            # 3. Update Landmark Memory with Exponential Moving Average (EMA) filtering
            if label not in self.landmarks:
                self.landmarks[label] = {
                    "x": x_obj,
                    "y": y_obj,
                    "confidence": conf,
                    "last_updated": time.time()
                }
            else:
                alpha = 0.20 # Smooth factor (weight of new observation)
                self.landmarks[label]["x"] = (1 - alpha) * self.landmarks[label]["x"] + alpha * x_obj
                self.landmarks[label]["y"] = (1 - alpha) * self.landmarks[label]["y"] + alpha * y_obj
                self.landmarks[label]["confidence"] = max(self.landmarks[label]["confidence"], conf)
                self.landmarks[label]["last_updated"] = time.time()
                
            # 4. Raycast in Occupancy Grid (Bresenham's algorithm)
            tgx, tgy = self.world_to_grid(x_obj, y_obj)
            self._raycast_free_line(rgx, rgy, tgx, tgy)
            
            # 5. Mark target cell and neighbors as occupied
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    ny = tgy + dy
                    nx = tgx + dx
                    if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                        self.grid[ny][nx] = 2

    def _raycast_free_line(self, x0: int, y0: int, x1: int, y1: int):
        """
        Traces a line from (x0, y0) to (x1, y1) in grid coordinates,
        marking cells along the path as Free (1).
        Does not overwrite Occupied (2) cells to preserve map details.
        """
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        cx, cy = x0, y0
        while True:
            # Avoid marking target point itself as free
            if cx == x1 and cy == y1:
                break
                
            if 0 <= cx < self.grid_size and 0 <= cy < self.grid_size:
                if self.grid[cy][cx] != 2: # Keep occupied cells occupied
                    self.grid[cy][cx] = 1
                    
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                cx += sx
            if e2 < dx:
                err += dx
                cy += sy
                
            if cx == x1 and cy == y1:
                break

    def get_map_data(self) -> Dict[str, Any]:
        """Returns the serialized map and landmarks."""
        return {
            "grid_size": self.grid_size,
            "resolution": self.resolution,
            "landmarks": self.landmarks,
            "grid": self.grid
        }
