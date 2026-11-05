@echo off
rem Buat pintasan di Desktop: satu untuk tiap situs + satu untuk semuanya.
rem Cukup jalankan sekali.
setlocal
cd /d "%~dp0"

set "DESKTOP="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%D"

if "%DESKTOP%"=="" (
    echo Tidak bisa menemukan folder Desktop.
    pause
    exit /b 1
)

echo Membuat pintasan di: %DESKTOP%
echo.

for %%N in ("Lamar JobStreet" "Lamar Glints" "Lamar Indeed" "Lamar Otomatis") do (
    if exist "%~dp0%%~N.bat" (
        powershell -NoProfile -Command ^
          "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%DESKTOP%\%%~N.lnk');" ^
          "$s.TargetPath='%~dp0%%~N.bat';" ^
          "$s.WorkingDirectory='%~dp0';" ^
          "$s.IconLocation='%SystemRoot%\System32\shell32.dll,21';" ^
          "$s.Save()"
        if errorlevel 1 (
            echo [GAGAL] %%~N
        ) else (
            echo [OK] %%~N
        )
    ) else (
        echo [LEWATI] %%~N.bat tidak ditemukan
    )
)

echo.
echo Selesai. Sekarang di Desktop ada pintasan Lamar JobStreet, Lamar Glints,
echo Lamar Indeed, dan Lamar Otomatis.
pause
exit /b 0
