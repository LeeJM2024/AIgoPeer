"""Browser smoke check for the teacher shell with deterministic API responses."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

RESPONSES = {
    "/api/teacher/dashboard": {
        "active_assignments": 2,
        "awaiting_grading": 1,
        "published_assignments": 3,
        "task_count": 80,
        "completed_tasks": 62,
        "pending_tasks": 18,
        "open_anomalies": 2,
    },
    "/api/teacher/assignments": [
        {
            "id": 1,
            "title": "算法微课期末作业",
            "type": "FINAL_PROJECT",
            "status": "TEACHER_GRADING",
            "teacher_weight": 0.6,
            "designated_review_weight": 0.4,
            "submission_count": 16,
            "review_task_count": 80,
        },
        {
            "id": 2,
            "title": "动态规划专题练习",
            "type": "PROGRAMMING",
            "status": "SUBMITTING",
            "teacher_weight": 0.7,
            "designated_review_weight": 0.3,
            "submission_count": 12,
            "review_task_count": 0,
        },
    ],
}


def run() -> None:
    output = Path("storage/qa")
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, viewport in (
            ("desktop-1440", {"width": 1440, "height": 1000}),
            ("desktop-1024", {"width": 1024, "height": 768}),
        ):
            page = browser.new_page(viewport=viewport)
            page.on(
                "console",
                lambda message: (
                    errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.add_init_script("""
                localStorage.setItem('algopeer_token', 'qa-token');
                localStorage.setItem('algopeer_user', JSON.stringify({id: 1, name: '演示教师', role: 'TEACHER'}));
            """)

            def handle(route):
                path = route.request.url.split("localhost:5173", 1)[-1]
                payload = RESPONSES.get(path)
                if payload is None:
                    route.fulfill(
                        status=404,
                        content_type="application/json",
                        body='{"detail":"QA_MOCK_NOT_FOUND"}',
                    )
                else:
                    route.fulfill(
                        content_type="application/json",
                        body=json.dumps(
                            {"code": 0, "data": payload}, ensure_ascii=False
                        ),
                    )

            page.route("http://localhost:5173/api/**", handle)
            page.goto("http://localhost:5173/teacher")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)
            if not page.locator("h1").is_visible():
                page.screenshot(
                    path=str(output / f"teacher-dashboard-{name}-failure.png"),
                    full_page=True,
                )
                raise AssertionError(
                    f"Teacher page did not render. url={page.url}, html={page.content()[:2000]}, errors={errors}"
                )
            assert page.locator(".metric-strip").is_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
            )
            page.screenshot(
                path=str(output / f"teacher-dashboard-{name}.png"), full_page=True
            )
            page.close()
        browser.close()
    if errors:
        raise AssertionError(f"Browser console errors: {errors}")


if __name__ == "__main__":
    run()
