"""Kontrol formulir non-`input` (ARIA) dan verifikasi hasil isian.

Temuan audit: formulir modern tidak selalu memakai `<input>`. Opsi bisa berupa
`div role="radio"`, `div role="checkbox"`, atau combobox kustom
(`[role='combobox']`). Kode lama hanya membaca `input[type='radio']`, sehingga
pertanyaan seperti itu tidak terlihat sama sekali — bukan gagal dijawab,
tetapi tidak pernah dicoba.

Yang diuji: deteksi peran, interaksi sesuai jenis kontrol, dan VERIFIKASI
status setelah diklik (properti asli atau `aria-checked`).
"""

import pytest
from selenium.common.exceptions import NoSuchElementException

import auto_apply
import jawaban
from config import config
from database import Database


@pytest.fixture
def basis(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "aria.db"))
    monkeypatch.setattr(jawaban, "db", db)
    monkeypatch.setattr(config, "ingat_jawaban", True)
    return db


@pytest.fixture(autouse=True)
def _tanpa_jeda(monkeypatch):
    monkeypatch.setattr(auto_apply.time, "sleep", lambda *_: None)


class Elemen:
    """Elemen tiruan dengan tag, atribut ARIA, dan status terpilih."""

    def __init__(
        self,
        tag="div",
        teks="",
        attrs=None,
        terpilih=False,
        parent=None,
        on_click=None,
        terlihat=True,
        aktif=True,
    ):
        self.tag_name = tag
        self.text = teks
        self._attrs = dict(attrs or {})
        self._selected = terpilih
        self.parent = parent
        self._on_click = on_click
        self._terlihat = terlihat
        self._aktif = aktif

    def get_attribute(self, nama):
        return self._attrs.get(nama)

    def is_selected(self):
        return self._selected

    def is_displayed(self):
        return self._terlihat

    def is_enabled(self):
        return self._aktif

    def click(self):
        if self._on_click:
            self._on_click(self)

    def find_elements(self, by, selector):
        return []

    def find_element(self, by, selector):
        if selector == ".." and self.parent is not None:
            return self.parent
        raise NoSuchElementException(selector)


class DriverPalsu:
    def __init__(self, peta=None):
        self.peta = peta or {}
        self.skrip = []

    def find_elements(self, by, selector):
        return list(self.peta.get(selector, []))

    def execute_script(self, *args, **kwargs):
        self.skrip.append(args)
        return None

    def find_element(self, by, selector):
        raise NoSuchElementException(selector)


# ------------------------------------------------------------ deteksi peran ---
@pytest.mark.parametrize(
    "tag, attrs, peran",
    [
        ("input", {"type": "radio"}, "radio"),
        ("input", {"type": "checkbox"}, "checkbox"),
        ("input", {"type": "text"}, "teks"),
        ("textarea", {}, "teks"),
        ("select", {}, "pilihan"),
        ("div", {"role": "radio"}, "radio"),
        ("div", {"role": "menuitemradio"}, "radio"),
        ("div", {"role": "checkbox"}, "checkbox"),
        ("div", {"role": "switch"}, "checkbox"),
        ("div", {"role": "combobox"}, "combobox"),
        ("div", {"aria-haspopup": "listbox"}, "combobox"),
        ("div", {}, ""),
        ("span", {}, ""),
    ],
)
def test_peran_kontrol(tag, attrs, peran):
    assert auto_apply.peran_kontrol(Elemen(tag=tag, attrs=attrs)) == peran


def test_status_terpilih_dibaca_dari_aria():
    assert auto_apply.aria_terpilih(Elemen(attrs={"aria-checked": "true"})) is True
    assert auto_apply.aria_terpilih(Elemen(attrs={"aria-selected": "TRUE"})) is True
    assert auto_apply.aria_terpilih(Elemen(attrs={"aria-checked": "false"})) is False

    # Elemen tanpa properti `is_selected` (div) tetap terverifikasi.
    div = Elemen(attrs={"aria-checked": "true"})
    div.is_selected = None
    assert auto_apply.terpilih_kontrol(div) is True


# ------------------------------------------------- pengelompokan & jawaban ---
def _applier(monkeypatch, peta, pertanyaan):
    applier = auto_apply.AutoApplier(DriverPalsu(peta))
    monkeypatch.setattr(applier, "_visible", lambda *_: True)
    monkeypatch.setattr(applier, "_enabled", lambda *_: True)
    monkeypatch.setattr(applier, "_label_terlihat", lambda *_: True)
    monkeypatch.setattr(applier, "_pertanyaan", lambda el, opsi=(): pertanyaan)
    monkeypatch.setattr(
        applier,
        "_label_untuk",
        lambda el: el.text or (el.get_attribute("aria-label") or ""),
    )
    return applier


