"""Aturan JobStreet yang sama juga berlaku di Glints.

Mencakup: syarat logo perusahaan, pemilihan kandidat paling cocok, dan
pemotongan sesuai sisa kuota harian.
"""

import pytest

import glints as glints_module
import job_filter as job_filter_module
from config import config
from database import Database
from glints import (
    alasan_tidak_layak,
    logo_kartu,
    pilih_teratas,
    rapikan_kartu,
)


@pytest.fixture(autouse=True)
def db_kosong(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "glints_aturan.db"))
    monkeypatch.setattr(job_filter_module, "db", database)
    monkeypatch.setattr(glints_module, "db", database)
    return database


# ----------------------------------------------------------------------
# Logo perusahaan
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "kandidat, perusahaan, harapan",
    [
        # alt berisi nama perusahaan (pola Glints: <img alt="PT X">)
        (
            [{"alt": "PT Sinar Abadi", "src": "https://cdn/x.png", "penanda": ""}],
            "PT Sinar Abadi",
            True,
        ),
        # penanda/class memuat "logo"
        (
            [{"alt": "", "src": "https://cdn/x.png", "penanda": "company-logo"}],
            "",
            True,
        ),
        # url memuat "logo"
        (
            [{"alt": "", "src": "https://cdn/brand/logo-abc.png", "penanda": ""}],
            "",
            True,
        ),
        # ikon/placeholder bukan logo
        (
            [{"alt": "", "src": "https://cdn/icon-search.svg", "penanda": ""}],
            "",
            False,
        ),
        (
            [{"alt": "", "src": "https://cdn/placeholder.png", "penanda": ""}],
            "",
            False,
        ),
        # tidak ada gambar di kartu
        ([], "PT Apa Saja", False),
        (None, "", False),
    ],
)
def test_logo_kartu(kandidat, perusahaan, harapan):
    ada, _ = logo_kartu(kandidat, perusahaan)
    assert ada is harapan


def test_rapikan_kartu_menyimpan_status_logo():
    kartu = {
        "url": "https://glints.com/id/opportunities/jobs/staff-gudang/"
        "aaaaaaaa-1111-2222-3333-444444444444",
        "title": "Staff Gudang",
        "company": "PT Sinar Abadi",
        "location": "Bekasi",
        "salary": "Rp 5-6jt",
        "text": "Staff Gudang PT Sinar Abadi Bekasi Rp 5-6jt",
        "logo": [
            {"alt": "PT Sinar Abadi", "src": "https://cdn/x.png", "penanda": ""}
        ],
    }

    hasil = rapikan_kartu(kartu)

    assert hasil["has_logo"] is True
    assert hasil["logo_src"]

    kartu["logo"] = []
    tanpa_logo = rapikan_kartu(kartu)
    assert tanpa_logo["has_logo"] is False


