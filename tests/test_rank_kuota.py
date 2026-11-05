"""Pilih yang paling cocok lebih dulu, lalu batasi kuota harian.

Pengguna meminta maksimal 50 lamaran/hari dan hanya lowongan dengan kecocokan
tertinggi yang dikirim — jadi semua kandidat dari semua lokasi dikumpulkan dan
dibandingkan dulu, baru diambil yang terbaik sebanyak sisa kuota.
"""

from types import SimpleNamespace

import pytest

import job_filter as job_filter_module
import main as main_module
from config import config
from database import Database


class BotPalsu:
    """Bot tiruan: mengingat urutan lamaran yang dicoba."""

    def __init__(self, halaman):
        self.halaman = halaman
        self.dilamar = []

    def search_jobs(self, keyword, page=1, location=""):
        return list(self.halaman.get((location, keyword, page), []))

    def apply_job(self, job):
        self.dilamar.append(job["job_id"])
        return SimpleNamespace(
            applied=True, status="applied", reason="Terkirim otomatis"
        )


def lowongan(job_id, age_days, title, salary="Rp 6.000.000",
             date_posted="Hari ini", company="PT Contoh"):
    return {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": "Bandung",
        "salary": salary,
        "description": "",
        "url": f"https://id.jobstreet.com/job/{job_id}",
        "date_posted": date_posted,
        "age_days": age_days,
    }


@pytest.fixture
def siapkan(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "rank.db"))
    monkeypatch.setattr(main_module, "db", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "locations", ["Bandung", "Jakarta"])
    monkeypatch.setattr(config, "keywords", ["inventory", "ppic"])
    monkeypatch.setattr(config, "max_pages", 1)
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "collect_before_apply", True)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "max_age_days", 0)
    monkeypatch.setattr(config, "min_salary", 0)
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", [])
    monkeypatch.setattr(config, "require_company_logo", False)
    monkeypatch.setattr(config, "max_apply_per_day", 50)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0)
    monkeypatch.setattr(config, "delay_between_apply", 0)
    monkeypatch.setattr(config, "sort_mode", "ListedDate")
    monkeypatch.setattr(config, "rank_by", "relevance")
    monkeypatch.setattr(main_module.notifier, "send_apply_success", lambda *_: None)
    monkeypatch.setattr(main_module.notifier, "send_error", lambda *_: None)

    # Skor kecocokan (kata kunci di judul +10, gaji +5, "hari ini" +5):
    #   A "Staff Inventory" = 20   (paling cocok, tapi paling lama)
    #   C "PPIC Admin"      = 18
    #   B "Staf Gudang"     = 10   (paling baru)
    # Tersebar di dua lokasi untuk memastikan pencarian lintas lokasi.
    halaman = {
        ("Bandung", "inventory", 1): [
            lowongan("A", 5, "Staff Inventory"),
            lowongan("B", 0, "Staf Gudang"),
        ],
        ("Jakarta", "ppic", 1): [
            lowongan("C", 10, "PPIC Admin", date_posted="Kemarin"),
        ],
    }

    mesin = main_module.AutoApplyEngine()
    mesin.bot = BotPalsu(halaman)
    return mesin, database


def test_kecocokan_tertinggi_didahulukan(siapkan):
    mesin, _ = siapkan
    mesin._kumpulkan_lalu_lamar()

    assert mesin.bot.dilamar == ["A", "C", "B"]


def test_rank_by_newest_mengembalikan_urutan_lama(siapkan, monkeypatch):
    mesin, _ = siapkan
    monkeypatch.setattr(config, "rank_by", "newest")

    mesin._kumpulkan_lalu_lamar()

    assert mesin.bot.dilamar == ["B", "A", "C"]


def test_hanya_sebanyak_sisa_kuota_yang_dilamar(siapkan, monkeypatch):
    mesin, database = siapkan
    monkeypatch.setattr(config, "max_apply_per_day", 2)

    mesin._kumpulkan_lalu_lamar()

    # Dua yang paling cocok saja (A skor 20, C skor 18), B tidak disentuh.
    assert mesin.bot.dilamar == ["A", "C"]


def test_kuota_memperhitungkan_lamaran_hari_ini(siapkan, monkeypatch):
    mesin, database = siapkan
    monkeypatch.setattr(config, "max_apply_per_day", 2)

    database.record_application("lain-1", "applied")
    database.record_application("lain-2", "applied")

    mesin._kumpulkan_lalu_lamar()

    assert mesin.bot.dilamar == []


def test_sisa_kuota_satu_dari_lima_puluh(siapkan, monkeypatch):
    mesin, database = siapkan
    monkeypatch.setattr(config, "max_apply_per_day", 50)

    for nomor in range(49):
        database.record_application(f"lama-{nomor}", "applied")

    mesin._kumpulkan_lalu_lamar()

    # Tinggal satu slot: hanya kandidat terbaik (A) yang dilamar.
    assert mesin.bot.dilamar == ["A"]


def test_rank_by_tidak_dikenal_kembali_ke_relevance(monkeypatch):
    from config import _pilihan_setting

    pilihan = ("relevance", "newest")

    monkeypatch.setenv("RANK_BY", "acak")
    assert _pilihan_setting("RANK_BY", "relevance", pilihan) == "relevance"

    monkeypatch.setenv("RANK_BY", "NEWEST")
    assert _pilihan_setting("RANK_BY", "relevance", pilihan) == "newest"
