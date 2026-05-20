"""
SmartRouter — two-level intent classifier for Hungarian voice commands.

Level 1 (regex fast-path, <1ms):
    Matches deterministic motor commands like "előre", "hátra", "balra"…
    Routes them to the DirectController for sub-100ms execution.

Level 2 (keyword heuristics):
    Detects vision / follower / navigation keywords and routes to the
    appropriate handler (direct follow API or Hermes delegation).

Level 3 (fallback):
    Everything else is delegated to Hermes for natural-language reasoning.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Pattern

logger = logging.getLogger("smart-router")


@dataclass
class Intent:
    """Classified intent produced by the SmartRouter."""

    action: str
    """Semantic action key, e.g. 'walk_forward', 'follow_target', 'hermes_chat'."""

    route: Literal["direct", "hermes"]
    """Target subsystem for execution."""

    confidence: float = 1.0
    """Routing confidence (1.0 for regex hits, lower for heuristic matches)."""

    params: Dict = field(default_factory=dict)
    """Optional extracted parameters (e.g. target_label for follow)."""

    raw_text: str = ""
    """Original input text that was classified."""


# ──────────────────────────────────────────────────────────
# Level 1 — Regex fast-path (deterministic motor commands)
# ──────────────────────────────────────────────────────────

# Reuses the proven patterns from voice_control.py COMMAND_MAP,
# extended with a few extra colloquial variants.
_MOTOR_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "walk_forward": re.compile(
        r"\b(el[őo]re|el[őo]rehalad|menj\s*el[őo]re|s[ée]t[áa]lj\s*el[őo]re"
        r"|haladj\s*el[őo]re|l[őo]re|ind[uü]lj)\b",
        re.IGNORECASE,
    ),
    "walk_backward": re.compile(
        r"\b(h[áa]tra|menj\s*h[áa]tra|s[ée]t[áa]lj\s*h[áa]tra|tolat[áa]s|tolass)\b",
        re.IGNORECASE,
    ),
    "turn_left": re.compile(
        r"\b(balra|bal|ford[uü]lj\s*balra|menj\s*balra|kanyarodj\s*balra)\b",
        re.IGNORECASE,
    ),
    "turn_right": re.compile(
        r"\b(jobbra|jobb|ford[uü]lj\s*jobbra|menj\s*jobbra|kanyarodj\s*jobbra)\b",
        re.IGNORECASE,
    ),
    "stop": re.compile(
        r"\b([áa]llj|[áa]llj\s*meg|meg[áa]llj|stop|v[ée]ge|sz[üu]net|[áa]ll[íi]tsd\s*le)\b",
        re.IGNORECASE,
    ),
    "reset": re.compile(
        r"\b([úu]jra|alaphelyzet|alap|vissza[áa]ll[íi]t|reset)\b",
        re.IGNORECASE,
    ),
}

# ──────────────────────────────────────────────────────────
# Level 2 — Keyword heuristics (vision / follow / complex)
# ──────────────────────────────────────────────────────────

_FOLLOW_PATTERN = re.compile(
    r"\b(k[öo]vesd|k[öo]vet|keresd|k[öo]vess)\b",
    re.IGNORECASE,
)
_STOP_FOLLOW_PATTERN = re.compile(
    r"\b(ne\s*k[öo]vesd|k[öo]vet[ée]s\s*le|[áa]ll[íi]tsd\s*le\s*a\s*k[öo]vet[ée]st)\b",
    re.IGNORECASE,
)
_TARGET_LABEL_PATTERN = re.compile(
    r"\b(?:a\s+)?(\w+?)(?:et|t|ot|at|öt)?\s*$",
    re.IGNORECASE,
)

# Keywords that signal we need Hermes for reasoning / NLU
_HERMES_KEYWORDS = re.compile(
    r"\b(mit\s*l[áa]t|mit\s*[ée]rz[ée]kel|hol\s*vagy|hol\s*vagyok|mond[dj]|mes[ée]l"
    r"|magyar[áa]z|seg[íi]ts|mi\s*ez|mi\s*az|n[ée]zz\s*k[öo]r[üu]l"
    r"|navig[áa]l|menj\s*a\s*.*\s*fel[ée]|keresd\s*meg"
    r"|besz[ée]l[jg]|mi\s*a\s*helyzet|st[áa]tusz)\b",
    re.IGNORECASE,
)


class SmartRouter:
    """
    Classifies Hungarian text input into an Intent with a routing decision.

    Usage::

        router = SmartRouter()
        intent = router.classify("sétálj előre")
        # Intent(action='walk_forward', route='direct', confidence=1.0)

        intent = router.classify("mit látsz a kamerán?")
        # Intent(action='hermes_chat', route='hermes', confidence=0.8)
    """

    def classify(self, text: str) -> Intent:
        """Classify *text* and return a routing Intent."""
        cleaned = text.strip()
        if not cleaned:
            return Intent(action="noop", route="direct", confidence=0.0, raw_text=text)

        lower = cleaned.lower()

        # ── Level 2a: stop following (checked BEFORE motor commands
        #    because "állítsd le a követést" would otherwise match "stop") ──
        if _STOP_FOLLOW_PATTERN.search(lower):
            logger.debug("L2 stop_following hit: %s", lower)
            return Intent(
                action="stop_following",
                route="direct",
                confidence=0.95,
                raw_text=text,
            )

        # ── Level 1: regex motor commands ──
        for action, pattern in _MOTOR_PATTERNS.items():
            if pattern.search(lower):
                logger.debug("L1 regex hit: %s → %s", lower, action)
                return Intent(
                    action=action,
                    route="direct",
                    confidence=1.0,
                    raw_text=text,
                )

        # ── Level 2b: start following ──
        if _FOLLOW_PATTERN.search(lower):
            # Try to extract target label from the tail of the phrase
            target = self._extract_follow_target(lower)
            logger.debug("L2 follow_target hit: %s → target=%s", lower, target)
            return Intent(
                action="follow_target",
                route="direct",
                confidence=0.9,
                params={"target_label": target or "chair"},
                raw_text=text,
            )

        # ── Level 2c: Hermes keyword triggers ──
        if _HERMES_KEYWORDS.search(lower):
            logger.debug("L2 hermes keyword hit: %s", lower)
            return Intent(
                action="hermes_chat",
                route="hermes",
                confidence=0.8,
                raw_text=text,
            )

        # ── Level 3: fallback → Hermes ──
        logger.debug("L3 fallback → hermes: %s", lower)
        return Intent(
            action="hermes_chat",
            route="hermes",
            confidence=0.5,
            raw_text=text,
        )

    # ──────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_follow_target(text: str) -> Optional[str]:
        """
        Best-effort extraction of the target noun from a follow command.

        Examples:
            "kövesd a széket"  → "szék"
            "kövesd a labdát"  → "labda"
            "kövesd"           → None (caller uses default)
        """
        # Known Hungarian object names → YOLO English labels
        _HU_TO_EN: Dict[str, str] = {
            "szék": "chair",
            "széket": "chair",
            "labda": "ball",
            "labdát": "ball",
            "ember": "person",
            "embert": "person",
            "személy": "person",
            "személyt": "person",
            "kutya": "dog",
            "kutyát": "dog",
            "macska": "cat",
            "macskát": "cat",
            "autó": "car",
            "autót": "car",
            "palack": "bottle",
            "palackot": "bottle",
        }

        for hu_word, en_label in _HU_TO_EN.items():
            if hu_word in text:
                return en_label
        return None
