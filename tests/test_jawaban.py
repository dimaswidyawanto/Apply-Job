"""Ingatan jawaban formulir.

Aturan pemakai: isian yang pernah dilakukan pengguna harus diingat dan dipakai
otomatis; bot hanya perlu bantuan untuk pertanyaan yang belum pernah dijawab.

Contoh nyata: formulir skill Glints "Seberapa mahir kamu dengan keahlian
berikut ini?" dengan pilihan Tidak Berpengalaman/Dasar/Menengah/Ahli untuk
keahlian Manajemen Rantai Pasokan, Microsoft Excel, Manajemen Persediaan.
"""

import auto_apply
import jawaban
from config import config


class DatabasePalsu:
    def __init__(self):
        self.baris = {}

    def simpan_jawaban(self, kunci, pertanyaan, jawaban, jenis="", sumber="pengguna"):
        self.baris[kunci] = {
            "kunci": kunci,
            "pertanyaan": pertanyaan,
            "jawaban": jawaban,
            "jenis": jenis,
            "sumber": sumber,
            "dipakai": 0,
        }
        return True

    def cari_jawaban(self, kunci):
        return self.baris.get(kunci)

    def daftar_jawaban(self):
        return list(self.baris.values())

    def hitung_jawaban(self):
        return len(self.baris)

    def tandai_jawaban_dipakai(self, kunci):
        if kunci in self.baris:
            self.baris[kunci]["dipakai"] += 1

    def hapus_jawaban(self, kunci):
        return self.baris.pop(kunci, None) is not None

    def reset_jawaban(self):
        jumlah = len(self.baris)
        self.baris.clear()
        return jumlah


def _siapkan(monkeypatch):
    db = DatabasePalsu()
    monkeypatch.setattr(jawaban, "db", db)
    monkeypatch.setattr(config, "ingat_jawaban", True, raising=False)
    return db


# ------------------------------------------------------------ dasar ----
def test_kunci_pertanyaan_seragam():
    assert (
        jawaban.kunci_pertanyaan("Manajemen Rantai Pasokan")
        == "manajemen rantai pasokan"
    )
    assert (
        jawaban.kunci_pertanyaan("  Microsoft   Excel? ")
        == jawaban.kunci_pertanyaan("microsoft excel")
    )


def test_ingat_dan_cari_persis(monkeypatch):
    _siapkan(monkeypatch)

    assert jawaban.ingat("Manajemen Rantai Pasokan", "Menengah") is True
    assert jawaban.cari("manajemen rantai pasokan") == "Menengah"


def test_cari_mirip_saat_teks_sedikit_berbeda(monkeypatch):
    _siapkan(monkeypatch)
    jawaban.ingat("Microsoft Excel", "Ahli")

    # Spasi/tanda baca berbeda tetap dikenali.
    assert jawaban.cari("  microsoft   excel ") == "Ahli"


def test_cari_tidak_menebak_pertanyaan_berbeda(monkeypatch):
    _siapkan(monkeypatch)
    jawaban.ingat("Manajemen Rantai Pasokan", "Menengah")

    assert jawaban.cari("Manajemen Persediaan") is None


def test_jawaban_diperbarui_bila_berubah(monkeypatch):
    db = _siapkan(monkeypatch)
    jawaban.ingat("Microsoft Excel", "Dasar")
    jawaban.ingat("Microsoft Excel", "Ahli")

    assert jawaban.cari("Microsoft Excel") == "Ahli"
    assert len(db.baris) == 1


def test_lupakan_dan_reset(monkeypatch):
    _siapkan(monkeypatch)
    jawaban.ingat("Microsoft Excel", "Ahli")
    jawaban.ingat("Manajemen Persediaan", "Menengah")

    assert jawaban.lupakan("microsoft excel") is True
    assert jawaban.cari("Microsoft Excel") is None
    assert jawaban.lupakan_semua() == 1
    assert jawaban.jumlah() == 0


def test_ingat_nonaktif_bila_setelan_mati(monkeypatch):
    _siapkan(monkeypatch)
    monkeypatch.setattr(config, "ingat_jawaban", False, raising=False)

    assert jawaban.ingat("Microsoft Excel", "Ahli") is False
    assert jawaban.cari("Microsoft Excel") is None


