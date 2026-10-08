@echo off
chcp 65001 > nul
title سيرفر ماسينجر عيادة الأطفال — Uvicorn
cd /d "%~dp0"
echo ===================================================
echo     تشغيل سيرفر الـ API لربط ماسينجر فيسبوك
echo ===================================================
echo.
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
pause
