"""`cek-target`: mengukur peluang mencapai 50 lamaran dari isi database.

Yang diuji:
* lowongan yang belum pernah dilamar bisa dibaca dari database;
* skenario pelonggaran aturan menaikkan jumlah yang lolos;
* alasan penolakan dihitung, dan saran tindakan mengikuti alasan terbanyak;
* perhitungan tidak mengubah konfigurasi asli (tidak ada efek samping).
"""

from collections import Counter

import pytest

import job_filter as job_filter_module
import target_audit
from config import config
from database import Database


def lowongan(job_id, title="Staff Inventory", salary="Rp 6.000.000",
             has_logo=1, lokasi="Bandung"):
    return {
        "job_id": str(job_id),
        "title": title,
        "company": "PT Contoh",
        "location": lokasi,
        "salary": salary,
        "description": "",
        "url": f"https://id.jobstreet.com/job/{job_id}",
        "date_posted": "Hari ini",
        "has_logo": has_logo,
    }


@pytest.fixture
def siapkan(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "target.db"))
    monkeypatch.setattr(target_audit, "db_baku", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "locations", ["Bandung"])
    monkeypatch.setattr(config, "location", "Bandung")
    monkeypatch.setattr(config, "strict_location", False)
    monkeypatch.setattr(config, "keywords", ["inventory", "ppic"])
    monkeypatch.setattr(config, "title_keywords", [])
    monkeypatch.setattr(config, "exclude_keywords", [])
    monkeypatch.setattr(config, "max_age_days", 0)
    monkeypatch.setattr(config, "min_salary", 0)
    monkeypatch.setattr(config, "max_experience", 99)
    monkeypatch.setattr(config, "require_keyword_match", True)
    monkeypatch.setattr(config, "require_company_logo", True)
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", [])
    monkeypatch.setattr(config, "max_apply_per_day", 50)

    return database


def test_lowongan_belum_dilamar_mengecualikan_yang_sudah_dilamar(siapkan):
    database = siapkan
    database.add_job(lowongan(1))
    database.add_job(lowongan(2))
    database.record_application("1", "applied", "Terkirim")

    tersisa = database.lowongan_belum_dilamar()

    assert [baris["job_id"] for baris in tersisa] == ["2"]


def test_skenario_tanpa_logo_menambah_yang_lolos(siapkan):
    database = siapkan

    for nomor in range(1, 5):
        database.add_job(lowongan(nomor, has_logo=1))
    for nomor in range(5, 9):
        database.add_job(lowongan(nomor, has_logo=0))

    hasil = target_audit.hitung(database, situs="jobstreet")
    angka = {baris["nama"]: baris["lolos"] for baris in hasil["skenario"]}

    assert hasil["kandidat"] == 8
    assert angka["Sekarang (semua aturan aktif)"] == 4
    assert angka["Tanpa syarat logo"] == 8


def test_skenario_gaji_dan_judul_ikut_dihitung(siapkan, monkeypatch):
    database = siapkan
    database.add_job(lowongan(1, salary="Rp 2.000.000"))
    database.add_job(lowongan(2, title="Sales Executive"))
    database.add_job(lowongan(3))

    monkeypatch.setattr(config, "min_salary", 5_000_000)

    hasil = target_audit.hitung(database, situs="jobstreet")
    angka = {baris["nama"]: baris["lolos"] for baris in hasil["skenario"]}

    assert angka["Sekarang (semua aturan aktif)"] == 1
    assert angka["Tanpa syarat logo + gaji minimum"] == 2
    assert angka["Tanpa logo + gaji + pencocokan judul"] == 3


def test_alasan_terbanyak_tercatat(siapkan):
    database = siapkan
    for nomor in range(1, 4):
        database.add_job(lowongan(nomor, has_logo=0))

    hasil = target_audit.hitung(database, situs="jobstreet")

    assert hasil["alasan"]["Tanpa logo perusahaan"] == 3


def test_saran_mengikuti_alasan_terbanyak():
    saran = target_audit.saran(
        {"alasan": Counter({"Tanpa logo perusahaan": 9, "Salary terlalu rendah": 2})}
    )

    assert any("REQUIRE_COMPANY_LOGO" in baris for baris in saran)
    assert any("MIN_SALARY" in baris for baris in saran)


def test_hitung_tidak_mengubah_konfigurasi(siapkan):
    database = siapkan
    database.add_job(lowongan(1, has_logo=0))

    before = (
        config.require_company_logo,
        config.min_salary,
        config.require_keyword_match,
    )
    target_audit.hitung(database, situs="jobstreet")
    after = (
        config.require_company_logo,
        config.min_salary,
        config.require_keyword_match,
    )

    assert before == after


def test_database_kosong_tidak_error(siapkan):
    hasil = target_audit.hitung(siapkan, situs="jobstreet")

    assert hasil["kandidat"] == 0
    assert all(baris["lolos"] == 0 for baris in hasil["skenario"])


def test_perintah_cek_target_menampilkan_skenario(siapkan, monkeypatch):
    """Perintah `cek-target` mencetak tabel skenario & alasan penolakan."""
    from rich.console import Console

    import cli

    database = siapkan
    database.add_job(lowongan(1, has_logo=1))
    database.add_job(lowongan(2, has_logo=0))

    console = Console(record=True, width=100)
    monkeypatch.setattr(cli, "db", database)
    monkeypatch.setattr(cli, "console", console)

    hasil = cli.cek_target("jobstreet", 0)
    keluaran = console.export_text()

    assert hasil["kandidat"] == 2
    assert "Tanpa syarat logo" in keluaran
    assert "Tanpa logo perusahaan" in keluaran
    assert "REQUIRE_COMPANY_LOGO" in keluaran
