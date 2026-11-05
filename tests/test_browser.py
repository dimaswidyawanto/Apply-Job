"""Penanganan Chrome yang gagal dibuka.

Galat nyata di PC pengguna:
`session not created: Chrome failed to start ... DevToolsActivePort file
doesn't exist`. Penyebab umumnya profil Chrome masih terkunci / rusak. Tes ini
memastikan bot mencoba membersihkan kunci, memakai profil sementara, lalu
memberi langkah perbaikan yang jelas.
"""

import pytest

import browser as browser_module
from cli import perbaiki_chrome
from config import config


def test_bersihkan_kunci_profil(tmp_path):
    (tmp_path / "SingletonLock").write_text("x")
    (tmp_path / "DevToolsActivePort").write_text("1")
    (tmp_path / "Preferences").write_text("{}")

    dihapus = browser_module.bersihkan_kunci_profil(tmp_path)

    assert set(dihapus) == {"SingletonLock", "DevToolsActivePort"}
    # Berkas profil asli tidak ikut terhapus.
    assert (tmp_path / "Preferences").exists()


def test_bersihkan_kunci_profil_tidak_ada(tmp_path):
    assert browser_module.bersihkan_kunci_profil(tmp_path / "belum-ada") == []


def test_buka_chrome_membersihkan_kunci_setelah_gagal(monkeypatch, tmp_path):
    profil = tmp_path / "profil"
    profil.mkdir()
    (profil / "SingletonLock").write_text("x")

    dipanggil = []

    def buka_palsu(options):
        dipanggil.append(list(options.arguments))
        if len(dipanggil) == 1:
            raise RuntimeError(
                "session not created: DevToolsActivePort file doesn't exist"
            )
        return "driver-palsu"

    monkeypatch.setattr(browser_module, "_buka", buka_palsu)

    hasil = browser_module.buka_chrome(
        profile_dir=str(profil), use_profile=True, headless=False
    )

    assert hasil == "driver-palsu"
    assert len(dipanggil) == 2
    assert not (profil / "SingletonLock").exists()


def test_buka_chrome_pakai_profil_sementara_bila_profil_terkunci(
    monkeypatch, tmp_path
):
    profil = tmp_path / "profil"
    profil.mkdir()

    dipanggil = []

    def buka_palsu(options):
        argumen = " ".join(options.arguments)
        dipanggil.append(argumen)
        if "user-data-dir" in argumen:
            raise RuntimeError("session not created: Chrome failed to start")
        return "driver-sementara"

    monkeypatch.setattr(browser_module, "_buka", buka_palsu)

    hasil = browser_module.buka_chrome(
        profile_dir=str(profil), use_profile=True, headless=False
    )

    assert hasil == "driver-sementara"
    assert len(dipanggil) == 3
    assert "user-data-dir" not in dipanggil[-1]


def test_buka_chrome_pesan_perbaikan_saat_semua_gagal(monkeypatch, tmp_path):
    def buka_palsu(options):
        raise RuntimeError(
            "session not created: DevToolsActivePort file doesn't exist"
        )

    monkeypatch.setattr(browser_module, "_buka", buka_palsu)

    with pytest.raises(RuntimeError) as info:
        browser_module.buka_chrome(
            profile_dir=str(tmp_path / "profil"),
            use_profile=True,
            headless=False,
        )

    pesan = str(info.value)
    assert "perbaiki-chrome" in pesan
    assert "Task Manager" in pesan


def test_buka_chrome_tanpa_profil(monkeypatch):
    monkeypatch.setattr(browser_module, "_buka", lambda options: "driver")

    assert browser_module.buka_chrome(
        profile_dir="", use_profile=False, headless=False
    ) == "driver"


def test_perbaiki_chrome_memindahkan_profil(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "profile_dir", str(tmp_path / "chrome-profile"))
    profil = tmp_path / "chrome-profile"
    profil.mkdir()
    (profil / "Preferences").write_text("{}")

    perbaiki_chrome()

    assert not profil.exists()
    cadangan = list(tmp_path.glob("chrome-profile-lama-*"))
    assert cadangan
    assert (cadangan[0] / "Preferences").exists()
    assert "profil lama dipindahkan" in capsys.readouterr().out.lower()


def test_perbaiki_chrome_tanpa_profil(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "profile_dir", str(tmp_path / "belum-ada"))

    perbaiki_chrome()

    keluaran = capsys.readouterr().out.lower()
    assert "belum ada" in keluaran
