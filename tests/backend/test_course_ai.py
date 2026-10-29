"""Text assistants: provider contract, real database authorization and grounded context."""

import json
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.main import app
from app.services import text_ai_provider as provider
from app.services.video_ai_provider import VideoAIError
from app.services.video_ai_settings import cipher
from sqlalchemy import text


def configuration(**extra):
    return {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "api_key": "teacher-secret-text",
        "enabled": True,
        **extra,
    }


@contextmanager
def student(identity):
    previous = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        identity, "STUDENT"
    )
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = previous


@pytest.fixture
def ai(course, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    course["calls"] = []

    def respond(config, messages, **kwargs):
        course["calls"].append((config, messages))
        return "先检查边界，再分析循环。\n```cpp\nint x = 0;\n```", {"total_tokens": 50}

    monkeypatch.setattr(provider, "complete", respond)
    result = course["client"].put("/api/teacher/ai-text/settings", json=configuration())
    assert result.status_code == 200, result.text
    with course["engine"].connect() as db:
        course["topic"] = db.execute(
            text("SELECT id FROM topics ORDER BY id LIMIT 1")
        ).scalar_one()
    return course


def test_settings_encrypt_retain_clear_and_connection_does_not_save(ai):
    client, engine = ai["client"], ai["engine"]
    result = client.get("/api/teacher/ai-text/settings")
    assert result.json()["data"]["student_daily_limit"] == 30
    assert "teacher-secret" not in result.text
    assert "no-store" in result.headers["cache-control"]
    with engine.connect() as db:
        encrypted = db.execute(
            text("SELECT api_key_encrypted FROM course_text_ai_settings")
        ).scalar_one()
    assert "secret" not in encrypted
    assert cipher().decrypt(encrypted.encode()).decode() == "teacher-secret-text"
    assert (
        client.put(
            "/api/teacher/ai-text/settings", json=configuration(api_key=None)
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/teacher/ai-text/settings",
            json=configuration(api_key=None, base_url="https://different.example/v1"),
        ).status_code
        == 422
    )
    result = client.post(
        "/api/teacher/ai-text/test", json=configuration(model="test-model")
    )
    assert result.status_code == 200
    assert (
        client.get("/api/teacher/ai-text/settings").json()["data"]["model"]
        == "deepseek-flash"
    )
    assert client.delete("/api/teacher/ai-text/settings").status_code == 200
    assert not client.get("/api/teacher/ai-text/settings").json()["data"]["configured"]


def test_knowledge_followup_is_persisted_isolated_and_quota_enforced(ai):
    client = ai["client"]
    base = f"/api/student/ai/topics/{ai['topic']}"
    conversation = str(uuid4())
    client.put(
        "/api/teacher/ai-text/settings", json=configuration(student_daily_limit=2)
    )
    with student(ai["reviewers"][0][0]):
        result = client.get("/api/student/ai/status")
        assert "base_url" not in result.text and "secret" not in result.text
        assert client.get("/api/teacher/ai-text/settings").status_code == 403
        for question in ("解释这个知识点", "继续举一个例子"):
            result = client.post(
                base + "/messages",
                json={"conversation_id": conversation, "question": question},
            )
            assert result.status_code == 200, result.text
        assert result.json()["data"]["remaining_today"] == 0
        result = client.post(
            base + "/messages",
            json={"conversation_id": conversation, "question": "第三次"},
        )
        assert result.status_code == 429
        rows = client.get(base + "/history").json()["data"]["items"]
        assert len(rows) == 2 and rows[0]["status"] == "SUCCEEDED"
    messages = ai["calls"][-1][1]
    assert messages[1] == {"role": "user", "content": "解释这个知识点"}
    assert messages[2]["role"] == "assistant"
    assert "description" in messages[-1]["content"]
    with student(ai["reviewers"][0][1]):
        assert client.get(base + "/history").json()["data"]["items"] == []
        result = client.post(
            base + "/messages",
            json={"conversation_id": conversation, "question": "不属于我的对话"},
        )
        assert result.status_code == 404
        assert client.get("/api/student/ai/topics/999999/history").status_code == 404


def test_failed_request_is_saved_and_can_retry(ai, monkeypatch):
    client = ai["client"]
    base = f"/api/student/ai/topics/{ai['topic']}"
    payload = {"conversation_id": str(uuid4()), "question": "讲解"}
    with student(ai["reviewers"][0][0]):
        original = provider.complete

        def fail(*args, **kwargs):
            raise VideoAIError("AI_AUTH_FAILED")

        monkeypatch.setattr(provider, "complete", fail)
        result = client.post(base + "/messages", json=payload)
        assert result.status_code == 502 and "teacher-secret" not in result.text
        row = client.get(base + "/history").json()["data"]["items"][0]
        assert row["status"] == "FAILED" and row["error_code"] == "AI_AUTH_FAILED"
        monkeypatch.setattr(provider, "complete", original)
        assert client.post(base + "/messages", json=payload).status_code == 200


def test_active_request_blocks_parallel_then_stale_request_expires(ai):
    user = ai["reviewers"][0][0]
    conversation = str(uuid4())
    with ai["engine"].begin() as db:
        db.execute(
            text("""INSERT INTO text_ai_requests(user_id,conversation_id,mode,context_key,model,question,status)
            VALUES (:u,:c,'KNOWLEDGE',:key,'model','之前的问题','PROCESSING')"""),
            {"u": user, "c": conversation, "key": f"knowledge:{ai['topic']}"},
        )
    with student(user):
        base = f"/api/student/ai/topics/{ai['topic']}"
        payload = {"conversation_id": conversation, "question": "新问题"}
        assert ai["client"].post(base + "/messages", json=payload).status_code == 409
        with ai["engine"].begin() as db:
            db.execute(
                text(
                    "UPDATE text_ai_requests SET created_at=now()-interval '11 minutes'"
                )
            )
        row = ai["client"].get(base + "/history").json()["data"]["items"][0]
        assert row["status"] == "FAILED" and row["error_code"] == "AI_INTERRUPTED"
        assert ai["client"].post(base + "/messages", json=payload).status_code == 200


@pytest.fixture
def programming(ai):
    with ai["engine"].begin() as db:
        aid = db.execute(
            text("""INSERT INTO assignments(title,type,status,created_by,submit_deadline)
            VALUES ('整数求和','PROGRAMMING','DRAFT',:t,'2030-01-01') RETURNING id"""),
            {"t": ai["teacher"]},
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO assignment_classes(assignment_id,class_id) VALUES (:a,:c)"
            ),
            {"a": aid, "c": ai["classes"][0]},
        )
        db.execute(
            text("""INSERT INTO programming_problems(assignment_id,statement,input_description,output_description,time_limit_ms,memory_limit_mb)
            VALUES (:a,'计算两个整数之和','两个整数','整数和',1000,256)"""),
            {"a": aid},
        )
        for public, source in [(True, "1 2"), (False, "HIDDEN_TEST_SECRET")]:
            db.execute(
                text("""INSERT INTO programming_test_cases(problem_assignment_id,input_data,expected_output,is_public,sort_order)
                VALUES (:a,:input,'3',:public,:order)"""),
                {
                    "a": aid,
                    "input": source,
                    "public": public,
                    "order": 1 if public else 2,
                },
            )
        db.execute(text("UPDATE assignments SET status='PUBLISHED' WHERE id=:a"), {"a": aid})
        sid = db.execute(
            text("""INSERT INTO code_submissions(assignment_id,author_id,class_id,language,source_code,version,status,compiler_output)
            VALUES (:a,:u,:c,'cpp17','OLD_CODE',1,'CE','undefined variable') RETURNING id"""),
            {"a": aid, "u": ai["reviewers"][0][0], "c": ai["classes"][0]},
        ).scalar_one()
    return ai, aid, sid


