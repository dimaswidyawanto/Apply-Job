"""Indeed: hasil dari halaman yang diblokir tidak boleh masuk cache.

Log 2026-11-14 memperlihatkan akibatnya:

    Cache riset Indeed dipakai 'inventory control' — Bandung (0 lowongan).
    Kemajuan riset Indeed: 1/180 kombinasi, 0 lowongan, 0 detik berlalu

Kombinasi itu belum pernah benar-benar dibaca — hasil "0 lowongan" berasal
dari sesi sebelumnya yang diblokir Cloudflare. Karena cache berlaku
CACHE_RISET_MENIT, kombinasi tersebut hilang dari riset berikutnya dan bot
tidak pernah mendapat kesempatan membacanya.

Selain itu ada pemanasan sesi: satu halaman dibuka lebih dulu agar verifikasi
Cloudflare bisa diselesaikan sekali di jendela Chrome.
"""

import indeed
from config import config


class BotPalsu:
    """Bot tiruan untuk `kumpulkan_lowongan`: hasil per kombinasi diatur tes."""

    BATAS_CAPTCHA_BERTURUT = 2

    def __init__(self, hasil):
        self.hasil = list(hasil)
        self.captcha_berturut = 0
        self.keadaan_terakhir = ""
        self.dipanggil = []

    def cari(self, kata, halaman=0, location=""):
        self.dipanggil.append((kata, location))
        keadaan, kartu = self.hasil.pop(0) if self.hasil else ("siap", [])
        self.keadaan_terakhir = keadaan
        if keadaan == "blokir":
            # Sama seperti perilaku asli: blokir menghentikan riset.
            self.captcha_berturut = self.BATAS_CAPTCHA_BERTURUT
        return list(kartu)


def _kartu(job_id):
    return {
        "job_id": job_id,
        "title": "Staf Gudang",
        "company": "PT Uji",
        "location": "Bandung",
        "url": f"https://id.indeed.com/viewjob?jk={job_id}",
        "has_logo": True,
        "salary": "",
        "posted": "",
    }


def _siapkan(monkeypatch, hasil):
    disimpan = []
    monkeypatch.setattr(
        indeed.cache_riset, "ambil", lambda *a, **k: None
    )
    monkeypatch.setattr(
        indeed.cache_riset,
        "simpan",
        lambda kunci, data, **k: disimpan.append((kunci, len(data))),
    )
    bot = BotPalsu(hasil)
    return bot, disimpan


def test_hasil_blokir_tidak_disimpan_ke_cache(monkeypatch, capsys):
    bot, disimpan = _siapkan(monkeypatch, [("blokir", [])])

    hasil = indeed.kumpulkan_lowongan(
        bot, ["inventory"], 1, lokasi=["Bandung"]
    )

    assert hasil == []
    assert disimpan == [], "hasil blokir tidak boleh di-cache"
    assert "tidak disimpan ke cache" in capsys.readouterr().out


def test_hasil_kosong_tetap_disimpan(monkeypatch):
    """Halaman yang benar-benar terbaca dan kosong boleh di-cache."""
    bot, disimpan = _siapkan(monkeypatch, [("kosong", [])])

    indeed.kumpulkan_lowongan(bot, ["inventory"], 1, lokasi=["Bandung"])

    assert disimpan, "halaman kosong yang sah tetap boleh di-cache"


def test_hasil_terbaca_disimpan(monkeypatch):
    bot, disimpan = _siapkan(monkeypatch, [("siap", [_kartu("a1")])])

    hasil = indeed.kumpulkan_lowongan(
        bot, ["inventory"], 1, lokasi=["Bandung"]
    )

    assert len(hasil) == 1
    assert disimpan


def test_rincian_kombinasi_membedakan_kosong_dan_terblokir(
    monkeypatch, capsys
):
    bot, _ = _siapkan(monkeypatch, [("kosong", []), ("blokir", [])])

    indeed.kumpulkan_lowongan(
        bot, ["inventory", "ppic"], 1, lokasi=["Bandung"]
    )

    keluaran = capsys.readouterr().out
    assert "1 kosong" in keluaran
    assert "1 terblokir" in keluaran


# ------------------------------------------------------- pemanasan sesi ---
class DriverPalsu:
    def __init__(self):
        self.dibuka = []
        self.current_url = ""

    def get(self, url):
        self.dibuka.append(url)
        self.current_url = url


def test_panaskan_langsung_siap_tanpa_menunggu(monkeypatch):
    bot = indeed.IndeedBot()
    bot.driver = DriverPalsu()
    monkeypatch.setattr(
        bot, "_tunggu_halaman_siap", lambda detik=None: "siap"
    )

    assert bot.panaskan("inventory", "Bandung") == "siap"
    assert len(bot.driver.dibuka) == 1
    assert "jobs?q=inventory" in bot.driver.dibuka[0]


def test_panaskan_menunggu_verifikasi_selesai(monkeypatch):
    """Halaman pertama diblokir, pengguna menyelesaikan, lalu terbaca."""
    bot = indeed.IndeedBot()
    bot.driver = DriverPalsu()

    urutan = iter(["blokir", "blokir", "siap"])
    monkeypatch.setattr(
        bot, "_tunggu_halaman_siap", lambda detik=None: next(urutan, "siap")
    )
    monkeypatch.setattr(indeed.time, "sleep", lambda d: None)

    assert bot.panaskan("inventory", "Bandung", detik=30) == "siap"
    assert bot.keadaan_terakhir == "siap"


class JamPalsu:
    """Pengganti modul `time` di indeed.py agar tes tidak menunggu lama."""

    def __init__(self):
        self.sekarang = 0.0

    def time(self):
        return self.sekarang

    def sleep(self, detik):
        self.sekarang += float(detik)


def test_panaskan_menyerah_setelah_batas_waktu(monkeypatch):
    bot = indeed.IndeedBot()
    bot.driver = DriverPalsu()

    monkeypatch.setattr(indeed, "time", JamPalsu())
    monkeypatch.setattr(
        bot, "_tunggu_halaman_siap", lambda detik=None: "blokir"
    )

    assert bot.panaskan("inventory", "Bandung", detik=4) == "blokir"
    assert bot.keadaan_terakhir == "blokir"


def test_panaskan_tanpa_kata_kunci_tidak_membuka_halaman():
    bot = indeed.IndeedBot()
    bot.driver = DriverPalsu()

    assert bot.panaskan("") == ""
    assert bot.driver.dibuka == []


def test_panaskan_memakai_lokasi_pertama(monkeypatch):
    bot = indeed.IndeedBot()
    bot.driver = DriverPalsu()
    monkeypatch.setattr(
        bot, "_tunggu_halaman_siap", lambda detik=None: "siap"
    )

    bot.panaskan("ppic", "Bandung")

    assert "l=Bandung" in bot.driver.dibuka[0]


def test_headless_menunggu_lebih_singkat(monkeypatch, capsys):
    """Tanpa jendela Chrome, tidak ada yang bisa menyelesaikan verifikasi."""
    assert indeed.PANAS_MAKS_DETIK_HEADLESS < indeed.PANAS_MAKS_DETIK

    bot = indeed.IndeedBot()
    bot.driver = DriverPalsu()
    monkeypatch.setattr(config, "headless", True)
    monkeypatch.setattr(config, "chrome_debug_port", 0)
    monkeypatch.setattr(indeed, "time", JamPalsu())
    monkeypatch.setattr(
        bot, "_tunggu_halaman_siap", lambda detik=None: "blokir"
    )

    bot.panaskan("inventory", "Bandung")

    assert "maksimal 20 detik" in capsys.readouterr().out
