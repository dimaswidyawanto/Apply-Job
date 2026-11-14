"""Rotasi log aktivitas (temuan E-6).

Sebelum diperbaiki, `logs/aktivitas.log` hanya dipangkas jumlah barisnya dan
seluruh isi dibaca ulang pada setiap penulisan. Sekarang berkas yang melewati
batas ukuran diganti nama menjadi `aktivitas.log.1` (satu arsip).
"""

import log_aktivitas


def test_log_dirotasi_saat_melewati_batas(tmp_path):
    (tmp_path / "aktivitas.log").write_text("x" * 2048, encoding="utf-8")

    log_aktivitas._rotasi(tmp_path / "aktivitas.log", maks_byte=1024)

    assert (tmp_path / "aktivitas.log.1").exists()
    assert not (tmp_path / "aktivitas.log").exists()


def test_arsip_lama_diganti_bukan_menumpuk(tmp_path):
    (tmp_path / "aktivitas.log").write_text("x" * 2048, encoding="utf-8")
    (tmp_path / "aktivitas.log.1").write_text("arsip lama", encoding="utf-8")

    log_aktivitas._rotasi(tmp_path / "aktivitas.log", maks_byte=1024)

    assert (tmp_path / "aktivitas.log.1").read_text(encoding="utf-8").startswith(
        "xxxx"
    )
    arsip = sorted(
        item.name for item in tmp_path.iterdir()
        if item.name.startswith("aktivitas.log")
    )
    assert arsip == ["aktivitas.log.1"]


def test_log_kecil_tidak_dirotasi(tmp_path):
    (tmp_path / "aktivitas.log").write_text("halo", encoding="utf-8")

    log_aktivitas._rotasi(tmp_path / "aktivitas.log", maks_byte=1024)

    assert (tmp_path / "aktivitas.log").exists()
    assert not (tmp_path / "aktivitas.log.1").exists()


def test_catat_tetap_menulis_setelah_rotasi(tmp_path):
    (tmp_path / "aktivitas.log").write_text("x" * 2048, encoding="utf-8")
    log_aktivitas._rotasi(tmp_path / "aktivitas.log", maks_byte=1024)

    log_aktivitas.catat("lamaran terkirim", "info", folder=tmp_path)

    isi = (tmp_path / "aktivitas.log").read_text(encoding="utf-8")
    assert "lamaran terkirim" in isi
