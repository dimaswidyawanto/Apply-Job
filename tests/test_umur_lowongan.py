"""Umur lowongan: parsing tanggal, zona waktu, dan batas MAX_AGE_DAYS.

Aturan (audit #26):

* relatif ("3 hari lalu", "kemarin") dan absolut ("2026-11-15",
  "15 Nov 2026", "Nov 15, 2026") sama-sama dikenali;
* perhitungan memakai WIB (Asia/Jakarta);
* batas bersifat INKLUSIF — umur 7 hari masih diterima saat MAX_AGE_DAYS=7;
* tanggal tidak terbaca = `None` (DATE_UNKNOWN), BUKAN 0, dan hanya ditolak
  bila TOLAK_UMUR_TAK_DIKETAHUI diaktifkan.
"""

import importlib
import zoneinfo
from datetime import UTC, datetime, timedelta, timezone

import pytest

import glints
import indeed
import scraper
import umur
from config import config
from job_filter import JobFilter

# 17 Nov 2026, 17:00 WIB (= 10:00 UTC)
SEKARANG = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


# --------------------------------------------------------------- parsing ---
@pytest.mark.parametrize(
    "teks, harapan",
    [
        ("Hari ini", 0),
        ("Baru saja", 0),
        ("Kemarin", 1),
        ("yesterday", 1),
        ("3 jam lalu", 0),
        ("5 jam yang lalu", 0),
        ("2 hari yang lalu", 2),
        ("3 days ago", 3),
        ("1 minggu lalu", 7),
        ("2 minggu yang lalu", 14),
        ("1 bulan yang lalu", 30),
        ("2 months ago", 60),
        ("1 tahun lalu", 365),
        ("1 year ago", 365),
        ("30+ hari yang lalu", 30),
        ("2026-11-15", 2),
        ("15 Nov 2026", 2),
        ("15 November 2026", 2),
        ("Nov 15, 2026", 2),
        ("15/11/2026", 2),
        ("11/15/2026", 2),
        ("17 Nov 2026", 0),
        ("10 Nov 2026", 7),
        ("tidak ada tanggal", None),
        ("", None),
        ("Tanpa keterangan", None),
    ],
)
def test_umur_dari_teks(teks, harapan):
    assert umur.umur_dari_teks(teks, SEKARANG) == harapan


def test_zona_waktu_wib_dipakai():
    """18:00 UTC = 01:00 WIB tanggal berikutnya."""
    malam = datetime(2026, 11, 17, 18, 0, tzinfo=UTC)

    # Tanggal absolut 17 Nov: di WIB sudah tanggal 18 → umur 1 hari.
    assert umur.umur_dari_teks("2026-11-17", malam) == 1
    assert umur.umur_dari_teks("kemarin", malam) == 1


def test_tanggal_masa_depan_tidak_negatif():
    assert umur.umur_dari_teks("2026-12-31", SEKARANG) == 0


def test_label_umur():
    assert umur.label_umur(0) == "Hari ini"
    assert umur.label_umur(3) == "3 hari lalu"
    assert umur.label_umur(None) == ""


def test_parser_platform_memakai_aturan_yang_sama():
    """JobStreet, Glints, dan Indeed memakai parser bersama."""
    assert scraper.JobStreetBot._parse_listing_age("15 Nov 2026") is not None
    assert scraper.JobStreetBot._parse_listing_age("3 hari yang lalu") == 3
    assert glints.umur_dari_teks("2 minggu lalu") == 14
    assert glints.umur_dari_teks("15 Nov 2026") is not None
    assert indeed.umur_dari_teks is glints.umur_dari_teks


def test_label_jobstreet_lama_tetap_dikenali():
    assert scraper.JobStreetBot._parse_listing_age("Baru") == 0
    assert scraper.JobStreetBot._parse_listing_age("30+ hari yang lalu") == 30


# ----------------------------------------------------------- batas umur ----
def _job(**tambahan):
    data = {
        "job_id": "uji:1",
        "title": "Inventory Staff",
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "",
        "description": "",
        "url": "https://contoh/1",
        "age_days": 0,
    }
    data.update(tambahan)
    return data


