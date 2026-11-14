"""Backup & pemulihan database lamaran (master prompt pasal 12).

Database berisi seluruh riwayat lamaran dan ingatan jawaban formulir — kalau
hilang, tidak ada cara membangunnya kembali. Modul ini membuat salinan aman
memakai API backup SQLite (aman walau database sedang dipakai, termasuk mode
WAL), tanpa menghentikan sesi yang sedang berjalan.

Perintah:

    jalankan.bat backup                  # buat salinan baru
    jalankan.bat backup --daftar         # lihat salinan yang ada
    jalankan.bat backup --pulihkan NAMA  # kembalikan salinan
"""

import contextlib
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, config

FOLDER_BAKU = "backups"
AWALAN = "jobstreet_auto"
MAKS_SIMPAN = 20


def folder(path: str | Path | None = None) -> Path:
    """Folder penyimpanan backup (dibuat bila belum ada)."""
    tujuan = Path(path) if path else (Path(BASE_DIR) / FOLDER_BAKU)
    tujuan.mkdir(parents=True, exist_ok=True)
    return tujuan


def _nama_unik(tujuan: Path) -> str:
    sekarang = datetime.now().strftime("%Y%m%d-%H%M%S")
    nama = f"{AWALAN}-{sekarang}.db"
    urutan = 1
    while (tujuan / nama).exists():
        nama = f"{AWALAN}-{sekarang}-{urutan}.db"
        urutan += 1
    return nama


def buat(path_db: str | None = None,
         path_folder: str | Path | None = None) -> Path:
    """Buat salinan database; kembalikan path berkas backup."""
    sumber = Path(path_db or config.db_path)
    if not sumber.exists():
        raise FileNotFoundError(f"Database belum ada: {sumber}")

    tujuan = folder(path_folder)
    sasaran = tujuan / _nama_unik(tujuan)

    asal = sqlite3.connect(str(sumber))
    try:
        salinan = sqlite3.connect(str(sasaran))
        try:
            with salinan:
                asal.backup(salinan)
        finally:
            salinan.close()
    finally:
        asal.close()

    _bersihkan(tujuan)
    return sasaran


def pastikan_harian(path_db: str | None = None,
                    path_folder: str | Path | None = None) -> Path | None:
    """Buat backup bila hari ini (WIB) belum ada; None bila sudah ada.

    Dipanggil di awal sesi supaya data aman tanpa perlu diingat pengguna
    (master prompt pasal 13). Kegagalan backup tidak boleh menghentikan sesi.
    """
    hari_ini = datetime.now().strftime("%Y-%m-%d")

    try:
        for item in daftar(path_folder):
            if str(item.get("waktu", "")).startswith(hari_ini):
                return None
    except Exception:
        pass

    try:
        return buat(path_db, path_folder)
    except Exception:
        return None


def _bersihkan(tujuan: Path) -> None:
    """Sisakan MAKS_SIMPAN backup terbaru saja."""
    berkas = sorted(tujuan.glob(f"{AWALAN}-*.db"))
    for lama in berkas[:-MAKS_SIMPAN] if len(berkas) > MAKS_SIMPAN else []:
        with contextlib.suppress(OSError):
            lama.unlink()


def daftar(path_folder: str | Path | None = None) -> list[dict]:
    """Daftar backup terbaru lebih dulu: nama, ukuran, waktu."""
    tujuan = folder(path_folder)
    hasil = []
    for berkas in sorted(tujuan.glob(f"{AWALAN}-*.db"), reverse=True):
        info = berkas.stat()
        hasil.append(
            {
                "nama": berkas.name,
                "path": str(berkas),
                "ukuran": info.st_size,
                "waktu": datetime.fromtimestamp(info.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        )
    return hasil


def _periksa(berkas: Path) -> None:
    """Pastikan berkas benar-benar database SQLite yang sehat."""
    try:
        koneksi = sqlite3.connect(str(berkas))
        try:
            hasil = koneksi.execute("PRAGMA integrity_check").fetchone()
        finally:
            koneksi.close()
    except sqlite3.DatabaseError as salah:
        raise ValueError(
            f"Backup rusak atau bukan database SQLite: {berkas.name}"
        ) from salah

    if not hasil or str(hasil[0]).lower() != "ok":
        raise ValueError(f"Backup rusak atau bukan database SQLite: {berkas.name}")


def pulihkan(nama: str, path_db: str | None = None,
             path_folder: str | Path | None = None) -> Path:
    """Kembalikan database dari backup. Database lama disimpan sebagai .bak."""
    tujuan = folder(path_folder)
    berkas = tujuan / Path(str(nama)).name  # cegah path keluar folder
    if not berkas.exists():
        raise FileNotFoundError(f"Backup tidak ditemukan: {berkas.name}")

    _periksa(berkas)

    sasaran = Path(path_db or config.db_path)
    sasaran.parent.mkdir(parents=True, exist_ok=True)

    if sasaran.exists():
        cadangan = sasaran.with_suffix(sasaran.suffix + ".bak")
        shutil.copy2(sasaran, cadangan)

    # Berkas pendamping WAL harus dibuang agar isi lama tidak tercampur,
    # termasuk bila database utamanya sudah terhapus (hanya WAL tersisa).
    for akhiran in ("-wal", "-shm"):
        pendamping = Path(str(sasaran) + akhiran)
        with contextlib.suppress(OSError):
            pendamping.unlink()

    shutil.copy2(berkas, sasaran)
    return sasaran
