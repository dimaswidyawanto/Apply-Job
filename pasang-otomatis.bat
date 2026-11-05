@echo off
rem Pasang pemantau otomatis: setiap kali Anda login, pantau.bat berjalan
rem diam-diam di latar belakang dan mengirim perubahan ke GitHub.
rem Jalankan sekali saja. Untuk melepas: matikan-otomatis.bat
setlocal
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\Pantau Apply-Job.lnk"

if not exist "%~dp0pantau-diam.vbs" (
    echo [GAGAL] pantau-diam.vbs tidak ditemukan di folder ini.
    exit /b 1
)

if not exist "%STARTUP%" (
    echo [GAGAL] Folder Startup tidak ditemukan: %STARTUP%
    exit /b 1
)

echo Membuat pintasan otomatis di folder Startup...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$sh = New-Object -ComObject WScript.Shell; $s = $sh.CreateShortcut('%LINK%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%~dp0pantau-diam.vbs\"'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Pantau perubahan dan kirim ke GitHub'; $s.Save()"

if not exist "%LINK%" (
    echo [GAGAL] Pintasan gagal dibuat.
    exit /b 1
)

echo.
echo Selesai. Mulai sekarang, setiap Anda login:
echo   - pemantau berjalan diam-diam (tanpa jendela)
echo   - perubahan di folder ini dikirim ke GitHub otomatis tiap 60 detik
echo   - pembaruan dari GitHub / repo pengembangan ditarik otomatis
echo   - catatan aktivitas ada di pantau.log
echo.
echo Ingin langsung aktif sekarang tanpa menunggu login? jalankan:
echo   wscript "%~dp0pantau-diam.vbs"
exit /b 0
