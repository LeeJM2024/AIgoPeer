"""Run a C++17 submission in an ephemeral, constrained Docker container.

The worker is intentionally the only component with access to the Docker socket.
Student requests merely enqueue an integer submission id; neither the API process
nor the Vue client executes or receives hidden testcase data.
"""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.types import LogConfig
from requests.exceptions import ConnectionError, ReadTimeout
from urllib3.exceptions import ReadTimeoutError

from app.core.config import settings


class JudgeInfrastructureError(RuntimeError):
    """Docker or the worker's isolated workspace could not be used safely."""


@dataclass(frozen=True)
class JudgeCase:
    input_data: str
    expected_output: str


@dataclass(frozen=True)
class JudgeRunResult:
    status: str
    executed_case_count: int
    passed_case_count: int
    time_ms: int | None
    memory_kb: int | None
    compiler_output: str | None = None


@dataclass(frozen=True)
class ContainerProcessResult:
    returncode: int
    stdout: str
    stderr: str


def _normalized_output(value: str) -> str:
    """Ignore line-end whitespace and trailing blank lines, but nothing else."""
    return "\n".join(line.rstrip() for line in value.splitlines()).rstrip()


def _run_container(
    *, work_name: str, memory_limit_mb: int, script: str, timeout_seconds: float
) -> ContainerProcessResult:
    container = None
    try:
        client = docker.from_env()
        container = client.containers.run(
            image=settings.judge_image,
            command=["sh", "-ceu", script],
            name=f"algopeer-{work_name}",
            detach=True,
            network_disabled=True,
            read_only=True,
            tmpfs={"/tmp": "rw,nosuid,nodev,size=64m"},
            security_opt=["no-new-privileges"],
            pids_limit=64,
            nano_cpus=1_000_000_000,
            mem_limit=f"{memory_limit_mb}m",
            user=f"{_work_uid(work_name)}:{_work_uid(work_name)}",
            cap_drop=["ALL"],
            log_config=LogConfig(type="json-file", config={"max-size": "1m", "max-file": "1"}),
            ulimits=[docker.types.Ulimit(name="nofile", soft=128, hard=128),
                     docker.types.Ulimit(name="core", soft=0, hard=0)],
            volumes={settings.judge_work_volume: {"bind": "/workspace", "mode": "rw"}},
            working_dir=f"/workspace/{work_name}",
        )
        try:
            status = container.wait(timeout=timeout_seconds)
        except (ReadTimeout, ConnectionError) as exc:
            # requests wraps a streamed Docker wait read timeout in ConnectionError.
            read_timeout = isinstance(exc, ReadTimeout) or any(
                isinstance(cause, ReadTimeoutError) for cause in exc.args
            )
            if not read_timeout:
                raise JudgeInfrastructureError("Docker wait connection is unavailable") from exc
            try:
                container.kill()
            except DockerException:
                pass
            raise TimeoutError from exc
        logs = container.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
        exit_code = int(status.get("StatusCode", 1))
        return ContainerProcessResult(
            returncode=exit_code,
            # Student stdout is redirected to a file.  Container logs therefore
            # only contain compiler/runtime diagnostics and /usr/bin/time output.
            stdout=logs,
            stderr=logs,
        )
    except APIError as exc:
        raise JudgeInfrastructureError("Docker could not create the judge container") from exc
    except DockerException as exc:
        if container is None:
            raise JudgeInfrastructureError("Docker socket is unavailable") from exc
        try:
            container.kill()
        except DockerException:
            pass
        raise TimeoutError from exc
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except (DockerException, NotFound):
                pass


def _work_uid(work_name: str) -> int:
    # Each submission gets a distinct OS identity inside the shared worker volume.
    if work_name.startswith("submission-"):
        submission_id = int(work_name.split("-", 2)[1])
        if not 0 < submission_id < 2**31 - 100000:
            raise JudgeInfrastructureError("submission id exceeds sandbox identity range")
        return 100000 + submission_id
    return 10001  # Unit-test container names never handle submitted code.


def _prepare_work_dir(*, submission_id: int, source_code: str) -> tuple[str, Path]:
    work_name = f"submission-{submission_id}-{uuid.uuid4().hex}"
    work_dir = settings.judge_work_dir / work_name
    try:
        work_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        source_path = work_dir / "main.cpp"
        source_path.write_text(source_code, encoding="utf-8")
        # The worker is root in its private volume; the runner is deliberately not.
        uid = _work_uid(work_name)
        shutil.chown(work_dir, user=uid, group=uid)
        shutil.chown(source_path, user=uid, group=uid)
    except OSError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise JudgeInfrastructureError("judge workspace is unavailable") from exc
    return work_name, work_dir


def _read_regular(path: Path, limit: int) -> str:
    # The worker is privileged; never follow student-created symlinks/FIFOs.
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit or path.is_symlink():
            raise ValueError("unsafe judge output")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("output exceeds limit")
        return data.decode("utf-8", errors="replace")