def test_programming_context_uses_only_own_public_data_and_version(programming):
    c, aid, sid = programming
    path = f"/api/student/assignments/{aid}/ai/messages"
    payload = {
        "conversation_id": str(uuid4()),
        "question": "哪里错了",
        "action": "debug",
        "source_code": "int changed;",
        "selected_code": "changed",
        "submission_id": sid,
    }
    with student(c["reviewers"][0][0]):
        result = c["client"].post(path, json=payload)
        assert result.status_code == 200, result.text
        sent = c["calls"][-1][1]
        assert "提示辅导模式" in sent[0]["content"]
        content = sent[-1]["content"]
        assert "HIDDEN_TEST_SECRET" not in content
        assert '"editor_changed_since_submission": true' in content
        assert (
            "OLD_CODE" in content
            and "undefined variable" in content
            and "int changed;" in content
        )
        assert (
            c["client"]
            .post(path, json={**payload, "selected_code": "stale"})
            .status_code
            == 422
        )
    with student(c["reviewers"][0][1]):
        assert (
            c["client"]
            .post(path, json={**payload, "conversation_id": str(uuid4())})
            .status_code
            == 404
        )
    with student(c["reviewers"][1][0]):
        assert (
            c["client"].get(f"/api/student/assignments/{aid}/ai/history").status_code
            == 404
        )