@pytest.fixture
def saringan(monkeypatch):
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "min_salary", 0, raising=False)
    monkeypatch.setattr(config, "require_company_logo", False, raising=False)
    monkeypatch.setattr(config, "max_age_days", 7, raising=False)
    monkeypatch.setattr(config, "tolak_umur_tak_diketahui", False, raising=False)
    return JobFilter()


@pytest.mark.parametrize(
    "umur_hari, lolos",
    [(0, True), (1, True), (3, True), (7, True), (8, False)],
)
def test_batas_umur_inklusif(saringan, umur_hari, lolos):
    hasil, alasan = saringan.should_apply(_job(age_days=umur_hari))

    assert hasil is lolos
    if not lolos:
        assert "MAX_AGE_DAYS=7" in alasan


def test_alasan_penolakan_menyebut_angka(saringan):
    hasil, alasan = saringan.should_apply(_job(age_days=10))

    assert hasil is False
    assert "10 hari" in alasan
    assert "7" in alasan


def test_umur_tak_diketahui_diterima_secara_bawaan(saringan):
    assert saringan.should_apply(_job(age_days=None))[0] is True


def test_umur_tak_diketahui_ditolak_bila_diaktifkan(saringan, monkeypatch):
    monkeypatch.setattr(config, "tolak_umur_tak_diketahui", True, raising=False)

    hasil, alasan = saringan.should_apply(_job(age_days=None))

    assert hasil is False
    assert "DATE_UNKNOWN" in alasan


def test_max_age_days_nol_tanpa_batas(saringan, monkeypatch):
    monkeypatch.setattr(config, "max_age_days", 0, raising=False)
    monkeypatch.setattr(config, "tolak_umur_tak_diketahui", True, raising=False)

    assert saringan.should_apply(_job(age_days=999))[0] is True
    assert saringan.should_apply(_job(age_days=None))[0] is True


# ------------------------------------------------- zona WIB tanpa tzdata ---
def test_zona_wib_jatuh_ke_offset_tetap_bila_tzdata_tidak_ada(monkeypatch):
    """Windows tanpa paket `tzdata`: jangan berhenti, pakai +07:00.

    Gejala nyata di mesin pengguna (commit c8af9dc):
      ModuleNotFoundError: No module named 'tzdata'
      zoneinfo._common.ZoneInfoNotFoundError: 'No time zone found with key
      Asia/Jakarta'
    Seluruh perintah (dry-run, run, glints, indeed) mati saat impor.
    """

    def gagal(_kunci):
        raise zoneinfo.ZoneInfoNotFoundError("Asia/Jakarta")

    monkeypatch.setattr(umur, "ZoneInfo", gagal)
    zona = umur.zona_wib()

    assert zona.utcoffset(datetime(2026, 1, 15, 9, 0)) == timedelta(hours=7)
    assert zona.utcoffset(datetime(2026, 7, 15, 9, 0)) == timedelta(hours=7)


def test_cadangan_wib_setara_dengan_asia_jakarta():
    """WIB tanpa DST: offset tetap +07:00 sama sepanjang tahun."""
    asli = zoneinfo.ZoneInfo("Asia/Jakarta")
    cadangan = timezone(timedelta(hours=7), "WIB")

    for bulan in (1, 4, 7, 10, 12):
        saat = datetime(2026, bulan, 15, 12, 0)
        assert (
            saat.replace(tzinfo=asli).utcoffset()
            == saat.replace(tzinfo=cadangan).utcoffset()
            == timedelta(hours=7)
        )


def test_impor_umur_tetap_berhasil_tanpa_tzdata(monkeypatch):
    """Modul harus bisa diimpor walau ZoneInfo melempar (bukan crash saat impor)."""

    def gagal(_kunci):
        raise zoneinfo.ZoneInfoNotFoundError("Asia/Jakarta")

    monkeypatch.setattr(zoneinfo, "ZoneInfo", gagal)
    modul = importlib.reload(umur)

    try:
        assert modul.WIB.utcoffset(datetime(2026, 11, 17, 9, 0)) == timedelta(
            hours=7
        )
        # Perhitungan umur tetap jalan memakai offset cadangan.
        assert modul.umur_dari_teks("3 hari lalu") == 3
        assert modul.batas_umur(8, 7) == (
            "Lowongan terlalu lama (8 hari > MAX_AGE_DAYS=7)"
        )
    finally:
        monkeypatch.undo()
        importlib.reload(umur)
