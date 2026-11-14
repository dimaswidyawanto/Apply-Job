"""Riwayat lamaran dengan alasannya (`jalankan.bat history --alasan`).

Alasan yang dicatat bot adalah satu-satunya cara mengetahui kenapa lamaran
Indeed berakhir "perlu manual" (sesi 12 Nov 2026: 84 perlu manual, 0 terkirim)
tanpa menebak dari kode.
"""

import cli
from database import Database


def _basis(tmp_path, monkeypatch):
    basis = Database(str(tmp_path / "riwayat.db"))
    monkeypatch.setattr(cli, "db", basis)
    monkeypatch.setattr("database.db", basis)
    return basis


def test_riwayat_menyertakan_alasan(tmp_path, monkeypatch):
    basis = _basis(tmp_path, monkeypatch)
    basis.record_application(
        "indeed:abc", "manual_required", "Tombol Lamar tidak ditemukan di halaman"
    )

    baris = basis.get_recent_applications(5, situs="indeed")

    assert baris[0]["notes"] == "Tombol Lamar tidak ditemukan di halaman"


def test_alasan_kosong_tetap_teks_kosong(tmp_path, monkeypatch):
    basis = _basis(tmp_path, monkeypatch)
    basis.record_application("indeed:def", "applied", "")

    baris = basis.get_recent_applications(5, situs="indeed")

    assert baris[0]["notes"] == ""


def test_cli_menampilkan_kolom_alasan(tmp_path, monkeypatch, capsys):
    basis = _basis(tmp_path, monkeypatch)
    basis.record_application(
        "indeed:abc", "manual_required", "Alur lamaran tidak dikenali dalam 12 detik"
    )

    cli.show_applications(5, "indeed", alasan=True)

    keluaran = capsys.readouterr().out
    assert "Alasan" in keluaran
    # Tabel membungkus teks, jadi cukup periksa satu kata yang khas.
    assert "dikenali" in keluaran


def test_cli_tanpa_alasan_tidak_menambah_kolom(tmp_path, monkeypatch, capsys):
    basis = _basis(tmp_path, monkeypatch)
    basis.record_application("indeed:abc", "manual_required", "contoh alasan")

    cli.show_applications(5, "indeed")

    keluaran = capsys.readouterr().out
    assert "contoh alasan" not in keluaran
