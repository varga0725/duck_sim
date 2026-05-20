import numpy as np
from typing import List, Dict

class CentroidTracker:
    """
    Lightweight Nearest-Center Centroid Tracker.
    Assigns and maintains stable tracking IDs for detected objects between frames.
    """
    def __init__(self, max_distance: float = 100.0):
        self.next_id = 1
        self.tracked_objects: Dict[int, np.ndarray] = {}
        self.max_distance = max_distance
        
    def update(self, detections: List[Dict]) -> List[Dict]:
        """
        Updates tracked object states with new detections and assigns tracking IDs.
        Modifies the detections in-place.
        """
        if not detections:
            return detections
            
        input_centers = np.array([det["center"] for det in detections])
        
        # If tracker has no objects, register all detections as new
        if not self.tracked_objects:
            for i, det in enumerate(detections):
                det["tracking_id"] = self.next_id
                self.tracked_objects[self.next_id] = input_centers[i]
                self.next_id += 1
            return detections
            
        object_ids = list(self.tracked_objects.keys())
        object_centers = np.array(list(self.tracked_objects.values()))
        
        # Compute pairwise Euclidean distance between existing tracking centers and incoming centers
        # shape: (num_tracked, num_detected)
        dists = np.linalg.norm(object_centers[:, np.newaxis] - input_centers, axis=2)
        
        matched_inputs = set()
        matched_objects = set()
        
        # Match centers greedily starting from smallest distance
        for _ in range(min(len(object_ids), len(detections))):
            if dists.size == 0:
                break
            min_idx = np.argmin(dists)
            obj_idx, inp_idx = np.unravel_index(min_idx, dists.shape)
            
            dist = dists[obj_idx, inp_idx]
            if dist < self.max_distance:
                obj_id = object_ids[obj_idx]
                detections[inp_idx]["tracking_id"] = obj_id
                self.tracked_objects[obj_id] = input_centers[inp_idx]
                matched_inputs.add(inp_idx)
                matched_objects.add(obj_id)
                
                # Invalidate matched rows and columns to prevent multiple matches
                dists[obj_idx, :] = np.inf
                dists[:, inp_idx] = np.inf
            else:
                # Smallest distance exceeds threshold, stop matching
                break
                
        # Register remaining unmatched detections as new objects
        for inp_idx in range(len(detections)):
            if inp_idx not in matched_inputs:
                detections[inp_idx]["tracking_id"] = self.next_id
                self.tracked_objects[self.next_id] = input_centers[inp_idx]
                self.next_id += 1
                
        # Deregister any objects that disappeared
        for obj_id in list(self.tracked_objects.keys()):
            if obj_id not in matched_objects:
                del self.tracked_objects[obj_id]
                
        return detections
