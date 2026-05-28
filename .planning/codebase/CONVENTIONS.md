# Coding Conventions

**Analysis Date:** 2026-05-28

## Naming Patterns

**Files:**
- snake_case.py: All python source and helper scripts.
- test_*.py: Python test files located in the `tests/` directory.

**Classes:**
- PascalCase: Pydantic schemas (e.g., `RobotState`, `RobotCommand`), managers, and classes.

**Functions and Methods:**
- snake_case: All Python functions and object methods (e.g., `apply_command`, `get_state`).

**Variables:**
- snake_case: Standard variables and instance attributes.
- UPPER_SNAKE_CASE: Global constants and environment configuration overrides (e.g., `DUCK_SIM_MODE`, `SIM_DT`).

## Code Style

**Formatting & Linting:**
- Ruff is configured in `pyproject.toml` as the primary style guide.
- Line length is restricted to 88 characters.
- Ruff select rules: `E` (errors), `F` (Pyflakes), `I` (isort imports), `W` (warnings).

**Type Annotations:**
- Python type hints are highly recommended and widely used throughout schemas and functions (`typing.List`, `Tuple`, `Optional`, etc.).

## Import Organization

**Order:**
1. Standard library imports (e.g., `math`, `time`, `os`, `sys`).
2. Third-party packages (e.g., `numpy`, `fastapi`, `pydantic`).
3. Local module imports (e.g., `from duck_agent_sim.schemas import RobotState`).

**Imports sorting:**
- Handled automatically by Ruff's `I` rules.

## Error Handling

**Safety Failures:**
- Physical crashes, tipping, and low voltage do not raise exceptions; they transition the system to `"fallen"` status, set linear speeds to 0, and log warnings.

**API Validation:**
- Let Pydantic validate request parameters automatically and return structured JSON responses containing errors rather than raising raw Server 500 exceptions.

**Runtime/Process Failures:**
- Try-except blocks catch system crashes (e.g. shared memory connection failures) and print descriptive logs with `logger.error` or fallback gracefully to standard memory channels.

## Logging

**Framework:**
- Standard Python `logging` library.
- Root logger is named `"duck-agent-sim"`.
- Log level defaults to `logging.INFO` with clear timestamping formatting.

---

*Convention analysis: 2026-05-28*
*Update when patterns change*
