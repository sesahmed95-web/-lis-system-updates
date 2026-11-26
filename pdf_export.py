# -*- coding: utf-8 -*-
"""
تحويل صفحات التقارير (نفس القوالب المستخدمة بزر "طباعة") إلى PDF حقيقي على جهاز المختبر.
v107 — إصلاحات:
  1) make_temp_pdf_path كان يفشل (FileNotFoundError) إذا مجلد static/whatsapp_pdfs غير موجود عند العميل،
     فيسقط البرنامج صامتاً إلى صفحة HTML بدل PDF. الآن ينشئ المجلد، وإن لم يقدر يستعمل مجلد temp.
  2) إذا Playwright غير منصّب أو فشل تشغيله: بديل مباشر عبر Edge/Chrome (--headless --print-to-pdf) بدون أي تنصيب.
تثبيت Playwright (اختياري الآن):  pip install playwright   (ولا يحتاج playwright install إن كان Edge موجوداً)
"""
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

_playwright_lock = threading.Lock()


def _inject_base(html_content: str, base_url: str) -> str:
    if "<head>" in html_content and "<base " not in html_content:
        html_content = html_content.replace("<head>", f'<head><base href="{base_url}">', 1)
    return html_content


def _find_browser():
    cands = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        b = os.environ.get(env)
        if b:
            cands.append(os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe"))
            cands.append(os.path.join(b, "Google", "Chrome", "Application", "chrome.exe"))
    for n in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser"):
        w = shutil.which(n)
        if w:
            cands.append(w)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def _cli_pdf(html_content: str, base_url: str, output_path: str) -> None:
    """بديل بدون Playwright: متصفح Edge/Chrome بوضع headless يطبع الصفحة PDF."""
    exe = _find_browser()
    if not exe:
        raise RuntimeError("No Edge/Chrome/Chromium browser found for PDF export")
    html_content = _inject_base(html_content, base_url)
    tmp = tempfile.mkdtemp(prefix="lis_pdf_")
    try:
        src = os.path.join(tmp, "in.html")
        with open(src, "w", encoding="utf-8") as f:
            f.write(html_content)
        cmd = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
               "--user-data-dir=" + os.path.join(tmp, "profile"),
               "--no-pdf-header-footer", "--print-to-pdf-no-header",
               "--virtual-time-budget=8000",
               "--print-to-pdf=" + os.path.abspath(output_path), Path(src).as_uri()]
        if os.name != "nt":
            cmd.insert(1, "--no-sandbox")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.run(cmd, timeout=90, capture_output=True, creationflags=flags)
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 500:
            raise RuntimeError("browser CLI did not produce a PDF")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def html_to_pdf(html_content: str, base_url: str, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return _cli_pdf(html_content, base_url, output_path)

    html2 = _inject_base(html_content, base_url)
    try:
        with _playwright_lock:
            with sync_playwright() as p:
                browser = None
                for _ch in ("msedge", "chrome", None):
                    try:
                        browser = p.chromium.launch(channel=_ch) if _ch else p.chromium.launch()
                        break
                    except Exception:
                        continue
                if browser is None:
                    raise RuntimeError("No Edge/Chrome/Chromium browser found for PDF export")
                try:
                    page = browser.new_page()
                    page.set_content(html2, wait_until="load")
                    page.emulate_media(media="print")
                    page.pdf(path=output_path, format="A4", print_background=True,
                             margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"})
                finally:
                    browser.close()
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return
    except Exception:
        pass
    _cli_pdf(html_content, base_url, output_path)      # بديل أخير


def merge_pdfs(pdf_paths, output_path: str) -> None:
    from pypdf import PdfWriter
    writer = PdfWriter()
    for path in pdf_paths:
        writer.append(path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)


def make_temp_pdf_path(prefix: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.join(here, "static", "whatsapp_pdfs")
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".w")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
    except Exception:
        base = os.path.join(tempfile.gettempdir(), "lis_pdfs")
        os.makedirs(base, exist_ok=True)
    safe = (prefix or "report")[:60]
    fd, path = tempfile.mkstemp(prefix=f"{safe}_", suffix=".pdf", dir=base)
    os.close(fd)
    return path
