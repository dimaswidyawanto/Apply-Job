"""Rapikan jawaban yang bertentangan dalam satu kelompok pertanyaan.

Latar belakang (ingatan jawaban sesi 12 Nov 2026, 124 baris): pertanyaan
pengalaman purchasing dijawab "Less than 1 year", "1 year", "2 tahun", dan
"3 years" di lowongan berbeda. Setelah pencocokan berdasarkan maksud, bot bisa
memilih salah satunya secara berubah-ubah. `konflik()` menampilkan
pertentangannya, `tetapkan()` menyamakannya setelah pengguna memilih satu
nilai resmi.

Semua nilai di bawah adalah contoh dari ingatan pengguna; tes ini tidak
memutuskan nilai resmi apa pun.
"""

import pytest

import config as config_modul
import jawaban
from config import config
from database import Database

Q_STAFF = "How many years' experience do you have as a Purchasing Staff?"
Q_ROLE = "How many years' experience do you have in a Purchasing Role?"
Q_SPEC = "How many years' experience do you have as a Purchasing Specialist?"
Q_ID = "Berapa tahun pengalaman kerjamu di bidang pengadaan?"
Q_TANYA = "How many years of experience do you have in a purchasing role?"
Q_GUDANG = "How many years' experience do you have as a Warehouse Helper?"


@pytest.fixture
def basis(tmp_path, monkeypatch):
    basis = Database(str(tmp_path / "konflik.db"))
    monkeypatch.setattr(jawaban, "db", basis)
    monkeypatch.setattr(config, "ingat_jawaban", True)
    return basis


def _isi(basis, baris):
    for pertanyaan, nilai, dipakai in baris:
        kunci = jawaban.kunci_pertanyaan(pertanyaan)
        basis.simpan_jawaban(kunci, pertanyaan, nilai, "", "uji")
        for _ in range(dipakai):
            basis.tandai_jawaban_dipakai(kunci)


# --------------------------------------------------------------- subjek utama ---
def test_subjek_utama_membuang_kata_jabatan():
    assert jawaban.subjek_utama(Q_SPEC) == "purchasing"
    assert jawaban.subjek_utama(Q_GUDANG) == "warehouse"
    # Subjek Indonesia dinormalkan ke istilah Inggris oleh `subjek()`.
    assert (
        jawaban.subjek_utama("Berapa tahun pengalaman di bidang gudang?") == "warehouse"
    )


def test_subjek_utama_tetap_kosong_untuk_pertanyaan_gaji():
    assert jawaban.subjek_utama("What's your expected monthly basic salary?") == (
        "what s expected monthly basic salary"
    )


# --------------------------------------------------------------------- konflik ---
def test_konflik_mengelompokkan_semua_tingkat_jabatan(basis):
    _isi(
        basis,
        [
            (Q_STAFF, "Less than 1 year", 2),
            (Q_ROLE, "1 year", 1),
            (Q_SPEC, "3 years", 2),
            (Q_ID, "2 tahun", 0),
        ],
    )

    hasil = jawaban.konflik()

    assert len(hasil) == 1
    kelompok = hasil[0]
    assert kelompok["keluarga"] == "pengalaman"
    assert kelompok["subjek"] == "purchasing"
    assert kelompok["jumlah"] == 4
    # "Less than 1 year" dan "1 year" TIDAK boleh dianggap nilai yang sama.
    assert set(kelompok["nilai"]) == {
        "Less than 1 year",
        "1 year",
        "3 years",
        "2 tahun",
    }


def test_konflik_menggabungkan_gaji_dari_dua_bahasa(basis):
    _isi(
        basis,
        [
            ("What's your expected monthly basic salary?", "Rp 5 million", 1),
            ("Berapa gaji bulanan yang kamu inginkan?", "Rp 5 Jt", 0),
            ("Berapa gaji bulanan yang diharapkan?", "Rp 7 Jt", 0),
        ],
    )

    hasil = jawaban.konflik()

    assert len(hasil) == 1
    assert hasil[0]["keluarga"] == "gaji"
    assert hasil[0]["subjek"] == ""
    # "Rp 5 million" dan "Rp 5 Jt" sama nilainya → satu nilai, bukan konflik.
    # Label yang tersimpan = yang lebih dulu ditemukan, jadi dibandingkan maknanya.
    nilai = list(hasil[0]["nilai"])
    assert len(nilai) == 2
    assert any(jawaban.sama_nilai(n, "Rp 5 million") for n in nilai)
    assert any(jawaban.sama_nilai(n, "Rp 7 Jt") for n in nilai)
    assert not jawaban.sama_nilai(nilai[0], nilai[1])


def test_konflik_kosong_bila_semua_sepakat(basis):
    _isi(basis, [(Q_STAFF, "3 years", 1), (Q_SPEC, "3 years", 1)])

    assert jawaban.konflik() == []


def test_konflik_mengabaikan_jenis_tak_dikenal(basis):
    _isi(basis, [("Warna favorit?", "biru", 0), ("Warna kesukaan?", "hijau", 0)])

    assert jawaban.konflik() == []


def test_konflik_menerima_daftar_langsung_tanpa_database():
    baris = [
        {
            "kunci": "a",
            "pertanyaan": Q_STAFF,
            "jawaban": "1 year",
            "dipakai": 1,
        },
        {
            "kunci": "b",
            "pertanyaan": "Berapa tahun pengalaman di bidang purchasing?",
            "jawaban": "3 years",
            "dipakai": 4,
        },
    ]

    hasil = jawaban.konflik(baris)

    assert len(hasil) == 1
    assert jawaban._nilai_terbanyak(hasil[0]["nilai"]) == "3 years"


