"""Kuota 50 per situs dalam siklus 24 jam bergulir.

Permintaan pemakai (2026-11-11): batas 50 itu **per 24 jam sejak lamaran
pertama**, bukan per hari kalender. Contoh: mulai 20:30 → slot ke-51 baru
boleh besok 20:30, bukan besok 00:00.
"""

from datetime import UTC, datetime, timedelta

import pytest

import kuota
from database import Database, bentuk_siklus


# ------------------------------------------------------------ logika murni ---
def _jam(hari=11, jam=13, menit=30) -> datetime:
    return datetime(2026, 11, hari, jam, menit, tzinfo=UTC)


def test_siklus_dimulai_lamaran_pertama():
    mulai = _jam()
    hasil = bentuk_siklus([mulai], mulai + timedelta(minutes=5))

    assert hasil["jumlah"] == 1
    assert hasil["mulai_at"] == "2026-11-11 13:30:00"
    assert hasil["berakhir_at"] == "2026-11-12 13:30:00"
    assert hasil["aktif"] is True


def test_belum_24_jam_tetap_siklus_sama():
    mulai = _jam()
    lamaran = [mulai + timedelta(hours=jam) for jam in (0, 3, 8, 23)]
    hasil = bentuk_siklus(lamaran, mulai + timedelta(hours=23, minutes=59))

    assert hasil["jumlah"] == 4
    assert hasil["mulai_at"] == "2026-11-11 13:30:00"


def test_lewat_24_jam_siklus_baru():
    mulai = _jam()
    lewat = mulai + timedelta(hours=25)
    hasil = bentuk_siklus([mulai, mulai + timedelta(hours=2), lewat],
                          lewat + timedelta(minutes=1))

    assert hasil["jumlah"] == 1
    assert hasil["mulai_at"] == lewat.strftime("%Y-%m-%d %H:%M:%S")


def test_bukan_reset_tengah_malam():
    """Lamaran 20:30 tidak boleh mendapat slot baru pukul 00:00."""
    mulai = datetime(2026, 11, 11, 20, 30, tzinfo=UTC)
    tengah_malam = datetime(2026, 11, 12, 0, 1, tzinfo=UTC)

    hasil = bentuk_siklus(
        [mulai + timedelta(hours=jam) for jam in range(5)], tengah_malam
    )

    assert hasil["jumlah"] == 5
    assert hasil["berakhir_at"] == "2026-11-12 20:30:00"


def test_sisa_detik_mengecil():
    mulai = _jam()
    awal = bentuk_siklus([mulai], mulai)
    akhir = bentuk_siklus([mulai], mulai + timedelta(hours=20))

    assert awal["sisa_detik"] == pytest.approx(24 * 3600)
    assert akhir["sisa_detik"] == pytest.approx(4 * 3600)


def test_lima_puluh_lamaran_menghabiskan_slot():
    mulai = _jam()
    lamaran = [mulai + timedelta(minutes=n) for n in range(50)]

    assert bentuk_siklus(lamaran, mulai + timedelta(minutes=50))["jumlah"] == 50
    # Lamaran ke-51 di dalam 24 jam yang sama tetap siklus lama.
    assert (
        bentuk_siklus(lamaran + [mulai + timedelta(hours=1)],
                      mulai + timedelta(hours=2))["jumlah"] == 51
    )


# ------------------------------------------------------- database sungguhan ---
@pytest.fixture
def database(tmp_path):
    return Database(str(tmp_path / "siklus.db"))


def _catat(database, job_id: str, waktu: datetime, status: str = "applied"):
    with database._get_conn() as conn:  # noqa: SLF001 (tes)
        conn.execute(
            "INSERT INTO applications (job_id, status, applied_at) "
            "VALUES (?, ?, ?)",
            (job_id, status, waktu.strftime("%Y-%m-%d %H:%M:%S")),
        )


def test_siklus_dari_database(database):
    mulai = _jam()
    for nomor in range(3):
        _catat(database, f"glints:{nomor}", mulai + timedelta(minutes=nomor))

    data = database.siklus_kuota("glints", sekarang=mulai + timedelta(hours=1))

    assert data["jumlah"] == 3
    assert data["mulai_at"] == mulai.strftime("%Y-%m-%d %H:%M:%S")
    assert data["situs"] == "glints"


def test_siklus_situs_lain_tidak_tercampur(database):
    mulai = _jam()
    for nomor in range(2):
        _catat(database, f"glints:{nomor}", mulai)
    _catat(database, "jobstreet:1", mulai)

    assert database.siklus_kuota("glints", sekarang=mulai)["jumlah"] == 2
    assert database.siklus_kuota("jobstreet", sekarang=mulai)["jumlah"] == 1
    assert database.siklus_kuota("indeed", sekarang=mulai)["jumlah"] == 0


def test_status_gagal_tidak_memakai_kuota(database):
    mulai = _jam()
    _catat(database, "glints:1", mulai, status="failed")
    _catat(database, "glints:2", mulai, status="manual_required")

    assert database.siklus_kuota("glints", sekarang=mulai)["jumlah"] == 0


class ConfigPalsu:
    def __init__(self, batas):
        self.max_apply_per_day = batas


def test_habis_setelah_50_lalu_penuh_lagi_setelah_24_jam(database):
    cfg = ConfigPalsu(50)
    sekarang = datetime.now(UTC)
    mulai = sekarang - timedelta(hours=2)

    for nomor in range(50):
        _catat(database, f"glints:{nomor}", mulai + timedelta(minutes=nomor))

    assert kuota.habis(database, cfg, situs="glints") is True
    assert kuota.sisa(database, cfg, situs="glints") == 0


def test_siklus_kemarin_tidak_menahan_kuota_hari_ini(database):
    cfg = ConfigPalsu(50)
    kemarin = datetime.now(UTC) - timedelta(hours=30)

    for nomor in range(50):
        _catat(database, f"glints:{nomor}", kemarin + timedelta(minutes=nomor))

    # Siklus lama sudah lewat 24 jam; siklus baru mulai pada lamaran berikutnya.
    assert kuota.habis(database, cfg, situs="glints") is False
    assert kuota.sisa(database, cfg, situs="glints") == 50


def test_ringkasan_menyebut_siklus_dan_jam_reset(database):
    cfg = ConfigPalsu(50)
    mulai = datetime.now(UTC) - timedelta(hours=1)
    _catat(database, "glints:1", mulai)

    teks = kuota.ringkasan(database, cfg, situs="glints")

    assert teks.startswith("Kuota Glints:")
    assert "pada siklus ini" in teks
    assert "Siklus 24 jam berakhir" in teks


def test_ringkasan_situs_memuat_jam_reset(database):
    cfg = ConfigPalsu(50)
    _catat(database, "glints:1", datetime.now(UTC) - timedelta(hours=1))

    daftar = {baris["situs"]: baris for baris in kuota.ringkasan_situs(database, cfg)}

    assert daftar["glints"]["terpakai"] == 1
    assert daftar["glints"]["berakhir"] != ""
    assert daftar["jobstreet"]["terpakai"] == 0
    assert daftar["jobstreet"]["berakhir"] == ""
