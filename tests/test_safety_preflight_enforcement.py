from fastapi.testclient import TestClient

from duck_agent_sim.bridge import api
from duck_agent_sim.main import app
from duck_agent_sim.schemas import FeetContact, Orientation, RobotState

client = TestClient(app)


class SpySimulator:
    def __init__(self, states):
        self.states = list(states)
        self.apply_command_calls = []
        self.stop_calls = 0
        self.reset_calls = 0

    def get_state(self):
        return self.states[-1].model_copy(deep=True)

    def stop(self):
        self.stop_calls += 1
        stopped = RobotState(status="stopped", last_command="stop")
        self.states.append(stopped)
        return stopped

    def reset(self):
        self.reset_calls += 1
        reset = RobotState(status="idle", last_command="reset")
        self.states.append(reset)
        return reset

    def apply_command(self, cmd):
        self.apply_command_calls.append(cmd)
        state = RobotState(status="walking", last_command=cmd.command, position=(0.2, 0.0, 0.41))
        self.states.append(state)
        from duck_agent_sim.schemas import CommandResponse, ControlIntent
        return CommandResponse(
            accepted=True,
            command=cmd.command,
            mapped_control=ControlIntent(linear_x=cmd.speed, linear_y=0.0, yaw=cmd.turn),
            state=state,
        )


def unstable_state(**overrides):
    data = {
        "status": "fallen",
        "fallen": True,
        "orientation": Orientation(roll_deg=0.0, pitch_deg=0.0, yaw_deg=0.0),
        "position": (0.0, 0.0, 0.41),
        "feet_contact": FeetContact(left=True, right=True),
    }
    data.update(overrides)
    return RobotState(**data)


def test_command_preflight_recovers_and_does_not_execute_requested_motion(monkeypatch):
    sim = SpySimulator([unstable_state(status="fallen", fallen=True)])
    monkeypatch.setattr(api, "active_simulator", sim)

    res = client.post("/command", json={"command": "walk_forward", "speed": 0.25, "duration_sec": 1.0})

    assert res.status_code == 200
    data = res.json()
    assert data["accepted"] is False
    assert data["command"] == "walk_forward"
    assert data["state"]["last_command"] == "reset"
    assert data["safety_intervention"] == "preflight_recovered"
    assert "fallen_flag" in data["safety_reasons"]
    assert sim.stop_calls == 1
    assert sim.reset_calls == 1
    assert sim.apply_command_calls == []


def test_command_post_check_recovers_if_motion_destabilizes(monkeypatch):
    class DestabilizingSimulator(SpySimulator):
        def apply_command(self, cmd):
            self.apply_command_calls.append(cmd)
            fallen = unstable_state(
                status="fallen",
                fallen=True,
                position=(0.2, 0.0, 0.10),
                feet_contact=FeetContact(left=False, right=False),
            )
            from duck_agent_sim.schemas import CommandResponse, ControlIntent
            return CommandResponse(
                accepted=True,
                command=cmd.command,
                mapped_control=ControlIntent(linear_x=cmd.speed, linear_y=0.0, yaw=cmd.turn),
                state=fallen,
            )

    sim = DestabilizingSimulator([RobotState()])
    monkeypatch.setattr(api, "active_simulator", sim)

    res = client.post("/command", json={"command": "walk_forward", "speed": 0.25, "duration_sec": 1.0})

    assert res.status_code == 200
    data = res.json()
    assert data["accepted"] is True
    assert data["state"]["last_command"] == "reset"
    assert data["safety_intervention"] == "post_command_recovered"
    assert "fallen_flag" in data["safety_reasons"]
    assert sim.stop_calls == 1
    assert sim.reset_calls == 1
    assert len(sim.apply_command_calls) == 1


def test_walk_square_preflight_uses_same_recovery_and_skips_scenario(monkeypatch):
    sim = SpySimulator([unstable_state(position=(0.0, 0.0, 0.05), fallen=False, status="idle")])
    monkeypatch.setattr(api, "active_simulator", sim)

    res = client.post("/scenario/walk-square")

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["steps_executed"] == []
    assert data["safety_intervention"] == "preflight_recovered"
    assert "body_height_below_min" in data["safety_reasons"]
    assert sim.stop_calls == 1
    assert sim.reset_calls == 1
    assert sim.apply_command_calls == []


def test_follow_start_preflight_recovers_and_does_not_start_follower(monkeypatch):
    sim = SpySimulator([
        unstable_state(
            status="idle",
            fallen=False,
            feet_contact=FeetContact(left=False, right=False),
        )
    ])
    monkeypatch.setattr(api, "active_simulator", sim)

    started = {"called": False}
    monkeypatch.setattr(api.follower, "configure", lambda params: None)
    monkeypatch.setattr(api.follower, "start", lambda: started.__setitem__("called", True))

    res = client.post("/vision/follow/start", json={"target_label": "person"})

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "blocked_by_safety"
    assert data["safety_intervention"] == "preflight_recovered"
    assert "no_feet_contact" in data["safety_reasons"]
    assert started["called"] is False
    assert sim.stop_calls == 1
    assert sim.reset_calls == 1
