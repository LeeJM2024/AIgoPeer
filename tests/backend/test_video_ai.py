import json
from decimal import Decimal
from zipfile import ZipFile

import httpx
import pytest
from app.core.config import settings
from app.services import video_ai_provider as provider
from app.services import video_analysis as analysis
from app.services.video_ai_settings import cipher
from sqlalchemy import text


def configuration(**overrides):
    return {
        "provider": "qwen",
        "base_url": "https://example.com/v1",
        "model": "qwen3.5-omni-flash",
        "api_key": "test-secret-123",
        "enabled": True,
        **overrides,
    }


def answer(rubric_id=1, score=80, start=1, end=5):
    return {
        "summary": "清楚展示算法步骤。",
        "assessments": [
            {
                "rubric_item_id": rubric_id,
                "suggested_score": score,
                "confidence": 0.8,
                "rationale": "讲解清楚，复杂度可继续完善。",
                "evidence": [
                    {
                        "start_seconds": start,
                        "end_seconds": end,
                        "description": "展示算法过程。",
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize("kind", ["qwen", "gemini"])
def test_native_video_request_and_response(monkeypatch, tmp_path, kind):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video-with-audio")
    original_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        if kind == "qwen":
            return httpx.Response(
                200,
                text="data: "
                + json.dumps({"choices": [{"delta": {"content": "视频内容"}}]})
                + "\n\ndata: [DONE]\n",
            )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": "视频内容"}]},
                    }
                ]
            },
        )

    monkeypatch.setattr(provider, "validate_endpoint", lambda _url: None)
    monkeypatch.setattr(
        provider.httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs, transport=httpx.MockTransport(respond)
        ),
    )
    result = provider.request_text(configuration(provider=kind), "描述视频", video)
    assert result == "视频内容"
    body = json.loads(requests[0].content)
    if kind == "qwen":
        assert body["stream"] is True
        assert body["messages"][0]["content"][0]["type"] == "video_url"
        assert requests[0].headers["Authorization"] == "Bearer test-secret-123"
    else:
        assert (
            body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "video/mp4"
        )
        assert requests[0].headers["x-goog-api-key"] == "test-secret-123"
    assert "test-secret" not in str(requests[0].url)


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "AI_AUTH_FAILED"),
        (429, "AI_RATE_LIMIT"),
        (400, "AI_MODEL_OR_REQUEST_INVALID"),
        (302, "AI_PROVIDER_ERROR"),
    ],
)
def test_provider_errors_do_not_expose_secrets(monkeypatch, status, expected):
    original_client = httpx.Client
    monkeypatch.setattr(provider, "validate_endpoint", lambda _url: None)
    monkeypatch.setattr(
        provider.httpx,
        "Client",
        lambda **kwargs: original_client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(
                    status, text="test-secret-123 provider echoed credential"
                )
            ),
        ),
    )
    with pytest.raises(provider.VideoAIError) as caught:
        provider.request_text(configuration(), "test")
    assert str(caught.value) == expected
    assert "secret" not in str(caught.value)


