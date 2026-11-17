"""Jawaban ya/tidak yang sudah tersimpan harus benar-benar terpakai.

Latar belakang (audit #25, sesi JobStreet 17 Nov 2026): 13 lamaran dilewati
karena pertanyaan ya/tidak yang SUDAH punya jawaban tersimpan tetap ditanyakan
— masing-masing membakar 60 detik waktu tunggu (±13 menit per sesi). Contoh
berulang: "do you have sales negotiation experience?" (tersimpan "No"),
"do you have procurement coordination experience?" (tersimpan "Yes"),
"do you have experience using google workspace?".

Tiga sebab yang diuji di sini:
1. Label opsi tidak terbaca (JobStreet kadang hanya mengisi atribut `value`).
2. Status terpilih dibaca seketika setelah klik, padahal React baru
   memperbaruinya beberapa ratus milidetik kemudian.
3. Kalimat pertanyaan diulang dengan susunan/kata berbeda sehingga di bawah
   ambang kemiripan, walau maksudnya sama.
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


# ------------------------------------------------------- sisi ya / tidak ---
@pytest.mark.parametrize(
    "teks, sisi",
    [
        ("Yes", "ya"),
        ("No", "tidak"),
        ("No, I don't have any", "tidak"),
        ("Tidak, saya belum pernah", "tidak"),
        ("Yes, I have", "ya"),
        ("Ya, saya bersedia", "ya"),
        ("No experience", ""),          # jawaban bernilai, bukan ya/tidak
        ("Sudah vaksinasi lengkap", ""),  # bukan ya/tidak
        ("3 years", ""),
        ("", ""),
    ],
)
def test_padanan_ya_tidak(teks, sisi):
    assert jawaban.padanan_ya_tidak(teks) == sisi


# ------------------------------------------------------ jawaban ↔ opsi ----
def test_opsi_yes_no_bahasa_indonesia_dicocokkan():
    assert jawaban.cocok_opsi("No", ["Yes", "No"]) == "No"
    assert jawaban.cocok_opsi("No", ["Ya", "Tidak"]) == "Tidak"
    assert jawaban.cocok_opsi("Yes", ["Tidak", "Ya"]) == "Ya"


def test_opsi_panjang_dengan_kata_penegas():
    assert jawaban.cocok_opsi("Yes", ["Yes, I have", "No, I don't have"]) == (
        "Yes, I have"
    )
    assert jawaban.cocok_opsi("No", ["Yes, I have", "No, I don't have"]) == (
        "No, I don't have"
    )


def test_opsi_ambigu_tidak_ditebak():
    """Dua opsi di sisi "tidak" → jangan menebak."""
    assert jawaban.cocok_opsi("Tidak", ["No", "No, not right now"]) == ""


def test_opsi_tiga_dengan_satu_sisi_tidak_tetap_dijawab():
    assert jawaban.cocok_opsi("Tidak", ["Yes", "No", "Not sure"]) == "No"


def test_angka_tidak_dicocokkan_asal_angka():
    assert jawaban.cocok_opsi("Rp 5 Jt", ["Rp 1 jt", "Rp 3 jt", "Rp 5 jt"]) == (
        "Rp 5 jt"
    )
    assert jawaban.cocok_opsi("Rp 5 Jt", ["Rp 1 jt", "Rp 2 jt"]) == ""


def test_opsi_berskala_dari_ingatan():
    opsi = ["Tidak Berpengalaman", "Dasar", "Menengah", "Ahli"]
    assert jawaban.cocok_opsi("Ahli", opsi) == "Ahli"
    assert jawaban.cocok_opsi("menengah ", opsi) == "Menengah"


def test_pernyataan_panjang_dicocokkan_walau_tanda_baca_berbeda():
    opsi = [
        "Belum pernah vaksinasi COVID-19",
        "Sudah vaksinasi lengkap (2 dosis)",
        "Sudah vaksinasi booster",
    ]
    assert jawaban.cocok_opsi(
        "Sudah vaksinasi lengkap (2 dosis)", opsi
    ) == "Sudah vaksinasi lengkap (2 dosis)"


# ------------------------------------- pertanyaan sama, kalimat berbeda ---
def test_pertanyaan_ya_tidak_disusun_ulang_tetap_terpakai(basis):
    jawaban.ingat("Do you have sales negotiation experience?", "No")

    assert jawaban.cari(
        "Do you have experience in sales negotiation?"
    ) == "No"


def test_pertanyaan_ya_tidak_tanpa_keluarga_khusus(basis):
    """Tanpa kata "pengalaman/gaji/…", kemiripan 0.80 tetap dipakai."""
    jawaban.ingat("Can you work under pressure?", "Yes")

    assert jawaban.cari("Are you able to work under pressure?") == "Yes"


def test_pertanyaan_berbeda_tetap_ditanya(basis):
    jawaban.ingat("Do you have sales negotiation experience?", "No")
    jawaban.ingat("Do you have procurement coordination experience?", "Yes")

    assert jawaban.cari(
        "Do you have procurement coordination experience?"
    ) == "Yes"
    assert jawaban.cari("Do you have ERP implementation experience?") is None


def test_jawaban_bukan_ya_tidak_tidak_dipakai_untuk_pertanyaan_ya_tidak(basis):
    jawaban.ingat("How many years' experience do you have as a Purchasing?", "3 years")

    assert jawaban.cari("Are you able to work under pressure?") is None


# ------------------------------------------------------------- DOM palsu ---
class ElemenPalsu:
    """Radio tiruan; `is_selected` bisa telat seperti komponen React."""

    def __init__(self, label="", nilai="", nama="q1", tunda=0, aktif_setelah_klik=True):
        self.label = label
        self.nilai = nilai
        self.nama = nama
        self.tunda = tunda
        self.sisa_tunda = tunda
        self.aktif_setelah_klik = aktif_setelah_klik
        self.selected = False
        self.diklik = 0

    def get_attribute(self, nama):
        return {"name": self.nama, "value": self.nilai}.get(nama, "")

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def is_selected(self):
        if self.selected:
            return True
        if self.sisa_tunda > 0:
            self.sisa_tunda -= 1
            return False
        return False

    def click(self):
        self.diklik += 1
        if self.aktif_setelah_klik:
            self.selected = True

    def find_elements(self, by, selector):
        return []


@pytest.fixture(autouse=True)
def _tanpa_jeda(monkeypatch):
    monkeypatch.setattr(auto_apply.time, "sleep", lambda *_: None)


def _applier(monkeypatch, elemen, jawaban_pertanyaan="Do you have SAP experience?"):
    applier = auto_apply.AutoApplier(driver=None)
    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: list(elemen) if "radio" in selector else [],
    )
    monkeypatch.setattr(applier, "_visible", lambda *_: True)
    monkeypatch.setattr(applier, "_enabled", lambda *_: True)
    monkeypatch.setattr(applier, "_selected", lambda e: e.selected)
    monkeypatch.setattr(
        applier, "_label_untuk", lambda e: e.label or e.nilai
    )
    monkeypatch.setattr(
        applier, "_pertanyaan", lambda e, opsi=(): jawaban_pertanyaan
    )
    return applier


def test_klik_yang_nyangkut_belakangan_dianggap_berhasil(monkeypatch):
    """React baru menandai radio terpilih sesudah klik (audit #25)."""
    radio = ElemenPalsu("No", tunda=5)
    applier = _applier(monkeypatch, [radio])

    assert applier._pilih_radio(radio) is True
    assert radio.selected is True


def test_opsi_tanpa_label_dibaca_dari_atribut_value():
    applier = auto_apply.AutoApplier(driver=None)

    # Tidak ada label/aria/wadah → value dipakai sebagai teks opsi.
    assert applier._label_untuk(ElemenPalsu("", "No")) == "No"
    assert applier._label_untuk(ElemenPalsu("", "opt_3")) == ""


def test_value_id_internal_tidak_dipakai_sebagai_label():
    applier = auto_apply.AutoApplier(driver=None)

    for nilai in ("option-2", "choice_1", "radio1", "12345"):
        assert applier._label_untuk(ElemenPalsu("", nilai)) == ""


def test_radio_ya_tidak_dijawab_dari_ingatan(monkeypatch, basis):
    """Skenario nyata: "No" tersimpan, opsi hanya "Yes"/"No"."""
    jawaban.ingat("Do you have sales negotiation experience?", "No")

    ya = ElemenPalsu("Yes", nama="q7")
    tidak = ElemenPalsu("No", nama="q7")
    applier = _applier(
        monkeypatch, [ya, tidak],
        jawaban_pertanyaan="Do you have sales negotiation experience?",
    )

    gagal = applier._jawab_radio()

    assert gagal == []
    assert tidak.selected is True
    assert ya.selected is False


def test_radio_gagal_mencatat_alasan_ke_log(monkeypatch, basis, tmp_path):
    """Tanpa jawaban tersimpan, alasan kegagalan harus terlihat di log."""
    catatan = []
    monkeypatch.setattr(
        auto_apply.log_aktivitas,
        "catat",
        lambda pesan, tingkat="info", **kwargs: catatan.append(pesan),
    )

    monkeypatch.setattr(auto_apply, "pilih_jawaban_radio", lambda *_: "")

    ya = ElemenPalsu("Yes", nama="q8")
    tidak = ElemenPalsu("No", nama="q8")
    applier = _applier(
        monkeypatch, [ya, tidak], jawaban_pertanyaan="Do you have ERP experience?"
    )

    gagal = applier._jawab_radio()

    assert gagal == ["Do you have ERP experience?"]
    assert any("Radio tidak terjawab" in item for item in catatan)