# ------------------------------------------------- integrasi formulir ----
class ElemenPalsu:
    def __init__(self, label, grup, nama):
        self.label = label
        self.grup = grup
        self.nama = nama
        self.diklik = False
        self.selected = False

    def get_attribute(self, nama):
        return self.nama if nama == "name" else ""


def _applier(monkeypatch, elemen):
    applier = auto_apply.AutoApplier(driver=None)
    monkeypatch.setattr(
        applier, "_find_all", lambda sel: elemen if "radio" in sel else []
    )
    monkeypatch.setattr(applier, "_visible", lambda *_: True)
    monkeypatch.setattr(applier, "_enabled", lambda *_: True)
    monkeypatch.setattr(applier, "_selected", lambda e: e.selected)
    monkeypatch.setattr(applier, "_label_untuk", lambda e: e.label)
    monkeypatch.setattr(applier, "_pertanyaan", lambda e, opsi=(): "Microsoft Excel")
    monkeypatch.setattr(
        auto_apply, "_norm", auto_apply._norm, raising=False
    )

    def klik(e):
        e.selected = True
        e.diklik = True
        return True

    monkeypatch.setattr(applier, "_click", klik)
    return applier


def test_radio_diisi_dari_ingatan_tanpa_bantuan_user(monkeypatch):
    _siapkan(monkeypatch)
    jawaban.ingat("Microsoft Excel", "Ahli")

    opsi = [
        ElemenPalsu("Tidak Berpengalaman", "excel", "skill_excel"),
        ElemenPalsu("Dasar", "excel", "skill_excel"),
        ElemenPalsu("Menengah", "excel", "skill_excel"),
        ElemenPalsu("Ahli", "excel", "skill_excel"),
    ]
    applier = _applier(monkeypatch, opsi)

    gagal = applier._jawab_radio()

    assert gagal == []
    terpilih = [item.label for item in opsi if item.selected]
    assert terpilih == ["Ahli"]


def test_radio_pertanyaan_baru_tetap_ditanyakan(monkeypatch):
    _siapkan(monkeypatch)

    opsi = [
        ElemenPalsu("Dasar", "rantai", "skill_scm"),
        ElemenPalsu("Ahli", "rantai", "skill_scm"),
    ]
    applier = _applier(monkeypatch, opsi)

    gagal = applier._jawab_radio()

    # Tidak ada ingatan → dilaporkan sebagai belum terjawab (user diminta isi).
    assert gagal == ["Microsoft Excel"]
    assert not any(item.selected for item in opsi)


def test_potret_dan_rekam_jawaban_pengguna(monkeypatch):
    db = _siapkan(monkeypatch)

    opsi = [
        ElemenPalsu("Tidak Berpengalaman", "excel", "skill_excel"),
        ElemenPalsu("Menengah", "excel", "skill_excel"),
    ]
    applier = _applier(monkeypatch, opsi)

    sebelum = applier._potret_jawaban()
    assert sebelum == {}

    # Pengguna memilih "Menengah" sendiri di Chrome.
    opsi[1].selected = True
    jumlah = applier._rekam_jawaban_pengguna(sebelum)

    assert jumlah == 1
    assert db.baris["microsoft excel"]["jawaban"] == "Menengah"
    assert jawaban.cari("Microsoft Excel") == "Menengah"


def test_jawaban_tebakan_bot_tidak_ikut_diingat(monkeypatch):
    db = _siapkan(monkeypatch)
    opsi = [
        ElemenPalsu("Dasar", "excel", "skill_excel"),
        ElemenPalsu("Ahli", "excel", "skill_excel"),
    ]
    applier = _applier(monkeypatch, opsi)

    opsi[0].selected = True
    sebelum = applier._potret_jawaban()

    # Tidak ada perubahan setelah menunggu: tidak ada yang dicatat.
    assert applier._rekam_jawaban_pengguna(sebelum) == 0
    assert db.baris == {}


