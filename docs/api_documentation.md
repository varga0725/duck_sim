# Open Duck Mini v2 Simulation Bridge: Complete REST API Documentation

This document provides a comprehensive specification of all REST API endpoints exposed by the Open Duck Mini v2 Simulation Bridge. 

The API handles:
1. **Locomotion Control**: Direct motion commands with safety limits.
2. **Perception Stack**: Live camera frames (JPEG), structured object detections, and tracker statistics.
3. **Autonomous Servoing**: Controls for starting, stopping, and tuning the vision-guided target-following stack.

---

## Endpoint Summary Matrix

| Category | Method | Path | Description |
|---|---|---|---|
| **System** | `GET` | `/health` | Fetch API health status, active simulation backend mode. |
| **System** | `GET` | `/camera/info` | Get the camera's resolution, vertical FOV, pinhole intrinsics, and extrinsics coordinates for the active simulation mode. |
| **Control** | `POST` | `/command` | Validate and execute high-level motion command with safety parameters. |
| **Control** | `GET` | `/state` | Retrieve current 3D position, orientation, feet contacts, stability status, safety thresholds, and fall state. |
| **Control** | `POST` | `/stop` | Immediately halt robot motion and reset waddle trajectory. |
| **Control** | `POST` | `/reset` | Teleport the robot back to the initial stable starting coordinate. |
| **Control** | `POST` | `/scenario/walk-square` | Execute a pre-scripted 4-sided square route with safety tracking. |
| **Perception** | `GET` | `/vision/frame` | Stream the raw camera frame (JPEG). |
| **Perception** | `GET` | `/vision/detections` | Get structured list of currently tracked objects with labels and IDs. |
| **Perception** | `GET` | `/vision/state` | Get perception pipeline diagnostics (e.g. running FPS, lag). |
| **Follower** | `POST` | `/vision/follow/start` | Start the autonomous following loop (with optional parameter tuning). |
| **Follower** | `POST` | `/vision/follow/stop` | Stop the follow loop and command the robot to stand still. |
| **Follower** | `GET` | `/vision/follow/status` | Get telemetry, state machine mode, target coordinates, and command offsets. |
| **Map** | `GET` | `/map` | Retrieve the 2D occupancy grid and semantic landmarks mapped by the Spatial World Model. |
| **Map** | `POST` | `/map/reset` | Reset the 2D occupancy grid map and semantic landmarks memory. |

---

## 1. System Endpoints

### `GET /health`
Returns the status of the bridge API and the active simulation backend.

* **Response Model**: `HealthResponse`
* **Response Fields**:
  * `status` (string, `"ok"` or `"error"`): The service health.
  * `sim_mode` (string, `"mock"` or `"real"`): The active simulation backend.
  * `robot` (string): The identifier of the active robot model.

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/health
```

#### Example Response
```json
{
  "status": "ok",
  "sim_mode": "mock",
  "robot": "open_duck_mini_v2"
}
```

---

### `GET /camera/info`
Returns the public camera intrinsics/extrinsics contract for the active simulation mode (`mock`, `real`, or `webcam`).

* **Response Model**: `CameraInfoResponse`
* **Response Fields**:
  * `mode` (string): The active simulation mode (`"mock"`, `"real"`, `"webcam"`).
  * `width` (int): Camera frame width in pixels (`640`).
  * `height` (int): Camera frame height in pixels (`480`).
  * `fovy` (float, optional): Vertical field of view in degrees (e.g. `45.0` in mock/real).
  * `intrinsics` (object, optional): Pinhole camera intrinsics (`fx`, `fy`, `cx`, `cy`).
  * `distortion` (array of floats, optional): Lens distortion parameters (currently null/undistorted).
  * `calibrated` (bool): True if camera parameters are contract-defined and calibrated.
  * `camera_frame` (string): Name of the camera frame (e.g. `"fpv"`, `"mock_camera"`, `"webcam"`).
  * `extrinsics` (object, optional): The transform from the reference frame (`reference_frame`, `translation_m`, `quaternion_wxyz`).

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/camera/info
```

#### Example Response (Real Mode)
```json
{
  "mode": "real",
  "width": 640,
  "height": 480,
  "fovy": 45.0,
  "intrinsics": {
    "fx": 579.4112549695428,
    "fy": 579.4112549695428,
    "cx": 320.0,
    "cy": 240.0
  },
  "distortion": null,
  "calibrated": true,
  "camera_frame": "fpv",
  "extrinsics": {
    "reference_frame": "head_assembly",
    "translation_m": [0.08, 0.0, 0.05],
    "quaternion_wxyz": [0.70710678, 0.0, 0.0, -0.70710678]
  }
}
```

---

## 2. Locomotion Control Endpoints

### `POST /command`
Sends a high-level locomotion command to step the robot forward, backward, or to turn.

