"""Cache hasil riset lowongan (temuan audit E-13).

Sebelumnya setiap `run`/`lamar` memanggil situs dari nol, termasuk ketika
siklus kuota yang sama dijalankan dua kali untuk mengejar 50 lamaran. Sekarang
hasil satu kombinasi **situs + kata kunci + lokasi + halaman** disimpan di
SQLite dan dipakai ulang selama masih segar.

Aturan:
* `CACHE_RISET_MENIT` (bawaan 60) = masa berlaku. `0` = cache dimatikan.
* `--segar` (atau `cache_riset.paksa_segar()`) memaksa ambil ulang dari situs.
* Cache **tidak** dipakai untuk mengirim lamaran: setiap lamaran tetap membuka
  halaman lowongannya sendiri, jadi lowongan yang sudah tutup tetap gagal
  dengan aman.
* Baris yang lebih tua dari 3 hari dibuang otomatis setiap menyimpan.
"""

import contextlib
import hashlib

from config import config
from database import db as db_baku

# Statistik sesi berjalan (dipakai untuk pesan ringkas).
_dipakai = 0
_disimpan = 0
_TTL_PAKSA = None


def ttl_detik(cfg=None) -> int:
    """Masa berlaku cache dalam detik (0 = cache mati)."""
    if _TTL_PAKSA is not None:
        return _TTL_PAKSA

    cfg = cfg or config
    menit = max(0, int(getattr(cfg, "cache_riset_menit", 0) or 0))
    return menit * 60


def aktif(cfg=None) -> bool:
    return ttl_detik(cfg) > 0


def paksa_segar(aktifkan: bool = True) -> None:
    """Matikan cache untuk sesi ini (dipakai oleh `--segar`)."""
    global _TTL_PAKSA
    _TTL_PAKSA = 0 if aktifkan else None


def kunci(situs: str, kata_kunci: str, lokasi: str = "",
          halaman: int = 0) -> str:
    """Kunci cache yang stabil dan pendek untuk satu kombinasi riset."""
    bahan = "|".join(
        [
            str(situs or "").strip().lower(),
            " ".join(str(kata_kunci or "").lower().split()),
            " ".join(str(lokasi or "").lower().split()),
            str(int(halaman or 0)),
        ]
    )
    sidik = hashlib.sha1(bahan.encode("utf-8")).hexdigest()[:16]
    return f"{str(situs or '').strip().lower()}:{sidik}"


def ambil(kunci_cache: str, db_obj=None, cfg=None, situs: str = "") -> list | None:
    """Daftar lowongan dari cache, atau None bila harus mengambil dari situs."""
    global _dipakai

    ttl = ttl_detik(cfg)
    if ttl <= 0:
        return None

    data = (db_obj or db_baku).cache_riset_ambil(kunci_cache, ttl)

    if data is None:
        return None

    _dipakai += 1
    return data if isinstance(data, list) else None


def simpan(kunci_cache: str, data: list, db_obj=None, cfg=None,
           situs: str = "") -> None:
    """Simpan hasil riset satu kombinasi (dilewati bila cache dimatikan)."""
    global _disimpan

    if ttl_detik(cfg) <= 0:
        return

    store = db_obj or db_baku
    store.cache_riset_simpan(kunci_cache, situs, list(data or []))
    _disimpan += 1

    # Housekeeping ringan: jangan biarkan tabel tumbuh selamanya.
    with contextlib.suppress(Exception):
        store.cache_riset_bersih()


def statistik() -> dict:
    return {"dipakai": _dipakai, "disimpan": _disimpan}


def reset_statistik() -> None:
    global _dipakai, _disimpan
    _dipakai = 0
    _disimpan = 0


def ringkas(cfg=None) -> str:
    """Kalimat ringkas untuk akhir riset (kosong bila cache tidak dipakai)."""
    if not aktif(cfg) or not (_dipakai or _disimpan):
        return ""

    menit = ttl_detik(cfg) // 60
    return (
        f"Cache riset: {_dipakai} kombinasi dipakai ulang, "
        f"{_disimpan} disimpan (berlaku {menit} menit; "
        "pakai --segar untuk ambil ulang dari situs)."
    )
