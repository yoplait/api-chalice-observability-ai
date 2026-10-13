#!/usr/bin/env python3
"""
Generate screenshots for the Chalice DevOps Lab observability dashboards.
Creates:
  1. Grafana - Main Observability Dashboard
  2. Grafana - External API & Status Pages (Okta, AWS, GitHub, etc.)
  3. SonarQube - Quality Gate Report
"""
import contextlib
import os
import subprocess
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3001")
OUTPUT_DIR = Path(__file__).parent.parent / "screenshots"

def get_grafana_password():
    """Get Grafana admin password from .env"""
    env_file = Path(__file__).parent.parent / ".env"
    password = "admin"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("GRAFANA_ADMIN_PASSWORD="):
                    password = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return password

def grafana_session_cookie():
    """Login to Grafana API and return session cookie value."""
    resp = requests.post(
        f"{GRAFANA_URL}/login",
        json={"user": "admin", "password": get_grafana_password()},
        timeout=10
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Grafana login failed: {resp.status_code}")
    cookie = resp.cookies.get("grafana_session")
    if not cookie:
        raise RuntimeError("No grafana_session cookie received")
    return cookie

def screenshot_grafana(page, uid, filename, title):
    """Open a Grafana dashboard in Playwright with session cookie and screenshot it.

    Grafana lazy-renders panels via content-visibility, so full_page screenshots
    capture blank panels. Instead we grow the viewport to the full content height
    so every panel is inside the viewport and gets painted, then take a normal shot.
    """
    print(f"\n  Capturing {title}...")
    try:
        page.goto(f"{GRAFANA_URL}/d/{uid}?orgId=1&kiosk&from=now-1h&to=now&refresh=0")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Wait for panels to exist
        page.wait_for_selector("[data-testid*='panel']", timeout=20000)
        page.wait_for_timeout(3000)

        # Grow viewport to full content height so all panels render
        height = page.evaluate("Math.max(document.body.scrollHeight, 1080)")
        page.set_viewport_size({"width": 1920, "height": min(height + 40, 8000)})
        page.wait_for_timeout(4000)

        # Wait until panels have rendered content (no "No data")
        with contextlib.suppress(Exception):
            page.wait_for_function(
                """() => {
                    const panels = document.querySelectorAll("[data-testid*='panel']");
                    if (panels.length === 0) return false;
                    const nodata = [...panels].filter(p => p.textContent.includes('No data')).length;
                    return nodata === 0;
                }""",
                timeout=20000,
            )  # proceed with whatever is rendered

        page.wait_for_timeout(2000)
        path = OUTPUT_DIR / filename
        page.screenshot(path=str(path))
        print(f"  ✓ Saved to {path}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def take_sonarqube_screenshot(page, filename):
    """Take a screenshot of SonarQube quality gate report (HTML generated)."""
    print("\n  Capturing SonarQube quality gate report...")
    try:
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "sonar_report.py")],
            check=True, capture_output=True
        )
        report_path = Path(__file__).parent.parent / "tmp" / "sonar-report.html"
        page.goto(report_path.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        path = OUTPUT_DIR / filename
        page.screenshot(path=str(path), full_page=True)
        print(f"  ✓ Saved to {path}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cookie = grafana_session_cookie()
    print("[1/3] Grafana session established")

    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        context.add_cookies([{
            "name": "grafana_session",
            "value": cookie,
            "url": GRAFANA_URL,
        }])
        page = context.new_page()

        results["main"] = screenshot_grafana(
            page, "chalice-observability",
            "grafana-main-dashboard.png",
            "Main Observability Dashboard",
        )
        results["external"] = screenshot_grafana(
            page, "external-apis-status",
            "grafana-external-apis.png",
            "External API & Status Pages Monitoring",
        )
        results["sonar"] = take_sonarqube_screenshot(page, "sonarqube-dashboard.png")

        browser.close()

    ok = sum(1 for v in results.values() if v)
    print(f"\n{ok}/3 screenshots generated in {OUTPUT_DIR}")
    if ok == 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
