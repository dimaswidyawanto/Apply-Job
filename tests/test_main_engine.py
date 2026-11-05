"""Urutan pelamaran: mulai dari posting terbaru."""

from types import SimpleNamespace

import pytest

import job_filter as job_filter_module
import main as main_module
from config import config
from database import Database


class BotPalsu:
    def __init__(self, halaman):
        self.halaman = halaman
        self.dilamar = []

    def search_jobs(self, keyword, page=1, location=""):
        return list(self.halaman.get((keyword, page), []))

    def apply_job(self, job):
        self.dilamar.append(job["job_id"])
        return SimpleNamespace(
            applied=True, status="applied", reason="Terkirim otomatis"
        )


def lowongan(job_id, age_days, title="Staff Inventory"):
    return {
        "job_id": str(job_id),
        "title": title,
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "Rp 5.000.000",
        "description": "",
        "url": f"https://id.jobstreet.com/job/{job_id}",
        "date_posted": "Hari ini",
        "age_days": age_days,
    }


@pytest.fixture
def siapkan(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "engine.db"))
    monkeypatch.setattr(main_module, "db", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "locations", ["Bandung"])
    monkeypatch.setattr(config, "keywords", ["inventory", "ppic"])
    monkeypatch.setattr(config, "max_pages", 1)
    # Fixture ini menguji satu halaman per kata kunci; riset tanpa batas
    # diuji terpisah di tests/test_riset.py.
    monkeypatch.setattr(config, "research_max_pages", 1)
    monkeypatch.setattr(config, "research_max_jobs", 0)
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "max_age_days", 0)
    monkeypatch.setattr(config, "min_salary", 0)
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "max_apply_per_day", 500)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 500)
    monkeypatch.setattr(config, "delay_between_apply", 0)
    monkeypatch.setattr(config, "sort_mode", "ListedDate")
    monkeypatch.setattr(config, "prefer_newest", True)
    monkeypatch.setattr(main_module.notifier, "send_apply_success", lambda *_: None)
    monkeypatch.setattr(main_module.notifier, "send_error", lambda *_: None)

    halaman = {
        ("inventory", 1): [lowongan("A", 5), lowongan("B", 1)],
        ("inventory", 2): [lowongan("D", 10)],
        ("ppic", 1): [lowongan("C", 0)],
    }

    mesin = main_module.AutoApplyEngine()
    mesin.bot = BotPalsu(halaman)
    return mesin


def test_kumpulkan_dulu_urut_posting_terbaru(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", True)

    siapkan._kumpulkan_lalu_lamar()

    # max_pages=1, jadi halaman 2 (D) tidak ikut dikumpulkan.
    assert siapkan.bot.dilamar == ["C", "B", "A"]


def test_streaming_halaman_terbaru_dulu(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", False)
    monkeypatch.setattr(config, "max_pages", 2)

    siapkan._streaming_halaman()

    # Halaman 1 semua kata kunci dulu (lowongan terbaru), halaman 2 menyusul.
    assert siapkan.bot.dilamar == ["B", "A", "C", "D"]


def test_kumpulkan_menghormati_batas_sesi(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", True)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 2)

    siapkan._kumpulkan_lalu_lamar()

    assert siapkan.bot.dilamar == ["C", "B"]


def test_tidak_ada_kandidat_tidak_error(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", True)
    siapkan.bot.halaman = {}

    siapkan._kumpulkan_lalu_lamar()

    assert siapkan.bot.dilamar == []


def test_login_habis_menghentikan_pelamaran(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", True)

    def habis(job):
        siapkan.bot.dilamar.append(job["job_id"])
        return SimpleNamespace(
            applied=False, status="login_required", reason="Sesi habis"
        )

    monkeypatch.setattr(siapkan.bot, "apply_job", habis)

    siapkan._kumpulkan_lalu_lamar()

    # Hanya satu lamaran dicoba; sisanya dihentikan.
    assert siapkan.bot.dilamar == ["C"]
    assert siapkan.stop_requested is True


def test_batas_nol_berarti_tanpa_batas(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", True)
    monkeypatch.setattr(config, "max_apply_per_day", 0)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0)

    siapkan._kumpulkan_lalu_lamar()

    assert siapkan.bot.dilamar == ["C", "B", "A"]


def test_lowongan_sama_tidak_dilamar_dua_kali(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", False)
    siapkan.bot.halaman = {
        ("inventory", 1): [lowongan("X", 0)],
        ("ppic", 1): [lowongan("X", 0)],
    }

    siapkan._streaming_halaman()

    assert siapkan.bot.dilamar == ["X"]


def test_lokasi_tidak_dikenal_pakai_alias(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", False)
    monkeypatch.setattr(config, "locations", ["Jababeka"])

    diminta = []

    def cari(keyword, page=1, location=""):
        diminta.append(location)
        if location.lower() == "jababeka":
            return []
        return [lowongan("Z", 0)]

    monkeypatch.setattr(siapkan.bot, "search_jobs", cari)

    siapkan._streaming_halaman()

    assert "Cikarang" in diminta
    assert siapkan.bot.dilamar == ["Z"]


def test_lokasi_kosong_dilewati_setelah_tiga_kata_kunci(siapkan, monkeypatch):
    monkeypatch.setattr(config, "collect_before_apply", False)
    monkeypatch.setattr(config, "locations", ["Jababeka"])
    monkeypatch.setattr(config, "keywords", ["satu", "dua", "tiga", "empat"])
    monkeypatch.setattr(config, "max_pages", 2)

    diminta = []

    def cari(keyword, page=1, location=""):
        diminta.append(keyword)
        return []

    monkeypatch.setattr(siapkan.bot, "search_jobs", cari)

    siapkan._streaming_halaman()

    # Alias ikut dicoba, jadi tiap kata kunci bisa 2 permintaan; setelah 3
    # kata kunci gagal, lokasi dihentikan (kata kunci keempat tidak dicari).
    assert "empat" not in diminta
