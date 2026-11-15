"""Ukur peluang mencapai target 50 lamaran dari isi database.

Pengguna menetapkan target **50 lamaran per situs per siklus 24 jam**.
Modul ini menjawab pertanyaan yang muncul saat target tidak tercapai:
"berapa lamaran yang sebenarnya bisa dikirim hari ini, dan aturan mana yang
menghalangi?"

Cara kerjanya murni membaca database (tanpa membuka browser, tanpa mengirim
lamaran): lowongan yang tersimpan dinilai ulang dengan `job_filter` pada
beberapa skenario aturan, lalu dihitung berapa yang lolos. Selisih antar
skenario menunjukkan kontribusi tiap aturan, sehingga pengguna bisa memutuskan
aturan mana yang dilonggarkan — bukan menebak.

Batas jujur:
* Yang dihitung hanya lowongan yang **sudah ada di database**. Lowongan yang
  belum pernah ditemukan tidak bisa diperkirakan di sini.
* Umur lowongan (`age_days`) tidak tersimpan di database, jadi saringan
  `MAX_AGE_DAYS` tidak ikut dihitung. Angka bisa sedikit lebih tinggi dari
  kenyataan bila batas umur dipakai.
"""

from collections import Counter

import job_filter as job_filter_module
from config import config
from database import db as db_baku
from kuota import NAMA_SITUS, ringkasan, sisa


class _DbPenilai:
    """Pembungkus database untuk penilaian ulang.

    Penilaian memakai daftar lowongan yang sudah disaring "belum dilamar",
    jadi `is_already_applied` cukup mengembalikan False tanpa query per
    lowongan (menghindari ribuan koneksi SQLite).
    """

    def __init__(self, db_obj):
        self._db = db_obj
        self._blacklist = None

    def is_already_applied(self, job_id: str) -> bool:  # noqa: ARG002
        return False

    def get_blacklist(self):
        if self._blacklist is None:
            try:
                self._blacklist = self._db.get_blacklist()
            except Exception:
                self._blacklist = []
        return self._blacklist


# Skenario aturan: nama → nilai config yang diubah saat menilai.
SKENARIO = (
    ("Sekarang (semua aturan aktif)", {}),
    ("Tanpa syarat logo", {"require_company_logo": False}),
    (
        "Tanpa syarat logo + gaji minimum",
        {"require_company_logo": False, "min_salary": 0},
    ),
    (
        "Tanpa logo + gaji + pencocokan judul",
        {
            "require_company_logo": False,
            "min_salary": 0,
            "require_keyword_match": False,
        },
    ),
)


def _rapikan(job: dict) -> dict:
    """Samakan tipe data dari database dengan yang dipakai `job_filter`.

    SQLite menyimpan `has_logo` sebagai 0/1, sedangkan aturan logo memakai
    perbandingan identitas (`is False`). Tanpa ini, lowongan tanpa logo akan
    terlihat "lolos" saat dinilai ulang.
    """
    data = dict(job)

    if "has_logo" in data and data["has_logo"] is not None:
        data["has_logo"] = bool(data["has_logo"])

    return data


def _nilai(semua: list[dict], ubahan: dict) -> tuple[int, Counter]:
    """Hitung berapa lowongan lolos dengan satu set aturan."""
    asal = {}
    for kunci, nilai in ubahan.items():
        asal[kunci] = getattr(config, kunci)
        setattr(config, kunci, nilai)

    db_lama = job_filter_module.db
    job_filter_module.db = _DbPenilai(db_baku)

    try:
        penilai = job_filter_module.JobFilter()
        lolos = 0
        alasan = Counter()

        for job in semua:
            try:
                boleh, sebab = penilai.should_apply(job)
            except Exception as exc:  # data lama bisa tidak lengkap
                alasan[f"Gagal dinilai: {exc.__class__.__name__}"] += 1
                continue

            if boleh:
                lolos += 1
            else:
                alasan[sebab] += 1
    finally:
        job_filter_module.db = db_lama
        for kunci, nilai in asal.items():
            setattr(config, kunci, nilai)

    return lolos, alasan


def hitung(db_obj=None, situs: str = "jobstreet", batas: int = 0) -> dict:
    """Ringkas peluang mencapai target dari isi database."""
    db_obj = db_obj or db_baku

    semua = [_rapikan(job) for job in db_obj.lowongan_belum_dilamar(batas=batas)]
    skenario = []
    alasan_sekarang: Counter = Counter()

    for nama, ubahan in SKENARIO:
        lolos, alasan = _nilai(semua, ubahan)
        skenario.append({"nama": nama, "ubahan": ubahan, "lolos": lolos})
        if not ubahan:
            alasan_sekarang = alasan

    sisa_slot = sisa(db_obj, situs=situs)

    return {
        "situs": situs,
        "nama_situs": NAMA_SITUS.get(situs, situs.title()),
        "kandidat": len(semua),
        "skenario": skenario,
        "alasan": alasan_sekarang,
        "sisa_slot": sisa_slot,
        "kuota": ringkasan(db_obj, situs=situs),
    }


def saran(hasil: dict, maksimal: int = 3) -> list[str]:
    """Saran tindakan dari alasan penolakan terbanyak (untuk ditampilkan)."""
    peta = {
        "logo": "set-env REQUIRE_COMPANY_LOGO=false",
        "salary": "set-env MIN_SALARY=0",
        "judul": "tambah KEYWORDS / RESEARCH_KEYWORDS",
        "lokasi": "tambah LOCATIONS atau set-env STRICT_LOCATION=false",
        "senior": "periksa daftar EXCLUDE_KEYWORDS",
    }

    keluaran = []

    for alasan, jumlah in hasil["alasan"].most_common(maksimal):
        teks = str(alasan).lower()
        for penanda, tindakan in peta.items():
            if penanda in teks:
                keluaran.append(f"{alasan} ({jumlah}) → {tindakan}")
                break
        else:
            continue

    return keluaran