def test_private_endpoint_rejected(monkeypatch):
    monkeypatch.setattr(
        provider.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(provider.VideoAIError, match="AI_INVALID_ENDPOINT"):
        provider.validate_endpoint("https://internal.example/v1")


@pytest.mark.parametrize(
    "data",
    [answer(score=101), answer(start=8, end=7), answer(end=11), answer(rubric_id=999)],
)
def test_scores_and_evidence_are_validated(data):
    with pytest.raises(provider.VideoAIError, match="AI_RESPONSE_INVALID"):
        analysis.validate_result(
            json.dumps(data),
            [{"rubric_item_id": 1, "name": "正确性", "max_score": Decimal(100)}],
            10,
        )


@pytest.fixture
def ai_course(course, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    manifest = {
        "ppt_path": "slides.pptx",
        "video_path": "video.mp4",
        "readme_path": "README.md",
        "examples": [{"location": "PPT", "pages": [1, 2, 3]}],
        "source_paths": ["main.cpp"],
        "tests": [
            {"input_path": f"{i}.in", "expected_path": f"{i}.out"} for i in range(3)
        ],
    }
    with ZipFile(tmp_path / "work.zip", "w") as archive:
        archive.writestr("video.mp4", b"video")
    with course["engine"].begin() as db:
        submission = db.execute(
            text("""INSERT INTO submissions
            (assignment_id,author_id,class_id,status,anonymous_token,manifest_json)
            VALUES (:a,:u,:c,'VALID','ai-test',CAST(:m AS jsonb)) RETURNING id"""),
            {
                "a": course["id"],
                "u": course["reviewers"][0][0],
                "c": course["classes"][0],
                "m": json.dumps(manifest),
            },
        ).scalar_one()
        file_id = db.execute(
            text("""INSERT INTO submission_files
            (submission_id,file_kind,storage_key,file_name,size_bytes,checksum)
            VALUES (:s,'ZIP','work.zip','work.zip',100,'test') RETURNING id"""),
            {"s": submission},
        ).scalar_one()
        rubric_id = db.execute(text("SELECT id FROM rubric_items")).scalar_one()
    course.update(submission=submission, file_id=file_id, rubric_id=rubric_id)
    return course


def test_teacher_settings_encrypted_and_isolated(
    teacher_api, pg_engine, tmp_path, monkeypatch
):
    from app.core.security import CurrentUser, get_current_user
    from app.main import app

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    client, teacher = teacher_api
    result = client.put("/api/teacher/ai-video/settings", json=configuration())
    assert result.status_code == 200, result.text
    assert result.json()["data"]["configured"]
    assert "test-secret" not in result.text
    with pg_engine.connect() as db:
        encrypted = db.execute(
            text("SELECT api_key_encrypted FROM teacher_video_ai_settings")
        ).scalar_one()
    assert "test-secret" not in encrypted
    assert cipher().decrypt(encrypted.encode()).decode() == "test-secret-123"
    assert (
        client.put(
            "/api/teacher/ai-video/settings", json=configuration(api_key=None)
        ).status_code
        == 200
    )
    changed = client.put(
        "/api/teacher/ai-video/settings",
        json=configuration(api_key=None, base_url="https://other.example/v1"),
    )
    assert changed.status_code == 422
    with pg_engine.begin() as db:
        other = db.execute(
            text("""INSERT INTO users(student_no,name,password_hash,system_role)
          VALUES ('OTHER-T','另一教师','unused','TEACHER') RETURNING id""")
        ).scalar_one()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(other, "TEACHER")
    assert not client.get("/api/teacher/ai-video/settings").json()["data"]["configured"]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(teacher, "STUDENT")
    assert client.get("/api/teacher/ai-video/settings").status_code == 403


def test_missing_and_invalid_configuration(teacher_api):
    client, _ = teacher_api
    assert (
        client.put(
            "/api/teacher/ai-video/settings", json=configuration(api_key=None)
        ).status_code
        == 422
    )
    for url in [
        "http://localhost:123",
        "https://user:pass@example.com",
        "https://example.com?key=secret",
    ]:
        assert (
            client.put(
                "/api/teacher/ai-video/settings", json=configuration(base_url=url)
            ).status_code
            == 422
        )


def test_full_analysis_persists_advice_and_reuses_without_changing_grades(
    ai_course, monkeypatch
):
    c = ai_course
    client = c["client"]
    monkeypatch.setattr(analysis, "probe", lambda _p: 125.0)
    monkeypatch.setattr(
        analysis, "make_clip", lambda _v, output, _s, _d: output.write_bytes(b"clip")
    )
    calls = []

    def respond(_config, prompt, video=None):
        calls.append((prompt, video is not None))
        return (
            "片段中的观察"
            if video
            else json.dumps(answer(c["rubric_id"], start=121, end=124))
        )

    monkeypatch.setattr(analysis, "request_text", respond)
    assert (
        client.put("/api/teacher/ai-video/settings", json=configuration()).status_code
        == 200
    )
    path = f"/api/teacher/submissions/{c['submission']}/video-analysis"
    first = client.post(path, json={})
    assert first.status_code == 200, first.text
    data = client.get(path).json()["data"]["runs"]
    assert data[0]["status"] == "SUCCEEDED", data
    assert (
        data[0]["result_json"]["assessments"][0]["evidence"][0]["start_seconds"] == 121
    )
    assert len(calls) == 3 and "开始秒数120" in calls[1][0]
    second = client.post(path, json={}).json()["data"]
    assert second["reused"] and second["run_id"] == first.json()["data"]["run_id"]
    with c["engine"].connect() as db:
        assert (
            db.execute(text("SELECT count(*) FROM ai_rubric_assessments")).scalar_one()
            == 1
        )
        assert db.execute(text("SELECT count(*) FROM teacher_grades")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM final_grades")).scalar_one() == 0


def test_failure_is_persisted_without_partial_scores(ai_course, monkeypatch):
    c = ai_course
    monkeypatch.setattr(analysis, "probe", lambda _p: 20.0)
    monkeypatch.setattr(
        analysis, "make_clip", lambda _v, output, _s, _d: output.write_bytes(b"clip")
    )
    monkeypatch.setattr(
        analysis, "request_text", lambda *args: "invalid-secret-response"
    )
    c["client"].put("/api/teacher/ai-video/settings", json=configuration())
    path = f"/api/teacher/submissions/{c['submission']}/video-analysis"
    assert c["client"].post(path, json={}).status_code == 200
    data = c["client"].get(path).json()["data"]["runs"][0]
    assert data["status"] == "FAILED" and data["error_code"] == "AI_RESPONSE_INVALID"
    assert "secret-response" not in json.dumps(data)
    with c["engine"].connect() as db:
        assert (
            db.execute(text("SELECT count(*) FROM ai_rubric_assessments")).scalar_one()
            == 0
        )


def test_active_dedup_cancel_delete_and_disabled(ai_course, monkeypatch):
    from app.api.routes import teacher_video_ai

    c = ai_course
    monkeypatch.setattr(teacher_video_ai, "analyze_run", lambda *args: None)
    c["client"].put("/api/teacher/ai-video/settings", json=configuration())
    path = f"/api/teacher/submissions/{c['submission']}/video-analysis"
    first = c["client"].post(path, json={}).json()["data"]
    second = c["client"].post(path, json={"force": True}).json()["data"]
    assert second["reused"] and first["run_id"] == second["run_id"]
    assert c["client"].post(path + f"/{first['run_id']}/cancel").status_code == 200
    assert c["client"].get(path).json()["data"]["runs"][0]["status"] == "CANCELLED"
    c["client"].post(path, json={})
    assert c["client"].delete("/api/teacher/ai-video/settings").status_code == 200
    assert c["client"].get(path).json()["data"]["runs"][0]["status"] == "CANCELLED"
    assert c["client"].post(path, json={}).status_code == 409


def test_connection_uses_saved_key_without_saving_draft(ai_course, monkeypatch):
    from app.api.routes import teacher_video_ai

    client = ai_course["client"]
    client.put("/api/teacher/ai-video/settings", json=configuration())
    received = []
    monkeypatch.setattr(
        teacher_video_ai, "test_connection", lambda value: received.append(value)
    )
    result = client.post(
        "/api/teacher/ai-video/test",
        json=configuration(api_key=None, model="other-omni"),
    )
    assert result.status_code == 200
    assert received[0]["api_key"] == "test-secret-123"
    assert (
        client.get("/api/teacher/ai-video/settings").json()["data"]["model"]
        == "qwen3.5-omni-flash"
    )


def test_cancellation_during_provider_request_does_not_save_advice(
    ai_course, monkeypatch
):
    c = ai_course
    monkeypatch.setattr(analysis, "probe", lambda _p: 20.0)
    monkeypatch.setattr(
        analysis, "make_clip", lambda _v, output, _s, _d: output.write_bytes(b"clip")
    )
    calls = []

    def respond(*args):
        calls.append(args)
        with c["engine"].begin() as db:
            db.execute(text("UPDATE video_analysis_runs SET status='CANCELLED'"))
        return "观察结果"

    monkeypatch.setattr(analysis, "request_text", respond)
    c["client"].put("/api/teacher/ai-video/settings", json=configuration())
    path = f"/api/teacher/submissions/{c['submission']}/video-analysis"
    assert c["client"].post(path, json={}).status_code == 200
    assert c["client"].get(path).json()["data"]["runs"][0]["status"] == "CANCELLED"
    assert len(calls) == 1
    with c["engine"].connect() as db:
        assert (
            db.execute(text("SELECT count(*) FROM ai_rubric_assessments")).scalar_one()
            == 0
        )
