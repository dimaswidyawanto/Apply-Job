@echo off
rem Buka Chrome dengan port debug supaya bot bisa MENEMPEL ke Chrome ini.
rem Berguna untuk situs di balik Cloudflare ("Just a moment...", "Security
rem Check") karena Chrome yang dibuka sendiri lebih dicurigai sebagai bot.
rem
rem Pemakaian:  chrome-debug.bat [port] [situs]
rem   port  : bawaan 9222
rem   situs : indeed (bawaan) | glints | jobstreet | kosong | URL http...
rem Contoh:   chrome-debug.bat
rem           chrome-debug.bat 9222 glints
rem           chrome-debug.bat 9222 https://id.indeed.com/jobs?q=inventory+staff
rem
rem Dulu skrip ini selalu membuka halaman Glints, sehingga saat menguji
rem Indeed yang terbuka justru Glints. Sekarang halaman mengikuti situs yang
rem diminta dan perintah uji yang dicetak ikut menyesuaikan.
setlocal
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=9222"

set "SITUS=%~2"
if "%SITUS%"=="" set "SITUS=indeed"

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

rem --- Halaman awal + perintah yang dicetak, sesuai situs yang diminta ---
set "URL=https://id.indeed.com"
set "NAMA=Indeed"
set "UJI=jalankan.bat indeed diagnosa --keyword "inventory staff" --location Bandung"
set "JALAN=jalankan.bat indeed run --max-pages 1 --limit 5"

rem Ditulis satu baris per `if` (bukan blok) supaya `%%20` tetap menjadi
rem `%20` seperti versi sebelumnya yang sudah terbukti berjalan.
if /I "%SITUS%"=="glints" set "URL=https://glints.com/id/opportunities/jobs/explore?keyword=inventory%%20staff"
if /I "%SITUS%"=="glints" set "NAMA=Glints"
if /I "%SITUS%"=="glints" set "UJI=jalankan.bat glints diagnosa --keyword "inventory staff""
if /I "%SITUS%"=="glints" set "JALAN=jalankan.bat glints run"

if /I "%SITUS%"=="jobstreet" set "URL=https://id.jobstreet.com/id/jobs?keywords=inventory%%20staff"
if /I "%SITUS%"=="jobstreet" set "NAMA=JobStreet"
if /I "%SITUS%"=="jobstreet" set "UJI=jalankan.bat run --auto --situs jobstreet"
if /I "%SITUS%"=="jobstreet" set "JALAN=jalankan.bat status"

if /I "%SITUS%"=="kosong" set "URL=about:blank"
if /I "%SITUS%"=="kosong" set "NAMA=halaman kosong"
if /I "%SITUS%"=="kosong" set "UJI=(buka sendiri halaman situsnya di jendela itu)"
if /I "%SITUS%"=="kosong" set "JALAN=(buka sendiri)"

rem Argumen berupa URL penuh: pakai apa adanya.
set "AWALAN=%SITUS:~0,4%"
if /I "%AWALAN%"=="http" set "URL=%SITUS%"
if /I "%AWALAN%"=="http" set "NAMA=halaman dari argumen"
if /I "%AWALAN%"=="http" set "UJI=(pilih perintah diagnosa situs itu)"
if /I "%AWALAN%"=="http" set "JALAN=(pilih perintah run situs itu)"

echo Membuka Chrome khusus bot (port debug %PORT%)...
echo Halaman: %NAMA% - %URL%
echo Profil : %PROFIL%
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFIL%" --profile-directory=Default --no-first-run --no-default-browser-check "%URL%"

echo.
echo 1. Tunggu halaman %NAMA% tampil. Bila muncul verifikasi ("Just a moment...",
echo    "Security Check"), selesaikan di jendela itu (sekali saja).
echo 2. Lalu jalankan:
echo      jalankan.bat set-env CHROME_DEBUG_PORT=%PORT%
echo      %UJI%
echo 3. Setelah itu: %JALAN%
echo.
echo JANGAN tutup jendela Chrome itu selama bot berjalan.
echo Sesudah selesai, kembalikan mode biasa: jalankan.bat set-env CHROME_DEBUG_PORT=0
endlocal
