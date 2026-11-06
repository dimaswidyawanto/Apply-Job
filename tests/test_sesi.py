"""Ringkasan sesi tersimpan di database (tidak hilang saat program ditutup).

Aturan pemakai: evaluasi berkala harus memakai angka nyata — berapa lowongan
ditemukan, berapa duplikat, berapa lamaran terkirim — bukan perkiraan.
"""

import dashboard
import laporan
from database import db


def test_sesi_disimpan_dan_dibaca():
    db.catat_sesi(
        situs="jobstreet",
        ditemukan=90,
        baru=70,
        duplikat=20,
        dilamar=10,
        gagal=2,
        diulang=3,
        durasi=120.5,
    )

    sesi = db.sesi_terakhir(1)

    assert len(sesi) == 1
    assert sesi[0]["situs"] == "jobstreet"
    assert sesi[0]["ditemukan"] == 90
    assert sesi[0]["dilamar"] == 10
    assert sesi[0]["diulang"] == 3
    assert sesi[0]["durasi"] == 120.5


def test_sesi_terbaru_di_urutan_pertama():
    db.catat_sesi(situs="jobstreet", ditemukan=1)
    db.catat_sesi(situs="glints", ditemukan=2)

    assert db.sesi_terakhir(2)[0]["situs"] == "glints"


def test_statistik_sesi_menghitung_rasio_duplikat():
    db.catat_sesi(situs="jobstreet", ditemukan=80, duplikat=20, diulang=1)
    db.catat_sesi(situs="glints", ditemukan=80, duplikat=20, diulang=2)

    stat = db.statistik_sesi()

    assert stat["jumlah"] == 2
    assert stat["ditemukan"] == 160
    assert stat["duplikat"] == 40
    assert stat["diulang"] == 3
    assert stat["rasio_duplikat"] == 20.0


def test_statistik_sesi_kosong_aman():
    stat = db.statistik_sesi()

    assert stat["jumlah"] == 0
    assert stat["rasio_duplikat"] == 0.0


def test_laporan_memuat_sesi_terakhir():
    db.catat_sesi(situs="jobstreet", ditemukan=50, dilamar=5)
    data = laporan.ringkasan()

    assert data["sesi_terakhir"]
    assert data["statistik_sesi"]["jumlah"] == 1
    assert "Sesi terakhir" in laporan.teks_markdown(data)
    assert "Rasio duplikat" in laporan.teks_markdown(data)


def test_dashboard_menampilkan_sesi():
    db.catat_sesi(situs="indeed", ditemukan=10, dilamar=1)
    data = dashboard.status()

    assert data["sesi_terakhir"][0]["situs"] == "indeed"


def test_saran_muncul_bila_duplikat_tinggi():
    data = {
        "tingkat_berhasil": 100,
        "statistik_sesi": {"rasio_duplikat": 45.0},
    }

    assert any("duplikat" in teks.lower() for teks in laporan.saran(data))
