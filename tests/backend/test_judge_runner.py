"""Container wall timeouts and in-container program budgets have separate semantics."""

from types import SimpleNamespace

import pytest
from app.services import judge_runner
from requests.exceptions import ConnectionError, ReadTimeout
from urllib3.exceptions import ReadTimeoutError


@pytest.mark.parametrize(
    "error",
    [ReadTimeout("wait expired"), ConnectionError(ReadTimeoutError(None, None, "stream timed out"))],
)
def test_docker_wait_read_timeout_kills_and_removes_container(monkeypatch, error):
    events = []

    class Container:
        def wait(self, **kwargs):
            raise error

        def kill(self):
            events.append("kill")

        def remove(self, **kwargs):
            events.append("remove")

    client = SimpleNamespace(containers=SimpleNamespace(run=lambda **kwargs: Container()))
    monkeypatch.setattr(judge_runner.docker, "from_env", lambda: client)
    with pytest.raises(TimeoutError):
        judge_runner._run_container(
            work_name="test-timeout", memory_limit_mb=256, script="./main", timeout_seconds=2
        )
    assert events == ["kill", "remove"]


def test_docker_wait_connection_loss_is_infrastructure_failure(monkeypatch):
    events = []

    class Container:
        def wait(self, **kwargs):
            raise ConnectionError("daemon connection lost")

        def remove(self, **kwargs):
            events.append("remove")

    client = SimpleNamespace(containers=SimpleNamespace(run=lambda **kwargs: Container()))
    monkeypatch.setattr(judge_runner.docker, "from_env", lambda: client)
    with pytest.raises(judge_runner.JudgeInfrastructureError):
        judge_runner._run_container(
            work_name="test-connection", memory_limit_mb=256, script="./main", timeout_seconds=2
        )
    assert events == ["remove"]


@pytest.fixture
def simulated_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(judge_runner, "_prepare_work_dir", lambda **kwargs: ("test", tmp_path))
    monkeypatch.setattr(judge_runner.shutil, "chown", lambda *args, **kwargs: None)
    monkeypatch.setattr(judge_runner.settings, "judge_total_time_limit_ms", 1000)
    calls = []

    def simulate(results):
        values = iter(results)
        def run(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return judge_runner.ContainerProcessResult(0, "", "")
            elapsed, status, output = next(values)
            (tmp_path / f"usage-{len(calls) - 1}.txt").write_text(f"{elapsed} 4096\n")
            (tmp_path / "output.txt").write_text(output)
            return judge_runner.ContainerProcessResult(status, "", "ALGOPEER_MEMORY_KB:999999")
        monkeypatch.setattr(judge_runner, "_run_container", run)
        return calls
    return simulate


def judge(cases=1):
    return judge_runner.run_cpp17_submission(submission_id=1, source_code="", cases=[
        judge_runner.JudgeCase("", "3") for _ in range(cases)
    ], time_limit_ms=500, memory_limit_mb=128)


def test_only_program_usage_is_counted(simulated_runner):
    calls = simulated_runner([("0.01", 0, "3"), ("0.02", 0, "3")])
    result = judge(2)
    assert (result.status, result.time_ms, result.memory_kb, result.passed_case_count) == ("AC", 30, 4096, 2)
    assert "timeout --kill-after=0.1s 0.500s" in calls[1]["script"]
    assert calls[1]["timeout_seconds"] > 5


@pytest.mark.parametrize("elapsed,status,output,expected", [
    ("0.50", 124, "3", "TLE"), ("0.60", 137, "", "TLE"),
    ("0.51", 0, "wrong", "TLE"), ("0.01", 139, "", "RE"),
    ("0.01", 0, "wrong", "WA"),
    ("0.01", 125, "", "RE"),
])
def test_runtime_verdicts(simulated_runner, elapsed, status, output, expected):
    simulated_runner([(elapsed, status, output)])
    result = judge()
    assert result.status == expected
    assert result.passed_case_count == 0


def test_total_budget_counts_program_time_and_limits_next_case(simulated_runner, monkeypatch):
    monkeypatch.setattr(judge_runner.settings, "judge_total_time_limit_ms", 700)
    calls = simulated_runner([("0.40", 0, "3"), ("0.30", 124, "")])
    result = judge(3)
    assert (result.status, result.executed_case_count, result.passed_case_count, result.time_ms) == ("TLE", 2, 1, 700)
    assert "0.300s" in calls[2]["script"]


def test_missing_usage_is_infrastructure_error(simulated_runner, monkeypatch):
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        return judge_runner.ContainerProcessResult(0, "", "")
    monkeypatch.setattr(judge_runner, "_run_container", run)
    with pytest.raises(judge_runner.JudgeInfrastructureError, match="usage"):
        judge()


def test_outer_timeout_is_infrastructure_error(simulated_runner, monkeypatch):
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return judge_runner.ContainerProcessResult(0, "", "")
        raise TimeoutError
    monkeypatch.setattr(judge_runner, "_run_container", run)
    with pytest.raises(judge_runner.JudgeInfrastructureError, match="wall timeout"):
        judge()


def test_sandbox_submissions_have_distinct_os_identities():
    assert judge_runner._work_uid('submission-1-random') != judge_runner._work_uid('submission-2-random')
    assert judge_runner._work_uid('submission-1-first') == judge_runner._work_uid('submission-1-retry')


def test_worker_rejects_symlinked_output(tmp_path):
    secret = tmp_path / 'secret'
    secret.write_text('not a student result')
    output = tmp_path / 'output.txt'
    try:
        output.symlink_to(secret)
    except OSError:
        pytest.skip('Creating symlinks requires Windows developer mode')
    with pytest.raises((judge_runner.JudgeInfrastructureError, ValueError)):
        judge_runner._read_output(output)
