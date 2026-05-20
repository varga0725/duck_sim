"""
Tests for SmartRouter intent classification.

Verifies that all Hungarian command variants are correctly routed to either
'direct' or 'hermes', and that the extracted Intent fields are accurate.
"""

import pytest

from duck_agent_sim.agent.smart_router import SmartRouter, Intent


@pytest.fixture
def router():
    return SmartRouter()


# ──────────────────────────────────────────────────────────
# Level 1 — Motor commands → direct
# ──────────────────────────────────────────────────────────

class TestMotorCommands:
    """Regex fast-path motor commands should route to 'direct' with confidence=1.0."""

    @pytest.mark.parametrize(
        "text, expected_action",
        [
            # walk_forward variants
            ("előre", "walk_forward"),
            ("Előre", "walk_forward"),
            ("ELŐRE", "walk_forward"),
            ("elore", "walk_forward"),
            ("menj előre", "walk_forward"),
            ("sétálj előre", "walk_forward"),
            ("haladj előre", "walk_forward"),
            ("indulj", "walk_forward"),
            # walk_backward variants
            ("hátra", "walk_backward"),
            ("hatra", "walk_backward"),
            ("menj hátra", "walk_backward"),
            ("sétálj hátra", "walk_backward"),
            ("tolass", "walk_backward"),
            # turn_left variants
            ("balra", "turn_left"),
            ("bal", "turn_left"),
            ("fordulj balra", "turn_left"),
            ("menj balra", "turn_left"),
            ("kanyarodj balra", "turn_left"),
            # turn_right variants
            ("jobbra", "turn_right"),
            ("jobb", "turn_right"),
            ("fordulj jobbra", "turn_right"),
            ("menj jobbra", "turn_right"),
            ("kanyarodj jobbra", "turn_right"),
            # stop variants
            ("állj", "stop"),
            ("allj", "stop"),
            ("állj meg", "stop"),
            ("megállj", "stop"),
            ("stop", "stop"),
            ("vége", "stop"),
            ("szünet", "stop"),
            ("állítsd le", "stop"),
            # reset variants
            ("újra", "reset"),
            ("ujra", "reset"),
            ("alaphelyzet", "reset"),
            ("alap", "reset"),
            ("visszaállít", "reset"),
            ("reset", "reset"),
        ],
    )
    def test_motor_commands_route_direct(self, router, text, expected_action):
        intent = router.classify(text)
        assert intent.route == "direct", f"'{text}' should route to direct, got {intent.route}"
        assert intent.action == expected_action, f"'{text}' should be {expected_action}, got {intent.action}"
        assert intent.confidence == 1.0


# ──────────────────────────────────────────────────────────
# Level 2 — Vision / follower commands
# ──────────────────────────────────────────────────────────

class TestFollowerCommands:
    """Follow/stop-follow commands should route to 'direct'."""

    @pytest.mark.parametrize(
        "text",
        [
            "kövesd a széket",
            "kövesd",
            "keresd a széket",
            "kövess",
        ],
    )
    def test_follow_routes_direct(self, router, text):
        intent = router.classify(text)
        assert intent.route == "direct"
        assert intent.action == "follow_target"
        assert intent.confidence > 0.8

    def test_follow_extracts_chair_label(self, router):
        intent = router.classify("kövesd a széket")
        assert intent.params.get("target_label") == "chair"

    def test_follow_extracts_person_label(self, router):
        intent = router.classify("kövesd az embert")
        assert intent.params.get("target_label") == "person"

    def test_follow_default_label(self, router):
        """When no known target is mentioned, default to 'chair'."""
        intent = router.classify("kövesd azt")
        assert intent.params.get("target_label") == "chair"

    @pytest.mark.parametrize(
        "text",
        [
            "ne kövesd",
            "követés le",
            "állítsd le a követést",
        ],
    )
    def test_stop_following_routes_direct(self, router, text):
        intent = router.classify(text)
        assert intent.route == "direct"
        assert intent.action == "stop_following"


# ──────────────────────────────────────────────────────────
# Level 2 — Hermes keyword triggers
# ──────────────────────────────────────────────────────────

class TestHermesKeywords:
    """Complex / NLU queries should route to 'hermes'."""

    @pytest.mark.parametrize(
        "text",
        [
            "mit látsz?",
            "mit érzékelsz?",
            "hol vagyok?",
            "mondj valamit",
            "mesélj a környezetről",
            "magyarázd el",
            "segíts nekem",
            "mi ez?",
            "mi az?",
            "nézz körül",
            "mi a helyzet?",
            "státusz",
            "navigálj a konyháig",
        ],
    )
    def test_hermes_keywords_route_hermes(self, router, text):
        intent = router.classify(text)
        assert intent.route == "hermes", f"'{text}' should route to hermes, got {intent.route}"
        assert intent.action == "hermes_chat"


# ──────────────────────────────────────────────────────────
# Level 3 — Fallback
# ──────────────────────────────────────────────────────────

class TestFallback:
    """Unrecognised input should fall back to Hermes with lower confidence."""

    def test_unknown_text_routes_to_hermes(self, router):
        intent = router.classify("abcxyz blabla")
        assert intent.route == "hermes"
        assert intent.confidence < 1.0

    def test_empty_string_routes_to_direct_noop(self, router):
        intent = router.classify("")
        assert intent.route == "direct"
        assert intent.action == "noop"
        assert intent.confidence == 0.0


# ──────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────

class TestEdgeCases:
    """Various edge cases for the router."""

    def test_case_insensitivity(self, router):
        for text in ["ELŐRE", "Előre", "előre", "eLőRe"]:
            intent = router.classify(text)
            assert intent.action == "walk_forward"

    def test_whitespace_handling(self, router):
        intent = router.classify("  előre  ")
        assert intent.action == "walk_forward"

    def test_raw_text_preserved(self, router):
        intent = router.classify("sétálj előre kérlek")
        assert intent.raw_text == "sétálj előre kérlek"
