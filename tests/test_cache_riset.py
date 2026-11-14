"""Cache riset lowongan (audit E-13)."""

from datetime import UTC, datetime, timedelta

import pytest

import cache_riset
import glints
import indeed
from database import Database


class ConfigPalsu:
    def __init__(self, menit=60):
        self.cache_riset_menit = menit

    # dipakai glints/indeed saat memanggil cache_riset tanpa cfg
    max_age_days = 0


@pytest.fixture(autouse=True)
def _bersihkan_penanda():
    cache_riset.paksa_segar(False)
    cache_riset.reset_statistik()
    yield
    cache_riset.paksa_segar(False)
    cache_riset.reset_statistik()


@pytest.fixture
def database(tmp_path, monkeypatch):
    basis = Database(str(tmp_path / "cache.db"))
    monkeypatch.setattr(cache_riset, "db_baku", basis)
    return basis


def _lowongan(nomor: int) -> dict:
    return {
        "job_id": f"glints:{nomor}",
        "title": f"PPIC {nomor}",
        "company": "PT Contoh",
        "location": "Bandung",
        "url": f"https://glints.com/x/{nomor}",
    }


# ------------------------------------------------------------- kunci cache ---
def test_kunci_berbeda_per_kombinasi():
    dasar = cache_riset.kunci("glints", "ppic", "Bandung", 0)

    assert dasar == cache_riset.kunci("glints", " PPIC ", "bandung ", 0)
    assert dasar != cache_riset.kunci("glints", "ppic", "Jakarta", 0)
    assert dasar != cache_riset.kunci("glints", "ppic", "Bandung", 1)
    assert dasar != cache_riset.kunci("indeed", "ppic", "Bandung", 0)


# --------------------------------------------------------------- ambil/simpan
def test_simpan_lalu_ambil(database):
    kunci = cache_riset.kunci("glints", "ppic", "", 1)
    cache_riset.simpan(kunci, [_lowongan(1)], situs="glints")

    assert cache_riset.ambil(kunci) == [_lowongan(1)]
    assert cache_riset.statistik() == {"dipakai": 1, "disimpan": 1}


def test_kunci_tak_dikenal_mengembalikan_none(database):
    assert cache_riset.ambil(cache_riset.kunci("glints", "tidak-ada")) is None


def test_cache_kedaluwarsa_setelah_ttl(database):
    kunci = cache_riset.kunci("glints", "ppic")
    lampau = datetime.now(UTC) - timedelta(minutes=90)
    database.cache_riset_simpan(kunci, "glints", [_lowongan(1)], sekarang=lampau)

    assert cache_riset.ambil(kunci) is None            # TTL bawaan 60 menit
    assert cache_riset.ambil(kunci, cfg=ConfigPalsu(120)) is not None


def test_ttl_nol_mematikan_cache(database):
    kunci = cache_riset.kunci("glints", "ppic")
    cache_riset.simpan(kunci, [_lowongan(1)], cfg=ConfigPalsu(0), situs="glints")

    assert cache_riset.ambil(kunci, cfg=ConfigPalsu(0)) is None
    assert cache_riset.statistik()["disimpan"] == 0


def test_paksa_segar_mengabaikan_cache(database):
    kunci = cache_riset.kunci("glints", "ppic")
    cache_riset.simpan(kunci, [_lowongan(1)], situs="glints")
    cache_riset.paksa_segar()

    assert cache_riset.ambil(kunci) is None
    assert cache_riset.aktif() is False


def test_ringkas_kosong_tanpa_aktivitas(database):
    assert cache_riset.ringkas() == ""


def test_pembersihan_membuang_baris_lama(database):
    kunci = cache_riset.kunci("glints", "lama")
    database.cache_riset_simpan(
        kunci, "glints", [_lowongan(1)],
        sekarang=datetime.now(UTC) - timedelta(days=10),
    )

    assert database.cache_riset_bersih(hari=3) == 1
    assert cache_riset.ambil(kunci) is None


# --------------------------------------------------- dipakai modul sungguhan --
class BotGlintsPalsu:
    def __init__(self):
        self.panggilan = 0

    def cari(self, kata, halaman, location="", **_):
        self.panggilan += 1
        return [_lowongan(1), _lowongan(2)]


def test_riset_glints_memakai_cache_pada_panggilan_kedua(database, monkeypatch):
    monkeypatch.setattr(
        cache_riset, "config", ConfigPalsu(60)
    )
    bot = BotGlintsPalsu()

    pertama = glints.kumpulkan_lowongan(bot, ["ppic"], 1, lokasi=["Bandung"])
    sesudah_pertama = bot.panggilan
    kedua = glints.kumpulkan_lowongan(bot, ["ppic"], 1, lokasi=["Bandung"])

    assert len(pertama) == 2
    assert [job["job_id"] for job in kedua] == [job["job_id"] for job in pertama]
    assert sesudah_pertama == 1
    # Panggilan kedua dilayani cache: tidak ada permintaan baru.
    assert bot.panggilan == sesudah_pertama


class BotIndeedPalsu(BotGlintsPalsu):
    def cari(self, kata, halaman, location="", **_):
        return super().cari(kata, halaman)


def test_riset_indeed_memakai_cache(database, monkeypatch):
    monkeypatch.setattr(cache_riset, "config", ConfigPalsu(60))
    bot = BotIndeedPalsu()

    pertama = indeed.kumpulkan_lowongan(bot, ["ppic"], 1, lokasi=["Bandung"])
    kedua = indeed.kumpulkan_lowongan(bot, ["ppic"], 1, lokasi=["Bandung"])

    assert len(pertama) == 2
    assert len(kedua) == 2
    assert bot.panggilan == 1


def test_cache_glints_dan_indeed_tidak_tercampur(database, monkeypatch):
    monkeypatch.setattr(cache_riset, "config", ConfigPalsu(60))
    bot_glints = BotGlintsPalsu()
    bot_indeed = BotIndeedPalsu()

    glints.kumpulkan_lowongan(bot_glints, ["ppic"], 1, lokasi=["Bandung"])
    indeed.kumpulkan_lowongan(bot_indeed, ["ppic"], 1, lokasi=["Bandung"])

    assert bot_glints.panggilan == 1
    assert bot_indeed.panggilan == 1


class BotJobStreetPalsu:
    def __init__(self):
        self.panggilan = 0

    def search_jobs(self, keyword, page, location=""):
        self.panggilan += 1
        return [
            {
                "job_id": "jobstreet:1",
                "title": "PPIC",
                "company": "PT Contoh",
                "location": location or "Bandung",
                "url": "https://id.jobstreet.com/job/1",
            }
        ]


def test_riset_jobstreet_memakai_cache(database, monkeypatch):
    import main

    monkeypatch.setattr(cache_riset, "config", ConfigPalsu(60))

    mesin = main.AutoApplyEngine()
    mesin.bot = BotJobStreetPalsu()
    mesin.seen_job_ids = set()
    mesin.duplikat_dilewati = 0
    mesin.waktu_halaman = 0.0
    mesin.jumlah_halaman = 0

    mesin._satu_halaman("ppic", 1, "Bandung")
    mesin.seen_job_ids = set()
    mesin._satu_halaman("ppic", 1, "Bandung")

    assert mesin.bot.panggilan == 1
    assert cache_riset.statistik()["dipakai"] == 1
