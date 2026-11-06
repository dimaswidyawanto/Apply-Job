"""Diagnosa kecepatan di komputer pengguna (master prompt pasal 13).

Dipakai saat aplikasi terasa lambat: mengukur bagian yang bisa diukur
(database, tulis berkas, dashboard lokal, jaringan ke tiga situs) lalu
memberi saran konkret. Tidak mengubah pengaturan apa pun.
"""

import contextlib
import shutil
import socket
import sqlite3
import time
from pathlib import Path
from typing import Callable, List

from config import BASE_DIR, config

SITUS_UJI = (
    ("JobStreet", "id.jobstreet.com"),
    ("Glints", "glints.com"),
    ("Indeed", "id.indeed.com"),
)

# Ambang sederhana: di atas ini pengguna akan terasa menunggu.
AMBANG_MS = {
    "Baca statistik database": 80,
    "Ringkasan laporan": 150,
    "Tulis berkas 1 MB": 250,
    "Dashboard lokal": 300,
}


def ukur(fungsi: Callable[[], object], ulang: int = 3) -> float:
    """Rata-rata waktu satu panggilan (milidetik)."""
    ulang = max(1, ulang)
    mulai = time.perf_counter()
    for _ in range(ulang):
        fungsi()
    return (time.perf_counter() - mulai) * 1000 / ulang


def ukur_jaringan(host: str, port: int = 443, batas: float = 4.0) -> float:
    """Waktu menyambung ke satu host (milidetik); -1 bila gagal."""
    mulai = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=batas):
            return (time.perf_counter() - mulai) * 1000
    except OSError:
        return -1.0


def ukur_dashboard(port: int = 8765, batas: float = 2.0) -> float:
    """Waktu satu permintaan ke dashboard lokal; -1 bila tidak berjalan."""
    import http.client

    mulai = time.perf_counter()
    try:
        koneksi = http.client.HTTPConnection("127.0.0.1", port, timeout=batas)
        koneksi.request("GET", "/api/status")
        jawab = koneksi.getresponse()
        jawab.read()
        koneksi.close()
    except OSError:
        return -1.0
    return (time.perf_counter() - mulai) * 1000


def _ukur_tulis(folder: Path) -> float:
    """Waktu menulis + membaca 1 MB (menguji disk & antivirus)."""
    data = b"x" * (1024 * 1024)
    berkas = Path(folder) / ".uji-tulis.tmp"
    try:
        mulai = time.perf_counter()
        berkas.write_bytes(data)
        berkas.read_bytes()
        return (time.perf_counter() - mulai) * 1000
    finally:
        with contextlib.suppress(OSError):
            berkas.unlink()


def _catatan(lokasi: str, nilai: float, saran: str = "") -> dict:
    ambang = AMBANG_MS.get(lokasi, 0)
    if nilai < 0:
        status = "lewat"
    elif ambang and nilai > ambang:
        status = "lambat"
    else:
        status = "ok"
    return {"bagian": lokasi, "ms": round(nilai, 1), "status": status,
            "saran": saran}


def kumpulkan(port: int = 8765, folder_uji: Path | None = None) -> List[dict]:
    """Semua pengukuran, siap ditampilkan sebagai tabel."""
    import laporan
    from database import db

    folder = Path(folder_uji) if folder_uji else Path(BASE_DIR)

    hasil = [
        _catatan(
            "Baca statistik database",
            ukur(db.get_stats),
            "Database di disk lambat atau sedang dipakai proses lain.",
        ),
        _catatan(
            "Ringkasan laporan",
            ukur(laporan.ringkasan, 2),
            "Data terlalu besar atau disk lambat.",
        ),
        _catatan(
            "Tulis berkas 1 MB",
            _ukur_tulis(folder),
            "Disk lambat, atau antivirus memindai setiap berkas.",
        ),
        _catatan(
            "Dashboard lokal",
            ukur_dashboard(port),
            "Dashboard tidak berjalan atau port dipakai proses lain.",
        ),
    ]

    for nama, host in SITUS_UJI:
        hasil.append(
            _catatan(
                f"Jaringan ke {nama}",
                ukur_jaringan(host),
                "Internet lambat/DNS bermasalah; situs juga butuh waktu render.",
            )
        )

    return hasil


def saran_umum() -> List[str]:
    """Saran yang tidak bergantung pada hasil angka."""
    saran = []
    dasar = str(BASE_DIR).lower()

    if "onedrive" in dasar:
        saran.append(
            "Folder proyek ada di OneDrive. Sinkronisasi membuat setiap tulis "
            "database menunggu awan — pindahkan ke C:\\Dimas\\..."
        )

    if "program files" in dasar or "windows" in dasar:
        saran.append(
            "Folder proyek ada di folder sistem; pindahkan ke folder pengguna."
        )

    jumlah = 0
    with contextlib.suppress(Exception):
        from database import db

        jumlah = int(db.get_stats().get("total_jobs_found", 0))

    if jumlah > 5000:
        saran.append(
            f"Database berisi {jumlah} lowongan. Jalankan `history --clear` "
            "bila riwayat lama tidak diperlukan, dan `backup` dulu."
        )

    saran.append(
        "Kecualikan folder proyek (dan .venv) di Windows Defender agar "
        "Python & Chrome tidak dipindai ulang setiap jalan."
    )
    return saran


def ukuran_database(path: str | None = None) -> float:
    """Ukuran berkas database dalam MB."""
    jalur = Path(path or config.db_path)
    if not jalur.exists():
        return 0.0
    return jalur.stat().st_size / (1024 * 1024)


def jumlah_baris(path: str | None = None) -> int:
    """Jumlah lowongan tersimpan (tanpa membuka objek Database)."""
    jalur = Path(path or config.db_path)
    if not jalur.exists():
        return 0

    try:
        with contextlib.closing(sqlite3.connect(str(jalur))) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
    except sqlite3.DatabaseError:
        return 0


def chrome_terpasang() -> bool:
    """Apakah Chrome ditemukan di lokasi lazim."""
    if shutil.which("chrome"):
        return True

    for nama in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        if Path(nama).exists():
            return True

    return False


def ringkas() -> dict:
    """Angka pendukung: jumlah lowongan, ukuran DB, Chrome, folder."""
    return {
        "folder": str(BASE_DIR),
        "jumlah_lowongan": jumlah_baris(),
        "ukuran_db_mb": round(ukuran_database(), 2),
        "chrome": chrome_terpasang(),
    }
