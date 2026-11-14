"""Batas lamaran harian: satu aturan untuk JobStreet dan Glints.

Pengguna meminta batas harian Glints **persis sama** dengan JobStreet: satu
hitungan, dipakai bersama, dan pesan yang sama. Tes ini menjaga agar aturan itu
tidak ditulis dua kali dengan hasil berbeda.
"""

import glints as glints_module
import kuota
import main as main_module
from config import config


class DbPalsu:
    def __init__(self, hari_ini=0):
        self.hari_ini = hari_ini

    def get_today_apply_count(self):
        return self.hari_ini


class ConfigPalsu:
    def __init__(self, batas):
        self.max_apply_per_day = batas


def test_kedua_situs_memakai_modul_yang_sama():
    assert main_module.kuota is kuota
    assert glints_module.kuota is kuota


def test_sisa_mengurangi_lamaran_hari_ini():
    cfg = ConfigPalsu(50)
    assert kuota.sisa(DbPalsu(0), cfg) == 50
    assert kuota.sisa(DbPalsu(49), cfg) == 1
    assert kuota.sisa(DbPalsu(50), cfg) == 0
    # Tidak pernah negatif walau data aneh.
    assert kuota.sisa(DbPalsu(90), cfg) == 0


def test_tanpa_batas_bila_nol():
    cfg = ConfigPalsu(0)
    assert kuota.sisa(DbPalsu(999), cfg) is None
    assert kuota.habis(DbPalsu(999), cfg) is False
    assert kuota.potong(list(range(5)), DbPalsu(999), cfg) == list(range(5))


def test_habis_saat_kuota_terpakai_semua():
    cfg = ConfigPalsu(2)
    assert kuota.habis(DbPalsu(1), cfg) is False
    assert kuota.habis(DbPalsu(2), cfg) is True


def test_ringkasan_memuat_angka_yang_sama_untuk_kedua_situs():
    cfg = ConfigPalsu(50)
    teks = kuota.ringkasan(DbPalsu(4), cfg)

    assert "4 sudah dilamar pada siklus ini" in teks
    assert "sisa 46 dari 50" in teks
    # JobStreet dan Glints memakai fungsi ini, jadi teksnya pasti identik.
    assert kuota.ringkasan(DbPalsu(4), cfg) == teks


def test_potong_mengambil_sesuai_sisa_kuota():
    cfg = ConfigPalsu(2)
    assert kuota.potong(["a", "b", "c"], DbPalsu(1), cfg) == ["a"]
    assert kuota.potong(["a", "b"], DbPalsu(2), cfg) == []


def test_batas_membaca_config_asli():
    """Tanpa argumen, modul membaca config aktif (dipakai kode produksi)."""
    assert kuota.batas() == max(0, int(config.max_apply_per_day or 0))
