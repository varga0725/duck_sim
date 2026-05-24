import math
import heapq
import logging
from typing import List, Tuple, Optional, Any

logger = logging.getLogger("duck-path-planner")

class AStarPlanner:
    """
    A* Global Pathfinder on a 2D occupancy grid.
    """
    def __init__(self, spatial_model: Any):
        self.spatial_model = spatial_model
        
    def plan_path(self, start_world: Tuple[float, float], goal_world: Tuple[float, float]) -> List[Tuple[float, float]]:
        """
        Plans an obstacle-avoiding path from start_world to goal_world coordinates (meters).
        Returns a list of (x, y) waypoints in world space.
        """
        grid = self.spatial_model.grid
        grid_size = self.spatial_model.grid_size
        
        start_gx, start_gy = self.spatial_model.world_to_grid(start_world[0], start_world[1])
        goal_gx, goal_gy = self.spatial_model.world_to_grid(goal_world[0], goal_world[1])
        
        # Priority Queue: (f_score, (gx, gy))
        open_set = []
        heapq.heappush(open_set, (0.0, (start_gx, start_gy)))
        
        came_from = {}
        
        # Cost from start to node
        g_score = {(start_gx, start_gy): 0.0}
        
        # Estimated cost from start to goal through node
        f_score = {(start_gx, start_gy): self._heuristic((start_gx, start_gy), (goal_gx, goal_gy))}
        
        open_set_hash = {(start_gx, start_gy)}
        
        # 8-connected neighbors
        neighbors_offsets = [
            (0, 1, 1.0), (1, 0, 1.0), (0, -1, 1.0), (-1, 0, 1.0), # straight
            (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414) # diagonal
        ]
        
        iterations = 0
        max_iterations = 2000
        
        while open_set and iterations < max_iterations:
            iterations += 1
            _, current = heapq.heappop(open_set)
            open_set_hash.discard(current)
            
            if current == (goal_gx, goal_gy):
                # Path found, reconstruct it
                grid_path = self._reconstruct_path(came_from, current)
                # Convert back to world coordinates
                world_path = [self.spatial_model.grid_to_world(gx, gy) for gx, gy in grid_path]
                logger.info(f"A* path planned successfully with {len(world_path)} waypoints.")
                return world_path
                
            curr_gx, curr_gy = current
            
            for dx, dy, step_cost in neighbors_offsets:
                neighbor = (curr_gx + dx, curr_gy + dy)
                neg_gx, neg_gy = neighbor
                
                # Check bounds
                if not (0 <= neg_gx < grid_size and 0 <= neg_gy < grid_size):
                    continue
                    
                # Check collision (2 is occupied)
                if grid[neg_gy][neg_gx] == 2:
                    continue
                    
                tentative_g_score = g_score[current] + step_cost
                
                if tentative_g_score < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + self._heuristic(neighbor, (goal_gx, goal_gy))
                    
                    if neighbor not in open_set_hash:
                        heapq.heappush(open_set, (f_score[neighbor], neighbor))
                        open_set_hash.add(neighbor)
                        
        # If we couldn't find a path, return a direct straight path as fallback
        logger.warning("A* failed to find a valid path to target. Returning direct path.")
        return [start_world, goal_world]
        
    def _heuristic(self, p1: Tuple[int, int], p2: Tuple[int, int]) -> float:
        """Euclidean distance heuristic."""
        return math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        
    def _reconstruct_path(self, came_from: dict, current: Tuple[int, int]) -> List[Tuple[int, int]]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path


class PurePursuitTracker:
    """
    Pure Pursuit local waypoint tracker.
    Computes steering commands (linear_x and yaw rate) to track a set of waypoints.
    """
    def __init__(self, lookahead_distance: float = 0.4, max_speed: float = 0.25, max_yaw_speed: float = 0.5):
        self.lookahead_distance = lookahead_distance
        self.max_speed = max_speed
        self.max_yaw_speed = max_yaw_speed
        
    def get_steering_command(self, robot_pose: Tuple[float, float, float], path: List[Tuple[float, float]]) -> Tuple[float, float, bool]:
        """
        Computes the control command (linear_x, yaw) for the current robot_pose (x, y, yaw_deg).
        Returns:
            linear_x: forward speed command
            yaw: steering rate command
            arrived: boolean flag indicating if the target is reached
        """
        if not path:
            return 0.0, 0.0, True
            
        rx, ry, ryaw_deg = robot_pose
        
        # 1. Check if arrived at final waypoint
        goal_x, goal_y = path[-1]
        dist_to_goal = math.hypot(goal_x - rx, goal_y - ry)
        if dist_to_goal < 0.25:
            return 0.0, 0.0, True
            
        # 2. Find target waypoint on the path based on lookahead distance
        target_pt = path[-1] # fallback to final point
        for pt in path:
            dist = math.hypot(pt[0] - rx, pt[1] - ry)
            if dist >= self.lookahead_distance:
                target_pt = pt
                break
                
        tx, ty = target_pt
        dx = tx - rx
        dy = ty - ry
        
        # Calculate angle of lookahead point
        target_angle_rad = math.atan2(dy, dx)
        target_angle_deg = math.degrees(target_angle_rad)
        
        # Calculate yaw error
        diff_yaw = target_angle_deg - ryaw_deg
        # Normalize to [-180, 180]
        diff_yaw = (diff_yaw + 180) % 360 - 180
        
        # Proportional turning rate
        # error of 180 deg maps to max_yaw_speed
        yaw_rate = (diff_yaw / 180.0) * self.max_yaw_speed * 3.0
        yaw_rate = max(-self.max_yaw_speed, min(self.max_yaw_speed, yaw_rate))
        
        # Proportional speed scaling (slow down when yaw error is high)
        if abs(diff_yaw) > 30.0:
            linear_x = 0.0 # pivot turn
        else:
            linear_x = self.max_speed * (1.0 - (abs(diff_yaw) / 30.0) * 0.5)
            # scale down as we approach the lookahead point
            dist_to_lookahead = math.hypot(dx, dy)
            linear_x = min(linear_x, dist_to_lookahead * 0.5)
            linear_x = max(0.05, min(self.max_speed, linear_x))
            
        return float(linear_x), float(yaw_rate), False
