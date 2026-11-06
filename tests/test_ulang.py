"""Auto recovery: kegagalan sementara diulang, kegagalan permanen tidak.

Aturan pemakai: internet putus atau Chrome lambat tidak boleh langsung
membuang lowongan; tapi kesalahan permanen (mis. login habis) tidak boleh
diulang berkali-kali.
"""

import pytest

import antrean
from config import config


@pytest.fixture(autouse=True)
def _jeda_nol(monkeypatch):
    monkeypatch.setattr(config, "maks_ulang", 2)
    monkeypatch.setattr(config, "jeda_ulang", 0)


def test_galat_timeout_dianggap_sementara():
    assert antrean.sementara("Message: Timed out waiting for page load")
    assert antrean.sementara("net::ERR_INTERNET_DISCONNECTED")
    assert antrean.sementara("chrome not reachable")
    assert antrean.sementara("Something has gone wrong")


def test_galat_permanen_tidak_diulang():
    assert not antrean.sementara("login_required")
    assert not antrean.sementara("Elemen tombol Kirim tidak ditemukan")
    assert not antrean.sementara("")


def test_berhasil_pada_percobaan_pertama():
    panggilan = []

    hasil, galat, ulang = antrean.ulang_berbatas(
        lambda: panggilan.append(1) or "selesai", judul="tes"
    )

    assert hasil == "selesai"
    assert galat is None
    assert ulang == 0
    assert len(panggilan) == 1


def test_timeout_diulang_lalu_berhasil():
    panggilan = []

    def fungsi():
        panggilan.append(1)
        if len(panggilan) < 2:
            raise RuntimeError("Timed out waiting for element")
        return "berhasil"

    hasil, galat, ulang = antrean.ulang_berbatas(fungsi, judul="tes")

    assert hasil == "berhasil"
    assert galat is None
    assert ulang == 1
    assert len(panggilan) == 2


def test_berhenti_setelah_batas_ulang():
    panggilan = []

    def fungsi():
        panggilan.append(1)
        raise RuntimeError("connection reset by peer")

    hasil, galat, ulang = antrean.ulang_berbatas(fungsi, judul="tes")

    assert hasil is None
    assert isinstance(galat, RuntimeError)
    assert ulang == config.maks_ulang == 2
    assert len(panggilan) == 3  # percobaan awal + 2 ulangan


def test_galat_permanen_tidak_diulang_sama_sekali():
    panggilan = []

    def fungsi():
        panggilan.append(1)
        raise ValueError("login_required")

    _, galat, ulang = antrean.ulang_berbatas(fungsi)

    assert isinstance(galat, ValueError)
    assert ulang == 0
    assert len(panggilan) == 1


def test_pemeriksa_dipanggil_sebelum_percobaan():
    jejak = []

    hasil, galat, _ = antrean.ulang_berbatas(
        lambda: "ok", pemeriksa=lambda: jejak.append("periksa")
    )

    assert hasil == "ok" and galat is None
    assert jejak == ["periksa"]


def test_maks_ulang_nol_berarti_tanpa_ulang(monkeypatch):
    monkeypatch.setattr(config, "maks_ulang", 0)
    panggilan = []

    def fungsi():
        panggilan.append(1)
        raise RuntimeError("timeout")

    _, galat, ulang = antrean.ulang_berbatas(fungsi)

    assert isinstance(galat, RuntimeError)
    assert ulang == 0
    assert len(panggilan) == 1
