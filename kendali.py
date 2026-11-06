"""Kendali sesi dari dashboard: jeda dan berhenti (master prompt pasal 11.5).

Dashboard menulis berkas perintah kecil; sesi lamar memeriksanya di antara
lowongan sehingga tombol Pause/Stop benar-benar berpengaruh, bukan hiasan.
"""

import contextlib
import time
from pathlib import Path

NAMA_BERKAS = ".dimastes-kendali"
PERINTAH_SAH = ("lanjut", "jeda", "stop")

# Jeda maksimum agar proses tidak menggantung selamanya bila dashboard ditutup.
BATAS_JEDA_DETIK = 3600


class Berhenti(Exception):
    """Sesi dihentikan dari dashboard."""


def _path(folder: str | Path = ".") -> Path:
    return Path(folder) / NAMA_BERKAS


def perintah(teks: str, folder: str | Path = ".") -> bool:
    """Tulis perintah untuk sesi yang sedang berjalan."""
    teks = str(teks or "").strip().lower()
    if teks not in PERINTAH_SAH:
        return False

    try:
        _path(folder).write_text(teks + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def baca(folder: str | Path = ".") -> str:
    """Perintah aktif; "lanjut" bila tidak ada berkas."""
    try:
        isi = _path(folder).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return "lanjut"

    return isi if isi in PERINTAH_SAH else "lanjut"


def bersihkan(folder: str | Path = ".") -> None:
    with contextlib.suppress(OSError):
        _path(folder).unlink()


def periksa(folder: str | Path = ".", tidur=time.sleep,
            batas_detik: int = BATAS_JEDA_DETIK) -> None:
    """Berhenti bila diminta; tunggu selama dijeda.

    Melempar `Berhenti` sehingga pemanggil bisa menutup browser dengan rapi.
    """
    mulai = time.monotonic()

    while True:
        arahan = baca(folder)

        if arahan == "stop":
            raise Berhenti("Dihentikan dari dashboard")

        if arahan != "jeda":
            return

        if time.monotonic() - mulai > batas_detik:
            return

        tidur(1)
