"""Kunci sesi tunggal + data inti: status antrean, alasan, dan hari WIB.

Mengacu master prompt pasal 4.1–4.3 (antrean persisten) dan 9.2 (kuota harian
memakai zona waktu Asia/Jakarta).
"""

from datetime import datetime, timedelta, timezone

import pytest

import kunci
from database import WIB, Database, rentang_hari_wib


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "antrean.db"))


# ------------------------------------------------------------ kunci sesi ---
def test_kunci_dilepas_setelah_selesai(tmp_path):
    with kunci.sesi_tunggal(tmp_path) as path:
        assert path.exists()
    assert not path.exists()


def test_sesi_kedua_ditolak(tmp_path):
    with kunci.sesi_tunggal(tmp_path), pytest.raises(
        kunci.SesiBerjalan
    ) as info, kunci.sesi_tunggal(tmp_path):
        pass

    assert "sedang berjalan" in str(info.value)


def test_kunci_basi_dari_proses_mati_diambil_alih(tmp_path):
    path = tmp_path / kunci.NAMA_BERKAS
    path.write_text("999999 0 lamar\n", encoding="utf-8")

    with kunci.sesi_tunggal(tmp_path):
        assert path.exists()

    assert not path.exists()


def test_kunci_terlalu_tua_dianggap_basi(tmp_path):
    path = tmp_path / kunci.NAMA_BERKAS
    import os

    tua = int(datetime.now().timestamp()) - int(
        (kunci.MAKS_UMUR_JAM + 1) * 3600
    )
    path.write_text(f"{os.getpid()} {tua} lamar\n", encoding="utf-8")

    with kunci.sesi_tunggal(tmp_path):
        pass


# --------------------------------------------------- batas hari (WIB) ------
def test_rentang_hari_wib_memotong_pada_tengah_malam_jakarta():
    mulai, selesai = rentang_hari_wib(datetime(2026, 11, 6, 0, 30, tzinfo=WIB))

    # 00:30 WIB = 17:30 UTC hari sebelumnya.
    assert mulai == "2026-11-05 17:00:00"
    assert selesai == "2026-11-06 17:00:00"


def test_rentang_hari_wib_sama_sepanjang_hari():
    awal, _ = rentang_hari_wib(datetime(2026, 11, 6, 0, 0, tzinfo=WIB))
    _, akhir = rentang_hari_wib(datetime(2026, 11, 6, 23, 59, tzinfo=WIB))

    assert awal == "2026-11-05 17:00:00"
    assert akhir == "2026-11-06 17:00:00"


def test_kuota_menghitung_lamaran_hari_ini_wib(db):
    with db._get_conn() as conn:
        conn.execute(
            "INSERT INTO applications (job_id, status, applied_at) "
            "VALUES ('a1', 'applied', ?)",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),),
        )
        # 2 hari lalu: tidak boleh ikut dihitung.
        lama = (datetime.now(timezone.utc) - timedelta(days=2)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn.execute(
            "INSERT INTO applications (job_id, status, applied_at) "
            "VALUES ('a2', 'applied', ?)",
            (lama,),
        )

    assert db.get_today_apply_count() == 1


# ------------------------------------------------------- status antrean ----
def _lowongan(**ubah):
    job = {
        "job_id": "indeed:abc",
        "title": "Inventory Staff",
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "Rp 6jt",
        "description": "Mengelola stok.",
        "url": "https://id.indeed.com/viewjob?jk=abc",
        "date_posted": "3 hari lalu",
        "has_logo": False,
    }
    job.update(ubah)
    return job


def test_lowongan_baru_berstatus_found(db):
    assert db.add_job(_lowongan()) is True

    job = db.get_job("indeed:abc")
    assert job["status_antrean"] == "found"
    assert job["posted_at"] == "3 hari lalu"
    assert job["dikumpulkan_at"]


def test_status_antrean_dan_alasan_tersimpan(db):
    db.add_job(_lowongan())

    assert db.set_status_antrean(
        "indeed:abc", "rejected", "Tanpa logo perusahaan"
    ) is True

    job = db.get_job("indeed:abc")
    assert job["status_antrean"] == "rejected"
    assert job["alasan"] == "Tanpa logo perusahaan"


def test_status_tidak_dikenal_ditolak(db):
    db.add_job(_lowongan())

    assert db.set_status_antrean("indeed:abc", "entah") is False
    assert db.get_job("indeed:abc")["status_antrean"] == "found"


def test_hitung_status_antrean(db):
    db.add_job(_lowongan(job_id="a", url="https://x/a"))
    db.add_job(_lowongan(job_id="b", url="https://x/b"))
    db.set_status_antrean("b", "applied")

    hasil = db.hitung_status_antrean()

    assert hasil["found"] == 1
    assert hasil["applied"] == 1
    assert hasil["rejected"] == 0


def test_alasan_awal_bisa_disimpan_saat_menambah(db):
    db.add_job(_lowongan(job_id="c", url="https://x/c",
                         status_antrean="review_required",
                         alasan="Logo tidak dapat dipastikan"))

    job = db.get_job("c")
    assert job["status_antrean"] == "review_required"
    assert job["alasan"] == "Logo tidak dapat dipastikan"
