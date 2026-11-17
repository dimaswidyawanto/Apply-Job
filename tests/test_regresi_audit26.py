"""Regresi audit #26 — matriks keputusan lintas area.

Satu tempat untuk tujuh skenario yang diminta pada audit lanjutan:

1. lowongan baru + cocok tinggi      → APPLY
2. lowongan terlalu lama             → SKIP (alasan umur)
3. judul tidak relevan               → SKIP (alasan judul)
4. sudah pernah dilamar (duplikat)   → SKIP (alasan duplikat)
5. Cloudflare                        → PAUSE / requires_human
6. opsi `div role="radio"`           → DETEKSI → INTERAKSI → VERIFIKASI
7. pertanyaan screening tak diketahui → TIDAK MENEBAK
"""

import pytest

import auto_apply
import blokir
import jawaban
from config import config
from database import Database
from job_filter import JobFilter


def _job(**tambahan):
    data = {
        "job_id": "jobstreet:1001",
        "title": "Inventory Staff",
        "company": "PT Contoh Sejahtera",
        "location": "Bandung",
        "salary": "Rp 6.000.000",
        "description": "Mengelola stok gudang, PPIC, administrasi persediaan.",
        "url": "https://id.jobstreet.com/job/1001",
        "age_days": 1,
    }
    data.update(tambahan)
    return data


@pytest.fixture
def saringan(monkeypatch):
    for nama, nilai in (
        ("require_keyword_match", True),
        ("strict_location", False),
        ("min_salary", 0),
        ("require_company_logo", False),
        ("max_age_days", 7),
        ("tolak_umur_tak_diketahui", False),
        ("title_keywords", ["inventory", "gudang", "ppic", "logistik"]),
        ("exclude_keywords", []),
        ("locations", ["Bandung"]),
    ):
        monkeypatch.setattr(config, nama, nilai, raising=False)
    return JobFilter()


# ---------------------------------------------------------------- matriks ---
def test_matriks_keputusan(saringan):
    kasus = [
        # (nama, job, lolos, kata kunci alasan)
        ("strong match", _job(), True, ""),
        ("medium match", _job(title="PPIC Staff", age_days=5), True, ""),
        (
            "weak match (judul masih relevan)",
            _job(title="Logistik", age_days=7),
            True,
            "",
        ),
        ("wrong title", _job(title="Sales Executive"), False, "Judul"),
        ("too old", _job(age_days=8), False, "MAX_AGE_DAYS=7"),
    ]

    for nama, job, harapan, alasan in kasus:
        lolos, pesan = saringan.should_apply(job)
        assert lolos is harapan, f"{nama}: {pesan}"
        if alasan:
            assert alasan in pesan, f"{nama}: {pesan}"


def test_umur_tak_diketahui_bisa_dijadikan_penolakan(saringan, monkeypatch):
    monkeypatch.setattr(config, "tolak_umur_tak_diketahui", True, raising=False)

    lolos, pesan = saringan.should_apply(_job(age_days=None))

    assert lolos is False
    assert "DATE_UNKNOWN" in pesan


def test_duplikat_dilewati(tmp_path, monkeypatch, saringan):
    basis = Database(str(tmp_path / "regresi.db"))
    monkeypatch.setattr(jawaban, "db", basis)
    import indeed
    import job_filter

    monkeypatch.setattr(job_filter, "db", basis, raising=False)
    monkeypatch.setattr(indeed, "db", basis)

    job = _job(job_id="jobstreet:2002")
    basis.record_application(job["job_id"], "applied", "terkirim")

    assert basis.is_already_applied(job["job_id"]) is True
    assert indeed.alasan_tidak_layak(dict(job)) == "Sudah tercatat dilamar"


def test_cloudflare_menjadi_perlu_manusia():
    assert blokir.kena_blokir("Just a moment...") is True
    assert blokir.STATUS_PERLU_MANUSIA == "requires_human"
    assert not blokir.kena_blokir("Tombol Lamar tidak ditemukan")


# ------------------------------------------------- 6. radio ARIA (ringkas) ---
class Elemen:
    def __init__(self, teks, attrs=None, on_click=None):
        self.tag_name = "div"
        self.text = teks
        self._attrs = dict(attrs or {})
        self._on_click = on_click

    def get_attribute(self, nama):
        return self._attrs.get(nama)

    def is_selected(self):
        return False

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def click(self):
        if self._on_click:
            self._on_click(self)

    def find_elements(self, by, selector):
        return []

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        raise NoSuchElementException(selector)


class Driver:
    def __init__(self, peta):
        self.peta = peta

    def find_elements(self, by, selector):
        return list(self.peta.get(selector, []))

    def execute_script(self, *args, **kwargs):
        return None


def test_sepuluh_skenario_radio_aria_dijawab(monkeypatch, tmp_path):
    basis = Database(str(tmp_path / "aria.db"))
    monkeypatch.setattr(jawaban, "db", basis)
    monkeypatch.setattr(config, "ingat_jawaban", True)
    monkeypatch.setattr(auto_apply.time, "sleep", lambda *_: None)
    monkeypatch.setattr(auto_apply, "pilih_jawaban_radio", lambda *_: "")

    def pilih(el):
        for lain in opsi:
            lain._attrs["aria-checked"] = "false"
        el._attrs["aria-checked"] = "true"

    opsi = [
        Elemen("Ya", {"role": "radio", "aria-checked": "false"}, pilih),
        Elemen("Tidak", {"role": "radio", "aria-checked": "false"}, pilih),
    ]
    jawaban.ingat("Do you have procurement coordination experience?", "Ya")

    applier = auto_apply.AutoApplier(Driver({"[role='radio']": opsi}))
    monkeypatch.setattr(applier, "_visible", lambda *_: True)
    monkeypatch.setattr(applier, "_enabled", lambda *_: True)
    monkeypatch.setattr(applier, "_label_terlihat", lambda *_: True)
    monkeypatch.setattr(applier, "_label_untuk", lambda el: el.text)
    monkeypatch.setattr(
        applier,
        "_pertanyaan",
        lambda el, opsi=(): "Do you have procurement coordination experience?",
    )

    assert applier._jawab_radio() == []
    assert opsi[0]._attrs["aria-checked"] == "true"
    assert opsi[1]._attrs["aria-checked"] == "false"


# ------------------------------------- 7. pertanyaan tak dikenal: jangan tebak ---
def test_pertanyaan_screening_tak_dikenal_tidak_dijawab(monkeypatch, tmp_path):
    basis = Database(str(tmp_path / "tebak.db"))
    monkeypatch.setattr(jawaban, "db", basis)
    monkeypatch.setattr(config, "ingat_jawaban", True)

    assert jawaban.cari("Siapa nama atasan Anda sebelumnya?") is None
    assert (
        jawaban.cocok_opsi(
            "", ["Ya", "Tidak"]
        )
        == ""
    )
