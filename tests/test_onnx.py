import importlib.util
import os

import numpy as np
import pytest

from duck_agent_sim.config import DUCK_ONNX_MODEL_PATH
from duck_agent_sim.simulator.policy_contract import (
    OBSERVATION_SIZE,
    POLICY_OUTPUT_SIZE,
)


def test_onnx_model_loading_and_shape():
    assert DUCK_ONNX_MODEL_PATH != "", "Default DUCK_ONNX_MODEL_PATH should be configured"
    assert os.path.exists(DUCK_ONNX_MODEL_PATH), f"Model file must exist at {DUCK_ONNX_MODEL_PATH}"

    import onnxruntime as ort

    session = ort.InferenceSession(DUCK_ONNX_MODEL_PATH, providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]

    assert input_meta.name == "obs"
    assert input_meta.shape == [1, OBSERVATION_SIZE]
    assert output_meta.name == "continuous_actions"
    assert output_meta.shape == [1, POLICY_OUTPUT_SIZE]

    action = session.run(None, {input_meta.name: np.zeros((1, OBSERVATION_SIZE), dtype=np.float32)})[0]
    assert action.shape == (1, POLICY_OUTPUT_SIZE)
    assert action.dtype == np.float32


@pytest.mark.skipif(importlib.util.find_spec("mujoco") is None, reason="MuJoCo is optional in unit-test environments")
def test_real_simulator_onnx_observation_shape_when_mujoco_available():
    from duck_agent_sim.simulator.duck_sim import RealDuckSimulator

    sim = RealDuckSimulator(headless=True)
    sim.reset()

    try:
        assert sim._onnx_active is True, "ONNX policy should be active in simulator"
        assert sim._onnx_session is not None, "ONNX InferenceSession should be initialized"

        obs = sim._get_onnx_obs()
        assert obs.shape == (OBSERVATION_SIZE,)
        assert obs.dtype == np.float32

        sim._apply_onnx_inference()
        assert len(sim.last_action) == sim.num_dofs == POLICY_OUTPUT_SIZE
        assert len(sim.motor_targets) == sim.num_dofs == POLICY_OUTPUT_SIZE
    finally:
        sim.close()
