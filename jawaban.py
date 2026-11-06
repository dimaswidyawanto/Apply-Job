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


# Padanan istilah lintas bahasa. Formulir lamaran yang sama sering muncul
# dalam bahasa Indonesia atau Inggris ("Nama Lengkap" / "Full Name"), jadi
# kedua bentuk dipetakan ke satu kata kunci canonik sebelum dibandingkan.
PADANAN = {
    # identitas
    "nama lengkap": "nama",
    "nama": "nama",
    "full name": "nama",
    "name": "nama",
    "nama depan": "nama depan",
    "first name": "nama depan",
    "given name": "nama depan",
    "nama belakang": "nama belakang",
    "last name": "nama belakang",
    "surname": "nama belakang",
    "family name": "nama belakang",
    "email": "email",
    "surel": "email",
    "alamat email": "email",
    "email address": "email",
    "telepon": "telepon",
    "telpon": "telepon",
    "phone": "telepon",
    "phone number": "telepon",
    "mobile phone": "telepon",
    "nomor telepon": "telepon",
    "no telepon": "telepon",
    "nomor handphone": "telepon",
    "handphone": "telepon",
    "hp": "telepon",
    "alamat": "alamat",
    "address": "alamat",
    "alamat tinggal": "alamat",
    "current address": "alamat",
    "kota": "kota",
    "city": "kota",
    "kabupaten": "kota",
    "provinsi": "provinsi",
    "province": "provinsi",
    "kode pos": "kode pos",
    "postal code": "kode pos",
    "zip code": "kode pos",
    "negara": "negara",
    "country": "negara",
    "kewarganegaraan": "kewarganegaraan",
    "nationality": "kewarganegaraan",
    "citizenship": "kewarganegaraan",
    "tempat lahir": "tempat lahir",
    "place of birth": "tempat lahir",
    "tanggal lahir": "tanggal lahir",
    "date of birth": "tanggal lahir",
    "birth date": "tanggal lahir",
    "jenis kelamin": "jenis kelamin",
    "gender": "jenis kelamin",
    "sex": "jenis kelamin",
    "agama": "agama",
    "religion": "agama",
    "status perkawinan": "status perkawinan",
    "status pernikahan": "status perkawinan",
    "marital status": "status perkawinan",
    # pendidikan & pengalaman
    "pendidikan": "pendidikan",
    "pendidikan terakhir": "pendidikan",
    "education": "pendidikan",
    "highest education": "pendidikan",
    "educational background": "pendidikan",
    "universitas": "universitas",
    "university": "universitas",
    "sekolah": "universitas",
    "school": "universitas",
    "institusi": "universitas",
    "institution": "universitas",
    "jurusan": "jurusan",
    "major": "jurusan",
    "bidang studi": "jurusan",
    "field of study": "jurusan",
    "ipk": "ipk",
    "gpa": "ipk",
    "pengalaman": "pengalaman",
    "pengalaman kerja": "pengalaman",
    "experience": "pengalaman",
    "work experience": "pengalaman",
    "years of experience": "pengalaman",
    "lama pengalaman": "pengalaman",
    # pekerjaan
    "gaji": "gaji",
    "gaji yang diharapkan": "gaji",
    "ekspektasi gaji": "gaji",
    "expected salary": "gaji",
    "salary": "gaji",
    "salary expectation": "gaji",
    "jabatan": "posisi",
    "posisi": "posisi",
    "position": "posisi",
    "applied position": "posisi",
    "posisi yang dilamar": "posisi",
    "kapan bisa mulai": "mulai",
    "tanggal bergabung": "mulai",
    "available start date": "mulai",
    "start date": "mulai",
    "notice period": "mulai",
    "sim": "sim",
    "sim c": "sim",
    "driving license": "sim",
    "bahasa": "bahasa",
    "language": "bahasa",
}


def kunci_padanan(pertanyaan: str) -> str:
    """Kunci canonik setelah istilah Indonesia/Inggris disamakan."""
    kata = kunci_pertanyaan(pertanyaan).split()
    hasil = []
    i = 0
    while i < len(kata):
        dua = " ".join(kata[i : i + 2])
        if dua in PADANAN:
            hasil.append(PADANAN[dua])
            i += 2
            continue
        hasil.append(PADANAN.get(kata[i], kata[i]))
        i += 1
    return " ".join(hasil)


def _mirip_kunci(pertanyaan: str, kunci_tersimpan: str) -> float:
    """Kemiripan teks, juga setelah istilah dua bahasa disamakan."""
    kunci = kunci_pertanyaan(pertanyaan)
    skor = SequenceMatcher(None, kunci, kunci_tersimpan).ratio()
    skor_padanan = SequenceMatcher(
        None, kunci_padanan(pertanyaan), kunci_padanan(kunci_tersimpan)
    ).ratio()
    return max(skor, skor_padanan)


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
        skor = _mirip_kunci(pertanyaan, baris.get("kunci") or "")
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
        skor = _mirip_kunci(pertanyaan, baris.get("kunci") or "")
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
