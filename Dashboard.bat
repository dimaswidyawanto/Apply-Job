@echo off
rem ============================================================
rem  DASHBOARD LAMAR OTOMATIS
rem ------------------------------------------------------------
rem  Membuka dashboard monitoring di browser (http://127.0.0.1:8765).
rem  Kontrol Start / Pause / Resume / Stop / Retry / Clear queue
rem  benar-benar menjalankan atau menghentikan sesi lamar.
rem
rem  Berkas ini memakai CRLF dan tanpa label goto.
rem ============================================================
setlocal
cd /d "%~dp0"
title Dashboard - Lamar Otomatis
call jalankan.bat dashboard %*
exit /b %errorlevel%
