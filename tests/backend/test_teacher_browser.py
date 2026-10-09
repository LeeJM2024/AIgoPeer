"""Real browser → Vite proxy → FastAPI → PostgreSQL; opt in with RUN_BROWSER_TESTS=1."""

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser integration"
)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def browser_app(grading_course):
    import uvicorn
    from app.core.security import get_current_user, hash_password
    from app.main import app

    c = grading_course
    with c["engine"].begin() as conn:
        conn.execute(
            text("UPDATE users SET password_hash=:password WHERE id=:id"),
            {"password": hash_password("Test-browser-123!"), "id": c["teacher"]},
        )
        conn.execute(
            text("""INSERT INTO anomaly_records(submission_id,algorithm_run_id,risk_level,risk_score,evidence_json)
            SELECT :s,id,'HIGH',.9,'{"reason":"测试异常证据"}' FROM algorithm_runs ORDER BY id DESC LIMIT 1"""),
            {"s": c["submissions"][0]},
        )
        conn.execute(
            text("""UPDATE submissions
            SET final_review_status='ESCALATED_FOR_TEACHER_FINAL_REVIEW'
            WHERE id=:submission"""),
            {"submission": c["submissions"][0]},
        )
    del app.dependency_overrides[get_current_user]
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    api_port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    env = {**os.environ, "API_PROXY_TARGET": f"http://127.0.0.1:{api_port}"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    log_path = ROOT / "storage/qa/browser-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--host",
                "127.0.0.1",
                "--port",
                "15173",
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            env=env,
            stdout=log,
            stderr=log,
            creationflags=flags,
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(
                        "Vite exited; inspect storage/qa/browser-server.log"
                    )
                try:
                    if (
                        httpx.get(
                            "http://127.0.0.1:15173/api/health", timeout=1
                        ).status_code
                        == 200
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Browser test servers did not become ready")
            yield c, "http://127.0.0.1:15173"
        finally:
            process.terminate()
            process.wait(timeout=10)
            server.should_exit = True
            thread.join(timeout=10)
            sock.close()


@pytest.mark.parametrize("width,height", [(1440, 1000), (1024, 768)])
def test_real_teacher_workflow(browser_app, width, height, tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright
    from test_teacher_delivery import attach_material

    _course, base = browser_app
    attach_material(_course, tmp_path, monkeypatch)
    errors = []
    output = ROOT / "storage/qa"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: (
                errors.append(f"{message.text} {message.location}")
                if message.type == "error"
                else None
            ),
        )
        page.on(
            "requestfailed",
            lambda request: errors.append(
                f"{request.method} {request.url}: {request.failure}"
            ),
        )
        page.on("dialog", lambda dialog: dialog.accept())
        try:
            page.goto(base + "/login")
            page.wait_for_load_state("networkidle")
            expect(page.get_by_label("账号", exact=True)).to_be_empty()
            page.get_by_label("账号", exact=True).fill("TEST-TEACHER")
            page.get_by_label("密码", exact=True).fill("Test-browser-123!")
            page.get_by_role("button", name="登录", exact=True).click()
            page.wait_for_url("**/teacher")
            expect(page.locator(".metric-strip")).to_be_visible()
            page.wait_for_load_state("networkidle")
            page.locator(".assignment-row").first.click()
            page.get_by_role("link", name="进入评分工作台", exact=True).click()
            page.wait_for_load_state("networkidle")
            expect(page.get_by_role("heading", name="评分工作台")).to_be_visible()
            readme = page.locator(".material-list li").filter(has_text="README.md")
            readme.get_by_role("button", name="查看内容", exact=True).click()
            expect(page.locator(".material-preview pre")).to_contain_text(
                "原始材料说明"
            )
            page.get_by_role("button", name="关闭预览", exact=True).click()
            expect(page.get_by_role("button", name="发布全部成绩")).to_be_disabled()
            page.locator(".score-input input").fill("90")
            page.get_by_label("教师反馈", exact=True).fill("已核对原始材料。")
            page.get_by_role("button", name="保存教师评分", exact=True).click()
            page.get_by_role("button", name="锁定当前评分", exact=True).click()
            page.get_by_role("button", name="创建更正版本", exact=True).click()
            page.locator(".score-input input").fill("95")
            page.get_by_label("更正原因", exact=True).fill("复核例题步骤后更正")
            page.get_by_role("button", name="保存更正版本", exact=True).click()
            page.get_by_role("button", name="锁定当前评分", exact=True).click()
            expect(page.locator(".grade-history summary").first).to_contain_text("v2")
            page.locator(".submission-index button").nth(1).click()
            page.locator(".score-input input").fill("88")
            page.get_by_role("button", name="保存教师评分", exact=True).click()
            page.get_by_role("button", name="锁定当前评分", exact=True).click()
            expect(page.get_by_role("button", name="发布全部成绩")).to_be_disabled()
            page.get_by_role("link", name="评审与异常", exact=True).click()
            page.wait_for_load_state("networkidle")
            page.locator("details").last.locator("summary").click()
            expect(
                page.get_by_text("高风险异常须在评分工作台录入复核最终分")
            ).to_be_visible()
            expect(
                page.get_by_role("button", name="驳回异常", exact=True)
            ).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(output / f"teacher-reviews-{width}.png"), full_page=True
            )
            page.get_by_role("link", name="返回评分", exact=True).click()
            page.locator(".submission-index button").first.click()
            expect(
                page.get_by_role("heading", name="高风险作品复核最终分")
            ).to_be_visible()
            page.get_by_label("复核最终分", exact=True).fill("91")
            page.get_by_label("复核理由", exact=True).fill(
                "已核对教师初评、同伴评分与异常证据。"
            )
            page.get_by_role("button", name="锁定复核最终分", exact=True).click()
            expect(page.get_by_text("复核最终分已锁定：91")).to_be_visible()
            page.get_by_role("button", name="发布全部成绩", exact=True).click()
            expect(
                page.get_by_role("button", name="成绩已发布", exact=True)
            ).to_be_disabled()
            expect(
                page.get_by_role("button", name="创建更正版本", exact=True)
            ).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(output / f"teacher-grading-{width}.png"), full_page=True
            )
            page.get_by_role("link", name="查看并导出已发布成绩", exact=True).click()
            page.wait_for_load_state("networkidle")
            with page.expect_download() as download:
                page.get_by_role("button", name="导出已发布成绩", exact=True).click()
            download.value.save_as(str(output / f"grades-{width}.csv"))
            exported = (output / f"grades-{width}.csv").read_text(encoding="utf-8-sig")
            assert "91.00" in exported
            assert "84.80" in exported
            page.get_by_role("link", name="班级与学生", exact=True).click()
            page.get_by_label("班级名称", exact=True).fill("浏览器导入测试班")
            page.get_by_label("学期", exact=True).fill("测试学期")
            page.get_by_role("button", name="保存班级", exact=True).click()
            page.get_by_label("学生名单", exact=True).fill(
                "BROWSER-NEW\t虚构学生\tBrowser-test-123!"
            )
            page.get_by_role("button", name="导入到当前班级", exact=True).click()
            expect(page.locator("table")).to_contain_text("BROWSER-NEW")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(output / f"teacher-classes-{width}.png"), full_page=True
            )
            page.get_by_role("link", name="作业与评分", exact=True).click()
            page.get_by_role("button", name="新建作业", exact=True).click()
            page.get_by_label("作业名称", exact=True).fill("浏览器草稿")
            page.get_by_label("提交截止时间", exact=True).fill("2030-12-01T12:00")
            page.get_by_label("评审截止时间", exact=True).fill("2030-12-15T12:00")
            page.locator(".editor-panel input[type=checkbox]").nth(0).check()
            page.locator(".editor-panel input[type=checkbox]").nth(1).check()
            page.get_by_role("button", name="保存草稿", exact=True).click()
            row = page.get_by_role("row").filter(has_text="浏览器草稿")
            row.get_by_role("button", name="编辑", exact=True).click()
            page.get_by_label("作业名称", exact=True).fill("浏览器草稿已更新")
            page.get_by_role("button", name="保存草稿", exact=True).click()
            updated = page.get_by_role("row").filter(has_text="浏览器草稿已更新")
            expect(updated).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(output / f"teacher-assignments-{width}.png"), full_page=True
            )
            updated.get_by_role("button", name="删除", exact=True).click()
            expect(updated).to_have_count(0)
            page.get_by_role("button", name="新建作业", exact=True).click()
            page.get_by_label("作业类型", exact=True).select_option("PROGRAMMING")
            page.get_by_label("作业名称", exact=True).fill("浏览器编程题")
            page.get_by_label("提交截止时间", exact=True).fill("2030-12-01T12:00")
            page.locator(".editor-panel input[type=checkbox]").nth(0).check()
            page.locator(".editor-panel input[type=checkbox]").nth(1).check()
            page.get_by_label("题面", exact=True).fill("输入两个整数，输出和。")
            page.get_by_label("输入说明", exact=True).fill("两个整数")
            page.get_by_label("输出说明", exact=True).fill("一个整数")
            for index in range(2):
                case = page.locator(".test-case").nth(index)
                case.get_by_label("输入", exact=True).fill("1 2\n")
                case.get_by_label("预期输出", exact=True).fill("3\n")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(output / f"teacher-programming-editor-{width}.png"),
                full_page=True,
            )
            page.get_by_role("button", name="保存草稿", exact=True).click()
            page.get_by_role("row").filter(has_text="浏览器编程题").get_by_role(
                "link", name="管理"
            ).click()
            expect(
                page.get_by_role("heading", name="固定跨班五人评审组")
            ).to_have_count(0)
            page.get_by_role("button", name="确认并发布作业", exact=True).click()
            expect(page.locator(".status-chip")).to_contain_text("已发布")
            expect(page.get_by_role("button", name="初始化跨班评审任务")).to_have_count(
                0
            )
            page.get_by_role("link", name="知识点目录", exact=True).click()
            page.get_by_label("编号", exact=True).fill("WEB01")
            page.get_by_label("章节", exact=True).fill("动态规划")
            page.get_by_label("知识点名称", exact=True).fill("浏览器知识点")
            page.get_by_role("button", name="保存知识点", exact=True).click()
            topic = page.get_by_role("row").filter(has_text="WEB01")
            expect(topic).to_contain_text("浏览器知识点")
            topic.get_by_role("button", name="编辑", exact=True).click()
            page.get_by_label("知识点名称", exact=True).fill("浏览器知识点已更新")
            page.get_by_role("button", name="保存知识点", exact=True).click()
            expect(topic).to_contain_text("浏览器知识点已更新")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(
                path=str(output / f"teacher-topics-{width}.png"), full_page=True
            )
            topic.get_by_role("button", name="删除", exact=True).click()
            expect(topic).to_have_count(0)
            assert not errors, errors
        except Exception:
            page.screenshot(
                path=str(output / f"teacher-failure-{width}.png"), full_page=True
            )
            raise
        finally:
            browser.close()
