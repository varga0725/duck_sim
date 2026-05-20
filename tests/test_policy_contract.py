import importlib.util

import numpy as np
import onnxruntime as ort
import pytest

from duck_agent_sim.config import DUCK_ONNX_MODEL_PATH
from duck_agent_sim.schemas import RobotCommand
from duck_agent_sim.simulator.command_mapper import map_command
from duck_agent_sim.simulator.policy_contract import (
    ACTION_SCALE,
    ACTUATOR_CTRL_RANGES,
    ACTUATOR_ORDER,
    DEFAULT_ACTUATOR,
    OBSERVATION_SIZE,
    POLICY_COMMAND_LIMITS,
    POLICY_OUTPUT_SIZE,
    apply_action_to_targets,
    clamp_control_to_policy_limits,
)

EXPECTED_ACTUATOR_ORDER = [
    "left_hip_yaw",
    "left_hip_roll",
    "left_hip_pitch",
    "left_knee",
    "left_ankle",
    "neck_pitch",
    "head_pitch",
    "head_yaw",
    "head_roll",
    "right_hip_yaw",
    "right_hip_roll",
    "right_hip_pitch",
    "right_knee",
    "right_ankle",
]


EXPECTED_CTRL_RANGES = np.array(
    [
        [-0.523599, 0.523599],
        [-0.436332, 0.436332],
        [-1.221730, 0.523599],
        [-1.570796, 1.570796],
        [-1.570796, 1.570796],
        [-0.349066, 1.134464],
        [-0.785398, 0.785398],
        [-2.792527, 2.792527],
        [-0.523599, 0.523599],
        [-0.523599, 0.523599],
        [-0.436332, 0.436332],
        [-0.523599, 1.221730],
        [-1.570796, 1.570796],
        [-1.570796, 1.570796],
    ],
    dtype=np.float32,
)


def test_onnx_policy_io_contract_matches_documented_shapes():
    session = ort.InferenceSession(
        DUCK_ONNX_MODEL_PATH,
        providers=["CPUExecutionProvider"],
    )

    inputs = session.get_inputs()
    outputs = session.get_outputs()

    assert len(inputs) == 1
    assert inputs[0].name == "obs"
    assert inputs[0].shape == [1, OBSERVATION_SIZE]
    assert inputs[0].type == "tensor(float)"

    assert len(outputs) == 1
    assert outputs[0].name == "continuous_actions"
    assert outputs[0].shape == [1, POLICY_OUTPUT_SIZE]
    assert outputs[0].type == "tensor(float)"

    action = session.run(
        None,
        {"obs": np.zeros((1, OBSERVATION_SIZE), dtype=np.float32)},
    )[0]
    assert action.shape == (1, POLICY_OUTPUT_SIZE)
    assert action.dtype == np.float32


def test_actuator_order_and_ranges_match_documented_contract():
    assert ACTUATOR_ORDER == EXPECTED_ACTUATOR_ORDER
    assert len(ACTUATOR_ORDER) == POLICY_OUTPUT_SIZE
    assert DEFAULT_ACTUATOR.shape == (POLICY_OUTPUT_SIZE,)
    assert ACTUATOR_CTRL_RANGES.shape == (POLICY_OUTPUT_SIZE, 2)
    np.testing.assert_allclose(ACTUATOR_CTRL_RANGES, EXPECTED_CTRL_RANGES, atol=1e-6)


def test_action_scale_maps_zero_and_small_actions_to_expected_targets():
    zero_targets = apply_action_to_targets(
        np.zeros(POLICY_OUTPUT_SIZE, dtype=np.float32)
    )
    safe_positive_action = np.full(POLICY_OUTPUT_SIZE, 0.1, dtype=np.float32)
    safe_negative_action = np.full(POLICY_OUTPUT_SIZE, -0.1, dtype=np.float32)
    positive_targets = apply_action_to_targets(safe_positive_action)
    negative_targets = apply_action_to_targets(safe_negative_action)

    np.testing.assert_allclose(zero_targets, DEFAULT_ACTUATOR, atol=1e-6)
    np.testing.assert_allclose(
        positive_targets,
        DEFAULT_ACTUATOR + 0.1 * ACTION_SCALE,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        negative_targets,
        DEFAULT_ACTUATOR - 0.1 * ACTION_SCALE,
        atol=1e-6,
    )


