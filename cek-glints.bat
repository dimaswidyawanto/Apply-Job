@echo off
rem Periksa kesehatan Glints berurutan dalam satu perintah:
rem   1) baca kartu lowongan   2) saring kandidat (logo & duplikat)
rem   3) simulasi alur lamaran 4) kirim N lamaran uji  5) catatan database
rem
rem Pemakaian:
rem   cek-glints.bat            -> tanpa melamar (aman, hanya membaca)
rem   cek-glints.bat 3          -> ikut mengirim maksimal 3 lamaran uji
rem   cek-glints.bat 3 --ya     -> tanpa pertanyaan konfirmasi
setlocal
cd /d "%~dp0"

set "LAMAR=0"
if not "%~1"=="" set "LAMAR=%~1"
set "YA="
if /I "%~2"=="--ya" set "YA=--ya"

echo ============================================================
echo  PERIKSA GLINTS  ^(lamar uji: %LAMAR%^)
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    rem Lingkungan sudah siap: jalankan langsung, tanpa memasang ulang dependensi.
    ".venv\Scripts\python.exe" cli.py glints cek --keyword "inventory staff" --max-pages 1 --lamar %LAMAR% %YA%
) else (
    call jalankan.bat glints cek --keyword "inventory staff" --max-pages 1 --lamar %LAMAR% %YA%
)

echo.
echo ============================================================
echo  Selesai. Bila ada tahap GAGAL, kirim isi folder debug\
echo  (HTML + PNG terbaru) untuk penyesuaian.
echo ============================================================
pause
endlocal