* **Request Model**: `RobotCommand`
* **Request Fields**:
  * `command` (string, Required): One of `"walk_forward"`, `"walk_backward"`, `"turn_left"`, `"turn_right"`, `"stop"`, `"reset"`, `"look_around"`.
  * `speed` (float, Default: `0.25`, Min: `0.0`, Max: `1.0`): Locomotion speed scaling factor.
  * `turn` (float, Default: `0.0`, Min: `-1.0`, Max: `1.0`): Turning rate or yaw factor.
  * `duration_sec` (float, Default: `1.0`, Min: `0.1`, Max: `10.0`): Execution duration in seconds.
  * `safety` (Object):
    * `stop_on_fall` (bool, Default: `true`): Halt simulation if the robot falls.
    * `max_pitch_deg` (float, Default: `35.0`): Maximum pitch angle limit.
    * `max_roll_deg` (float, Default: `35.0`): Maximum roll angle limit.

* **Response Model**: `CommandResponse`

#### Curl Example
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"command": "walk_forward", "speed": 0.3, "duration_sec": 2.0}' \
  http://127.0.0.1:8765/command
```

#### Example Response
```json
{
  "accepted": true,
  "command": "walk_forward",
  "mapped_control": {
    "linear_x": 0.3,
    "linear_y": 0.0,
    "yaw": 0.0
  },
  "state": {
    "robot": "open_duck_mini_v2",
    "status": "walking",
    "sim_time": 2.0,
    "position": [0.15, 0.0, 0.41],
    "orientation": {
      "roll_deg": 1.2,
      "pitch_deg": -0.8,
      "yaw_deg": 0.0
    },
    "feet_contact": {
      "left": true,
      "right": false
    },
    "fallen": false,
    "last_command": "walk_forward"
  }
}
```

---

### `GET /state`
Retrieves the full telemetry state of the robot.

* **Response Model**: `RobotState`
* **Response Fields**:
  * `robot` (string): Model name.
  * `status` (string): One of `"idle"`, `"walking"`, `"turning"`, `"stopped"`, `"fallen"`, `"resetting"`.
  * `sim_time` (float): Accumulated simulation time (seconds).
  * `position` (Array of 3 floats): `[X, Y, Z]` position coordinates in meters.
  * `orientation` (Object): Roll, Pitch, and Yaw angles in degrees.
  * `feet_contact` (Object): Left and right feet contact state.
  * `fallen` (bool): True if the safety threshold is breached (fallen status).
  * `last_command` (string): Last received command.

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/state
```

#### Example Response
```json
{
  "robot": "open_duck_mini_v2",
  "status": "idle",
  "sim_time": 4.52,
  "position": [0.0, 0.0, 0.41],
  "orientation": {
    "roll_deg": 0.0,
    "pitch_deg": 0.0,
    "yaw_deg": 0.0
  },
  "feet_contact": {
    "left": true,
    "right": true
  },
  "fallen": false,
  "last_command": "stop"
}
```

---

### `POST /stop`
Immediately halts robot motion and resets waddle trajectory cycles.

* **Response Fields**:
  * `stopped` (bool): True if halted.
  * `state` (`RobotState`): Telemetry following stop.

#### Curl Example
```bash
curl -X POST http://127.0.0.1:8765/stop
```

#### Example Response
```json
{
  "stopped": true,
  "state": {
    "robot": "open_duck_mini_v2",
    "status": "stopped",
    "sim_time": 4.52,
    "position": [0.35, -0.02, 0.41],
    "orientation": {
      "roll_deg": 0.0,
      "pitch_deg": 0.0,
      "yaw_deg": 0.0
    },
    "feet_contact": {
      "left": true,
      "right": true
    },
    "fallen": false,
    "last_command": "stop"
  }
}
```

---

### `POST /reset`
Teleports the robot back to origin, resetting physics simulations.

#### Curl Example
```bash
curl -X POST http://127.0.0.1:8765/reset
```

#### Example Response
```json
{
  "reset": true,
  "state": {
    "robot": "open_duck_mini_v2",
    "status": "idle",
    "sim_time": 0.0,
    "position": [0.0, 0.0, 0.41],
    "orientation": {
      "roll_deg": 0.0,
      "pitch_deg": 0.0,
      "yaw_deg": 0.0
    },
    "feet_contact": {
      "left": true,
      "right": true
    },
    "fallen": false,
    "last_command": "reset"
  }
}
```

---

### `POST /scenario/walk-square`
Executes a pre-scripted 4-sided square route with safety tracking.

* **Response Model**: `ScenarioResponse`

#### Curl Example
```bash
curl -X POST http://127.0.0.1:8765/scenario/walk-square
```