def test_teaching_uses_real_class_aggregate_and_does_not_write_grades(programming):
    c, _aid, _ = programming
    url = f"/api/teacher/ai/teaching/messages?class_id={c['classes'][0]}"
    result = c["client"].post(
        url, json={"conversation_id": str(uuid4()), "question": "如何安排下节课"}
    )
    assert result.status_code == 200, result.text
    content = c["calls"][-1][1][-1]["content"]
    assert "整数求和" in content and '"CE": 1' in content
    assert (
        "student_no" not in content
        and "虚构学生" not in content
        and "OLD_CODE" not in content
    )
    with c["engine"].connect() as db:
        assert db.execute(text("SELECT count(*) FROM teacher_grades")).scalar_one() == 0
    assert (
        c["client"]
        .post(
            "/api/teacher/ai/teaching/messages?class_id=999999",
            json={"conversation_id": str(uuid4()), "question": "建议"},
        )
        .status_code
        == 404
    )
    with student(c["reviewers"][0][0]):
        assert (
            c["client"]
            .post(url, json={"conversation_id": str(uuid4()), "question": "建议"})
            .status_code
            == 403
        )


def test_disabled_assistant_no_network_call(ai):
    ai["client"].put("/api/teacher/ai-text/settings", json=configuration(enabled=False))
    with student(ai["reviewers"][0][0]):
        result = ai["client"].post(
            f"/api/student/ai/topics/{ai['topic']}/messages",
            json={"conversation_id": str(uuid4()), "question": "问题"},
        )
        assert result.status_code == 409
    assert not ai["calls"]


def test_text_provider_builds_deepseek_request(monkeypatch):
    original = httpx.Client
    captured = []

    def respond(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": "回答"}}],
                "usage": {"total_tokens": 10, "other": "ignored"},
            },
        )

    monkeypatch.setattr(provider, "validate_endpoint", lambda _: None)
    monkeypatch.setattr(
        provider.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    answer, usage = provider.complete(
        configuration(), [{"role": "user", "content": "问"}]
    )
    assert answer == "回答" and usage == {"total_tokens": 10}
    body = json.loads(captured[0].content)
    assert body["thinking"] == {"type": "disabled"} and body["stream"] is False
    assert str(captured[0].url) == "https://api.deepseek.com/chat/completions"


@pytest.mark.parametrize(
    "status,body,code",
    [
        (401, {"echo": "teacher-secret"}, "AI_AUTH_FAILED"),
        (429, {}, "AI_RATE_LIMIT"),
        (
            200,
            {"choices": [{"finish_reason": "length", "message": {"content": "cut"}}]},
            "AI_RESPONSE_TRUNCATED",
        ),
        (200, {"choices": None}, "AI_RESPONSE_INVALID"),
        (200, {"choices": ["malformed"]}, "AI_RESPONSE_INVALID"),
    ],
)
def test_text_provider_sanitizes_errors(monkeypatch, status, body, code):
    original = httpx.Client
    monkeypatch.setattr(provider, "validate_endpoint", lambda _: None)
    monkeypatch.setattr(
        provider.httpx,
        "Client",
        lambda **kwargs: original(
            **kwargs,
            transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body)),
        ),
    )
    with pytest.raises(VideoAIError) as exc:
        provider.complete(configuration(), [])
    assert exc.value.code == code and "secret" not in str(exc.value)
