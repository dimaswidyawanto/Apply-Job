"""Batas lamaran harian — satu aturan untuk JobStreet dan Glints.

Sebelumnya aturan ini ditulis dua kali (di `main.py` untuk JobStreet dan di
`glints.py` untuk Glints) sehingga mudah berbeda. Sekarang keduanya memakai
modul ini: hitungan yang sama, pesan yang sama, dan pemotongan kandidat yang
sama.

Aturan:
* `MAX_APPLY_PER_DAY` dihitung dari lamaran yang benar-benar dikirim alat ini,
  **dipakai bersama** oleh JobStreet dan Glints.
* Nilai 0 berarti tanpa batas.
* Kandidat dipotong sesuai sisa kuota **setelah** dinilai dan diperingkat,
  supaya slot dipakai untuk lowongan yang paling cocok.

Objek database dan konfigurasi bisa diberikan oleh pemanggil (dipakai tes agar
tidak menyentuh database asli).
"""

from typing import List, Optional

from config import config
from database import db


def batas(cfg=None) -> int:
    """Batas harian yang dikonfigurasi (0 = tanpa batas)."""
    cfg = cfg or config
    return max(0, int(getattr(cfg, "max_apply_per_day", 0) or 0))


def terpakai(db_obj=None) -> int:
    """Lamaran yang sudah terkirim hari ini (JobStreet + Glints)."""
    db_obj = db_obj or db
    return int(db_obj.get_today_apply_count() or 0)


def tanpa_batas(cfg=None) -> bool:
    return batas(cfg) <= 0


def sisa(db_obj=None, cfg=None) -> Optional[int]:
    """Sisa slot hari ini; None bila tanpa batas."""
    batas_harian = batas(cfg)

    if batas_harian <= 0:
        return None

    return max(0, batas_harian - terpakai(db_obj))


def habis(db_obj=None, cfg=None) -> bool:
    sisa_hari_ini = sisa(db_obj, cfg)
    return sisa_hari_ini is not None and sisa_hari_ini <= 0


def ringkasan(db_obj=None, cfg=None) -> str:
    """Kalimat kuota yang dipakai kedua situs (isinya identik)."""
    if tanpa_batas(cfg):
        return "Kuota harian: tanpa batas (MAX_APPLY_PER_DAY=0)."

    return (
        f"Kuota harian: {terpakai(db_obj)} sudah dilamar hari ini, "
        f"sisa {sisa(db_obj, cfg)} dari {batas(cfg)}."
    )


def potong(kandidat: List[dict], db_obj=None, cfg=None) -> List[dict]:
    """Batasi kandidat sesuai sisa kuota (tanpa batas = tidak dipotong)."""
    sisa_hari_ini = sisa(db_obj, cfg)

    if sisa_hari_ini is None:
        return list(kandidat)

    return list(kandidat)[:sisa_hari_ini]


def pesan_habis() -> str:
    return (
        "Kuota lamaran hari ini sudah habis. Tidak ada lamaran dikirim. "
        "Kuota ini dipakai bersama JobStreet dan Glints."
    )
