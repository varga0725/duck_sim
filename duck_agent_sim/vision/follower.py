import time
import logging
import threading
from typing import Dict, Any, List, Optional
from enum import Enum

from duck_agent_sim.schemas import ControlIntent, SafetyConfig
from duck_agent_sim.vision.perception_state import PerceptionState

logger = logging.getLogger("duck-agent-sim-follower")


def _publish_follower_stop() -> None:
    from duck_agent_sim.simulator.instance import active_simulator

    active_simulator.set_desired_control(
        ControlIntent(linear_x=0.0, linear_y=0.0, yaw=0.0),
        SafetyConfig(),
        command="vision_follow_stop",
        duration_sec=0.2,
    )

class FollowerState(str, Enum):
    SEARCHING = "SEARCHING"
    TRACKING = "TRACKING"
    FOLLOWING = "FOLLOWING"
    LOST = "LOST"
    STOPPED = "STOPPED"

class VisionGuidedFollower:
    """
    Real-time vision-guided servoing controller and navigation stack.
    Operates on a background thread to compute proportional turning rates and linear speeds
    from YOLO-tracked target bounding boxes, providing smooth waddling locomotion following.
    """
    def __init__(self, state_repo: PerceptionState):
        self.state_repo = state_repo
        self._lock = threading.RLock()
        
        # Thread & lifecycle control
        self.running = False
        self._thread: Optional[threading.Thread] = None
        
        # Servoing states
        self.state = FollowerState.STOPPED
        self.current_linear_x = 0.0
        self.current_yaw = 0.0
        self.error_x = 0.0
        self.error_h = 0.0
        self.last_target_box_height = 0.0
        self.active_target_id = -1
        self.lost_since: Optional[float] = None
        self.last_seen_direction = 1.0  # 1.0 for left/positive, -1.0 for right/negative
        
        # Configuration parameters
        self.target_label = "person"
        self.target_id = -1  # -1 means follow any/first person detected
        self.follow_height = 200.0  # Desired bounding box height in pixels (distance proxy)
        self.height_tolerance = 20.0  # Deadzone around height (pixels)
        self.center_deadzone = 30.0  # Centering deadzone (pixels)
        self.deadman_timeout = 1.0  # Max seconds before stopping if lost
        
        # Controller gains
        self.K_p_yaw = 0.003
        self.K_p_speed = 0.002
        self.max_speed = 0.3
        self.max_yaw = 0.8
        self.yaw_smooth_alpha = 0.3  # Exponential smoothing filter
        self.search_yaw_speed = 0.4  # Spin rate while searching for a lost target
        self.search_timeout = 15.0   # Search/scan duration in seconds before giving up
        
    def configure(self, config: Dict[str, Any]):
        """Configures the controller parameters thread-safely."""
        with self._lock:
            if "target_label" in config:
                self.target_label = str(config["target_label"])
            if "target_id" in config:
                self.target_id = int(config["target_id"])
            if "follow_height" in config:
                self.follow_height = float(config["follow_height"])
            if "height_tolerance" in config:
                self.height_tolerance = float(config["height_tolerance"])
            if "center_deadzone" in config:
                self.center_deadzone = float(config["center_deadzone"])
            if "deadman_timeout" in config:
                self.deadman_timeout = float(config["deadman_timeout"])
            if "K_p_yaw" in config:
                self.K_p_yaw = float(config["K_p_yaw"])
            if "K_p_speed" in config:
                self.K_p_speed = float(config["K_p_speed"])
            if "max_speed" in config:
                self.max_speed = float(config["max_speed"])
            if "max_yaw" in config:
                self.max_yaw = float(config["max_yaw"])
            if "yaw_smooth_alpha" in config:
                self.yaw_smooth_alpha = float(config["yaw_smooth_alpha"])
            if "search_yaw_speed" in config:
                self.search_yaw_speed = float(config["search_yaw_speed"])
            if "search_timeout" in config:
                self.search_timeout = float(config["search_timeout"])
            logger.info(f"Target follower configured: {config}")

    def start(self):
        """Starts the background target following thread."""
        with self._lock:
            if self.running:
                return
            self.running = True
            self.state = FollowerState.SEARCHING
            self.lost_since = None
            self.current_linear_x = 0.0
            self.current_yaw = 0.0
            self.active_target_id = -1
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="VisionFollowerLoop")
            self._thread.start()
            logger.info("Vision-guided follower loop thread started.")

    def stop(self):
        """Stops the target follower thread and halts the simulator."""
        with self._lock:
            self.running = False
            self.state = FollowerState.STOPPED
            self.current_linear_x = 0.0
            self.current_yaw = 0.0
            self.active_target_id = -1
            
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            
        # Publish a zero desired control without stepping physics directly.
        try:
            _publish_follower_stop()
        except Exception as e:
            logger.error(f"Failed to issue simulator stop command during follower shutdown: {e}")
        logger.info("Vision-guided follower loop thread stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and telemetry of the follower system."""
        with self._lock:
            return {
                "active": self.running,
                "state": self.state.value,
                "target_id": self.target_id,
                "active_target_id": self.active_target_id,
                "target_label": self.target_label,
                "error_x": round(self.error_x, 1),
                "error_h": round(self.error_h, 1),
                "last_target_box_height": round(self.last_target_box_height, 1),
                "commanded_linear_x": round(self.current_linear_x, 3),
                "commanded_yaw": round(self.current_yaw, 3),
                "lost_duration_sec": round(time.time() - self.lost_since, 2) if self.lost_since else 0.0
            }

    def _run_loop(self):
        from duck_agent_sim.simulator.instance import active_simulator
        dt = 0.1  # Loop period (10Hz)
        prev_yaw = 0.0
        
        while self.running:
            start_time = time.time()
            try:
                # 1. Fetch tracked objects
                detections = self.state_repo.get_detections()
                width = self.state_repo.width if self.state_repo.width > 0 else 640
                
                # 2. Target selection matching criteria
                target = self._find_target(detections)
                
                linear_x_target = 0.0
                yaw_target = 0.0
                
                if target is not None:
                    # Target acquired/tracked
                    self.lost_since = None
                    self.active_target_id = target.get("tracking_id", -1)
                    
                    # Bounding Box calculations
                    x1, y1, x2, y2 = target["bbox"]
                    box_height = y2 - y1
                    self.last_target_box_height = box_height
                    cx, cy = target["center"]
                    
                    # Compute errors
                    self.error_x = cx - (width / 2.0)
                    self.error_h = self.follow_height - box_height
                    
                    # State machine & Speed Control
                    if abs(self.error_h) <= self.height_tolerance:
                        self.state = FollowerState.TRACKING
                        # In deadzone, keep it centered but stationary or minor speed
                        linear_x_target = 0.0
                    else:
                        self.state = FollowerState.FOLLOWING
                        # Proportional speed with target box height proxy
                        # If box_height < follow_height: error_h > 0 -> walk forward
                        # If box_height > follow_height: error_h < 0 -> walk backward slowly
                        linear_x_target = self.K_p_speed * self.error_h
                        
                        # Clip forward and backward limits
                        if linear_x_target > 0.0:
                            linear_x_target = min(self.max_speed, linear_x_target)
                        else:
                            # Back up slowly if too close
                            linear_x_target = max(-0.15, linear_x_target)
                            
                    # Turn Controller with centering deadzone and max yaw clamp
                    if abs(self.error_x) <= self.center_deadzone:
                        yaw_target = 0.0
                    else:
                        # error_x > 0 means target right -> turn right (negative yaw)
                        # error_x < 0 means target left -> turn left (positive yaw)
                        yaw_target = -self.K_p_yaw * self.error_x
                        yaw_target = max(-self.max_yaw, min(self.max_yaw, yaw_target))
                        
                        # Save last seen direction based on yaw_target sign to guide active searching
                        if yaw_target != 0.0:
                            self.last_seen_direction = 1.0 if yaw_target > 0.0 else -1.0
                        
                        # Slowdown linear speed during aggressive turns to prioritize centering
                        if abs(self.error_x) > 2 * self.center_deadzone:
                            linear_x_target *= 0.4
                else:
                    # Target lost
                    self.active_target_id = -1
                    self.error_x = 0.0
                    self.error_h = 0.0
                    
                    if self.lost_since is None:
                        self.lost_since = time.time()
                        self.state = FollowerState.SEARCHING
                        logger.warning("Target lost! Initiating active search scanning...")
                        
                    lost_duration = time.time() - self.lost_since
                    if lost_duration >= self.search_timeout:
                        logger.warning(f"Search timeout of {self.search_timeout}s reached. Stopping follower and terminating thread.")
                        self.state = FollowerState.STOPPED
                        linear_x_target = 0.0
                        yaw_target = 0.0
                        self.running = False  # Terminate background thread loop so it can be cleanly restarted
                        _publish_follower_stop()
                    else:
                        # Active searching: spin on the spot in the direction last seen
                        self.state = FollowerState.SEARCHING
                        linear_x_target = 0.0
                        yaw_target = self.search_yaw_speed * self.last_seen_direction
                        
                # 3. Apply low-pass exponential smoothing filter to Turn Rate
                yaw_smoothed = self.yaw_smooth_alpha * prev_yaw + (1.0 - self.yaw_smooth_alpha) * yaw_target
                prev_yaw = yaw_smoothed
                
                with self._lock:
                    self.current_linear_x = linear_x_target
                    self.current_yaw = yaw_smoothed
                    
                # 4. Publish desired control. The simulator-owned timing loop
                # advances physics; follower must not call step().
                if self.state != FollowerState.STOPPED:
                    control = ControlIntent(
                        linear_x=self.current_linear_x,
                        linear_y=0.0,
                        yaw=self.current_yaw
                    )
                    active_simulator.set_desired_control(
                        control,
                        SafetyConfig(),
                        command="vision_follow",
                        duration_sec=dt * 1.5,
                    )
                    
            except Exception as e:
                logger.error(f"Error in follower control loop: {e}", exc_info=True)
                
            elapsed = time.time() - start_time
            sleep_time = max(0.01, dt - elapsed)
            time.sleep(sleep_time)
            
    def _find_target(self, detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Filters detections to find matching target label and ID."""
        candidates = [d for d in detections if d["label"].lower() == self.target_label.lower()]
        if not candidates:
            return None
            
        with self._lock:
            target_id = self.target_id
            
        if target_id >= 0:
            # Look for exact tracking ID match
            for cand in candidates:
                if cand.get("tracking_id") == target_id:
                    return cand
            return None
        else:
            # Default behavior: choose highest confidence person
            return max(candidates, key=lambda x: x["confidence"])
