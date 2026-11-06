"""Diagnosa kecepatan (master prompt pasal 13)."""

import time
from pathlib import Path

import performa
from database import Database


def test_ukur_mengembalikan_milidetik():
    def kerja():
        time.sleep(0.01)

    nilai = performa.ukur(kerja, 2)

    assert 8 <= nilai <= 200


def test_catatan_menandai_lambat():
    cepat = performa._catatan("Baca statistik database", 5)
    lambat = performa._catatan("Baca statistik database", 500)
    lewat = performa._catatan("Dashboard lokal", -1)

    assert cepat["status"] == "ok"
    assert lambat["status"] == "lambat"
    assert lewat["status"] == "lewat"
    assert "saran" in cepat


def test_jaringan_ke_host_tidak_ada_mengembalikan_minus_satu():
    assert performa.ukur_jaringan("host.tidak.ada.invalid", batas=1) == -1.0


def test_ukur_dashboard_saat_tidak_berjalan():
    assert performa.ukur_dashboard(port=1, batas=1) == -1.0


def test_jumlah_dan_ukuran_database(tmp_path):
    jalur = tmp_path / "data.db"
    Database(str(jalur)).add_job({
        "job_id": "js-1", "title": "Inventory", "company": "PT A",
        "url": "https://id.jobstreet.com/job/1",
    })

    assert performa.jumlah_baris(str(jalur)) == 1
    assert performa.ukuran_database(str(jalur)) > 0
    assert performa.jumlah_baris(str(tmp_path / "tidak-ada.db")) == 0


def test_jumlah_baris_database_rusak_tidak_error(tmp_path):
    jalur = tmp_path / "rusak.db"
    jalur.write_text("bukan database", encoding="utf-8")

    assert performa.jumlah_baris(str(jalur)) == 0


def test_tulis_berkas_membersihkan_berkas_uji(tmp_path):
    hasil = performa._ukur_tulis(tmp_path)

    assert hasil >= 0
    assert list(Path(tmp_path).glob(".uji-tulis.tmp")) == []


def test_kumpulkan_memuat_bagian_penting(monkeypatch, tmp_path):
    monkeypatch.setattr(performa, "ukur_jaringan", lambda host, **kw: 10.0)
    monkeypatch.setattr(performa, "ukur_dashboard", lambda *a, **kw: 5.0)

    bagian = [b["bagian"] for b in performa.kumpulkan(folder_uji=tmp_path)]

    assert "Baca statistik database" in bagian
    assert "Tulis berkas 1 MB" in bagian
    assert any("Jaringan ke" in b for b in bagian)


def test_saran_umum_selalu_memberi_saran():
    saran = performa.saran_umum()

    assert any("Defender" in s for s in saran)
