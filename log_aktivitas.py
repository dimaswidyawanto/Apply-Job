"""Log aktivitas sederhana untuk dashboard (master prompt pasal 11.4).

Ditulis sebagai teks satu baris per kejadian agar bisa dibaca dashboard,
`tail`, maupun dibuka dengan Notepad.
"""

import contextlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

WIB = timezone(timedelta(hours=7))
FOLDER = Path("logs")
BERKAS = FOLDER / "aktivitas.log"
MAKS_BARIS = 2000


def catat(pesan: str, tingkat: str = "info", folder: Path = FOLDER) -> None:
    """Tambah satu baris log; kegagalan menulis tidak boleh menghentikan sesi."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        berkas = folder / "aktivitas.log"
        waktu = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
        with berkas.open("a", encoding="utf-8") as f:
            f.write(f"{waktu} [{tingkat}] {str(pesan).strip()}\n")
        _pangkas(berkas)
    except OSError:
        pass


def _pangkas(berkas: Path, maks: int = MAKS_BARIS) -> None:
    try:
        baris = berkas.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    if len(baris) > maks:
        with contextlib.suppress(OSError):
            berkas.write_text("\n".join(baris[-maks:]) + "\n", encoding="utf-8")


def baris_terakhir(jumlah: int = 50, folder: Path = FOLDER) -> list[str]:
    """Ambil beberapa baris terakhir untuk ditampilkan di dashboard."""
    try:
        isi = (folder / "aktivitas.log").read_text(encoding="utf-8")
    except OSError:
        return []

    return isi.splitlines()[-max(1, jumlah):]


def kosongkan(folder: Path = FOLDER) -> None:
    with contextlib.suppress(OSError):
        (folder / "aktivitas.log").unlink()


def waktu_sekarang() -> str:
    return datetime.now(WIB).strftime("%H:%M:%S")


# Dipakai uji: memastikan cap waktu memakai WIB, bukan zona PC.
def cap_waktu(detik_epoch: float) -> str:
    return datetime.fromtimestamp(detik_epoch, WIB).strftime("%Y-%m-%d %H:%M:%S")


def umur_detik(baris: str) -> float:
    """Selisih detik antara sekarang dan cap waktu pada satu baris log."""
    try:
        teks = baris[:19]
        saat = datetime.strptime(teks, "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB)
    except (ValueError, TypeError):
        return -1.0

    return time.time() - saat.timestamp()
