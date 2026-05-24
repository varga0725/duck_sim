import math
import time
import logging
import json
import re
from typing import Optional, Tuple, Dict, Any

from duck_agent_sim.agent.hermes_client import HermesRobotClient
from duck_agent_sim.agent.hermes_delegator import HermesDelegator, HermesMode
from duck_agent_sim.agent.smart_router import SmartRouter, Intent
from duck_agent_sim.agent.direct_controller import DirectController
from duck_agent_sim.agent.agent_response import AgentResponse
from duck_agent_sim.agent.a2a_protocol import A2ARequest, A2AResponse, A2ARobotState, A2ASpatialModel, A2ALandmark

logger = logging.getLogger("local-duck-agent")

class LocalDuckAgent:
    """
    Local agent running on the robot. Integrates the SpatialWorldModel 
    and handles A2A communication with Hermes.
    """
    def __init__(self, bridge_url: str = "http://127.0.0.1:8765", hermes_mode: HermesMode = "oneshot"):
        self.bridge_url = bridge_url
        self.client = HermesRobotClient(base_url=bridge_url)
        self.hermes = HermesDelegator(mode=hermes_mode)
        self.router = SmartRouter()
        self.direct = DirectController(bridge_url=bridge_url)
        
    async def start(self):
        await self.hermes.start()
        logger.info("LocalDuckAgent started (bridge=%s, hermes_mode=%s)", self.bridge_url, self.hermes.mode)
        
    async def stop(self):
        await self.client.close()
        await self.direct.close()
        await self.hermes.stop()
        logger.info("LocalDuckAgent stopped.")
        
    def _extract_landmark_target(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        if any(k in text_lower for k in ["szék", "szek"]):
            return "chair"
        if any(k in text_lower for k in ["asztal"]):
            return "table"
        if any(k in text_lower for k in ["labda", "ball", "focilabda"]):
            return "sports_ball"
        if any(k in text_lower for k in ["ember", "személy", "person"]):
            return "person"
        return None

    def _is_navigation_command(self, text: str) -> bool:
        text_lower = text.lower()
        # Look for navigation/following verbs
        verbs = ["menj", "kövesd", "kovesd", "keresd", "irány", "irany", "haladj", "sétálj", "setalj"]
        has_verb = any(v in text_lower for v in verbs)
        has_target = self._extract_landmark_target(text_lower) is not None
        return has_verb and has_target

    def _extract_json(self, text: str) -> Optional[dict]:
        # Try looking for a json code block
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        # Try parsing the whole text
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try extracting anything that looks like a JSON object {...}
        match = re.search(r"(\{.*?\})", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return None

    async def _evaluate_obstacle_close(self, map_data: Dict[str, Any], rx: float, ry: float) -> bool:
        grid = map_data.get("grid")
        if not grid:
            return False
        
        resolution = map_data.get("resolution", 0.1)
        grid_size = map_data.get("grid_size", 80)
        half_grid = grid_size // 2
        
        # Convert robot to grid coords
        rgx = int(rx / resolution) + half_grid
        rgy = int(ry / resolution) + half_grid
        
        # Check within 0.5m radius (5 cells)
        radius = 5
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                ny = rgy + dy
                nx = rgx + dx
                if 0 <= nx < grid_size and 0 <= ny < grid_size:
                    if grid[ny][nx] == 2: # Occupied
                        return True
        return False

    async def process(self, text: str) -> AgentResponse:
        t0 = time.perf_counter()
        
        # 1. Check if the input is a local navigation command for an already-mapped landmark
        if self._is_navigation_command(text):
            target_label = self._extract_landmark_target(text)
            if target_label:
                try:
                    map_data = await self.client.get_map()
                    landmarks = map_data.get("landmarks", {})
                    
                    # Get current state
                    state = await self.client.get_state()
                    rx, ry, _ = state.position
                    ryaw = state.orientation.yaw_deg
                    
                    # Search matches using prefix matching and find the closest instance
                    matching_instances = []
                    for k, v in landmarks.items():
                        base_k = k.split('_')[0] if '_' in k else k
                        if base_k == target_label:
                            dist = math.hypot(v["x"] - rx, v["y"] - ry)
                            matching_instances.append((dist, v))
                            
                    if matching_instances:
                        # Sort by distance and pick closest
                        matching_instances.sort(key=lambda item: item[0])
                        lm = matching_instances[0][1]
                        tx, ty = lm["x"], lm["y"]
                        
                        # Calculate steering direction and distance
                        dx = tx - rx
                        dy = ty - ry
                        dist = math.hypot(dx, dy)
                        target_yaw_rad = math.atan2(dy, dx)
                        target_yaw_deg = math.degrees(target_yaw_rad)
                        
                        diff_yaw = target_yaw_deg - ryaw
                        # Normalize to [-180, 180]
                        diff_yaw = (diff_yaw + 180) % 360 - 180
                        
                        if dist < 0.3:
                            # Arrived
                            response_state = await self.client.stop()
                            elapsed = (time.perf_counter() - t0) * 1000
                            return AgentResponse(
                                action="stop",
                                source="direct",
                                robot_state=response_state,
                                speech=f"Megérkeztem a {target_label} közelébe. Távolság: {dist:.2f} méter.",
                                latency_ms=round(elapsed, 2)
                            )
                        elif abs(diff_yaw) > 15.0:
                            # Turn
                            direction = "turn_left" if diff_yaw > 0 else "turn_right"
                            turn_val = 0.4 if diff_yaw > 0 else -0.4
                            duration = min(1.5, abs(diff_yaw) / 45.0)
                            response = await self.client.send_command(
                                command=direction,
                                speed=0.0,
                                turn=turn_val,
                                duration_sec=duration
                            )
                            elapsed = (time.perf_counter() - t0) * 1000
                            return AgentResponse(
                                action=direction,
                                source="direct",
                                robot_state=response.state,
                                speech=f"Fordulok a {target_label} felé ({diff_yaw:.1f} fok eltérés).",
                                latency_ms=round(elapsed, 2)
                            )
                        else:
                            # Walk forward
                            speed_val = min(0.3, dist / 2.0)
                            turn_val = (diff_yaw / 15.0) * 0.1
                            duration = min(2.0, dist / speed_val) if speed_val > 0.01 else 1.0
                            response = await self.client.send_command(
                                command="walk_forward",
                                speed=speed_val,
                                turn=turn_val,
                                duration_sec=duration
                            )
                            elapsed = (time.perf_counter() - t0) * 1000
                            return AgentResponse(
                                action="walk_forward",
                                source="direct",
                                robot_state=response.state,
                                speech=f"Közeledem a {target_label}-hoz. Távolság: {dist:.2f} méter.",
                                latency_ms=round(elapsed, 2)
                            )
                except Exception as e:
                    logger.error(f"Local navigation heuristic failed: {e}", exc_info=True)
                    
        # 2. Check if the input is a simple motor/direct command via the smart router
        intent = self.router.classify(text)
        if intent.route == "direct":
            return await self.direct.execute(intent)
            
        # 3. Otherwise, delegate to Hermes using the structured A2A JSON protocol
        try:
            # Gather state and map data
            state = await self.client.get_state()
            sensor_state = await self.client.get_sensors_state()
            map_data = await self.client.get_map()
            
            # Calculate linear speed if IMU data is available
            speed = 0.0
            if sensor_state.imu and sensor_state.imu.available and sensor_state.imu.local_linvel:
                speed = math.hypot(sensor_state.imu.local_linvel[0], sensor_state.imu.local_linvel[1])
                
            obstacle_close = await self._evaluate_obstacle_close(map_data, state.position[0], state.position[1])
            
            # Construct A2ARequest
            request_data = A2ARequest(
                prompt=text,
                robot_state=A2ARobotState(
                    position=state.position,
                    yaw_deg=state.orientation.yaw_deg,
                    status=state.status,
                    fallen=state.fallen,
                    speed=speed
                ),
                spatial_world_model=A2ASpatialModel(
                    landmarks=[
                        A2ALandmark(label=k, x=v["x"], y=v["y"], confidence=v["confidence"])
                        for k, v in map_data.get("landmarks", {}).items()
                    ],
                    obstacle_close=obstacle_close
                )
            )
            
            # Serialize and prepare prompt for Hermes
            prompt_to_hermes = (
                "A2A_PROTOCOL_REQUEST\n"
                f"{request_data.model_dump_json(indent=2)}\n\n"
                "RESPONSE FORMAT REQUIRED:\n"
                "You must return ONLY a JSON response matching the A2AResponse schema inside a json code block:\n"
                "```json\n"
                "{\n"
                '  "action": "walk_forward" | "walk_backward" | "turn_left" | "turn_right" | "stop" | "reset" | "navigate_to" | "look_around" | "say",\n'
                '  "speed": float,\n'
                '  "turn": float,\n'
                '  "duration": float,\n'
                '  "target_landmark": string | null,\n'
                '  "target_coordinates": [float, float] | null,\n'
                '  "speech": "Hungarian TTS response text",\n'
                '  "reasoning": "Reasoning in Hungarian explaining your action selection"\n'
                "}\n"
                "```"
            )
            
            # Send to Hermes
            hermes_res = await self.hermes.delegate(prompt_to_hermes)
            
            if not hermes_res.success:
                return hermes_res
                
            # Parse A2AResponse JSON
            raw_text = hermes_res.hermes_raw or ""
            parsed_json = self._extract_json(raw_text)
            
            if parsed_json:
                try:
                    response_data = A2AResponse(**parsed_json)
                    action = response_data.action
                    speed = response_data.speed
                    turn = response_data.turn
                    duration = response_data.duration
                    speech = response_data.speech
                    
                    # Execute the determined action on the robot
                    response_state = None
                    if action == "reset":
                        response_state = await self.client.reset()
                    elif action == "stop":
                        response_state = await self.client.stop()
                    elif action == "navigate_to" and response_data.target_coordinates:
                        tx, ty = response_data.target_coordinates
                        rx, ry, _ = state.position
                        ryaw = state.orientation.yaw_deg
                        
                        dx = tx - rx
                        dy = ty - ry
                        dist = math.hypot(dx, dy)
                        target_yaw_rad = math.atan2(dy, dx)
                        target_yaw_deg = math.degrees(target_yaw_rad)
                        
                        diff_yaw = target_yaw_deg - ryaw
                        diff_yaw = (diff_yaw + 180) % 360 - 180
                        
                        if dist < 0.3:
                            response_state = await self.client.stop()
                        elif abs(diff_yaw) > 15.0:
                            direction = "turn_left" if diff_yaw > 0 else "turn_right"
                            turn_val = 0.4 if diff_yaw > 0 else -0.4
                            duration = min(1.5, abs(diff_yaw) / 45.0)
                            cmd_res = await self.client.send_command(
                                command=direction,
                                speed=0.0,
                                turn=turn_val,
                                duration_sec=duration
                            )
                            response_state = cmd_res.state
                        else:
                            speed_val = min(0.3, dist / 2.0)
                            turn_val = (diff_yaw / 15.0) * 0.1
                            duration = min(2.0, dist / speed_val) if speed_val > 0.01 else 1.0
                            cmd_res = await self.client.send_command(
                                command="walk_forward",
                                speed=speed_val,
                                turn=turn_val,
                                duration_sec=duration
                            )
                            response_state = cmd_res.state
                    elif action in ["walk_forward", "walk_backward", "turn_left", "turn_right", "look_around"]:
                        # Map look_around to turn_left spin if needed
                        cmd_name = action
                        if cmd_name == "look_around":
                            cmd_name = "turn_left"
                            turn = 0.4
                            duration = 3.14
                            
                        cmd_res = await self.client.send_command(
                            command=cmd_name,
                            speed=speed,
                            turn=turn,
                            duration_sec=duration
                        )
                        response_state = cmd_res.state
                        
                    elapsed = (time.perf_counter() - t0) * 1000
                    return AgentResponse(
                        action=action,
                        source="hermes",
                        robot_state=response_state,
                        speech=speech,
                        hermes_raw=raw_text,
                        latency_ms=round(elapsed, 2)
                    )
                except Exception as parse_err:
                    logger.error(f"Error executing parsed Hermes response: {parse_err}", exc_info=True)
                    
            # Fallback if parsing failed or schema didn't match
            elapsed = (time.perf_counter() - t0) * 1000
            return AgentResponse(
                action="hermes_chat",
                source="hermes",
                speech=raw_text,
                hermes_raw=raw_text,
                latency_ms=round(elapsed, 2)
            )
            
        except Exception as exc:
            logger.error(f"Hermes delegation / A2A processing failed: {exc}", exc_info=True)
            elapsed = (time.perf_counter() - t0) * 1000
            return AgentResponse(
                action="hermes_chat",
                source="hermes",
                success=False,
                error=str(exc),
                speech="Hiba történt a Hermes-szel való kommunikáció során.",
                latency_ms=round(elapsed, 2)
            )
            
    async def process_with_intent(self, text: str) -> tuple[Intent, AgentResponse]:
        # Emulate DuckAgent process_with_intent API
        intent = self.router.classify(text)
        if self._is_navigation_command(text):
            target_label = self._extract_landmark_target(text)
            if target_label:
                intent.action = "navigate_to"
                intent.route = "direct"
                intent.params = {"target_label": target_label}
        response = await self.process(text)
        return intent, response