def test_radio_aria_tanpa_name_dijawab_dari_ingatan(monkeypatch, basis):
    """`div role="radio"` (tanpa name, tanpa input) harus terjawab & terverifikasi."""

    def pilih(el):
        # Meniru React: aria-checked baru berubah setelah klik.
        for lain in opsi:
            lain._attrs["aria-checked"] = "false"
        el._attrs["aria-checked"] = "true"

    opsi = [
        Elemen(teks="Ya", attrs={"role": "radio", "aria-checked": "false"}),
        Elemen(teks="Tidak", attrs={"role": "radio", "aria-checked": "false"}),
    ]
    for el in opsi:
        el._on_click = pilih

    jawaban.ingat("Do you have sales negotiation experience?", "Tidak")

    applier = _applier(
        monkeypatch,
        {"[role='radio']": opsi},
        "Do you have sales negotiation experience?",
    )

    gagal = applier._jawab_radio()

    assert gagal == []
    assert opsi[1]._attrs["aria-checked"] == "true"
    assert opsi[0]._attrs["aria-checked"] == "false"


def test_klik_yang_tidak_mengubah_aria_dilaporkan_gagal(monkeypatch, basis):
    """Verifikasi: klik tanpa perubahan status = VERIFICATION_FAILED."""

    opsi = [
        Elemen(teks="Ya", attrs={"role": "radio", "aria-checked": "false"}),
        Elemen(teks="Tidak", attrs={"role": "radio", "aria-checked": "false"}),
    ]
    jawaban.ingat("Do you have ERP experience?", "Ya")

    applier = _applier(
        monkeypatch, {"[role='radio']": opsi}, "Do you have ERP experience?"
    )

    gagal = applier._jawab_radio()

    assert gagal == ["Do you have ERP experience?"]


def test_checkbox_aria_dicentang_dan_diverifikasi(monkeypatch, basis):
    def centang(el):
        el._attrs["aria-checked"] = "true"

    opsi = [
        Elemen(
            teks="Microsoft Excel",
            attrs={"role": "checkbox", "aria-checked": "false"},
        ),
        Elemen(teks="SAP", attrs={"role": "checkbox", "aria-checked": "false"}),
    ]
    for el in opsi:
        el._on_click = centang

    jawaban.ingat("Software yang kamu kuasai?", "Microsoft Excel")
    monkeypatch.setattr(config, "skill_keywords", [], raising=False)
    monkeypatch.setattr(config, "title_keywords", [], raising=False)

    applier = _applier(
        monkeypatch,
        {"[role='checkbox']": opsi},
        "Software yang kamu kuasai?",
    )

    gagal = applier._jawab_checkbox()

    assert gagal == []
    assert opsi[0]._attrs["aria-checked"] == "true"
    assert opsi[1]._attrs["aria-checked"] == "false"


# --------------------------------------------------------------- combobox ---
def test_combobox_diisi_dari_ingatan_dan_diverifikasi(monkeypatch, basis):
    combobox = Elemen(
        tag="div",
        teks="",
        attrs={"role": "combobox", "aria-expanded": "false"},
    )

    opsi_listbox = [
        Elemen(teks="Bandung", attrs={"role": "option"}, parent=combobox),
        Elemen(teks="Jakarta", attrs={"role": "option"}, parent=combobox),
    ]

    def buka(el):
        el._attrs["aria-expanded"] = "true"

    def pilih(el):
        combobox.text = el.text

    combobox._on_click = buka
    for el in opsi_listbox:
        el._on_click = pilih

    jawaban.ingat("Kota domisili?", "Bandung")

    applier = _applier(
        monkeypatch,
        {"[role='combobox']": [combobox], "[role='option']": opsi_listbox},
        "Kota domisili?",
    )

    gagal = applier._jawab_combobox()

    assert gagal == []
    assert combobox.text == "Bandung"


def test_combobox_tanpa_jawaban_tidak_menebak(monkeypatch, basis):
    combobox = Elemen(tag="div", attrs={"role": "combobox"})
    opsi_listbox = [Elemen(teks="Bandung", attrs={"role": "option"})]

    applier = _applier(
        monkeypatch,
        {"[role='combobox']": [combobox], "[role='option']": opsi_listbox},
        "Kota domisili?",
    )

    gagal = applier._jawab_combobox()

    # Tidak menebak: tidak dilaporkan gagal, tetapi tidak ada yang dipilih.
    assert gagal == []
    assert combobox.text == ""


def test_combobox_jawaban_tidak_ada_di_daftar_dilaporkan(monkeypatch, basis):
    combobox = Elemen(tag="div", attrs={"role": "combobox"})
    opsi_listbox = [
        Elemen(teks="Jakarta", attrs={"role": "option"}),
        Elemen(teks="Surabaya", attrs={"role": "option"}),
    ]
    jawaban.ingat("Kota domisili?", "Bandung")

    applier = _applier(
        monkeypatch,
        {"[role='combobox']": [combobox], "[role='option']": opsi_listbox},
        "Kota domisili?",
    )

    gagal = applier._jawab_combobox()

    assert gagal == ["Kota domisili?"]
    assert combobox.text == ""
