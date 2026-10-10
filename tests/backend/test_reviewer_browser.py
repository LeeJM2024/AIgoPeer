"""Browser coverage for task-gated navigation and anonymous review submission."""

import os
from zipfile import ZipFile

import pytest
from sqlalchemy import text

pytest_plugins = ["test_teacher_browser"]
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser integration"
)


@pytest.mark.parametrize("width,height", [(1440, 1000), (1024, 768)])
def test_task_gated_reviewer_workflow(
    browser_app, tmp_path, monkeypatch, width, height
):
    from app.core.config import settings
    from app.core.security import hash_password
    from playwright.sync_api import expect, sync_playwright
    from test_teacher_browser import ROOT

    c, base = browser_app
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    with ZipFile(tmp_path / "anonymous.zip", "w") as archive:
        archive.writestr("materials/001.md", "Anonymous algorithm explanation")
    with c["engine"].begin() as conn:
        conn.execute(text("UPDATE assignments SET status='REVIEWER_GRADING'"))
        conn.execute(text("UPDATE review_tasks SET status='PENDING',submitted_at=NULL"))
        conn.execute(
            text("UPDATE users SET password_hash=:p WHERE id=:u"),
            {"p": hash_password("Test-browser-123!"), "u": c["reviewers"][1][0]},
        )
        conn.execute(
            text("""INSERT INTO users(student_no,name,password_hash,system_role)
            VALUES ('NO-TASK','普通学生',:p,'STUDENT')"""),
            {"p": hash_password("Test-browser-123!")},
        )
        conn.execute(
            text("""INSERT INTO review_material_packages(submission_id,storage_key,status)
            SELECT id,'anonymous.zip','READY' FROM submissions""")
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def login(account):
            page.goto(base + "/login")
            page.wait_for_load_state("networkidle")
            page.get_by_label("账号", exact=True).fill(account)
            page.get_by_label("密码", exact=True).fill("Test-browser-123!")
            page.get_by_role("button", name="登录", exact=True).click()
            page.wait_for_url("**/student")
            page.wait_for_load_state("networkidle")

        try:
            login("TEST-1-0")
            page.get_by_role("link", name="评审任务", exact=True).click()
            expect(page.get_by_role("heading", name="我的评审任务")).to_be_visible()
            expect(
                page.get_by_role("button", name="提交评分", exact=True)
            ).to_be_disabled()
            with page.expect_download() as download_info:
                page.get_by_role("button", name="下载匿名材料并开始评审").click()
            download = download_info.value
            assert download.suggested_filename.startswith("anonymous-review-")
            with ZipFile(download.path()) as archive:
                assert archive.namelist() == ["materials/001.md"]
            expect(page.locator(".score-input input")).to_be_enabled()
            page.locator(".score-input input").fill("88")
            page.get_by_label("评语", exact=True).fill(
                "依据匿名材料核对原理及复杂度，建议补充边界样例。"
            )
            page.screenshot(
                path=str(ROOT / f"storage/qa/reviewer-{width}.png"), full_page=True
            )
            page.get_by_role("button", name="提交评分", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("评分已提交")
            expect(page.locator(".empty-state")).to_contain_text("没有待完成")
            with c["engine"].connect() as conn:
                assert (
                    conn.execute(
                        text("SELECT count(*) FROM review_scores")
                    ).scalar_one()
                    == 1
                )
            page.get_by_role("button", name="退出", exact=True).click()
            login("NO-TASK")
            expect(page.get_by_role("link", name="评审任务", exact=True)).to_have_count(
                0
            )
            page.goto(base + "/reviewer/tasks")
            expect(page.get_by_role("alert")).to_be_visible()
            expect(page.locator(".review-form")).to_have_count(0)
            assert errors == []
        finally:
            context.close()
            browser.close()
