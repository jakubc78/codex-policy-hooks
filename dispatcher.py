#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import sys

# Ensure validators importing "dispatcher" get this exact module instance.
# When this file is executed directly, Python names it "__main__".
# Without this alias, validators importing "dispatcher" would load the file
# a second time and get different Context / Result / Decision classes.
sys.modules.setdefault("dispatcher", sys.modules[__name__])

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
VALIDATORS_DIR = BASE_DIR / "validators"
CONFIG_PATH = BASE_DIR / "config.json"

# Allow validator modules to import shared helpers from validators/.
if str(VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATORS_DIR))


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class Result:
    decision: Decision
    reason: str = ""


@dataclass(frozen=True)
class Context:
    payload: dict[str, Any]
    cwd: Path
    tool_name: str
    tool_input: dict[str, Any]
    command: str | None
    argv: list[str]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Context":
        raw_input = payload.get("tool_input")
        tool_input = raw_input if isinstance(raw_input, dict) else {}

        command = tool_input.get("command")
        if not isinstance(command, str):
            command = None

        argv: list[str] = []

        if command:
            try:
                argv = shlex.split(command)
            except ValueError as exc:
                debug(f"Unable to parse command with shlex: {exc}")

        return cls(
            payload=payload,
            cwd=Path(str(payload.get("cwd", "."))),
            tool_name=str(payload.get("tool_name", "")),
            tool_input=tool_input,
            command=command,
            argv=argv,
        )


def debug(message: str) -> None:
    """
    Write diagnostic information to stderr when CODEX_POLICY_DEBUG=1.

    stdout must remain reserved for the JSON response consumed by Codex.
    """
    if os.environ.get("CODEX_POLICY_DEBUG") == "1":
        print(f"[codex-policy] {message}", file=sys.stderr)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        debug(f"No config file found at {CONFIG_PATH}")
        return {}

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("config.json root must be an object")

    return data


def load_module(path: Path) -> ModuleType:
    name = f"codex_policy_{path.stem}"

    spec = importlib.util.spec_from_file_location(name, path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load validator module: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def load_validators() -> list[ModuleType]:
    modules: list[ModuleType] = []

    debug(f"Scanning validators in {VALIDATORS_DIR}")

    if not VALIDATORS_DIR.exists():
        debug("Validators directory does not exist")
        return modules

    for path in sorted(VALIDATORS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            debug(f"Skipping private/helper module: {path.name}")
            continue

        debug(f"Loading validator: {path.name}")

        try:
            module = load_module(path)

            name = getattr(module, "NAME", None)
            evaluate = getattr(module, "evaluate", None)

            if not isinstance(name, str):
                debug(f"Skipping {path.name}: missing or invalid NAME")
                continue

            if not callable(evaluate):
                debug(f"Skipping {path.name}: missing evaluate(ctx, config)")
                continue

            modules.append(module)

            debug(
                f"Loaded validator: {name} "
                f"(priority={getattr(module, 'PRIORITY', 100)})"
            )

        except Exception as exc:
            print(
                f"[codex-policy] failed to load {path.name}: {exc}",
                file=sys.stderr,
            )

    modules.sort(
        key=lambda module: int(getattr(module, "PRIORITY", 100))
    )

    if modules:
        debug(
            "Validator order: "
            + ", ".join(
                f"{module.NAME}:{getattr(module, 'PRIORITY', 100)}"
                for module in modules
            )
        )
    else:
        debug("No validators loaded")

    return modules


def emit(decision: Decision, reason: str) -> None:
    """
    Emit a PermissionRequest hook decision.

    ABSTAIN deliberately produces no stdout.
    """
    if decision == Decision.ABSTAIN:
        return

    debug(f"Emitting decision={decision.value}: {reason}")

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": decision.value,
                        "message": reason,
                    },
                }
            }
        )
    )


