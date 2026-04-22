#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", help="Directory containing index.html")
    parser.add_argument("--out", help="PDF output path")
    parser.add_argument("--port", default="8765")
    args = parser.parse_args()

    report_dir = Path(args.report_dir).resolve()
    out = Path(args.out).resolve() if args.out else report_dir / "report.pdf"
    index = report_dir / "index.html"
    if not index.exists():
        raise SystemExit(f"Missing {index}")

    chrome = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
        or ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" if Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists() else None)
    )
    if chrome:
        server = subprocess.Popen([sys.executable, "-m", "http.server", args.port], cwd=report_dir)
        profile_dir = tempfile.mkdtemp(prefix="apk-monitor-chrome-pdf-")
        try:
            url = f"http://127.0.0.1:{args.port}/"
            try:
                subprocess.run(
                    [
                        chrome,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        f"--user-data-dir={profile_dir}",
                        f"--print-to-pdf={out}",
                        "--print-to-pdf-no-header",
                        url,
                    ],
                    check=True,
                    timeout=40,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                out.unlink(missing_ok=True)
            else:
                print(out)
                return
        finally:
            server.terminate()
            server.wait(timeout=10)
            shutil.rmtree(profile_dir, ignore_errors=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        marker = report_dir / "PDF_EXPORT_NOT_AVAILABLE.txt"
        marker.write_text(
            "PDF export requires Google Chrome/Chromium or Python Playwright. "
            "Install one of them, then run: python3 export_report_pdf.py <report_dir>\\n",
            encoding="utf-8",
        )
        print(f"PDF export unavailable; wrote {marker}")
        return

    server = subprocess.Popen([sys.executable, "-m", "http.server", args.port], cwd=report_dir)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1600})
            page.goto(f"http://127.0.0.1:{args.port}/", wait_until="networkidle")
            page.pdf(path=str(out), format="A4", print_background=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    print(out)


if __name__ == "__main__":
    main()
