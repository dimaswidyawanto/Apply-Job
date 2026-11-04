@echo off
rem Lepas pemantau otomatis yang dipasang oleh pasang-otomatis.bat
setlocal
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Pantau Apply-Job.lnk"

if exist "%LINK%" (
    del "%LINK%"
    echo Pintasan otomatis dihapus.
) else (
    echo Tidak ada pintasan otomatis yang terpasang.
)

echo.
echo Pemantau yang sedang berjalan (kalau ada) akan berhenti sendiri setelah
echo jendela/terminalnya ditutup, atau tekan Ctrl+C di jendela tersebut.
exit /b 0
