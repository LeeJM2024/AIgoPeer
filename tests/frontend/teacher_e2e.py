"""End-to-end teacher login/navigation check; requires seeded Docker services."""

from pathlib import Path

from playwright.sync_api import sync_playwright


def run() -> None:
    output = Path("storage/qa")
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto("http://localhost:5173/login")
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="登录").click()
        page.wait_for_url("**/teacher")
        page.locator(".metric-strip").wait_for()
        page.get_by_role("link", name="作业与评分").first.click()
        page.wait_for_url("**/teacher/assignments")
        page.locator("table").wait_for()
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        page.screenshot(path=str(output / "teacher-assignments-e2e.png"), full_page=True)
        browser.close()
    if errors:
        raise AssertionError(f"Browser console errors: {errors}")


if __name__ == "__main__":
    run()
