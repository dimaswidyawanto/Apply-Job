"""Cocokkan jawaban lama berdasarkan MAKSUD pertanyaan (bukan kalimat persis).

Latar belakang (log sesi 12 Nov 2026): 26 lamaran dilewati karena pertanyaan
"berapa tahun pengalaman" ditanyakan dengan kalimat berbeda dari yang sudah
pernah dijawab, dan pertanyaan gaji memakai pilihan "Rp 5 jt" sementara
ingatan menyimpan "Rp 5 Jt"/"Rp 5 million".
"""

import pytest

import auto_apply
import jawaban
from config import config
from database import Database


@pytest.fixture
def basis(tmp_path, monkeypatch):
    basis = Database(str(tmp_path / "jawaban.db"))
    monkeypatch.setattr(jawaban, "db", basis)
    monkeypatch.setattr(config, "ingat_jawaban", True)
    return basis


# ------------------------------------------------------------------ maksud ---
def test_keluarga_dan_subjek_pertanyaan_pengalaman():
    assert jawaban.maksud(
        "How many years' experience do you have as a Purchasing Specialist?"
    ) == ("pengalaman", "purchasing specialist")
    assert jawaban.maksud(
        "How many years of experience do you have in a Purchasing role?"
    ) == ("pengalaman", "purchasing")
    assert jawaban.maksud(
        "Berapa tahun pengalaman kerjamu di bidang pengadaan?"
    ) == ("pengalaman", "purchasing")


def test_keluarga_pertanyaan_lain():
    assert jawaban.keluarga("What's your expected monthly basic salary?") == "gaji"
    assert jawaban.keluarga("Berapa gaji bulanan yang kamu inginkan?") == "gaji"
    assert jawaban.keluarga("Kualifikasi mana yang kamu miliki?") == "pendidikan"
    assert jawaban.keluarga("Which cuisine types do you have experience with?") == (
        "pengalaman"
    )
    assert jawaban.keluarga("Nama lengkap") == ""


# ------------------------------------------------------ pemakaian ulang ------
def test_jawaban_lama_dipakai_untuk_kalimat_berbeda(basis):
    jawaban.ingat(
        "How many years' experience do you have as a Purchasing Specialist?",
        "1 year",
    )

    hasil = jawaban.cari(
        "How many years of experience do you have in a Purchasing role?"
    )

    assert hasil == "1 year"


def test_pertanyaan_beda_jenis_tidak_dipaksa_cocok(basis):
    jawaban.ingat("Berapa gaji bulanan yang kamu inginkan?", "Rp 5 Jt")

    # Pertanyaan masakan bukan pertanyaan gaji/pengalaman: harus tetap kosong.
    assert jawaban.cari("Which cuisine types do you have experience with?") is None


def test_pertanyaan_persetujuan_tetap_tidak_diisi_otomatis(basis):
    pertanyaan = "Saya setuju dengan pernyataan ini"
    jawaban.ingat(pertanyaan, "Ya")

    assert jawaban.cari(pertanyaan) is None


# ------------------------------------------------------------ angka/nilai ----
def test_angka_gaji_dinormalkan():
    assert jawaban.angka_dari_teks("Rp 5 Jt") == (5_000_000, "rupiah")
    assert jawaban.angka_dari_teks("Rp 5 million") == (5_000_000, "rupiah")
    assert jawaban.angka_dari_teks("Rp 5.000.000") == (5_000_000, "rupiah")
    assert jawaban.angka_dari_teks("Rp 1.5 jt") == (1_500_000, "rupiah")
    assert jawaban.angka_dari_teks("1 year") == (1, "tahun")


def test_sama_nilai():
    assert jawaban.sama_nilai("Rp 5 Jt", "Rp 5 million")
    assert jawaban.sama_nilai("Rp 5.000.000", "Rp 5 jt")
    assert not jawaban.sama_nilai("Rp 5 jt", "Rp 3 jt")
    assert not jawaban.sama_nilai("1 year", "3 years")
    assert not jawaban.sama_nilai("1 year", "Rp 1 jt")


def test_pilihan_gaji_dicocokkan_berdasarkan_angka():
    asli = jawaban.cari
    jawaban.cari = lambda q: "Rp 5 Jt"
    try:
        pilih = auto_apply.AutoApplier._dari_ingatan

        assert pilih("Gaji?", ["Rp 1 jt", "Rp 3 jt", "Rp 5 jt"]) == ("Rp 5 jt", True)
        assert pilih("Gaji?", ["Rp 1 million", "Rp 5 million"]) == (
            "Rp 5 million",
            True,
        )
        assert pilih("Gaji?", ["Rp 1 jt", "Rp 2 jt"]) == ("", False)
    finally:
        jawaban.cari = asli
