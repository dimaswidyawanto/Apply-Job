"""Kuota harian per situs: JobStreet 50, Glints 50, Indeed 50.

Permintaan pemakai (2026-11-11): 50 lamaran per hari **wajib** untuk tiap
situs, bukan satu batas bersama yang dibagi. Tes ini memastikan angka satu
situs tidak memakan jatah situs lain.
"""

import pytest

import kuota
from config import config
from database import Database


class ConfigPalsu:
    def __init__(self, batas):
        self.max_apply_per_day = batas


@pytest.fixture
def database(tmp_path):
    return Database(str(tmp_path / "kuota.db"))


def _job(nama_situs: str, nomor: int) -> dict:
    return {
        "job_id": f"{nama_situs}:{nomor}",
        "title": "PPIC",
        "company": "PT Contoh",
        "location": "Bekasi",
        "salary": "",
        "description": "",
        "url": f"https://{nama_situs}.com/job/{nomor}",
        "date_posted": "Hari ini",
        "sumber": nama_situs,
    }


def test_hitung_harian_dipisah_per_situs(database):
    for nomor in range(2):
        database.add_job(_job("jobstreet", nomor))
        database.record_application(f"jobstreet:{nomor}", "applied")

    database.add_job(_job("glints", 9))
    database.record_application("glints:9", "applied")

    assert database.get_today_apply_count("jobstreet") == 2
    assert database.get_today_apply_count("glints") == 1
    assert database.get_today_apply_count("indeed") == 0
    # Tanpa situs = semua.
    assert database.get_today_apply_count() == 3


def test_situs_dikenali_dari_job_id_walau_barisnya_hilang(database):
    """Lowongan bisa sudah dihapus dari tabel jobs; awalan id tetap menandai."""
    database.record_application("glints:hilang", "applied")
    database.record_application("indeed:hilang", "applied")
    database.record_application("12345", "applied")

    assert database.get_today_apply_count("glints") == 1
    assert database.get_today_apply_count("indeed") == 1
    assert database.get_today_apply_count("jobstreet") == 1


def test_status_dilewati_tidak_dihitung(database):
    database.record_application("glints:1", "manual_required")
    database.record_application("glints:2", "failed")

    assert database.get_today_apply_count("glints") == 0


class DbSitus:
    """Database palsu: hitungan per situs tanpa menyentuh SQLite."""

    def __init__(self, angka):
        self.angka = angka

    def get_today_apply_count(self, situs=""):
        return self.angka.get(situs, 0)


def test_kuota_satu_situs_habis_tidak_menghentikan_situs_lain():
    db = DbSitus({"jobstreet": 50, "glints": 0, "indeed": 0})
    cfg = ConfigPalsu(50)

    assert kuota.habis(db, cfg, situs="jobstreet") is True
    assert kuota.habis(db, cfg, situs="glints") is False
    assert kuota.sisa(db, cfg, situs="glints") == 50
    assert kuota.sisa(db, cfg, situs="jobstreet") == 0


def test_target_lima_puluh_per_situs():
    db = DbSitus({"jobstreet": 49, "glints": 50, "indeed": 12})
    cfg = ConfigPalsu(50)

    assert kuota.target(cfg) == 50
    assert kuota.kurang(db, cfg, situs="jobstreet") == 1
    assert kuota.kurang(db, cfg, situs="glints") == 0
    assert kuota.kurang(db, cfg, situs="indeed") == 38


def test_ringkasan_menyebut_nama_situs():
    db = DbSitus({"glints": 7})
    teks = kuota.ringkasan(db, ConfigPalsu(50), situs="glints")

    assert teks.startswith("Kuota Glints:")
    assert "7 sudah dilamar" in teks
    assert "sisa 43 dari 50" in teks


def test_ringkasan_situs_memuat_tiga_situs():
    db = DbSitus({"jobstreet": 50, "glints": 10, "indeed": 0})
    daftar = kuota.ringkasan_situs(db, ConfigPalsu(50))

    nama = [baris["situs"] for baris in daftar]
    assert nama == ["jobstreet", "glints", "indeed"]

    jobstreet = daftar[0]
    assert jobstreet["terpakai"] == 50
    assert jobstreet["sisa"] == 0
    assert jobstreet["tercapai"] is True

    glints = daftar[1]
    assert glints["sisa"] == 40
    assert glints["tercapai"] is False


def test_potong_memakai_sisa_situs_sendiri():
    db = DbSitus({"jobstreet": 49, "glints": 0})
    cfg = ConfigPalsu(50)

    assert kuota.potong(["a", "b", "c"], db, cfg, situs="jobstreet") == ["a"]
    assert kuota.potong(["a", "b", "c"], db, cfg, situs="glints") == [
        "a", "b", "c"
    ]


def test_tanpa_batas_berlaku_untuk_semua_situs():
    db = DbSitus({"jobstreet": 999})
    cfg = ConfigPalsu(0)

    for nama in kuota.SITUS_BAKU:
        assert kuota.sisa(db, cfg, situs=nama) is None
        assert kuota.habis(db, cfg, situs=nama) is False


def test_batas_bawaan_config_lima_puluh():
    """MAX_APPLY_PER_DAY bawaan harus 50 (target wajib, bukan 5)."""
    assert config.max_apply_per_day >= 50
