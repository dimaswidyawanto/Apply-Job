"""Kejar target 50 sampai kuota terisi, dan berhenti saat halaman macet.

Dua kejadian nyata 2026-11-16 yang dikunci di sini:

1. Sesi 00:33 menemukan 220 kandidat tetapi hanya **24 terkirim**: daftar
   dipotong tepat 50, lalu 26 formulir yang belum terjawab membakar 26 slot
   tanpa diganti kandidat berikutnya. Sekarang seluruh kandidat dicoba
   berurutan sampai kuota benar-benar terisi.
2. Sesi 00:46 kehilangan **16 kandidat dalam 74 detik** karena JobStreet
   menampilkan dinding verifikasi Cloudflare ("Just a moment...") dan bot terus
   mencoba di halaman yang sama. Sekarang ada jeda dan batas berhenti.
"""

from types import SimpleNamespace

import pytest

import job_filter as job_filter_module
import main as main_module
from config import config
from database import Database


class BotPalsu:
    """Bot yang hasilnya ditentukan per job_id."""

    def __init__(self, kandidat, gagal=(), manual=(), halaman_macet=()):
        self.kandidat = kandidat
        self.gagal = set(gagal)
        self.manual = set(manual)
        self.halaman_macet = set(halaman_macet)
        self.dilamar = []

    def search_jobs(self, keyword, page=1, location=""):
        return [dict(job) for job in self.kandidat] if page == 1 else []

    def apply_job(self, job):
        job_id = job["job_id"]
        self.dilamar.append(job_id)

        if job_id in self.manual:
            return SimpleNamespace(
                applied=False,
                status="manual_required",
                reason="Formulir meminta isian yang belum bisa dijawab",
            )

        if job_id in self.halaman_macet:
            return SimpleNamespace(
                applied=False,
                status="error",
                reason="Tombol Lamar tidak ditemukan di halaman",
            )

        if job_id in self.gagal:
            return SimpleNamespace(
                applied=False, status="error", reason="Gagal sementara"
            )

        # Seperti bot sungguhan: lamaran tercatat di database (dasar hitungan
        # kuota siklus 24 jam).
        main_module.db.record_application(job_id, "applied", "Terkirim otomatis")

        return SimpleNamespace(
            applied=True, status="applied", reason="Terkirim otomatis"
        )


def lowongan(job_id, judul="Staff Purchasing"):
    return {
        "job_id": str(job_id),
        "title": judul,
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
    database = Database(str(tmp_path / "kejar.db"))
    monkeypatch.setattr(main_module, "db", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "locations", ["Bandung"])
    monkeypatch.setattr(config, "keywords", ["purchasing"])
    monkeypatch.setattr(config, "research_keywords", [])
    monkeypatch.setattr(config, "max_pages", 1)
    monkeypatch.setattr(config, "research_max_pages", 1)
    monkeypatch.setattr(config, "research_max_jobs", 0)
    monkeypatch.setattr(config, "collect_before_apply", True)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "require_company_logo", False)
    monkeypatch.setattr(config, "min_salary", 0)
    monkeypatch.setattr(config, "max_age_days", 0)
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "blocked_companies", [])
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0)
    monkeypatch.setattr(config, "delay_between_apply", 0)
    monkeypatch.setattr(config, "max_apply_per_day", 50)
    monkeypatch.setattr(config, "jeda_macet_detik", 0)
    monkeypatch.setattr(config, "sort_mode", "ListedDate")
    monkeypatch.setattr(config, "prefer_newest", True)
    monkeypatch.setattr(main_module.notifier, "send_apply_success", lambda *_: None)
    monkeypatch.setattr(main_module.notifier, "send_error", lambda *_: None)

    return database


def _mesin(kandidat, **kata):
    mesin = main_module.AutoApplyEngine.__new__(main_module.AutoApplyEngine)
    mesin.bot = BotPalsu(kandidat, **kata)
    mesin.seen_job_ids = set()
    mesin.session_stats = {
        "found": 0, "new": 0, "applied": 0, "already": 0,
        "manual": 0, "skipped": 0, "errors": 0, "retry": 0,
    }
    mesin.manual_jobs = []
    mesin.stop_requested = False
    mesin.alias_lokasi = {}
    mesin.gagal_lokasi = {}
    mesin._logo_diingatkan = False
    mesin.duplikat_dilewati = 0
    mesin.alasan_tolak = {}
    mesin.gagal_halaman_beruntun = 0
    mesin.riset_mulai = 0.0
    mesin.riset_selesai = 0
    mesin.riset_total = 0
    mesin.durasi_riset = 0.0
    mesin.waktu_halaman = 0.0
    mesin.jumlah_halaman = 0
    return mesin


def test_formulir_gagal_tidak_membakar_slot_target(siapkan):
    """25 kandidat pertama gagal di formulir; sisanya tetap dicoba."""
    kandidat = [lowongan(nomor) for nomor in range(1, 61)]
    gagal_manual = {str(nomor) for nomor in range(1, 26)}
    mesin = _mesin(kandidat, manual=gagal_manual)

    mesin._kumpulkan_lalu_lamar()

    # Dulu: hanya 50 kandidat dicoba → 25 terkirim. Sekarang semua dicoba
    # sampai kuota 50 terisi atau kandidat habis.
    assert len(mesin.bot.dilamar) == 60
    assert mesin.session_stats["applied"] == 35
    assert mesin.session_stats["manual"] == 25


def test_berhenti_saat_kuota_terisi_tanpa_mencoba_sisanya(siapkan, monkeypatch):
    monkeypatch.setattr(config, "max_apply_per_day", 3)
    kandidat = [lowongan(nomor) for nomor in range(1, 11)]
    mesin = _mesin(kandidat)

    mesin._kumpulkan_lalu_lamar()

    assert mesin.session_stats["applied"] == 3
    assert len(mesin.bot.dilamar) == 3


def test_halaman_macet_dijeda_lalu_dihentikan(siapkan, monkeypatch):
    monkeypatch.setattr(config, "jeda_macet_detik", 0)
    kandidat = [lowongan(nomor) for nomor in range(1, 21)]
    macet = {str(nomor) for nomor in range(1, 21)}
    mesin = _mesin(kandidat, halaman_macet=macet)

    mesin._kumpulkan_lalu_lamar()

    # Berhenti di ambang, bukan menghabiskan 20 kandidat.
    assert len(mesin.bot.dilamar) == main_module.AutoApplyEngine.BATAS_MACET_BERHENTI
    assert mesin.stop_requested is True


def test_alasan_biasa_tidak_dihitung_macet(siapkan):
    mesin = _mesin([], gagal={str(n) for n in range(1, 10)})

    for _ in range(5):
        berhenti = mesin._periksa_halaman_macet(
            SimpleNamespace(reason="Gagal sementara: timeout")
        )
        assert berhenti is False

    assert mesin.gagal_halaman_beruntun == 0


def test_kegagalan_berhasil_mengulang_penghitung(siapkan):
    mesin = _mesin([])

    hasil_macet = SimpleNamespace(reason="Halaman tidak dikenali")
    hasil_ok = SimpleNamespace(reason="Terkirim otomatis")

    assert mesin._periksa_halaman_macet(hasil_macet) is False
    assert mesin._periksa_halaman_macet(hasil_macet) is False
    assert mesin.gagal_halaman_beruntun == 2

    mesin._periksa_halaman_macet(hasil_ok)
    assert mesin.gagal_halaman_beruntun == 0
