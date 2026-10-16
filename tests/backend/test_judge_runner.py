"""Docker wait timeouts must produce TLE rather than infrastructure retries."""

from types import SimpleNamespace

import pytest
from app.services import judge_runner
from requests.exceptions import ConnectionError, ReadTimeout
from urllib3.exceptions import ReadTimeoutError


@pytest.mark.parametrize(
    "error",
    [ReadTimeout("wait expired"), ConnectionError(ReadTimeoutError(None, None, "stream timed out"))],
)
def test_docker_wait_read_timeout_is_execution_timeout(monkeypatch, error):
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
