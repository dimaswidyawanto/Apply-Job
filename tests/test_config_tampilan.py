"""Tabel konfigurasi harus memperlihatkan aturan baru, bukan menyembunyikannya."""

import cli
from config import config


def test_show_config_menampilkan_aturan_baru(capsys, monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", True)
    monkeypatch.setattr(config, "auto_answer_wait", 35)
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "collect_before_apply", True)
    monkeypatch.setattr(config, "rank_by", "relevance")

    cli.show_config()

    keluaran = capsys.readouterr().out

    assert "Wajib ada logo perusahaan" in keluaran
    assert "Aktif" in keluaran
    # Tabel rich membungkus teks per kata, jadi periksa per kata.
    assert "Kumpulkan" in keluaran
    assert "bandingkan" in keluaran
    assert "kecocokan" in keluaran
    assert "tertinggi" in keluaran
    assert "35 detik" in keluaran


def test_show_config_saat_aturan_mati(capsys, monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", False)
    monkeypatch.setattr(config, "auto_answer_wait", 0)
    monkeypatch.setattr(config, "collect_before_apply", False)
    monkeypatch.setattr(config, "rank_by", "newest")

    cli.show_config()

    keluaran = capsys.readouterr().out

    assert "Wajib ada logo perusahaan" in keluaran
    assert "Aktif" in keluaran
    assert "Lamar sambil mencari" in keluaran
    assert "Tidak menunggu (langsung dilewati)" in keluaran


# --------------------------------------------------------------- DB_PATH ---
def test_db_path_kosong_memakai_bawaan():
    """DB_PATH= di .env tidak boleh membuat database sementara (data hilang)."""
    from config import BASE_DIR, Config

    baru = Config(db_path="")

    assert baru.db_path.endswith("jobstreet_auto.db")
    assert baru.db_path.startswith(str(BASE_DIR))


def test_db_path_relatif_dibuat_absolut():
    from config import BASE_DIR, Config

    assert Config(db_path="data/lain.db").db_path == str(
        BASE_DIR / "data" / "lain.db"
    )


def test_db_path_absolut_tidak_diubah(tmp_path):
    from config import Config

    jalur = tmp_path / "x.db"

    assert Config(db_path=str(jalur)).db_path == str(jalur)