def test_perubahan_jawaban_pengguna_menggantikan_ingatan_lama(monkeypatch):
    """Bot pernah diisi "Dasar"; pengguna mengubahnya ke "Ahli" → diingat."""
    db = _siapkan(monkeypatch)
    jawaban.ingat("Microsoft Excel", "Dasar")

    opsi = [
        ElemenPalsu("Tidak Berpengalaman", "excel", "skill_excel"),
        ElemenPalsu("Dasar", "excel", "skill_excel"),
        ElemenPalsu("Menengah", "excel", "skill_excel"),
        ElemenPalsu("Ahli", "excel", "skill_excel"),
    ]
    applier = _applier(monkeypatch, opsi)

    # Lamaran pertama: bot mengisi dari ingatan → "Dasar".
    sebelum = applier._potret_jawaban()
    applier._jawab_radio()
    assert [item.label for item in opsi if item.selected] == ["Dasar"]

    # Pengguna tidak setuju dan memilih "Ahli" sendiri di Chrome.
    for item in opsi:
        item.selected = False
    opsi[3].selected = True
    assert applier._rekam_jawaban_pengguna(sebelum) == 1
    assert db.baris["microsoft excel"]["jawaban"] == "Ahli"

    # Lamaran berikutnya: langsung "Ahli", tanpa bantuan pengguna.
    for item in opsi:
        item.selected = False
    assert applier._jawab_radio() == []
    assert [item.label for item in opsi if item.selected] == ["Ahli"]


def test_apply_merekam_jawaban_walau_hasil_gagal(monkeypatch):
    """Perubahan jawaban tetap diingat walau lamaran berakhir manual/error."""
    _siapkan(monkeypatch)
    applier = auto_apply.AutoApplier(driver=None)

    class DriverGagal:
        def get(self, url):
            raise RuntimeError("halaman tidak bisa dibuka")

    applier.driver = DriverGagal()
    dipanggil = {"n": 0}
    monkeypatch.setattr(applier, "_potret_jawaban", lambda: {"kunci": ("Q", "A")})
    monkeypatch.setattr(
        applier, "_rekam_jawaban_pengguna",
        lambda sebelum: dipanggil.__setitem__("n", dipanggil["n"] + 1),
    )

    hasil = applier.apply({"url": "https://glints.com/id/opportunities/jobs/x"})

    assert hasil.status == "login_required" or not hasil.applied
    assert dipanggil["n"] == 1


def test_pertanyaan_persetujuan_wajib_dikonfirmasi():
    """Pasal 8.4: persetujuan/hukum tidak boleh dijawab dari ingatan."""
    for pertanyaan in (
        "Saya menyetujui pernyataan ini",
        "Pernyataan di atas benar dan dapat dipertanggungjawabkan",
        "Saya bersedia ditempatkan di luar kota",
        "Bebas narkoba?",
        "I agree to the terms and conditions",
        "Setuju dengan syarat dan ketentuan",
    ):
        assert jawaban.perlu_konfirmasi(pertanyaan), pertanyaan


def test_pertanyaan_biasa_tetap_dijawab_otomatis():
    for pertanyaan in (
        "Nama Lengkap",
        "Full Name",
        "Apakah kamu bersedia bekerja dalam shift?",
        "Berapa gaji yang diharapkan?",
    ):
        assert not jawaban.perlu_konfirmasi(pertanyaan), pertanyaan


def test_cari_tidak_mengembalikan_jawaban_untuk_persetujuan(monkeypatch):
    class DatabaseIsi:
        def cari_jawaban(self, kunci):
            return {
                "jawaban": "Ya",
                "pertanyaan": "Saya menyetujui pernyataan ini",
                "jenis": "radio",
                "dipakai": 1,
            }

    monkeypatch.setattr(jawaban, "db", DatabaseIsi())

    assert jawaban.cari("Saya menyetujui pernyataan ini") is None


# ----------------------------------------------------------------------
# Kasus Glints: formulir skala per keahlian (bukti sesi 2026-11-11)
# ----------------------------------------------------------------------
class ElemenKartu:
    """Kartu satu keahlian; hanya berisi teks nama keahlian."""

    def __init__(self, teks):
        self.text = teks

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        raise NoSuchElementException(selector)


class ElemenSkala(ElemenPalsu):
    """Radio skala yang input aslinya tersembunyi dan tanpa atribut name."""

    def __init__(self, label, kartu):
        super().__init__(label, "", "")
        self.kartu = kartu

    def get_attribute(self, nama):
        return ""

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        if selector == "..":
            return self.kartu
        raise NoSuchElementException(selector)


SKALA = ("Tidak Berpengalaman", "Dasar", "Menengah", "Ahli")


