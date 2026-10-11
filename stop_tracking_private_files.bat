@echo off
chcp 65001 >nul
rem شغّله داخل مجلد مستودع GitHub (نفس مجلد البرنامج). يوقف تتبّع ملفات البيانات التي لا يجوز رفعها، ولا يحذفها من جهازك.
cd /d "%~dp0"
git rm -r --cached --ignore-unmatch portal_public.db portal_public.db-wal portal_public.db-shm portal_pdf_cache lis.db lis.db-wal lis.db-shm
echo.
echo Done. Now open GitHub Desktop: commit "stop tracking data files" then Push.
pause
