"""Ingatan jawaban formulir lamaran.

Aturan pemakai: **apa pun yang pernah diisi pengguna harus diingat** dan diisi
otomatis pada lamaran berikutnya. Bot hanya perlu bertanya (atau berhenti)
untuk pertanyaan yang benar-benar belum pernah dijawab.

Kunci ingatan dibuat dari teks pertanyaan yang dinormalkan, sehingga
"Manajemen Rantai Pasokan", "manajemen rantai pasokan" dan
"Manajemen  Rantai Pasokan " dianggap sama. Bila teks berubah sedikit
(tanda baca, spasi, salah ketik kecil), pencocokan mirip dipakai sebagai
cadangan.
"""

import re
from difflib import SequenceMatcher
from typing import List, Optional

from config import config
from database import db

# Batas kemiripan teks pertanyaan agar dianggap pertanyaan yang sama.
AMBANG_MIRIP = 0.86

_TANDA_BACA = re.compile(r"[^\w\s]+", re.UNICODE)


def kunci_pertanyaan(pertanyaan: str) -> str:
    """Kunci pencarian stabil dari teks pertanyaan."""
    teks = str(pertanyaan or "").casefold()
    teks = _TANDA_BACA.sub(" ", teks)
    return " ".join(teks.split())


def _aktif() -> bool:
    return bool(getattr(config, "ingat_jawaban", True))


def cari(pertanyaan: str) -> Optional[str]:
    """Jawaban yang pernah diberikan untuk pertanyaan ini (None bila belum).

    Pencocokan: kunci sama → kembalikan; bila tidak, cari pertanyaan tersimpan
    yang paling mirip (>= AMBANG_MIRIP). Setiap pemakaian dihitung supaya
    urutan prioritas bisa ditinjau lewat perintah `jawaban`.
    """
    if not _aktif():
        return None

    kunci = kunci_pertanyaan(pertanyaan)
    if not kunci:
        return None

    tersimpan = db.cari_jawaban(kunci)
    if tersimpan and tersimpan.get("jawaban"):
        db.tandai_jawaban_dipakai(kunci)
        return str(tersimpan["jawaban"])

    # Cadangan: pertanyaan yang mirip (mis. salah ketik / tanda baca berubah).
    terbaik = None
    skor_terbaik = 0.0

    for baris in db.daftar_jawaban():
        skor = SequenceMatcher(None, kunci, baris.get("kunci") or "").ratio()
        if skor > skor_terbaik:
            terbaik, skor_terbaik = baris, skor

    if terbaik and skor_terbaik >= AMBANG_MIRIP and terbaik.get("jawaban"):
        db.tandai_jawaban_dipakai(terbaik["kunci"])
        return str(terbaik["jawaban"])

    return None


def ingat(pertanyaan: str, jawaban: str, jenis: str = "",
          sumber: str = "pengguna") -> bool:
    """Simpan jawaban untuk pertanyaan ini (menimpa jawaban lama)."""
    if not _aktif():
        return False

    kunci = kunci_pertanyaan(pertanyaan)
    jawaban = " ".join(str(jawaban or "").split())

    if not kunci or not jawaban:
        return False

    return db.simpan_jawaban(
        kunci, " ".join(str(pertanyaan or "").split()), jawaban, jenis, sumber
    )


def daftar() -> List[dict]:
    """Semua jawaban tersimpan (untuk ditampilkan / diperiksa)."""
    return db.daftar_jawaban()


def lupakan(pertanyaan: str) -> bool:
    """Hapus satu jawaban dari ingatan."""
    kunci = kunci_pertanyaan(pertanyaan)
    if not kunci:
        return False

    if db.hapus_jawaban(kunci):
        return True

    # Bila yang diketik bukan kunci persis, pakai pencocokan mirip.
    terbaik = None
    skor_terbaik = 0.0

    for baris in db.daftar_jawaban():
        skor = SequenceMatcher(None, kunci, baris.get("kunci") or "").ratio()
        if skor > skor_terbaik:
            terbaik, skor_terbaik = baris, skor

    if terbaik and skor_terbaik >= AMBANG_MIRIP:
        return db.hapus_jawaban(terbaik["kunci"])

    return False


def lupakan_semua() -> int:
    """Kosongkan ingatan jawaban."""
    return db.reset_jawaban()


def jumlah() -> int:
    return db.hitung_jawaban()
