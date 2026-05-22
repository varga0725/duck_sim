import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from duck_agent_sim.simulator.policy_contract import (
    ACTUATOR_ORDER,
    DEFAULT_ACTUATOR,
    POLICY_OUTPUT_SIZE,
)
from duck_agent_sim.simulator.policy_default_report import (
    compare_default_actuator_to_home_ctrl,
    compare_model_home_ctrl_to_policy_default,
)
from duck_agent_sim.simulator.upstream_policy_adapter import (
    UpstreamPolicyAdapterSpec,
    UpstreamPolicyExecutionAdapter,
)


def test_policy_default_report_is_stable_for_exact_home_ctrl_match():
    report = compare_default_actuator_to_home_ctrl(DEFAULT_ACTUATOR.copy())

    assert report.actuator_count == POLICY_OUTPUT_SIZE
    assert report.max_abs_delta == 0.0
    assert report.within_tolerance is True
    assert [delta.name for delta in report.deltas] == ACTUATOR_ORDER
    assert [delta.index for delta in report.deltas] == list(range(POLICY_OUTPUT_SIZE))


def test_policy_default_report_records_per_actuator_delta():
    home_ctrl = DEFAULT_ACTUATOR.copy()
    home_ctrl[2] += 0.01

    report = compare_default_actuator_to_home_ctrl(home_ctrl, tolerance=5e-3)
    delta = report.deltas[2]

    assert report.within_tolerance is False
    assert report.max_abs_delta == pytest.approx(0.01)
    assert delta.name == ACTUATOR_ORDER[2]
    assert delta.default_value == pytest.approx(float(DEFAULT_ACTUATOR[2]))
    assert delta.home_ctrl_value == pytest.approx(float(home_ctrl[2]))
    assert delta.delta == pytest.approx(0.01)
    assert delta.abs_delta == pytest.approx(0.01)


def test_policy_default_report_dict_names_all_actuators_in_order():
    payload = compare_default_actuator_to_home_ctrl(DEFAULT_ACTUATOR.copy()).as_dict()

    assert payload["actuator_count"] == POLICY_OUTPUT_SIZE
    assert [item["name"] for item in payload["deltas"]] == ACTUATOR_ORDER


def test_policy_default_report_rejects_wrong_home_ctrl_shape():
    with pytest.raises(ValueError, match="home_ctrl must have shape"):
        compare_default_actuator_to_home_ctrl(np.zeros(POLICY_OUTPUT_SIZE + 1, dtype=np.float32))


def test_upstream_policy_adapter_spec_and_state_can_be_instantiated_without_mujoco_step():
    adapter = UpstreamPolicyExecutionAdapter()
    state = adapter.initialize_state(DEFAULT_ACTUATOR)

    assert isinstance(adapter.spec, UpstreamPolicyAdapterSpec)
    assert adapter.spec.physics_rate_hz == pytest.approx(500.0)
    assert adapter.spec.policy_rate_hz == pytest.approx(50.0)
    np.testing.assert_allclose(state.motor_targets, DEFAULT_ACTUATOR)
    np.testing.assert_allclose(state.prev_motor_targets, DEFAULT_ACTUATOR)
    assert state.last_action.shape == (POLICY_OUTPUT_SIZE,)
    assert state.imitation_phase.tolist() == [1.0, 0.0]


@pytest.mark.skipif(
    importlib.util.find_spec("mujoco") is None
    or importlib.util.find_spec("mujoco_playground") is None,
    reason="MuJoCo/Open Duck Playground dependencies are optional",
)
def test_loaded_mujoco_home_ctrl_policy_default_report_when_dependencies_available():
    import mujoco

    external_path = Path(__file__).resolve().parents[1] / "external" / "Open_Duck_Playground"
    if str(external_path) not in sys.path:
        sys.path.append(str(external_path))

    from playground.open_duck_mini_v2 import base
    from playground.open_duck_mini_v2.constants import FLAT_TERRAIN_XML

    xml_text = base.epath.Path(FLAT_TERRAIN_XML).read_text()
    model = mujoco.MjModel.from_xml_string(xml_text, assets=base.get_assets())

    report = compare_model_home_ctrl_to_policy_default(model)

    assert report.actuator_count == POLICY_OUTPUT_SIZE
    assert [delta.name for delta in report.deltas] == ACTUATOR_ORDER