def test_filter_logo_berlaku_di_glints(monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", True)
    monkeypatch.setattr(config, "locations", ["Bekasi"])
    monkeypatch.setattr(config, "glints_min_salary", 4_500_000)

    dasar = {
        "job_id": "glints:aaaaaaaa-1111-2222-3333-444444444444",
        "title": "Staff Gudang",
        "company": "PT Sinar Abadi",
        "location": "Bekasi",
        "salary": "Rp 5-6jt",
        "description": "",
        "url": "https://glints.com/id/opportunities/jobs/staff-gudang/"
        "aaaaaaaa-1111-2222-3333-444444444444",
        "sudah_dilamar": False,
        "khusus_aplikasi": "",
    }

    # Logo wajib di JobStreet & Glints (master prompt pasal 6.1).
    assert alasan_tidak_layak({**dasar, "has_logo": True}) == ""
    assert alasan_tidak_layak({**dasar, "has_logo": False}) == (
        "Tanpa logo perusahaan"
    )


# ----------------------------------------------------------------------
# Pemilihan kandidat terbaik + kuota
# ----------------------------------------------------------------------
def glints_job(job_id, judul, gaji="Rp 6-7jt", lokasi="Bekasi"):
    return {
        "job_id": f"glints:{job_id}",
        "title": judul,
        "company": "PT Contoh",
        "location": lokasi,
        "salary": gaji,
        "description": "",
        "url": "https://glints.com/id/opportunities/jobs/x/"
        f"{job_id}",
        "age_days": None,
        "has_logo": True,
    }


def test_pilih_teratas_mengutamakan_kecocokan(monkeypatch):
    monkeypatch.setattr(config, "rank_by", "relevance")
    monkeypatch.setattr(config, "keywords", ["inventory", "ppic"])

    kandidat = [
        glints_job("a", "Staff Umum"),
        glints_job("b", "Staff Inventory"),
        glints_job("c", "Inventory Controller"),
    ]

    hasil = pilih_teratas(kandidat)

    assert [job["job_id"] for job in hasil] == [
        "glints:b",
        "glints:c",
        "glints:a",
    ]


def test_pilih_teratas_memotong_sesuai_kuota(monkeypatch):
    monkeypatch.setattr(config, "rank_by", "relevance")
    monkeypatch.setattr(config, "keywords", ["inventory"])

    kandidat = [
        glints_job("a", "Staff Umum"),
        glints_job("b", "Inventory Staff"),
        glints_job("c", "Inventory Admin"),
    ]

    hasil = pilih_teratas(kandidat, batas=2)

    assert len(hasil) == 2
    assert [job["job_id"] for job in hasil] == ["glints:b", "glints:c"]
    assert hasil[0]["_score"] >= hasil[1]["_score"]


def test_pilih_teratas_tanpa_batas(monkeypatch):
    monkeypatch.setattr(config, "keywords", ["inventory"])

    kandidat = [glints_job("a", "Staff Umum"), glints_job("b", "Inventory")]

    assert len(pilih_teratas(kandidat, batas=0)) == 2


def test_pilih_teratas_daftar_kosong():
    assert pilih_teratas([], batas=5) == []


# ----------------------------------------------------------------------
# Sesi penuh Glints: hanya kandidat terbaik yang dilamar, sesuai kuota
# ----------------------------------------------------------------------
class BotPalsu:
    def __init__(self, kartu):
        self.kartu = kartu
        self.dilamar = []
        self.filters = glints_module.JobFilter()

    def init_browser(self):
        return True

    def login(self):
        return True

    def cari(self, keyword, nomor=0):
        return list(self.kartu.get((keyword, nomor), []))

    def lamar(self, job):
        from auto_apply import ApplyResult

        self.dilamar.append(job["job_id"])
        return ApplyResult(True, "applied", "Terkirim otomatis")

    def tutup(self):
        return None


def _siapkan_sesi(monkeypatch, kartu, kuota=0, logo=False):
    bot = BotPalsu(kartu)

    monkeypatch.setattr(glints_module, "GlintsBot", lambda: bot)
    monkeypatch.setattr(glints_module.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        glints_module.notifier, "send_apply_success", lambda *_: None
    )
    monkeypatch.setattr(config, "keywords", ["inventory"])
    monkeypatch.setattr(config, "max_pages", 1)
    # Satu muat per kata kunci; riset tanpa batas diuji di test_riset.py.
    monkeypatch.setattr(config, "research_max_pages", 1)
    monkeypatch.setattr(config, "locations", ["Bekasi"])
    monkeypatch.setattr(config, "glints_min_salary", 0)
    monkeypatch.setattr(config, "max_apply_per_day", kuota)
    monkeypatch.setattr(config, "require_company_logo", logo)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "rank_by", "relevance")
    monkeypatch.setattr(config, "delay_between_apply", 0)

    laporan = glints_module.jalankan_glints()
    return bot, laporan


def test_sesi_glints_memakai_kuota_harian(monkeypatch):
    kartu = {
        ("inventory", 0): [
            glints_job("a", "Staff Umum"),
            glints_job("b", "Inventory Staff"),
            glints_job("c", "Inventory Admin"),
        ]
    }

    bot, laporan = _siapkan_sesi(monkeypatch, kartu, kuota=2)

    # Hanya dua yang paling cocok.
    assert bot.dilamar == ["glints:b", "glints:c"]
    assert laporan["dilamar"] == 2


def test_sesi_glints_menolak_tanpa_logo(monkeypatch):
    tanpa_logo = glints_job("a", "Inventory Staff")
    tanpa_logo["has_logo"] = False
    berlogo = glints_job("b", "Inventory Admin")

    kartu = {("inventory", 0): [tanpa_logo, berlogo]}

    bot, _ = _siapkan_sesi(monkeypatch, kartu, kuota=0, logo=True)

    # Hanya yang berlogo dilamar; kartu tanpa gambar dilewati.
    assert bot.dilamar == ["glints:b"]


def test_sesi_glints_berhenti_bila_kuota_habis(monkeypatch, db_kosong):
    kartu = {("inventory", 0): [glints_job("a", "Inventory Staff")]}

    db_kosong.record_application("lain-1", "applied")
    db_kosong.record_application("lain-2", "applied")

    bot, laporan = _siapkan_sesi(monkeypatch, kartu, kuota=2)

    assert bot.dilamar == []
    assert laporan["dilamar"] == 0


def test_glints_cari_menampilkan_status_logo(monkeypatch, capsys):
    """`glints cari` harus memperlihatkan deteksi logo (untuk verifikasi)."""
    import cli

    kandidat = [glints_job("a", "Inventory Staff"), glints_job("b", "Staff Umum")]
    kandidat[1]["has_logo"] = False

    monkeypatch.setattr(glints_module, "daftar_kandidat", lambda **_: kandidat)
    monkeypatch.setattr(config, "require_company_logo", True)

    cli.cari_glints(max_pages=1, batas=10)

    keluaran = capsys.readouterr().out
    assert "Logo" in keluaran
    assert "tidak" in keluaran
    assert "1" in keluaran and "2 kartu terdeteksi" in keluaran