def _read_output(path: Path) -> str:
    try:
        if not path.exists() or path.stat().st_size > settings.judge_output_limit_bytes:
            raise ValueError("output exceeds limit")
        return _read_regular(path, settings.judge_output_limit_bytes)
    except OSError as exc:
        raise JudgeInfrastructureError("judge output cannot be read") from exc


def _read_usage(path: Path) -> tuple[int, int]:
    """Read GNU time's final record, separate from student diagnostics."""
    try:
        elapsed, memory = _read_regular(path, 4096).splitlines()[-1].split()
        milliseconds = Decimal(elapsed) * 1000
        memory_kb = int(memory)
        if not milliseconds.is_finite() or milliseconds < 0 or memory_kb < 0:
            raise ValueError("invalid usage")
        return int(milliseconds.to_integral_value(rounding=ROUND_CEILING)), memory_kb
    except (OSError, ValueError, IndexError, InvalidOperation) as exc:
        raise JudgeInfrastructureError("judge runtime usage is unavailable") from exc


def run_cpp17_submission(
    *,
    submission_id: int,
    source_code: str,
    cases: list[JudgeCase],
    time_limit_ms: int,
    memory_limit_mb: int,
) -> JudgeRunResult:
    """Compile once and run test cases sequentially until the first non-AC result."""
    if not cases:
        raise JudgeInfrastructureError("programming problem has no test cases")
    work_name, work_dir = _prepare_work_dir(submission_id=submission_id, source_code=source_code)
    try:
        try:
            compile_result = _run_container(
                work_name=work_name,
                memory_limit_mb=memory_limit_mb,
                script="ulimit -f 32768; g++ -std=c++17 -O2 -pipe -fmax-errors=10 -o main main.cpp",
                timeout_seconds=max(5, settings.judge_total_time_limit_ms / 1000),
            )
        except TimeoutError:
            raise JudgeInfrastructureError("compilation timed out") from None
        if compile_result.returncode != 0:
            return JudgeRunResult(
                status="CE",
                executed_case_count=0,
                passed_case_count=0,
                time_ms=None,
                memory_kb=None,
                compiler_output=(compile_result.stderr or compile_result.stdout)[
                    : settings.judge_compiler_output_limit_bytes
                ],
            )

        elapsed_ms = 0
        max_memory_kb: int | None = None
        passed = 0
        executed = 0
        for case_index, case in enumerate(cases, start=1):
            remaining_ms = settings.judge_total_time_limit_ms - elapsed_ms
            if remaining_ms <= 0:
                return JudgeRunResult("TLE", executed, passed, elapsed_ms, max_memory_kb)
            case_budget_ms = min(time_limit_ms, remaining_ms)
            input_path = work_dir / "input.txt"
            output_path = work_dir / "output.txt"
            # A previous test may have replaced these with symlinks.
            input_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
            input_path.write_text(case.input_data, encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            uid = _work_uid(work_name)
            shutil.chown(input_path, user=uid, group=uid)
            shutil.chown(output_path, user=uid, group=uid)
            usage_path = work_dir / f"usage-{case_index}.txt"
            # `ulimit -f` keeps redirected program output within the agreed cap.
            file_blocks = max(1, settings.judge_output_limit_bytes // 512)
            script = (
                f"ulimit -f {file_blocks}; "
                f"/usr/bin/time -o {usage_path.name} -f '%e %M' "
                f"timeout --kill-after=0.1s {case_budget_ms / 1000:.3f}s "
                # Reserve timeout's 124 status; a student returning 124 is RE.
                "sh -c './main; code=$?; if [ \"$code\" -eq 124 ]; then exit 125; fi; exit \"$code\"' "
                "< input.txt > output.txt"
            )
            try:
                execution = _run_container(
                    work_name=work_name,
                    memory_limit_mb=memory_limit_mb,
                    script=script,
                    # Docker start/wait/remove is infrastructure time. The
                    # in-container timeout enforces the student's actual budget.
                    timeout_seconds=case_budget_ms / 1000 + 5,
                )
            except TimeoutError:
                raise JudgeInfrastructureError("judge container exceeded its wall timeout") from None
            executed += 1
            elapsed_case_ms, memory_kb = _read_usage(usage_path)
            elapsed_ms += elapsed_case_ms
            max_memory_kb = max(max_memory_kb or 0, memory_kb)
            if execution.returncode == 124 or elapsed_case_ms > case_budget_ms or (
                execution.returncode == 137 and elapsed_case_ms >= case_budget_ms
            ):
                return JudgeRunResult("TLE", executed, passed, elapsed_ms, max_memory_kb)
            if execution.returncode != 0:
                return JudgeRunResult(
                    "RE", executed, passed, elapsed_ms, max_memory_kb
                )
            try:
                actual_output = _read_output(output_path)
            except ValueError:
                return JudgeRunResult(
                    "RE", executed, passed, elapsed_ms, max_memory_kb
                )
            if _normalized_output(actual_output) != _normalized_output(case.expected_output):
                return JudgeRunResult(
                    "WA", executed, passed, elapsed_ms, max_memory_kb
                )
            passed += 1
        return JudgeRunResult(
            "AC", executed, passed, elapsed_ms, max_memory_kb
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