def self_test() -> int:
    """
    Validate the dispatcher environment and discover all validators.

    This does not execute validators against real commands.
    """
    print("Codex policy self-test")
    print("======================")
    print(f"Dispatcher:     {Path(__file__).resolve()}")
    print(f"Config:         {CONFIG_PATH}")
    print(f"Validators dir: {VALIDATORS_DIR}")
    print()

    failed = False

    try:
        config = load_config()
        print("Config: OK")
    except Exception as exc:
        print(f"Config: FAIL - {exc}")
        return 1

    try:
        validators = load_validators()
    except Exception as exc:
        print(f"Validators: FAIL - {exc}")
        return 1

    if not validators:
        print("Validators: FAIL - none found")
        return 1

    loaded_names = {
        getattr(validator, "NAME", None)
        for validator in validators
    }

    expected_names = {
        name
        for name, cfg in config.items()
        if isinstance(cfg, dict)
        and cfg.get("enabled", True) is True
    }

    missing_names = sorted(expected_names - loaded_names)

    if missing_names:
        print(
            "Validators: FAIL - configured but not loaded: "
            + ", ".join(missing_names)
        )
        failed = True

    print(f"Validators loaded: {len(validators)}")
    print()

    for validator in validators:
        name = getattr(validator, "NAME", "<missing>")
        priority = getattr(validator, "PRIORITY", 100)
        evaluate = getattr(validator, "evaluate", None)

        module_status = "OK" if callable(evaluate) else "FAIL"

        print(
            f"- {name} "
            f"(priority={priority}): "
            f"{module_status}"
        )

        if not callable(evaluate):
            failed = True

        cfg = config.get(name, {})

        if not isinstance(cfg, dict):
            print("  config: FAIL - expected JSON object")
            failed = True
            continue

        enabled = cfg.get("enabled", True)

        if not isinstance(enabled, bool):
            print(
                "  config: FAIL - 'enabled' must be true or false"
            )
            failed = True
            continue

        print(f"  enabled: {enabled}")
        print(f"  config keys: {', '.join(sorted(cfg.keys())) or '(none)'}")

    print()

    if failed:
        print("Self-test: FAIL")
        return 1

    print("Self-test: OK")
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(
            f"[codex-policy] invalid JSON input: {exc}",
            file=sys.stderr,
        )
        return 0

    event_name = payload.get("hook_event_name")

    debug(f"Hook event: {event_name}")

    if event_name != "PermissionRequest":
        debug("Ignoring non-PermissionRequest event")
        return 0

    ctx = Context.from_payload(payload)

    debug(f"Tool name: {ctx.tool_name}")
    debug(f"CWD: {ctx.cwd}")

    if ctx.command is not None:
        debug(f"Command: {ctx.command}")
        debug(f"ARGV: {ctx.argv}")

    try:
        config = load_config()
    except Exception as exc:
        print(
            f"[codex-policy] config error: {exc}",
            file=sys.stderr,
        )
        return 0

    validators = load_validators()

    allows: list[str] = []

    for validator in validators:
        name = validator.NAME
        validator_config = config.get(name, {})

        if not isinstance(validator_config, dict):
            debug(
                f"{name}: invalid config type "
                f"{type(validator_config).__name__}; skipping"
            )
            continue

        if validator_config.get("enabled", True) is False:
            debug(f"{name}: disabled")
            continue

        debug(f"Evaluating validator: {name}")

        try:
            result = validator.evaluate(ctx, validator_config)
        except Exception as exc:
            print(
                f"[codex-policy] {name} failed: {exc}",
                file=sys.stderr,
            )
            continue

        if not isinstance(result, Result):
            debug(
                f"{name}: returned invalid result type "
                f"{type(result).__name__}"
            )
            continue

        debug(
            f"{name}: {result.decision.value}"
            + (
                f" - {result.reason}"
                if result.reason
                else ""
            )
        )

        if result.decision == Decision.DENY:
            emit(
                Decision.DENY,
                f"{name}: {result.reason}",
            )
            return 0

        if result.decision == Decision.ALLOW:
            allows.append(
                f"{name}: {result.reason}"
            )

    if allows:
        emit(
            Decision.ALLOW,
            "; ".join(allows),
        )
    else:
        debug(
            "No validator allowed or denied the request; "
            "falling back to normal Codex approval flow"
        )

    # No stdout means:
    # continue with normal Codex approval handling.
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())

    raise SystemExit(main())