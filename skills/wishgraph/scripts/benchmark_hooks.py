#!/usr/bin/env python3
"""Benchmark WishGraph hook latency with real cold Python subprocesses."""

from __future__ import annotations

import argparse
import json
import math
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


SCRIPT_ROOT = Path(__file__).resolve().parent
HOOK_ASSETS = SCRIPT_ROOT.parent / "assets" / "hooks"
RUNTIME_FILES = (
    "memory_sync.py",
    "git_state.py",
    "workflow_state.py",
    "policy.py",
    "host_adapter.py",
)
PRETOOL_LIMIT_MS = 200.0
SESSION_LIMIT_MS = 500.0
BULK_DELTA_LIMIT_MS = 25.0


def run(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def nearest_rank_p95(samples: list[float]) -> float:
    if not samples:
        raise ValueError("at least one sample is required")
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def task_spec() -> str:
    return """# 012 - Hook benchmark fixture

<!-- wishgraph:task-state:start -->
```json
{
  "schema_version": 1,
  "kind": "task",
  "task_id": "012",
  "parent_task_id": null,
  "dependencies": [],
  "status": "approved",
  "work_type": "sequential",
  "batch_id": null,
  "attempt": 1,
  "execution_mode": "exclusive",
  "comparison_group": null,
  "run_report": "reports/runs/012-attempt-1.md",
  "worker_creation_authorized": true,
  "integration_policy": "inherited_task_approval"
}
```
<!-- wishgraph:task-state:end -->

## Intent

Exercise the hot-path Worker gate.

## Change Set

| Target | Anchor | Required Change |
| --- | --- | --- |
| `src/**` | benchmark | Permit the benchmark write probe. |

## Do Not Do

- Do not modify files outside `src/**`.

## Validation

- [ ] `python3 -m unittest`

## Rollback Boundary

Discard the temporary benchmark repository.
"""


def setup_fixture(base: Path) -> tuple[Path, Path]:
    root = base / "fixture"
    hook_dir = root / ".wishgraph" / "hooks"
    hook_dir.mkdir(parents=True)
    run(["git", "init", "-q"], cwd=root)
    run(["git", "config", "user.email", "benchmark@example.com"], cwd=root)
    run(["git", "config", "user.name", "WishGraph Benchmark"], cwd=root)

    shutil.copy2(HOOK_ASSETS / "config.json", root / ".wishgraph" / "config.json")
    for filename in RUNTIME_FILES:
        shutil.copy2(HOOK_ASSETS / filename, hook_dir / filename)

    task_path = root / "tasks" / "build" / "012-hook-benchmark.md"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(task_spec(), encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "probe.py").write_text("VALUE = 1\n", encoding="utf-8")
    run(["git", "add", "."], cwd=root)
    run(["git", "commit", "-qm", "benchmark fixture"], cwd=root)

    runtime = hook_dir / "memory_sync.py"
    neutral_payload = {
        "cwd": str(root),
        "session_id": "bench-neutral",
        "host": "codex",
    }
    invoke(runtime, root, "session-start", neutral_payload)
    acquired = run(
        [
            sys.executable,
            str(runtime),
            "claim",
            "acquire",
            "012",
            "--worker-id",
            "bench-worker",
            "--session-id",
            "bench-worker",
            "--host",
            "codex",
            "--host-thread-ref",
            "bench-worker",
        ],
        cwd=root,
        check=False,
    )
    claim_payload = json.loads(acquired.stdout or "{}")
    if not claim_payload.get("ok"):
        raise RuntimeError(
            "failed to prepare Worker Claim: "
            f"returncode={acquired.returncode}, payload={claim_payload}, "
            f"stderr={acquired.stderr.strip()}"
        )
    return root, runtime


def invoke(
    runtime: Path,
    root: Path,
    event: str,
    payload: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    process = run(
        [sys.executable, str(runtime), event],
        cwd=root,
        input_text=json.dumps(payload),
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if process.returncode != 0:
        raise RuntimeError(
            f"{event} returned {process.returncode}: {process.stderr.strip()}"
        )
    try:
        output = json.loads(process.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{event} returned invalid JSON: {process.stdout!r}") from exc
    if not isinstance(output, dict):
        raise RuntimeError(f"{event} returned non-object JSON")
    return elapsed_ms, output


def validate_output(case: str, output: dict[str, Any]) -> None:
    hook_output = output.get("hookSpecificOutput")
    if case == "pretool_neutral_write_deny":
        if not isinstance(hook_output, dict) or hook_output.get(
            "permissionDecision"
        ) != "deny":
            raise RuntimeError(f"neutral write was not denied: {output}")
    elif case in {
        "pretool_passthrough",
        "pretool_worker_write_allow",
        "pretool_commit_staged",
    }:
        if output != {}:
            raise RuntimeError(f"{case} expected an empty allow response: {output}")


def payload_factories(root: Path) -> dict[str, tuple[str, Callable[[int], dict[str, Any]]]]:
    write_input = {"file_path": str(root / "src" / "probe.py")}
    return {
        "pretool_passthrough": (
            "pre-tool-use",
            lambda _: {
                "cwd": str(root),
                "session_id": "bench-neutral",
                "host": "codex",
                "tool_name": "Bash",
                "tool_input": {"command": "pwd"},
            },
        ),
        "pretool_neutral_write_deny": (
            "pre-tool-use",
            lambda _: {
                "cwd": str(root),
                "session_id": "bench-neutral",
                "host": "codex",
                "tool_name": "Write",
                "tool_input": write_input,
            },
        ),
        "pretool_worker_write_allow": (
            "pre-tool-use",
            lambda _: {
                "cwd": str(root),
                "session_id": "bench-worker",
                "host": "codex",
                "tool_name": "Write",
                "tool_input": write_input,
            },
        ),
        "pretool_commit_staged": (
            "pre-tool-use",
            lambda _: {
                "cwd": str(root),
                "session_id": "bench-worker",
                "host": "codex",
                "tool_name": "Bash",
                "tool_input": {"command": "git commit -m benchmark"},
            },
        ),
        "session_existing": (
            "session-start",
            lambda _: {
                "cwd": str(root),
                "session_id": "bench-neutral",
                "host": "codex",
            },
        ),
        "session_fresh": (
            "session-start",
            lambda index: {
                "cwd": str(root),
                "session_id": f"bench-fresh-{time.time_ns()}-{index}",
                "host": "codex",
            },
        ),
    }


def measure_case(
    runtime: Path,
    root: Path,
    name: str,
    event: str,
    payload_factory: Callable[[int], dict[str, Any]],
    *,
    warmup: int,
    iterations: int,
    rounds: int,
) -> dict[str, Any]:
    for index in range(warmup):
        _, output = invoke(runtime, root, event, payload_factory(index))
        validate_output(name, output)

    round_results: list[dict[str, float]] = []
    for round_index in range(rounds):
        samples: list[float] = []
        for index in range(iterations):
            elapsed, output = invoke(
                runtime,
                root,
                event,
                payload_factory(round_index * iterations + index),
            )
            validate_output(name, output)
            samples.append(elapsed)
        round_results.append(
            {
                "p50_ms": round(sorted(samples)[len(samples) // 2], 3),
                "p95_ms": round(nearest_rank_p95(samples), 3),
                "max_ms": round(max(samples), 3),
            }
        )
    return {
        "p95_ms": max(result["p95_ms"] for result in round_results),
        "rounds": round_results,
    }


def create_bulk_tree(root: Path, count: int) -> None:
    bulk = root / "src" / "bulk"
    bulk.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (bulk / f"probe-{index:06d}.txt").write_text("x\n", encoding="utf-8")


def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="wishgraph-hook-bench-") as tempdir:
        root, runtime = setup_fixture(Path(tempdir))
        factories = payload_factories(root)
        results: dict[str, Any] = {}
        for name, (event, factory) in factories.items():
            results[name] = measure_case(
                runtime,
                root,
                name,
                event,
                factory,
                warmup=args.warmup,
                iterations=args.iterations,
                rounds=args.rounds,
            )

        bulk_probe: dict[str, Any] | None = None
        if args.bulk_files:
            create_bulk_tree(root, args.bulk_files)
            bulk_results: dict[str, Any] = {}
            for name in (
                "pretool_passthrough",
                "pretool_neutral_write_deny",
                "pretool_worker_write_allow",
            ):
                event, factory = factories[name]
                measured = measure_case(
                    runtime,
                    root,
                    name,
                    event,
                    factory,
                    warmup=max(1, args.warmup // 2),
                    iterations=args.iterations,
                    rounds=args.rounds,
                )
                measured["delta_ms"] = round(
                    measured["p95_ms"] - results[name]["p95_ms"], 3
                )
                bulk_results[name] = measured
            bulk_probe = {
                "file_count": args.bulk_files,
                "delta_limit_ms": args.bulk_delta_limit_ms,
                "results": bulk_results,
            }

        violations: list[str] = []
        for name, result in results.items():
            limit = (
                args.session_limit_ms
                if name.startswith("session_")
                else args.pretool_limit_ms
            )
            if result["p95_ms"] >= limit:
                violations.append(f"{name} p95 {result['p95_ms']}ms >= {limit}ms")
        if bulk_probe is not None:
            for name, result in bulk_probe["results"].items():
                if result["delta_ms"] > args.bulk_delta_limit_ms:
                    violations.append(
                        f"{name} bulk delta {result['delta_ms']}ms > "
                        f"{args.bulk_delta_limit_ms}ms"
                    )

        return {
            "schema_version": 1,
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "git": run(["git", "--version"], cwd=root).stdout.strip(),
            },
            "method": {
                "cold_python_subprocess": True,
                "p95": "nearest-rank",
                "warmup": args.warmup,
                "iterations": args.iterations,
                "rounds": args.rounds,
            },
            "thresholds_ms": {
                "pretool_p95": args.pretool_limit_ms,
                "session_start_p95": args.session_limit_ms,
                "bulk_p95_delta": args.bulk_delta_limit_ms,
            },
            "results": results,
            "bulk_probe": bulk_probe,
            "passed": not violations,
            "violations": violations,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--bulk-files", type=int, default=5000)
    parser.add_argument("--pretool-limit-ms", type=float, default=PRETOOL_LIMIT_MS)
    parser.add_argument("--session-limit-ms", type=float, default=SESSION_LIMIT_MS)
    parser.add_argument(
        "--bulk-delta-limit-ms", type=float, default=BULK_DELTA_LIMIT_MS
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    for name in ("warmup", "iterations", "rounds", "bulk_files"):
        if getattr(args, name) < 0 or (name in {"iterations", "rounds"} and not getattr(args, name)):
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


def main() -> int:
    args = parse_args()
    report = benchmark(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 1 if args.enforce and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