#### Example Response
```json
{
  "scenario": "walk_square",
  "success": true,
  "steps_executed": [
    {
      "command": "walk_forward",
      "duration_sec": 3.0,
      "state": {
        "robot": "open_duck_mini_v2",
        "status": "walking",
        "sim_time": 3.0,
        "position": [0.75, 0.0, 0.41],
        "orientation": { "roll_deg": 0.5, "pitch_deg": -0.2, "yaw_deg": 0.0 },
        "feet_contact": { "left": true, "right": true },
        "fallen": false,
        "last_command": "walk_forward"
      }
    }
  ]
}
```

---

## 3. Visual Perception Endpoints

### `GET /vision/frame`
Returns the latest raw camera frame captured from the active simulator as a JPEG image.

* **Response Content-Type**: `image/jpeg`
* **Response Content**: Raw JPEG binary.

#### Curl Example (Download to file)
```bash
curl -s -o frame.jpg http://127.0.0.1:8765/vision/frame
```

---

### `GET /vision/detections`
Returns a JSON-formatted list of currently tracked objects, complete with 2D bounding boxes and stable tracking IDs.

* **Response Fields**:
  * `objects` (Array of objects):
    * `label` (string): The YOLO object category (e.g., `"person"`, `"chair"`).
    * `confidence` (float): Detection confidence score (0.0 to 1.0).
    * `bbox` (Array of 4 floats): `[x_min, y_min, x_max, y_max]` in pixel coordinates.
    * `tracking_id` (int): Unique persistent identifier assigned by the Centroid Tracker.

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/vision/detections
```

#### Example Response
```json
{
  "objects": [
    {
      "label": "chair",
      "confidence": 0.88,
      "bbox": [170.0, 280.0, 240.0, 400.0],
      "tracking_id": 1
    },
    {
      "label": "person",
      "confidence": 0.93,
      "bbox": [404.0, 170.0, 484.0, 380.0],
      "tracking_id": 2
    }
  ]
}
```

---

### `GET /vision/state`
Returns the status, running framerate, and tracking metrics of the perception thread.

* **Response Fields**:
  * `num_objects` (int): Number of currently visible tracked objects.
  * `tracked_ids` (Array of ints): Active tracked IDs.
  * `labels` (Array of strings): Categories of visible objects.
  * `vision_fps` (float): The actual running rate of the YOLO loop.
  * `last_update_sec` (float): Time since last frame evaluation (seconds).

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/vision/state
```

#### Example Response
```json
{
  "num_objects": 2,
  "tracked_ids": [1, 2],
  "labels": ["person", "chair"],
  "vision_fps": 9.6,
  "last_update_sec": 0.082
}
```

---

## 4. Vision-Guided Target Follower Endpoints

### `POST /vision/follow/start`
Starts the vision-guided target follower. Accepts an optional configuration schema to override defaults and tune visual servoing on the fly.

* **Request Model**: `FollowerConfigSchema` (All fields optional, defaults used if omitted)
* **Request Fields**:
  * `target_label` (string, Default: `"person"`): Bounding box label to follow.
  * `target_id` (int, Default: `-1`): Specific tracking ID to chase. `-1` selects the highest confidence candidate matching `target_label`.
  * `follow_height` (float, Default: `200.0`): Target height of the bounding box (distance proxy in pixels).
  * `height_tolerance` (float, Default: `20.0`): Distance deadzone window (pixels).
  * `center_deadzone` (float, Default: `30.0`): Centering deadzone window (pixels).
  * `deadman_timeout` (float, Default: `1.0`): Failsafe duration to wait when target is lost before halting (seconds).
  * `K_p_yaw` (float, Default: `0.003`): Steering gain factor.
  * `K_p_speed` (float, Default: `0.002`): Speed gain factor.
  * `max_speed` (float, Default: `0.3`): Speed limit (m/s).
  * `max_yaw` (float, Default: `0.8`): Turn rate limit (rad/s).
  * `yaw_smooth_alpha` (float, Default: `0.3`): Smoothing filter coefficient.
  * `search_yaw_speed` (float, Default: `0.4`): Spin rate in rad/s while active search scanning for a lost target.
  * `search_timeout` (float, Default: `15.0`): Search/scan duration in seconds before giving up and stopping.

* **Response Fields**:
  * `status` (string, `"started"`): Confirms start.
  * `follower` (`Object`): Active state telemetry (matches `GET /vision/follow/status`).

#### Curl Example (Default)
```bash
curl -X POST -H "Content-Type: application/json" -d '{}' http://127.0.0.1:8765/vision/follow/start
```

#### Curl Example (Custom Tuning)
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"target_label": "person", "follow_height": 220.0, "max_speed": 0.4, "K_p_yaw": 0.004}' \
  http://127.0.0.1:8765/vision/follow/start
