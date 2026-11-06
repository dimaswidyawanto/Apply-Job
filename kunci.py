"""Kunci sesi tunggal agar dua peluncur tidak berjalan bersamaan.

Master prompt pasal 4.3: satu lowongan tidak boleh diproses dua worker
sekaligus. Di aplikasi ini "worker" adalah jendela peluncur (`Lamar
JobStreet.bat`, `Lamar Glints.bat`, `Lamar Indeed.bat`, `Lamar Otomatis.bat`)
atau perintah CLI. Tanpa kunci, dua jendela bisa melamar lowongan yang sama
sebelum catatan database sempat ditulis.

Kunci berupa berkas kecil berisi PID + waktu mulai. Kunci dianggap basi bila
prosesnya sudah tidak hidup (mis. komputer restart) atau umumya lebih dari
`MAKS_UMUR_JAM`.
"""

import atexit
import contextlib
import os
import time
from contextlib import contextmanager
from pathlib import Path

NAMA_BERKAS = ".dimastes-sesi.lock"
MAKS_UMUR_JAM = 6.0


class SesiBerjalan(RuntimeError):
    """Sudah ada sesi lamar otomatis lain yang memakai database ini."""


def _pid_hidup(pid: int) -> bool:
    """Apakah proses dengan PID itu masih berjalan (Windows & POSIX)."""
    if pid <= 0:
        return False

    if os.name == "nt":  # pragma: no cover - diuji di PC pengguna
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _baca(path: Path) -> tuple[int, float]:
    """(pid, waktu_mulai) dari berkas kunci; (0, 0) bila tidak terbaca."""
    try:
        bagian = path.read_text(encoding="utf-8").split()
    except OSError:
        return 0, 0.0

    pid = int(bagian[0]) if bagian and bagian[0].isdigit() else 0
    try:
        mulai = float(bagian[1]) if len(bagian) > 1 else 0.0
    except ValueError:
        mulai = 0.0

    return pid, mulai


def _basi(path: Path) -> bool:
    pid, mulai = _baca(path)
    if mulai and (time.time() - mulai) > MAKS_UMUR_JAM * 3600:
        return True
    return not _pid_hidup(pid)


def _hapus(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


@contextmanager
def sesi_tunggal(folder: str | Path = ".", nama: str = "lamar"):
    """Kunci eksklusif selama satu sesi lamar otomatis.

    `with sesi_tunggal(): ...` — melempar `SesiBerjalan` bila sesi lain aktif.
    """
    path = Path(folder) / NAMA_BERKAS

    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _basi(path):
                _hapus(path)
                continue
            pid, _ = _baca(path)
            raise SesiBerjalan(
                "Sesi lamar otomatis lain sedang berjalan"
                + (f" (PID {pid})" if pid else "")
                + ". Tutup jendela itu dulu, atau hapus berkas "
                f"{path} bila aplikasi memang sudah tidak jalan."
            ) from None

        with os.fdopen(fd, "w", encoding="utf-8") as berkas:
            berkas.write(f"{os.getpid()} {time.time():.0f} {nama}\n")
        break
    else:  # pragma: no cover - hanya bila berkas kunci terus dibuat ulang
        raise SesiBerjalan("Tidak bisa membuat berkas kunci sesi")

    def _lepas() -> None:
        pid, _ = _baca(path)
        if pid == os.getpid():
            _hapus(path)

    atexit.register(_lepas)
    try:
        yield path
    finally:
        _lepas()
        with contextlib.suppress(Exception):
            atexit.unregister(_lepas)
