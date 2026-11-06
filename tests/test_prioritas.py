"""Prioritas lokasi × kategori (master prompt pasal 3).

Prioritas hanya mengatur URUTAN lamaran: tidak pernah menolak lowongan, dan
tidak mengalahkan skor kecocokan — ia dipakai saat skornya sama.
"""

import pytest

import job_filter as jf_modul
from config import config
from database import Database
from job_filter import JobFilter


@pytest.fixture
def saring(tmp_path, monkeypatch):
    database = Database(str(tmp_path / "prioritas.db"))
    monkeypatch.setattr(jf_modul, "db", database)
    monkeypatch.setattr(config, "require_keyword_match", False)
    monkeypatch.setattr(config, "require_company_logo", False)
    monkeypatch.setattr(config, "strict_location", False)
    return JobFilter()


def lowongan(job_id, title, location, **ubah):
    job = {
        "job_id": job_id,
        "title": title,
        "company": "PT Contoh",
        "location": location,
        "salary": "Rp 7.000.000",
        "description": "Mengelola stok gudang.",
        "url": f"https://id.jobstreet.com/job/{job_id}",
        "date_posted": "Hari ini",
    }
    job.update(ubah)
    return job


def test_prioritas_lokasi_bawaan_mengikuti_daftar_lokasi(monkeypatch):
    monkeypatch.setattr(config, "locations", ["Bandung", "Jakarta"])
    from config import Config

    baru = Config.__new__(Config)
    baru.locations = ["Jakarta", "Bandung", "Jakarta"]
    baru.location = "Jakarta"
    baru.prioritas_lokasi = []
    baru.prioritas_kategori = []
    baru.title_keywords = []
    baru.keywords = ["inventory"]
    baru.research_keywords = []
    baru.skill_keywords = []
    Config.__post_init__(baru)

    # Urutan LOCATIONS dipakai, duplikat dibuang.
    assert baru.prioritas_lokasi == ["Jakarta", "Bandung"]


def test_prioritas_kategori_dibersihkan(monkeypatch):
    from config import Config

    baru = Config.__new__(Config)
    baru.locations = ["Bandung"]
    baru.location = "Bandung"
    baru.prioritas_lokasi = []
    baru.prioritas_kategori = ["PPIC", "ppic", " Warehouse "]
    baru.title_keywords = ["x"]
    baru.keywords = ["x"]
    baru.research_keywords = []
    baru.skill_keywords = []
    Config.__post_init__(baru)

    assert baru.prioritas_kategori == ["PPIC", "Warehouse"]


def test_peringkat_lokasi_urutan_daftar(saring, monkeypatch):
    monkeypatch.setattr(config, "prioritas_lokasi", ["Bandung", "Cikarang"])
    monkeypatch.setattr(config, "prioritas_kategori", ["inventory", "warehouse"])

    bandung = saring._peringkat_prioritas(lowongan("1", "Inventory Staff", "Bandung"))
    cikarang = saring._peringkat_prioritas(
        lowongan("2", "Warehouse Staff", "Cikarang")
    )
    lain = saring._peringkat_prioritas(lowongan("3", "Staf Gudang", "Medan"))

    assert bandung == (0, 0)
    assert cikarang == (1, 1)
    assert lain == (99, 99)


def test_urutan_memakai_prioritas_saat_skor_sama(saring, monkeypatch):
    monkeypatch.setattr(config, "prioritas_lokasi", ["Bandung", "Jakarta"])
    monkeypatch.setattr(config, "prioritas_kategori", [])

    medan = lowongan("1", "Inventory Staff", "Medan")
    jakarta = lowongan("2", "Inventory Staff", "Jakarta")
    bandung = lowongan("3", "Inventory Staff", "Bandung")

    hasil = saring.rank_jobs([medan, jakarta, bandung])

    # Skor ketiganya sama, jadi prioritas lokasi menentukan.
    assert [j["job_id"] for j in hasil] == ["3", "2", "1"]
    assert [j["_prioritas_lokasi"] for j in hasil] == [0, 1, 99]


def test_prioritas_tidak_menolak_lowongan(saring, monkeypatch):
    monkeypatch.setattr(config, "prioritas_lokasi", ["Bandung"])
    monkeypatch.setattr(config, "prioritas_kategori", ["ppic"])

    boleh, alasan = saring.should_apply(
        lowongan("9", "Inventory Staff", "Medan")
    )

    assert boleh is True, alasan
