"""Uji pemilihan lowongan Glints (dipakai `glints cari` & `glints uji`)."""

import pytest

import glints
import job_filter as job_filter_module
from config import config
from database import Database


@pytest.fixture(autouse=True)
def saringan(tmp_path, monkeypatch):
    """Database kosong + lokasi tetap, supaya hasil deterministik."""
    monkeypatch.setattr(
        job_filter_module, "db", Database(str(tmp_path / "pilih.db"))
    )
    monkeypatch.setattr(config, "locations", ["Bandung", "Bekasi", "Tangerang"])
    monkeypatch.setattr(config, "blocked_companies", ["royal abadi", "ifa"])
    monkeypatch.setattr(config, "blacklist_companies", [])
    monkeypatch.setattr(config, "min_salary", 0)
    monkeypatch.setattr(config, "strict_location", False)
    monkeypatch.setattr(config, "require_keyword_match", True)
    monkeypatch.setattr(
        config, "title_keywords", ["inventory", "gudang", "warehouse", "ppic"]
    )


def _job(**ubah):
    job = {
        "job_id": "glints:11111111-2222-3333-4444-555555555555",
        "title": "Staff Gudang",
        "company": "PT Contoh Nusantara",
        "location": "Bekasi, Jawa Barat",
        "salary": "Rp 5-6jt",
        "description": "Mengelola stok gudang.",
        "url": (
            "https://glints.com/id/opportunities/jobs/staff-gudang/"
            "11111111-2222-3333-4444-555555555555"
        ),
        "khusus_aplikasi": False,
        "sudah_dilamar": False,
    }
    job.update(ubah)
    return job


def test_lowongan_layak_tidak_punya_alasan():
    assert glints.alasan_tidak_layak(_job()) == ""


@pytest.mark.parametrize(
    "ubah, potongan",
    [
        ({"sudah_dilamar": True}, "sudah pernah"),
        ({"title": "Sales Executive"}, "judul"),
        ({"company": "PT IFA Indonesia"}, "blacklist"),
    ],
)
def test_alasan_tidak_layak(ubah, potongan):
    alasan = glints.alasan_tidak_layak(_job(**ubah))

    assert alasan, ubah
    assert potongan in alasan.lower()


@pytest.mark.parametrize(
    "ubah",
    [
        {"khusus_aplikasi": True},          # ditangani sebagai "perlu manual"
        {"salary": "Rp 2-3jt"},             # gaji tidak lagi jadi syarat Glints
        {"location": "Surabaya, Jawa Timur"},
    ],
)
def test_tidak_ada_syarat_tambahan_khusus_glints(ubah):
    """Aturan Glints identik dengan JobStreet — tanpa kriteria tambahan."""
    assert glints.alasan_tidak_layak(_job(**ubah)) == ""


def test_lokasi_ketat_mengikuti_setelan_jobstreet(monkeypatch):
    """Bila STRICT_LOCATION aktif, Glints memakai aturan yang sama."""
    monkeypatch.setattr(config, "strict_location", True)

    alasan = glints.alasan_tidak_layak(_job(location="Surabaya, Jawa Timur"))

    assert "okasi" in alasan


def test_pilih_kandidat_menjaga_urutan_dan_batas():
    lowongan = [
        _job(title="Sales Executive"),        # judul tidak sesuai -> dibuang
        _job(title="Staff Gudang A"),
        _job(title="Staff Gudang B"),
        _job(title="Staff Gudang C"),
    ]

    hasil = glints.pilih_kandidat(lowongan, batas=2)

    assert [job["title"] for job in hasil] == ["Staff Gudang A", "Staff Gudang B"]


def test_pilih_kandidat_semuanya():
    lowongan = [_job(salary="Rp 1jt"), _job(title="Sales")]

    assert len(glints.pilih_kandidat(lowongan, semuanya=True)) == 2


def test_kumpulkan_lowongan_tanpa_duplikat():
    kelas = type("BotPalsu", (), {})
    bot = kelas()

    satu = {"job_id": "glints:aaa", "title": "A", "url": "u"}
    dua = {"job_id": "glints:bbb", "title": "B", "url": "u"}

    def cari(keyword, halaman=0, location=""):
        return [satu, dua] if keyword == "x" else [satu]

    bot.cari = cari

    hasil = glints.kumpulkan_lowongan(bot, ["x", "y"], 1)

    assert [job["job_id"] for job in hasil] == ["glints:aaa", "glints:bbb"]


@pytest.mark.parametrize(
    "url, potongan",
    [
        ("", "URL belum diisi"),
        ("<URL lowongan yang tombol Lamar-nya membuka formulir>", "URL belum diisi"),
        ("https://id.jobstreet.com/job/1", "bukan alamat Glints"),
        (
            "https://glints.com/id/opportunities/jobs/explore?keyword=warehouse",
            "belum berisi kode lowongan",
        ),
    ],
)
def test_pesan_url_salah(url, potongan):
    assert potongan in glints.pesan_url_salah(url)


def test_uji_glints_menolak_url_placeholder():
    hasil = glints.uji_glints("<URL lowongan>")

    assert hasil.applied is False
    assert "URL" in hasil.reason
