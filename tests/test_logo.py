"""Uji filter logo perusahaan pada kartu lowongan JobStreet."""

import sqlite3

import pytest

import job_filter as job_filter_module
from config import config
from database import Database
from job_filter import JobFilter
from scraper import logo_perusahaan


@pytest.mark.parametrize(
    "alt, src, penanda, perusahaan, harapan",
    [
        # penanda HTML memuat "logo"
        ("", "https://cdn/a.png", "company-logo", "", True),
        ("", "https://cdn/a.png", "jobCardLogo", "", True),
        # teks alternatif memuat "logo"
        ("Company logo", "https://cdn/a.png", "", "", True),
        # URL gambar memuat "logo" atau "brand"
        ("", "https://cdn/seeks/logo/abc.png", "", "", True),
        ("", "https://cdn/brand/abc.png", "", "", True),
        # alt berisi nama perusahaan (pola umum di JobStreet)
        (
            "Trackerindo Anugerah Sejahtera",
            "https://image-service-cdn.seek.com.au/abc",
            "",
            "Trackerindo Anugerah Sejahtera CV",
            True,
        ),
        # ikon dan placeholder bukan logo
        ("", "https://cdn/icon-search.svg", "", "", False),
        ("", "https://cdn/company-placeholder.png", "", "", False),
        ("Ikon", "https://cdn/x.png", "", "", False),
        # gambar tanpa petunjuk apa pun
        ("", "https://image-service-cdn.seek.com.au/xyz", "", "PT Lain", False),
        # tidak ada gambar sama sekali
        ("", "", "", "", False),
    ],
)
def test_logo_perusahaan(alt, src, penanda, perusahaan, harapan):
    assert logo_perusahaan(alt, src, penanda, perusahaan) is harapan


@pytest.fixture
def filter_baru(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "logo.db"))
    monkeypatch.setattr(job_filter_module, "db", database)
    return JobFilter()


def make_job(**overrides):
    job = {
        "job_id": "logo-1",
        "title": "Admin PPIC",
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "Rp 6.000.000",
        "description": "Mengelola persediaan.",
        "url": "https://id.jobstreet.com/job/logo-1",
        "date_posted": "Hari ini",
        "has_logo": True,
    }
    job.update(overrides)
    return job


def test_tanpa_logo_tetap_layak_walau_aturan_aktif(filter_baru, monkeypatch):
    """Gambar/logo perusahaan tidak pernah menjadi alasan melewati lowongan."""
    monkeypatch.setattr(config, "require_company_logo", True)

    layak, alasan = filter_baru.should_apply(make_job(has_logo=False))
    assert layak is True, alasan


def test_berlogo_tetap_dilamar(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", True)
    layak, _ = filter_baru.should_apply(make_job(has_logo=True))
    assert layak is True


def test_aturan_mati_semua_boleh(filter_baru, monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", False)
    layak, _ = filter_baru.should_apply(make_job(has_logo=False))
    assert layak is True


def test_situs_lain_tanpa_info_logo_tidak_tertolak(filter_baru, monkeypatch):
    """Glints tidak mengisi has_logo; lowongannya tidak boleh ikut tertolak."""
    monkeypatch.setattr(config, "require_company_logo", True)
    job = make_job(job_id="glints:abc")
    job.pop("has_logo")
    layak, _ = filter_baru.should_apply(job)
    assert layak is True


def test_database_menyimpan_status_logo(tmp_path):
    database = Database(str(tmp_path / "logo2.db"))
    assert database.add_job(make_job(has_logo=True, logo_src="<img alt='x'>"))
    assert database.get_job("logo-1")["has_logo"] == 1

    assert database.add_job(make_job(job_id="logo-2", has_logo=False))
    assert database.get_job("logo-2")["has_logo"] == 0

    job_lain = make_job(job_id="glints:xyz")
    job_lain.pop("has_logo")
    assert database.add_job(job_lain)
    assert database.get_job("glints:xyz")["has_logo"] is None


def test_migrasi_menambah_kolom_logo_pada_database_lama(tmp_path):
    path = tmp_path / "lama.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            company TEXT,
            location TEXT,
            salary TEXT,
            description TEXT,
            url TEXT NOT NULL,
            date_posted TEXT,
            date_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()

    database = Database(str(path))
    kolom = {
        row[1]
        for row in sqlite3.connect(path).execute("PRAGMA table_info(jobs)")
    }

    assert {"has_logo", "logo_src"} <= kolom
    assert database.add_job(make_job(has_logo=False))
    assert database.get_job("logo-1")["has_logo"] == 0
