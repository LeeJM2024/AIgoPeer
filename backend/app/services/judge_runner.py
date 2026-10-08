"""Run a C++17 submission in an ephemeral, constrained Docker container.

The worker is intentionally the only component with access to the Docker socket.
Student requests merely enqueue an integer submission id; neither the API process
nor the Vue client executes or receives hidden testcase data.
"""

from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import docker
from docker.errors import APIError, DockerException, NotFound

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
            user="10001:10001",
            volumes={settings.judge_work_volume: {"bind": "/workspace", "mode": "rw"}},
            working_dir=f"/workspace/{work_name}",
        )
        status = container.wait(timeout=timeout_seconds)
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


def _prepare_work_dir(*, submission_id: int, source_code: str) -> tuple[str, Path]:
    work_name = f"submission-{submission_id}-{uuid.uuid4().hex}"
    work_dir = settings.judge_work_dir / work_name
    try:
        work_dir.mkdir(parents=True, exist_ok=False)
        source_path = work_dir / "main.cpp"
        source_path.write_text(source_code, encoding="utf-8")
        # The worker is root in its private volume; the runner is deliberately not.
        shutil.chown(work_dir, user=10001, group=10001)
        shutil.chown(source_path, user=10001, group=10001)
    except OSError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise JudgeInfrastructureError("judge workspace is unavailable") from exc
    return work_name, work_dir


def _read_output(path: Path) -> str:
    try:
        if not path.exists() or path.stat().st_size > settings.judge_output_limit_bytes:
            raise ValueError("output exceeds limit")
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise JudgeInfrastructureError("judge output cannot be read") from exc


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
                script="g++ -std=c++17 -O2 -pipe -o main main.cpp",
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

        started = time.monotonic()
        max_memory_kb: int | None = None
        passed = 0
        executed = 0
        for case_index, case in enumerate(cases, start=1):
            if (time.monotonic() - started) * 1000 >= settings.judge_total_time_limit_ms:
                return JudgeRunResult("TLE", executed, passed, settings.judge_total_time_limit_ms, max_memory_kb)
            input_path = work_dir / "input.txt"
            output_path = work_dir / "output.txt"
            input_path.write_text(case.input_data, encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            shutil.chown(input_path, user=10001, group=10001)
            shutil.chown(output_path, user=10001, group=10001)
            # `ulimit -f` keeps redirected program output within the agreed cap.
            file_blocks = max(1, settings.judge_output_limit_bytes // 512)
            script = (
                f"ulimit -f {file_blocks}; "
                "/usr/bin/time -f 'ALGOPEER_MEMORY_KB:%M' "
                "./main < input.txt > output.txt"
            )
            before = time.monotonic()
            try:
                execution = _run_container(
                    work_name=work_name,
                    memory_limit_mb=memory_limit_mb,
                    script=script,
                    timeout_seconds=max(1, time_limit_ms / 1000) + 0.25,
                )
            except TimeoutError:
                elapsed = int((time.monotonic() - started) * 1000)
                return JudgeRunResult("TLE", executed + 1, passed, elapsed, max_memory_kb)
            elapsed_case_ms = int((time.monotonic() - before) * 1000)
            executed += 1
            for line in (execution.stderr or "").splitlines():
                if line.startswith("ALGOPEER_MEMORY_KB:"):
                    try:
                        memory_kb = int(line.split(":", 1)[1])
                        max_memory_kb = max(max_memory_kb or 0, memory_kb)
                    except ValueError:
                        pass
            if execution.returncode != 0:
                return JudgeRunResult(
                    "RE", executed, passed, int((time.monotonic() - started) * 1000), max_memory_kb
                )
            try:
                actual_output = _read_output(output_path)
            except ValueError:
                return JudgeRunResult(
                    "RE", executed, passed, int((time.monotonic() - started) * 1000), max_memory_kb
                )
            if _normalized_output(actual_output) != _normalized_output(case.expected_output):
                return JudgeRunResult(
                    "WA", executed, passed, int((time.monotonic() - started) * 1000), max_memory_kb
                )
            passed += 1
            if elapsed_case_ms > time_limit_ms:
                return JudgeRunResult(
                    "TLE", executed, passed, int((time.monotonic() - started) * 1000), max_memory_kb
                )
        return JudgeRunResult(
            "AC", executed, passed, int((time.monotonic() - started) * 1000), max_memory_kb
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
