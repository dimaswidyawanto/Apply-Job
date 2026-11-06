"""Peluncur satu klik: JobStreet → Glints → Indeed dalam sekali jalan."""

import lamar_semua
from config import config


def _siapkan(monkeypatch, terpakai=0, batas=50):
    """Ganti semua sisi luar (browser, kuota, Telegram, git) dengan palsu."""
    dicatat = {"situs": [], "laporan": 0, "galat": []}

    monkeypatch.setattr(lamar_semua.kuota, "habis", lambda *a, **k: (
        bool(batas) and terpakai >= batas
    ))
    monkeypatch.setattr(
        lamar_semua.kuota, "pesan_habis", lambda *a, **k: "Kuota harian habis."
    )
    monkeypatch.setattr(
        lamar_semua.kuota, "ringkasan", lambda *a, **k: "Kuota harian: 0 dilamar."
    )

    def jalankan_situs(nama, max_pages, batas_sesi):
        dicatat["situs"].append((nama, max_pages, batas_sesi))
        return {
            "dibaca": 10, "baru": 5, "dilamar": 2, "sudah": 1,
            "perlu_manual": 0, "dilewati": 2, "gagal": 0,
        }

    monkeypatch.setattr(lamar_semua, "_jalankan_situs", jalankan_situs)
    monkeypatch.setattr(
        lamar_semua.notifier, "send_daily_report",
        lambda stats: dicatat.__setitem__("laporan", dicatat["laporan"] + 1),
    )
    monkeypatch.setattr(
        lamar_semua.notifier, "send_error",
        lambda pesan: dicatat["galat"].append(pesan),
    )
    return dicatat


def test_tiga_situs_dijalankan_berurutan(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    hasil = lamar_semua.jalankan(perbarui=False)

    assert [nama for nama, _, _ in dicatat["situs"]] == [
        "jobstreet", "glints", "indeed"
    ]
    assert set(hasil) == {"jobstreet", "glints", "indeed"}
    assert sum(data["dilamar"] for data in hasil.values()) == 6


def test_laporan_harian_hanya_sekali(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    lamar_semua.jalankan(perbarui=False)

    assert dicatat["laporan"] == 1


def test_situs_bisa_dipilih(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    lamar_semua.jalankan(situs="indeed,jobstreet", perbarui=False)

    assert [nama for nama, _, _ in dicatat["situs"]] == ["jobstreet", "indeed"]


def test_nama_situs_tidak_dikenal_diabaikan(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    hasil = lamar_semua.jalankan(situs="kalibrr", perbarui=False)

    assert dicatat["situs"] == []
    assert hasil == {}


def test_situs_terpilih_memakai_setelan_env(monkeypatch):
    monkeypatch.setattr(config, "situs_aktif", "indeed,glints", raising=False)

    assert lamar_semua.situs_terpilih("") == ["glints", "indeed"]


def test_kata_semua_berarti_tiga_situs():
    assert lamar_semua.situs_terpilih("semua") == list(lamar_semua.SITUS_BAKU)


def test_kuota_habis_situs_berikutnya_dilewati(monkeypatch):
    dicatat = _siapkan(monkeypatch, terpakai=50, batas=50)

    hasil = lamar_semua.jalankan(perbarui=False)

    assert dicatat["situs"] == []
    assert hasil == {}
    assert dicatat["laporan"] == 1


def test_satu_situs_gagal_situs_lain_tetap_jalan(monkeypatch):
    dicatat = _siapkan(monkeypatch)

    def rusak(nama, max_pages, batas_sesi):
        dicatat["situs"].append((nama, max_pages, batas_sesi))
        if nama == "glints":
            raise RuntimeError("Cloudflare menolak")
        return {"dilamar": 1}

    monkeypatch.setattr(lamar_semua, "_jalankan_situs", rusak)

    hasil = lamar_semua.jalankan(perbarui=False)

    assert [nama for nama, _, _ in dicatat["situs"]] == [
        "jobstreet", "glints", "indeed"
    ]
    assert "glints" not in hasil
    assert "indeed" in hasil
    assert any("Glints" in pesan for pesan in dicatat["galat"])


def test_perbarui_dilewati_bila_bukan_repo_git(monkeypatch, tmp_path):
    monkeypatch.setattr(lamar_semua, "AKAR", tmp_path)

    berhasil, pesan = lamar_semua.perbarui_kode()

    assert berhasil is False
    assert "repo Git" in pesan


def test_perbarui_tidak_pernah_melempar_galat(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()

    def meledak(*a, **k):
        raise OSError("git tidak ada")

    monkeypatch.setattr(lamar_semua, "AKAR", tmp_path)
    monkeypatch.setattr(lamar_semua, "_git", meledak)

    berhasil, pesan = lamar_semua.perbarui_kode()

    assert berhasil is False
    assert "pembaruan gagal" in pesan
