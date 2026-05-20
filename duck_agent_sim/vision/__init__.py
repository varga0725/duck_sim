from typing import List, Dict, Any, Optional
from duck_agent_sim.vision.perception_state import PerceptionState
from duck_agent_sim.vision.follower import VisionGuidedFollower

# Global perception state instance
perception_state = PerceptionState()

# Global follower instance
follower = VisionGuidedFollower(perception_state)

def get_visible_objects() -> List[Dict[str, Any]]:
    """Returns the latest list of tracked object detections."""
    return perception_state.get_detections()

def find_object(label: str) -> Optional[Dict[str, Any]]:
    """Finds the highest-confidence object matching the specified label."""
    objs = get_visible_objects()
    matching = [obj for obj in objs if obj["label"].lower() == label.lower()]
    if not matching:
        return None
    return max(matching, key=lambda x: x["confidence"])

def get_tracking_target(target_id: int) -> Optional[Dict[str, Any]]:
    """Returns the object matching the specific tracking ID."""
    objs = get_visible_objects()
    for obj in objs:
        if obj.get("tracking_id") == target_id:
            return obj
    return None
