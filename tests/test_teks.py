"""Normalisasi teks bersama (audit E-12)."""

import jawaban
import scraper
import teks


def test_bersihkan_membuang_karakter_tak_terlihat():
    kotor = "\u2060Submit\u200b application\ufeff"
    assert teks.bersihkan(kotor) == "Submit application"


def test_nbsp_menjadi_spasi_bukan_hilang():
    assert teks.bersihkan("years\u00a0experience") == "years experience"


def test_bersihkan_merapikan_spasi_dan_none():
    assert teks.bersihkan("  a   b\n\tc ") == "a b c"
    assert teks.bersihkan(None) == ""


def test_kunci_nama_hanya_huruf_dan_angka():
    assert teks.kunci_nama("PT. Sumber Makmur, Tbk") == "ptsumbermakmurtbk"
    assert teks.kunci_nama("Sumber\u00a0Makmur ") == "sumbermakmur"
    assert teks.kunci_nama(None) == ""


def test_jawaban_memakai_fungsi_yang_sama():
    assert jawaban.bersihkan_teks is teks.bersihkan
    assert jawaban.TAK_TERLIHAT is teks.TAK_TERLIHAT


def test_scraper_memakai_kunci_nama_yang_sama():
    for contoh in ("PT ABC", "abc", "A.B.C.", None, "  "):
        assert scraper._norm_teks(contoh) == teks.kunci_nama(contoh)


def test_logo_tetap_mengenali_nama_perusahaan():
    """Perilaku lama `logo_perusahaan` tidak boleh berubah (E-12)."""
    assert scraper.logo_perusahaan(
        alt="Logo PT Sumber Makmur", perusahaan="PT Sumber Makmur"
    )
    assert scraper.logo_perusahaan(
        alt="Sumber Makmur", src="https://x/logo.png", perusahaan="PT Sumber Makmur"
    )
    assert not scraper.logo_perusahaan(
        alt="ikon", src="https://x/icon.png", perusahaan="PT Sumber Makmur"
    )
