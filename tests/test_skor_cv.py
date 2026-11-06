"""Skor kecocokan berbobot + pembacaan CV (master prompt pasal 6.3 & 7)."""

import zipfile

import pytest

import cv
import skor_cv
from config import config

CV_TEKS = (
    "Curriculum Vitae\n"
    "Pengalaman: 4 tahun sebagai Inventory Control di gudang.\n"
    "Pendidikan: S1 Manajemen.\n"
    "Keterampilan: SAP, Excel, WMS, stock opname.\n"
    "Bidang: inventory, supply chain, ppic.\n"
)


@pytest.fixture
def cv_docx(tmp_path):
    berkas = tmp_path / "cv.docx"
    xml = f"<w:document><w:body><w:p><w:t>{CV_TEKS}</w:t></w:p></w:body></w:document>"
    with zipfile.ZipFile(berkas, "w") as arsip:
        arsip.writestr("word/document.xml", xml)
    return berkas


@pytest.fixture
def cv_txt(tmp_path):
    berkas = tmp_path / "cv.txt"
    berkas.write_text(CV_TEKS, encoding="utf-8")
    return berkas


def _job(**ubah):
    job = {
        "title": "Inventory Control Staff",
        "company": "PT Contoh",
        "location": "Bandung",
        "salary": "Rp 6jt",
        "description": (
            "Mengelola stok gudang, stock opname bulanan, SAP, "
            "minimal 2 tahun pengalaman, S1."
        ),
        "has_logo": True,
    }
    job.update(ubah)
    return job


# ------------------------------------------------------------- baca CV ----
def test_baca_txt(cv_txt):
    teks = cv.baca_berkas(cv_txt)
    assert "Inventory Control" in teks


def test_baca_docx_tanpa_pustaka_tambahan(cv_docx):
    teks = cv.baca_berkas(cv_docx)
    assert "Inventory Control" in teks
    assert "<" not in teks


def test_format_tidak_didukung(tmp_path):
    berkas = tmp_path / "cv.rtf"
    berkas.write_text("apa saja", encoding="utf-8")

    with pytest.raises(cv.CvTidakTerbaca):
        cv.baca_berkas(berkas)


def test_berkas_tidak_ada(tmp_path):
    with pytest.raises(cv.CvTidakTerbaca):
        cv.baca_berkas(tmp_path / "tidak-ada.docx")


def test_cv_path_kosong():
    with pytest.raises(cv.CvTidakTerbaca):
        cv.baca_berkas("")


# -------------------------------------------------------------- profil ----
def test_profil_dari_teks_membaca_angka_faktual(cv_txt):
    profil = cv.profil_cv(cv_txt)

    assert profil["pengalaman_tahun"] == 4
    assert profil["pendidikan"] == "s1"
    assert "inventory" in profil["bidang"]
    assert "ppic" in profil["bidang"]
    assert any("sap" in k for k in profil["keterampilan"])


def test_pengalaman_tidak_disebut_jadi_none():
    assert cv.pengalaman_tahun("Tanpa angka pengalaman di sini") is None


# ---------------------------------------------------------------- skor ----
def test_skor_none_bila_cv_belum_ada(monkeypatch):
    monkeypatch.setattr(config, "cv_path", "", raising=False)
    skor_cv.lupakan()

    assert skor_cv.aktif() is False
    assert skor_cv.hitung(_job()) is None


def test_skor_berbobot_0_sampai_100(cv_txt, monkeypatch):
    monkeypatch.setattr(config, "cv_path", str(cv_txt), raising=False)
    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    skor_cv.lupakan()

    hasil = skor_cv.hitung(_job())

    assert 0 <= hasil["skor"] <= 100
    assert set(hasil["rincian"]) == {
        "pengalaman", "keterampilan", "tanggung_jawab",
        "pendidikan", "jabatan", "lokasi",
    }
    # Bobot tidak boleh melebihi porsinya.
    assert hasil["rincian"]["pengalaman"] <= 30
    assert hasil["rincian"]["keterampilan"] <= 25
    assert hasil["rincian"]["tanggung_jawab"] <= 20
    assert hasil["rincian"]["pendidikan"] <= 10
    assert hasil["rincian"]["jabatan"] <= 10
    assert hasil["rincian"]["lokasi"] <= 5


def test_lowongan_cocok_lebih_tinggi_dari_yang_tidak(cv_txt, monkeypatch):
    monkeypatch.setattr(config, "cv_path", str(cv_txt), raising=False)
    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    skor_cv.lupakan()

    cocok = skor_cv.hitung(_job())
    tidak = skor_cv.hitung(
        _job(
            title="Sales Executive",
            location="Surabaya",
            description="Menjual produk, target bulanan, komunikasi.",
        )
    )

    assert cocok["skor"] > tidak["skor"]
    assert cocok["kategori"] in ("Sangat sesuai", "Sesuai", "Cukup sesuai")


def test_kategori_ambang_90_80_70():
    assert skor_cv.kategori(95) == "Sangat sesuai"
    assert skor_cv.kategori(85) == "Sesuai"
    assert skor_cv.kategori(72) == "Cukup sesuai"
    assert skor_cv.kategori(60) == "Tidak diprioritaskan"


def test_terapkan_menempel_ke_lowongan(cv_txt, monkeypatch):
    monkeypatch.setattr(config, "cv_path", str(cv_txt), raising=False)
    skor_cv.lupakan()

    job = _job()
    hasil = skor_cv.terapkan(job)

    assert hasil is not None
    assert job["_skor_cv"] == hasil["skor"]
    assert job["_kategori_skor"] == hasil["kategori"]


def test_saring_minimal_membuang_skor_rendah(cv_txt, monkeypatch):
    monkeypatch.setattr(config, "cv_path", str(cv_txt), raising=False)
    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    monkeypatch.setattr(config, "min_skor_cv", 80, raising=False)
    skor_cv.lupakan()

    bagus = _job()
    buruk = _job(title="Sales Executive", location="Surabaya",
                 description="Menjual produk.")
    lolos, dibuang = skor_cv.saring_minimal([bagus, buruk])

    assert bagus in lolos
    assert buruk in dibuang


def test_saring_minimal_tanpa_cv_semua_lolos(monkeypatch):
    monkeypatch.setattr(config, "cv_path", "", raising=False)
    monkeypatch.setattr(config, "min_skor_cv", 90, raising=False)
    skor_cv.lupakan()

    daftar = [_job(), _job(title="Sales")]
    lolos, dibuang = skor_cv.saring_minimal(daftar)

    assert lolos == daftar
    assert dibuang == []