def _applier_skala(monkeypatch, elemen, pertanyaan):
    applier = _applier(monkeypatch, elemen)
    monkeypatch.setattr(applier, "_visible", lambda *_: False)
    monkeypatch.setattr(applier, "_enabled", lambda *_: True)
    monkeypatch.setattr(applier, "_label_terlihat", lambda *_: True)
    monkeypatch.setattr(
        applier, "_pertanyaan", lambda e, opsi=(): pertanyaan
    )
    monkeypatch.setattr(applier, "_picu_perubahan", lambda *_: None)
    return applier


JUDUL_SKALA = "Seberapa mahir kamu dengan keahlian berikut ini?"


def test_jawaban_skala_tersembunyi_tanpa_name_tetap_terekam(monkeypatch):
    """Radio Glints tersembunyi dan tanpa `name` — dulu tidak pernah terekam."""
    db = _siapkan(monkeypatch)

    kartu = ElemenKartu("Microsoft Excel")
    opsi = [ElemenSkala(label, kartu) for label in SKALA]
    applier = _applier_skala(monkeypatch, opsi, JUDUL_SKALA)

    sebelum = applier._potret_jawaban()
    assert sebelum == {}

    # Pengguna menjawab sendiri di Chrome.
    opsi[2].selected = True
    assert applier._rekam_jawaban_pengguna(sebelum) == 1

    assert db.baris
    satu = next(iter(db.baris.values()))
    assert satu["jawaban"] == "Menengah"
    assert "microsoft excel" in satu["kunci"]


def test_dua_keahlian_tidak_saling_menimpa(monkeypatch):
    """Judul sama, keahlian berbeda → dua ingatan terpisah, bukan satu."""
    db = _siapkan(monkeypatch)

    excel = [ElemenSkala(label, ElemenKartu("Microsoft Excel")) for label in SKALA]
    layanan = [
        ElemenSkala(label, ElemenKartu("Pelayanan Pelanggan")) for label in SKALA
    ]
    semua = excel + layanan

    applier = _applier_skala(monkeypatch, semua, JUDUL_SKALA)

    sebelum = applier._potret_jawaban()
    excel[3].selected = True       # Excel → Ahli
    layanan[1].selected = True     # Pelayanan Pelanggan → Dasar

    assert applier._rekam_jawaban_pengguna(sebelum) == 2
    assert len(db.baris) == 2

    nilai = {baris["jawaban"] for baris in db.baris.values()}
    assert nilai == {"Ahli", "Dasar"}

    kunci = " ".join(db.baris)
    assert "microsoft excel" in kunci
    assert "pelayanan pelanggan" in kunci


def test_keahlian_diisi_dari_ingatan_pada_lamaran_berikutnya(monkeypatch):
    _siapkan(monkeypatch)
    jawaban.ingat(f"{JUDUL_SKALA} — Microsoft Excel", "Ahli")
    jawaban.ingat(f"{JUDUL_SKALA} — Pelayanan Pelanggan", "Dasar")

    excel = [ElemenSkala(label, ElemenKartu("Microsoft Excel")) for label in SKALA]
    layanan = [
        ElemenSkala(label, ElemenKartu("Pelayanan Pelanggan")) for label in SKALA
    ]

    applier = _applier_skala(monkeypatch, excel + layanan, JUDUL_SKALA)
    gagal = applier._jawab_radio()

    assert gagal == []
    assert [item.label for item in excel if item.selected] == ["Ahli"]
    assert [item.label for item in layanan if item.selected] == ["Dasar"]


def test_kotak_centang_diisi_dari_ingatan(monkeypatch):
    """Jawaban centang yang pernah diberikan dipakai ulang, bukan ditebak."""
    _siapkan(monkeypatch)
    jawaban.ingat("Keahlian yang kamu kuasai", "Excel; SAP")

    opsi = [
        ElemenPalsu("Excel", "keahlian", "keahlian[]"),
        ElemenPalsu("SAP", "keahlian", "keahlian[]"),
        ElemenPalsu("AutoCAD", "keahlian", "keahlian[]"),
    ]
    applier = _applier(monkeypatch, opsi)
    monkeypatch.setattr(
        applier, "_find_all", lambda sel: opsi if "checkbox" in sel else []
    )
    monkeypatch.setattr(
        applier, "_pertanyaan", lambda e, opsi=(): "Keahlian yang kamu kuasai"
    )
    monkeypatch.setattr(applier, "_picu_perubahan", lambda *_: None)

    gagal = applier._jawab_checkbox()

    assert gagal == []
    assert [item.label for item in opsi if item.selected] == ["Excel", "SAP"]
