"""Profil bersama dilepas sebelum situs berikutnya dijalankan.

Latar belakang (log 2026-11-13): `run --situs semua` menjalankan JobStreet lalu
Glints dalam satu sesi. Chrome JobStreet tidak benar-benar tertutup, profil
`chrome-profile` tetap terkunci, Glints gagal membukanya, turun ke profil
cadangan yang belum login ("Login Glints belum selesai"), lalu Indeed juga
memakai profil baru → dua situs menghasilkan 0 lamaran.
"""

import browser
import lamar_semua
from config import config


def test_profil_kosong_dilewati(monkeypatch):
    monkeypatch.setattr(config, "profile_dir", "")
    # Tidak ada profil → tidak ada yang ditunggu, tidak melempar.
    lamar_semua._lepas_profil_sebelum_situs_berikut()


def test_profil_bebas_tidak_menunggu(monkeypatch, tmp_path):
    profil = tmp_path / "p"
    profil.mkdir()
    monkeypatch.setattr(config, "profile_dir", str(profil))

    dipanggil = []

    def tunggu(*arg, **kwarg):
        dipanggil.append("tunggu")
        return True

    monkeypatch.setattr(browser, "tunggu_profil_bebas", tunggu)

    lamar_semua._lepas_profil_sebelum_situs_berikut()

    assert dipanggil == []


def test_profil_terkunci_ditunggu_lebih_dulu(monkeypatch, tmp_path, capsys):
    profil = tmp_path / "p"
    profil.mkdir()
    (profil / "SingletonLock").write_text("")
    monkeypatch.setattr(config, "profile_dir", str(profil))

    batas = {}

    def tunggu(profil_arg, batas_detik=8.0, jeda=1.0):
        batas["nilai"] = batas_detik
        return True

    monkeypatch.setattr(browser, "tunggu_profil_bebas", tunggu)

    lamar_semua._lepas_profil_sebelum_situs_berikut()

    assert batas["nilai"] == 20.0
    assert "masih memegang profil" in capsys.readouterr().out


def test_profil_masih_terkunci_lalu_chrome_sisa_ditutup(monkeypatch, tmp_path):
    profil = tmp_path / "p"
    profil.mkdir()
    (profil / "SingletonLock").write_text("")
    monkeypatch.setattr(config, "profile_dir", str(profil))

    jejak = []

    def tunggu(*arg, **kwarg):
        jejak.append("tunggu")
        return False

    monkeypatch.setattr(browser, "tunggu_profil_bebas", tunggu)
    monkeypatch.setattr(
        browser,
        "tutup_chrome_bot_tertinggal",
        lambda profil_arg: jejak.append("tutup") or 2,
    )

    lamar_semua._lepas_profil_sebelum_situs_berikut()

    # Tunggu 20 dtk → tutup Chrome sisa → tunggu 10 dtk lagi.
    assert jejak == ["tunggu", "tutup", "tunggu"]