# -------------------------------------------------------------- nilai terbanyak ---
def test_nilai_terbanyak_memilih_yang_paling_sering_dipakai():
    nilai = {
        "1 year": {"jumlah": 3, "dipakai": 1},
        "3 years": {"jumlah": 1, "dipakai": 7},
    }

    assert jawaban._nilai_terbanyak(nilai) == "3 years"


def test_nilai_terbanyak_jumlah_lalu_abjad_saat_seri():
    nilai = {
        "b": {"jumlah": 2, "dipakai": 0},
        "a": {"jumlah": 2, "dipakai": 0},
        "c": {"jumlah": 1, "dipakai": 0},
    }

    assert jawaban._nilai_terbanyak(nilai) == "a"


# ------------------------------------------------------------------- tetapkan ---
def test_tetapkan_menyamakan_satu_kelompok(basis):
    _isi(
        basis,
        [(Q_STAFF, "1 year", 1), (Q_SPEC, "3 years", 1), (Q_ID, "2 tahun", 0)],
    )

    # Satu baris sudah bernilai "3 years" → tidak ikut dihitung sebagai diubah.
    assert jawaban.tetapkan("purchasing", "3 years") == 2
    assert jawaban.konflik() == []

    nilai = {baris["jawaban"] for baris in basis.daftar_jawaban()}
    assert nilai == {"3 years"}


def test_tetapkan_tidak_menyentuh_jenis_lain(basis):
    _isi(
        basis,
        [
            (Q_STAFF, "1 year", 1),
            (Q_SPEC, "2 years", 1),
            ("Which industry are you experienced in purchasing?", "Manufaktur", 0),
        ],
    )

    assert jawaban.tetapkan("purchasing", "3 years") == 2
    nilai = {baris["jawaban"] for baris in basis.daftar_jawaban()}
    assert "Manufaktur" in nilai
    assert "3 years" in nilai


def test_tetapkan_bisa_menyentuh_pertanyaan_gaji(basis):
    _isi(
        basis,
        [
            ("What's your expected monthly basic salary?", "Rp 5 million", 1),
            ("Berapa gaji bulanan yang diharapkan?", "Rp 7 Jt", 0),
        ],
    )

    assert jawaban.tetapkan("gaji", "Rp 6 Jt") == 2
    nilai = {baris["jawaban"] for baris in basis.daftar_jawaban()}
    assert nilai == {"Rp 6 Jt"}


def test_tetapkan_tanpa_sasaran_mengembalikan_nol(basis):
    _isi(basis, [(Q_STAFF, "1 year", 0)])

    assert jawaban.tetapkan("akuntansi", "3 years") == 0
    assert jawaban.tetapkan("purchasing", "   ") == 0


def test_tetapkan_tidak_menulis_ulang_nilai_yang_sama(basis):
    _isi(basis, [(Q_STAFF, "3 years", 1)])

    assert jawaban.tetapkan("purchasing", "3 years") == 0


# --------------------------------------------------- pencocokan jadi ajek ---
def test_pencocokan_maksud_ajek_saat_nilai_seri(basis):
    """Dua nilai dengan skor sama tidak boleh berganti-ganti antar-panggilan."""
    _isi(basis, [(Q_STAFF, "Less than 1 year", 0), (Q_SPEC, "1 year", 0)])

    hasil = {jawaban.cari(Q_TANYA) for _ in range(8)}

    assert len(hasil) == 1
    assert None not in hasil


def test_pencocokan_memakai_nilai_yang_sering_dipakai(basis):
    _isi(basis, [(Q_STAFF, "Refuse to answer", 0), (Q_SPEC, "3 years", 5)])

    assert jawaban.cari(Q_TANYA) == "3 years"


def test_sama_nilai_tidak_menyamakan_angka_berbeda():
    assert jawaban.sama_nilai("Rp 5 Jt", "Rp 5 million")
    assert jawaban.sama_nilai("2 tahun", "2 years")
    assert not jawaban.sama_nilai("2 tahun", "3 years")
    assert not jawaban.sama_nilai("1 year", "Less than 1 year")


def test_config_modul_tetap_utuh():
    """Penjaga sederhana: modul config tidak ikut berubah karena tes ini."""
    assert config_modul.config is config


# ------------------------------------------------------------------ perintah CLI ---
def test_perintah_tetapkan_lewat_cli(basis, capsys):
    import cli

    _isi(basis, [(Q_STAFF, "1 year", 0), (Q_SPEC, "3 years", 0)])

    cli._tetapkan_jawaban(jawaban, "purchasing=3 years")

    keluaran = capsys.readouterr().out
    assert "disamakan" in keluaran
    assert {baris["jawaban"] for baris in basis.daftar_jawaban()} == {"3 years"}


def test_perintah_tetapkan_format_salah(basis, capsys):
    import cli

    cli._tetapkan_jawaban(jawaban, "purchasing")

    assert "Format" in capsys.readouterr().out


def test_perintah_tetapkan_subjek_tak_dikenal(basis, capsys):
    import cli

    cli._tetapkan_jawaban(jawaban, "akuntansi=3 years")

    assert "Tidak ada jawaban yang cocok" in capsys.readouterr().out


def test_perintah_rapikan_melaporkan_konflik(basis, capsys):
    import cli

    _isi(basis, [(Q_STAFF, "1 year", 0), (Q_SPEC, "3 years", 2)])

    cli._tampilkan_konflik(jawaban)

    keluaran = capsys.readouterr().out
    assert "bertentangan" in keluaran
    assert "3 years" in keluaran


def test_perintah_rapikan_saat_tidak_ada_konflik(basis, capsys):
    import cli

    cli._tampilkan_konflik(jawaban)

    assert "Tidak ada jawaban yang bertentangan" in capsys.readouterr().out
