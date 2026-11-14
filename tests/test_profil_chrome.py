"""Profil Chrome antar-situs: tunggu sampai Chrome sebelumnya melepas profil.

Latar belakang (log 12 Nov 2026): setelah JobStreet, Glints gagal membuka
profil yang sama ("Chrome instance exited") lalu turun ke profil baru yang
belum login, sehingga sesi Glints berakhir tanpa satu lamaran pun.
"""

from pathlib import Path

import browser


def _profil(tmp_path) -> Path:
    folder = tmp_path / "chrome-profile"
    folder.mkdir()
    return folder


def test_profil_tanpa_kunci_tidak_terkunci(tmp_path):
    assert browser.profil_terkunci(_profil(tmp_path)) is False


def test_profil_dengan_berkas_kunci_terkunci(tmp_path):
    profil = _profil(tmp_path)
    (profil / "SingletonLock").write_text("")

    assert browser.profil_terkunci(profil) is True


def test_profil_belum_ada_dianggap_bebas(tmp_path):
    assert browser.profil_terkunci(tmp_path / "belum-ada") is False


def test_tunggu_profil_bebas_langsung_true(tmp_path):
    assert browser.tunggu_profil_bebas(_profil(tmp_path), batas_detik=0.2) is True


def test_tunggu_profil_bebas_habis_waktu(tmp_path):
    profil = _profil(tmp_path)
    (profil / "lockfile").write_text("")

    assert (
        browser.tunggu_profil_bebas(profil, batas_detik=0.2, jeda=0.05) is False
    )


def test_kunci_dibersihkan_membuat_profil_bebas(tmp_path):
    profil = _profil(tmp_path)
    (profil / "SingletonLock").write_text("")
    (profil / "DevToolsActivePort").write_text("")

    dihapus = browser.bersihkan_kunci_profil(profil)

    assert sorted(dihapus) == ["DevToolsActivePort", "SingletonLock"]
    assert browser.profil_terkunci(profil) is False


# ------------------------------------------ Chrome sisa sesi sebelumnya ---
def test_pid_profil_kosong_di_luar_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(browser.sys, "platform", "linux")

    assert browser._pid_chrome_pakai_profil(_profil(tmp_path)) == []


def test_pid_profil_membaca_keluaran_powershell(monkeypatch, tmp_path):
    class Hasil:
        stdout = "1234\n\n 5678 \nbukan-angka\n"
        returncode = 0

    dipanggil = {}

    def palsu(perintah, **kwargs):
        dipanggil["perintah"] = perintah
        return Hasil()

    monkeypatch.setattr(browser.sys, "platform", "win32")
    monkeypatch.setattr(browser.subprocess, "run", palsu)

    profil = _profil(tmp_path)
    assert browser._pid_chrome_pakai_profil(profil) == [1234, 5678]
    # Hanya chrome.exe yang memakai folder profil bot yang dicari.
    assert "chrome.exe" in dipanggil["perintah"][-1]
    assert str(profil) in dipanggil["perintah"][-1]


def test_tutup_chrome_bot_tertinggal_menutup_semua_pid(monkeypatch, tmp_path):
    dipanggil = []

    class Hasil:
        def __init__(self, kode=0):
            self.returncode = kode

    def palsu(perintah, **kwargs):
        dipanggil.append(perintah)
        return Hasil(0 if perintah[0] == "taskkill" else 0)

    monkeypatch.setattr(
        browser, "_pid_chrome_pakai_profil", lambda profil: [11, 22]
    )
    monkeypatch.setattr(browser.subprocess, "run", palsu)

    assert browser.tutup_chrome_bot_tertinggal(_profil(tmp_path)) == 2
    assert dipanggil == [["taskkill", "/PID", "11", "/F"],
                         ["taskkill", "/PID", "22", "/F"]]


def test_tutup_chrome_bot_tertinggal_tidak_melempar_saat_gagal(
    monkeypatch, tmp_path
):
    def meledak(*args, **kwargs):
        raise OSError("taskkill tidak ada")

    monkeypatch.setattr(
        browser, "_pid_chrome_pakai_profil", lambda profil: [99]
    )
    monkeypatch.setattr(browser.subprocess, "run", meledak)

    assert browser.tutup_chrome_bot_tertinggal(_profil(tmp_path)) == 0


def test_buka_chrome_membersihkan_profil_terkunci_lewat_chrome_sisa(
    monkeypatch, tmp_path, capsys
):
    """Profil terkunci, Chrome sisa ditutup, lalu profil dipakai lagi."""
    profil = tmp_path / "chrome-profile"
    profil.mkdir()
    kunci = profil / "SingletonLock"
    kunci.write_text("")

    def tutup(kunci_path):
        kunci.unlink(missing_ok=True)

    monkeypatch.setattr(
        browser, "_pid_chrome_pakai_profil", lambda p: [4242]
    )

    def palsu(perintah, **kwargs):
        class Hasil:
            returncode = 0
            stdout = ""

        assert perintah[0] == "taskkill"
        tutup(kunci)
        return Hasil()

    monkeypatch.setattr(browser.subprocess, "run", palsu)
    monkeypatch.setattr(browser.config, "chrome_debug_port", 0)
    monkeypatch.setattr(browser, "tunggu_profil_bebas",
                        lambda p, batas_detik=8.0, jeda=1.0: False)
    monkeypatch.setattr(browser, "sembunyikan_otomasi", lambda d: d)
    monkeypatch.setattr(browser, "_buka", lambda opsi: "driver-profil")

    hasil = browser.buka_chrome(
        profile_dir=str(profil), use_profile=True, headless=False
    )

    assert hasil == "driver-profil"
    assert "sisa sesi sebelumnya ditutup" in capsys.readouterr().out
    assert not kunci.exists()
