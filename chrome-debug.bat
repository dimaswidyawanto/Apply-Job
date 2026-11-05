@echo off
rem Buka Chrome dengan port debug supaya bot bisa MENEMPEL ke Chrome ini.
rem Berguna untuk situs di balik Cloudflare ("Just a moment...") karena
rem Chrome yang dibuka sendiri tidak dicurigai sebagai bot.
rem Pemakaian:  chrome-debug.bat [port]     (bawaan 9222)
setlocal
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=9222"
set "PROFIL=%USERPROFILE%\.dimastes\chrome-debug"

set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
    echo [GAGAL] chrome.exe tidak ditemukan.
    echo Pasang Google Chrome, atau set CHROME_BINARY ke path chrome.exe Anda.
    pause
    exit /b 1
)

if not exist "%PROFIL%" mkdir "%PROFIL%"

echo Membuka Chrome khusus bot (port debug %PORT%)...
echo Profil: %PROFIL%
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFIL%" --profile-directory=Default --no-first-run --no-default-browser-check "https://glints.com/id/opportunities/jobs/explore?keyword=inventory%%20staff"

echo.
echo 1. Tunggu halaman lowongan tampil. Bila muncul "Just a moment...",
echo    selesaikan verifikasinya di jendela itu (sekali saja).
echo 2. Lalu jalankan:
echo      jalankan.bat set-env CHROME_DEBUG_PORT=%PORT%
echo      jalankan.bat glints diagnosa --keyword "inventory staff"
echo 3. Setelah itu: jalankan.bat glints run
echo.
echo JANGAN tutup jendela Chrome itu selama bot berjalan.
endlocal
