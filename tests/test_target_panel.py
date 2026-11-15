"""Panel target 50 di akhir sesi.

Pengguna menetapkan target **50 lamaran per situs per siklus 24 jam** dan
ingin setiap kali menjalankan `.bat` hasilnya terlihat jelas: sudah berapa,
kurang berapa, dan APA yang menghalangi bila belum tercapai. Tes ini mengunci
perilaku itu:

* setiap lamaran terkirim mencetak kemajuan `x/50`;
* alasan penolakan dihitung per jenis (bukan hanya total "dilewati");
* akhir sesi menyebut target belum tercapai beserta alasannya;
* target yang sudah tercapai dilaporkan hijau, bukan "belum tercapai";
* `MAX_APPLY_PER_DAY=0` (tanpa batas) tidak mencetak panel target.
"""

from collections import Counter
from types import SimpleNamespace

import pytest
from rich.console import Console

import job_filter as job_filter_module
import main as main_module
from config import config
from database import Database


class BotPalsu:
    def __init__(self, hasil=None):
        self.hasil = hasil or {}

    def search_jobs(self, keyword, page=1, location=""):
        return []

    def apply_job(self, job):
        return self.hasil.get(
            job["job_id"],
            SimpleNamespace(applied=True, status="applied", reason="Terkirim"),
        )


def lowongan(job_id, title="Staff Inventory"):
    return {
        "job_id": str(job_id),
        "title": title,
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "Rp 6.000.000",
        "description": "",
        "url": f"https://id.jobstreet.com/job/{job_id}",
        "date_posted": "Hari ini",
        "age_days": 0,
        "has_logo": True,
    }


@pytest.fixture
def siapkan(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "target-panel.db"))
    monkeypatch.setattr(main_module, "db", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "max_apply_per_day", 50)
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0)
    monkeypatch.setattr(config, "delay_between_apply", 0)
    monkeypatch.setattr(config, "require_company_logo", True)
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", [])

    return database


@pytest.fixture
def teks(monkeypatch):
    """Jalankan fungsi dengan console Rich yang bisa dibaca sebagai teks."""

    def _jalankan(fungsi, *args):
        console = Console(record=True, width=100)
        monkeypatch.setattr(main_module, "console", console)
        fungsi(*args)
        return console.export_text()

    return _jalankan


def test_setiap_lamaran_mencetak_kemajuan_target(siapkan, teks):
    engine = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    engine.bot = BotPalsu()
    engine.session_stats = {
        "found": 0, "new": 0, "applied": 0, "already": 0,
        "manual": 0, "skipped": 0, "errors": 0, "retry": 0,
    }
    engine.manual_jobs = []
    engine.stop_requested = False
    engine.alasan_tolak = {}

    keluaran = teks(engine._lapor_target)

    assert "Target JobStreet:" in keluaran
    assert "0/50" in keluaran


def test_alasan_penolakan_dihitung_per_jenis(siapkan):
    engine = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    engine.alasan_tolak = {}

    engine._catat_alasan("Tanpa logo perusahaan")
    engine._catat_alasan("Tanpa logo perusahaan")
    engine._catat_alasan("Salary terlalu rendah: 2,000,000")

    assert engine.alasan_tolak == {
        "Tanpa logo perusahaan": 2,
        "Salary terlalu rendah: 2,000,000": 1,
    }


def test_alasan_kosong_tetap_tercatat(siapkan):
    engine = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    engine.alasan_tolak = {}

    engine._catat_alasan("   ")

    assert engine.alasan_tolak == {"Tanpa alasan": 1}


def test_panel_menyebut_kurang_dan_alasan(siapkan, teks):
    engine = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    engine.session_stats = {
        "found": 0, "new": 0, "applied": 2, "already": 0,
        "manual": 3, "skipped": 0, "errors": 0, "retry": 0,
    }
    engine.alasan_tolak = Counter({"Tanpa logo perusahaan": 1402})

    keluaran = teks(engine._laporan_target)

    assert "belum tercapai" in keluaran
    assert "kurang 50" in keluaran
    assert "Tanpa logo perusahaan" in keluaran
    assert "1402" in keluaran
    assert "jawaban --isi" in keluaran
    assert "cek-target" in keluaran


def test_panel_target_tercapai_tidak_mengeluh(siapkan, teks):
    database = siapkan

    for nomor in range(1, 51):
        database.add_job(lowongan(nomor))
        database.record_application(str(nomor), "applied", "Terkirim")

    engine = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    engine.session_stats = {
        "found": 0, "new": 0, "applied": 5, "already": 0,
        "manual": 0, "skipped": 0, "errors": 0, "retry": 0,
    }
    engine.alasan_tolak = {}

    keluaran = teks(engine._laporan_target)

    assert "tercapai" in keluaran
    assert "belum tercapai" not in keluaran


def test_tanpa_batas_harian_panel_tidak_dicetak(siapkan, teks, monkeypatch):
    monkeypatch.setattr(config, "max_apply_per_day", 0)

    engine = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    engine.session_stats = {
        "found": 0, "new": 0, "applied": 0, "already": 0,
        "manual": 0, "skipped": 0, "errors": 0, "retry": 0,
    }
    engine.alasan_tolak = {}

    assert teks(engine._laporan_target).strip() == ""