def test_action_targets_are_explicitly_clipped_to_actuator_ctrl_ranges():
    unsafe_action = np.full(POLICY_OUTPUT_SIZE, 100.0, dtype=np.float32)
    targets = apply_action_to_targets(unsafe_action)

    assert np.all(targets <= ACTUATOR_CTRL_RANGES[:, 1])
    assert np.all(targets >= ACTUATOR_CTRL_RANGES[:, 0])
    np.testing.assert_allclose(targets, ACTUATOR_CTRL_RANGES[:, 1], atol=1e-6)

    unsafe_action = np.full(POLICY_OUTPUT_SIZE, -100.0, dtype=np.float32)
    targets = apply_action_to_targets(unsafe_action)
    np.testing.assert_allclose(targets, ACTUATOR_CTRL_RANGES[:, 0], atol=1e-6)


@pytest.mark.parametrize(
    ("command", "speed", "turn", "expected_x", "expected_yaw"),
    [
        (
            "walk_forward",
            1.0,
            1.0,
            POLICY_COMMAND_LIMITS.linear_x[1],
            POLICY_COMMAND_LIMITS.yaw[1],
        ),
        (
            "walk_backward",
            1.0,
            -1.0,
            POLICY_COMMAND_LIMITS.linear_x[0],
            POLICY_COMMAND_LIMITS.yaw[0],
        ),
        ("turn_left", 1.0, 1.0, 0.15, POLICY_COMMAND_LIMITS.yaw[1]),
        ("turn_right", 1.0, 1.0, 0.15, POLICY_COMMAND_LIMITS.yaw[0]),
    ],
)
def test_bridge_command_mapping_is_conservatively_clamped_to_policy_range(
    command, speed, turn, expected_x, expected_yaw
):
    control = map_command(RobotCommand(command=command, speed=speed, turn=turn))

    assert control.linear_y == 0.0
    assert control.linear_x == pytest.approx(expected_x)
    assert control.yaw == pytest.approx(expected_yaw)
    assert (
        POLICY_COMMAND_LIMITS.linear_x[0]
        <= control.linear_x
        <= POLICY_COMMAND_LIMITS.linear_x[1]
    )
    assert (
        POLICY_COMMAND_LIMITS.linear_y[0]
        <= control.linear_y
        <= POLICY_COMMAND_LIMITS.linear_y[1]
    )
    assert POLICY_COMMAND_LIMITS.yaw[0] <= control.yaw <= POLICY_COMMAND_LIMITS.yaw[1]


def test_clamp_control_to_policy_limits_rejects_command_range_regressions():
    clamped = clamp_control_to_policy_limits(linear_x=9.0, linear_y=-9.0, yaw=9.0)

    assert clamped.linear_x == POLICY_COMMAND_LIMITS.linear_x[1]
    assert clamped.linear_y == POLICY_COMMAND_LIMITS.linear_y[0]
    assert clamped.yaw == POLICY_COMMAND_LIMITS.yaw[1]


def test_mujoco_actuator_ctrlrange_is_present_or_policy_targets_stay_clipped():
    # In minimal CI environments MuJoCo is optional; the bridge-level explicit clip
    # still guarantees ctrl values stay inside the documented ctrlrange.
    if importlib.util.find_spec("mujoco") is None:
        targets = apply_action_to_targets(
            np.full(POLICY_OUTPUT_SIZE, 100.0, dtype=np.float32)
        )
        assert np.all(targets <= ACTUATOR_CTRL_RANGES[:, 1])
        return

    import mujoco
    from playground.open_duck_mini_v2 import base
    from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML

    xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()
    model = mujoco.MjModel.from_xml_string(xml_text, assets=base.get_assets())
    assert model.nu == POLICY_OUTPUT_SIZE
    np.testing.assert_allclose(
        model.actuator_ctrlrange,
        ACTUATOR_CTRL_RANGES,
        atol=1e-6,
    )
