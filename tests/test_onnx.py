import os
import numpy as np
import pytest
from duck_agent_sim.simulator.duck_sim import RealDuckSimulator
from duck_agent_sim.config import DUCK_ONNX_MODEL_PATH

def test_onnx_model_loading_and_shape():
    # Verify the model path is correctly resolved
    assert DUCK_ONNX_MODEL_PATH != "", "Default DUCK_ONNX_MODEL_PATH should be configured"
    assert os.path.exists(DUCK_ONNX_MODEL_PATH), f"Model file must exist at {DUCK_ONNX_MODEL_PATH}"

    # Initialize RealDuckSimulator in headless mode for automated unit tests
    sim = RealDuckSimulator(headless=True)
    
    # Trigger initialization (which loads the model)
    sim.reset()
    
    try:
        # Assert ONNX is active
        assert sim._onnx_active is True, "ONNX policy should be active in simulator"
        assert sim._onnx_session is not None, "ONNX InferenceSession should be initialized"

        # Get observation vector
        obs = sim._get_onnx_obs()
        
        # Assert observation vector shape is 101 (based on 14 actuator DOFs)
        assert len(obs) == 101, f"Observation vector must have exactly 101 elements, got {len(obs)}"
        assert obs.dtype == np.float32, "Observation vector must be float32"

        # Run inference step
        sim._apply_onnx_inference()
        
        # Verify action output size
        assert len(sim.last_action) == sim.num_dofs, "Actions must match the number of actuators"
        assert len(sim.motor_targets) == sim.num_dofs, "Motor targets must match the number of actuators"
        
    finally:
        # Stop simulation thread and cleanup
        sim._running = False
        if sim._thread:
            sim._thread.join(timeout=1.0)
