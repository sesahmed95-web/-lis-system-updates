# -*- coding: utf-8 -*-
"""
تحويل صفحات التقارير (نفس القوالب المستخدمة بزر "طباعة" بالمتصفح) إلى ملف
PDF حقيقي على السيرفر، بدون تدخل المستخدم — مطلوب لإرسال النتائج عبر واتساب.

نستخدم Playwright (متصفح Chromium يعمل بالخلفية) بدل أي مكتبة PDF بسيطة،
لأنه يرسم نفس الـHTML/CSS الموجود أصلاً بالقوالب (RTL، الشعار، الجداول...)
حرفيًا متل ما يطلع بالطباعة من المتصفح، فما نحتاج نعيد تصميم شي.

**تثبيت لمرة وحدة على جهاز السيرفر:**
    pip install playwright
    playwright install chromium
"""
import os
import tempfile
import threading

_playwright_lock = threading.Lock()


def html_to_pdf(html_content: str, base_url: str, output_path: str) -> None:
    """يحوّل نص HTML كامل (كما يرجعه render_template) إلى ملف PDF بنفس المسار
    output_path. base_url هو جذر الموقع (مثلاً request.url_root) حتى تنحل
    مسارات الصور النسبية زي /static/uploads/logo.png بشكل صحيح."""
    from playwright.sync_api import sync_playwright

    if "<head>" in html_content and "<base " not in html_content:
        html_content = html_content.replace(
            "<head>", f'<head><base href="{base_url}">', 1
        )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Playwright/Chromium مو thread-safe بشكل كامل عبر نفس العملية، فنحصر
    # الاستدعاءات المتزامنة بقفل بسيط بدل ما نشغّل event loop منفصل لكل طلب.
    with _playwright_lock:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html_content, wait_until="load")
                page.emulate_media(media="print")
                page.pdf(
                    path=output_path,
                    format="A4",
                    print_background=True,
                    margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"},
                )
            finally:
                browser.close()


def merge_pdfs(pdf_paths, output_path: str) -> None:
    """يدمج عدة ملفات PDF بملف واحد (مو مستخدم حاليًا لأن print_visit_results
    أصلاً يرسم كل نتائج الزيارة بصفحة واحدة، لكن موجودة كخيار احتياطي)."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for path in pdf_paths:
        writer.append(path)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)


def make_temp_pdf_path(prefix: str) -> str:
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=".pdf",
                                 dir=os.path.join(os.path.dirname(__file__), "static", "whatsapp_pdfs"))
    os.close(fd)
    return path