```

#### Example Response
```json
{
  "status": "started",
  "follower": {
    "active": true,
    "state": "SEARCHING",
    "target_id": -1,
    "active_target_id": -1,
    "target_label": "person",
    "error_x": 0.0,
    "error_h": 0.0,
    "last_target_box_height": 0.0,
    "commanded_linear_x": 0.0,
    "commanded_yaw": 0.0,
    "lost_duration_sec": 0.0
  }
}
```

---

### `POST /vision/follow/stop`
Stops the target follower thread and commands the active simulator to immediately halt.

* **Response Fields**:
  * `status` (string, `"stopped"`): Confirms shutdown.
  * `follower` (`Object`): State telemetry (resets commanded controls to zero).

#### Curl Example
```bash
curl -X POST http://127.0.0.1:8765/vision/follow/stop
```

#### Example Response
```json
{
  "status": "stopped",
  "follower": {
    "active": false,
    "state": "STOPPED",
    "target_id": -1,
    "active_target_id": -1,
    "target_label": "person",
    "error_x": 160.0,
    "error_h": -10.0,
    "last_target_box_height": 210.0,
    "commanded_linear_x": 0.0,
    "commanded_yaw": 0.0,
    "lost_duration_sec": 0.0
  }
}
```

---

### `GET /vision/follow/status`
Returns full tracking metrics and command signals computed by the visual servoing control loop.

* **Response Fields**:
  * `active` (bool): True if follow loop thread is running.
  * `state` (string): State machine mode: `"SEARCHING"`, `"TRACKING"`, `"FOLLOWING"`, `"LOST"`, `"STOPPED"`.
  * `target_id` (int): Configured target ID parameter filter.
  * `active_target_id` (int): The tracker ID currently targeted by the controllers.
  * `target_label` (string): Bounding box label filter.
  * `error_x` (float): Offset of target center from frame center (pixels). Positive means target is right.
  * `error_h` (float): Bounding box height error (pixels). Positive means target is too far.
  * `last_target_box_height` (float): Bounding box height proxy reading (pixels).
  * `commanded_linear_x` (float): Command signal sent to speed controller (m/s).
  * `commanded_yaw` (float): Command signal sent to steering controller (rad/s).
  * `lost_duration_sec` (float): Duration the active target has been lost (seconds).

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/vision/follow/status
```

#### Example Response (Active Servoing Trace)
```json
{
  "active": true,
  "state": "TRACKING",
  "target_id": -1,
  "active_target_id": 2,
  "target_label": "person",
  "error_x": 149.0,
  "error_h": -10.0,
  "last_target_box_height": 210.0,
  "commanded_linear_x": 0.0,
  "commanded_yaw": -0.446,
  "lost_duration_sec": 0.0
}
```
* **Interpretation of this Status Trace**: 
  1. The target follower is actively tracking a `"person"` object with tracker ID `2`.
  2. `error_x` is `149.0` (target is significantly to the right). The turn controller commands a proportional right turn: `commanded_yaw = -0.446 rad/s`.
  3. `error_h` is `-10.0` (target height `210.0` is within the distance deadzone of `200.0` with `20.0` tolerance). The speed controller commands the robot to stay stationary (`commanded_linear_x = 0.0 m/s`) to prioritize centering.

---

## 5. Spatial World Mapping Endpoints

### `GET /map`
Returns the 2D occupancy grid matrix and semantic landmarks stored in the Spatial World Model.

* **Response Fields**:
  * `grid` (array of arrays of ints): The 2D grid matrix (0 for free space, 1 for occupied space).
  * `grid_info` (object): Map dimensions, cell size (resolution in meters), and origin coordinate in meters.
  * `landmarks` (array of objects): Mapped landmarks with fields:
    * `label` (string): The landmark label (e.g. `"chair"`, `"table"`, `"ball"`).
    * `tracking_id` (int): The tracking ID.
    * `position_m` (array of 3 floats): `[x, y, z]` global coordinate in meters.
    * `last_seen_time` (float): Time since last update.

#### Curl Example
```bash
curl -s http://127.0.0.1:8765/map
```

#### Example Response
```json
{
  "grid": [
    [0, 0, 0],
    [0, 1, 0]
  ],
  "grid_info": {
    "width": 100,
    "height": 100,
    "resolution_m": 0.05,
    "origin_x_m": -2.5,
    "origin_y_m": -2.5
  },
  "landmarks": [
    {
      "label": "chair",
      "tracking_id": 1,
      "position_m": [1.2, 0.4, 0.2],
      "last_seen_time": 4.52
    }
  ]
}
```

---

### `POST /map/reset`
Resets the 2D occupancy grid and landmark memory.

* **Response Fields**:
  * `status` (string, `"success"`): Confirms reset.
  * `message` (string): Friendly status message.

#### Curl Example
```bash
curl -X POST http://127.0.0.1:8765/map/reset
```

#### Example Response
```json
{
  "status": "success",
  "message": "Map and landmarks reset successfully"
}
```
