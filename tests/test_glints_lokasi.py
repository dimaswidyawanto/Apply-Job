"""Glints: kombinasi riset kata kunci x lokasi, sama seperti JobStreet.

Sebelumnya Glints hanya mencari per kata kunci (URL tanpa lokasi), sehingga
20 kata kunci = 20 pencarian, sedangkan JobStreet 20 kata kunci x 9 lokasi =
180 kombinasi. Tes ini menjaga agar jumlah kombinasi Glints mengikuti
JobStreet, dan memastikan fallback tetap aman bila Glints mengabaikan
parameter lokasi.
"""

import glints
from config import config


# ------------------------------------------------------------------ pembantu ---
class DriverPalsu:
    """Driver minimal: hanya mencatat URL yang dibuka."""

    def __init__(self):
        self.dibuka = []
        self.current_url = ""

    def get(self, url):
        self.dibuka.append(url)
        self.current_url = url

    def find_elements(self, by, selector):
        return []

    def execute_script(self, *argumen):
        return None


def _bot():
    bot = glints.GlintsBot()
    bot.driver = DriverPalsu()
    return bot


def _tanpa_cache(monkeypatch):
    monkeypatch.setattr(glints.cache_riset, "ambil", lambda *a, **k: None)
    monkeypatch.setattr(
        glints.cache_riset, "simpan", lambda *a, **k: None
    )
    monkeypatch.setattr(glints.cache_riset, "kunci", lambda *a, **k: "kunci")


# ------------------------------------------------- kombinasi kata kunci x lokasi ---
def test_kumpulkan_lowongan_memakai_semua_lokasi(monkeypatch):
    _tanpa_cache(monkeypatch)
    dipanggil = []

    class Bot:
        def cari(self, keyword, halaman=0, location=""):
            dipanggil.append((keyword, location))
            return [
                {
                    "job_id": f"glints:{keyword}-{location}",
                    "title": keyword,
                    "url": "https://glints.com/x",
                }
            ]

    hasil = glints.kumpulkan_lowongan(
        Bot(), ["inventory", "gudang"], 1, lokasi=["Bandung", "Jakarta"]
    )

    assert dipanggil == [
        ("inventory", "Bandung"),
        ("gudang", "Bandung"),
        ("inventory", "Jakarta"),
        ("gudang", "Jakarta"),
    ]
    assert len(hasil) == 4


def test_kumpulkan_lowongan_menghapus_duplikat_antar_lokasi(monkeypatch):
    _tanpa_cache(monkeypatch)

    class Bot:
        def cari(self, keyword, halaman=0, location=""):
            return [
                {"job_id": "glints:sama", "title": "A", "url": "u"},
            ]

    hasil = glints.kumpulkan_lowongan(
        Bot(), ["inventory", "gudang"], 1, lokasi=["Bandung", "Jakarta"]
    )

    assert len(hasil) == 1


def test_kumpulkan_lowongan_tanpa_lokasi_tetap_jalan(monkeypatch):
    _tanpa_cache(monkeypatch)
    dipanggil = []

    class Bot:
        def cari(self, keyword, halaman=0, location=""):
            dipanggil.append((keyword, location))
            return []

    glints.kumpulkan_lowongan(Bot(), ["inventory"], 1, lokasi=[])

    assert dipanggil == [("inventory", "")]


def test_kunci_cache_membedakan_lokasi(monkeypatch):
    kunci = []

    def catat_kunci(situs, keyword, location, halaman):
        kunci.append((situs, keyword, location))
        return f"{situs}:{keyword}:{location}"

    monkeypatch.setattr(glints.cache_riset, "kunci", catat_kunci)
    monkeypatch.setattr(glints.cache_riset, "ambil", lambda *a, **k: None)
    monkeypatch.setattr(glints.cache_riset, "simpan", lambda *a, **k: None)

    class Bot:
        def cari(self, keyword, halaman=0, location=""):
            return []

    glints.kumpulkan_lowongan(
        Bot(), ["inventory"], 1, lokasi=["Bandung", "Jakarta"]
    )

    assert kunci == [
        ("glints", "inventory", "Bandung"),
        ("glints", "inventory", "Jakarta"),
    ]


# ---------------------------------------------------- URL pencarian per lokasi ---
def test_url_lokasi_dipakai_bila_kartu_muncul(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot, "kena_cloudflare", lambda: False)
    monkeypatch.setattr(bot, "_tunggu_kartu", lambda *a, **k: 3)

    assert bot.buka_pencarian("inventory", "Bandung") is True
    assert bot.lokasi_didukung is True
    assert "location=Bandung" in bot.driver.dibuka[0]


def test_nama_lokasi_di_url_di_encode(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot, "kena_cloudflare", lambda: False)
    monkeypatch.setattr(bot, "_tunggu_kartu", lambda *a, **k: 3)

    bot.buka_pencarian("inventory control", "Jakarta Selatan")

    assert "location=Jakarta+Selatan" in bot.driver.dibuka[0]


def test_fallback_bila_lokasi_diabaikan(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot, "kena_cloudflare", lambda: False)

    def kartu(*argumen, **kata_kunci):
        # URL ber-lokasi tidak menghasilkan kartu; URL biasa menghasilkan.
        return 0 if "location=" in bot.driver.current_url else 5

    monkeypatch.setattr(bot, "_tunggu_kartu", kartu)

    assert bot.buka_pencarian("inventory", "Bandung") is True
    assert bot.lokasi_didukung is False
    # Percobaan berikutnya langsung memakai URL tanpa lokasi.
    jumlah_awal = len(bot.driver.dibuka)
    assert bot.buka_pencarian("gudang", "Jakarta") is True
    assert all(
        "location=" not in url for url in bot.driver.dibuka[jumlah_awal:]
    )


def test_tanpa_lokasi_tidak_mencoba_url_lokasi(monkeypatch):
    bot = _bot()
    monkeypatch.setattr(bot, "kena_cloudflare", lambda: False)
    monkeypatch.setattr(bot, "_tunggu_kartu", lambda *a, **k: 2)

    assert bot.buka_pencarian("inventory") is True
    assert all("location=" not in url for url in bot.driver.dibuka)
    assert bot.lokasi_didukung is None


# --------------------------------------------------------- tampilan pengaturan ---
def test_pengaturan_menyebut_jumlah_kombinasi(monkeypatch, capsys):
    monkeypatch.setattr(config, "research_keywords", ["a", "b", "c"])
    monkeypatch.setattr(config, "locations", ["Bandung", "Jakarta"])

    glints.tampilkan_konfigurasi_glints()

    keluaran = capsys.readouterr().out
    assert "Kombinasi riset" in keluaran
    assert "3 kata kunci x 2 lokasi = 6" in keluaran


def test_lokasi_diabaikan_tidak_mengulang_riset(monkeypatch):
    """Bila Glints mengabaikan lokasi, sisa lokasi dilewati (bukan 9x kerja)."""
    _tanpa_cache(monkeypatch)
    dipanggil = []

    class Bot:
        lokasi_didukung = False

        def cari(self, keyword, halaman=0, location=""):
            dipanggil.append((keyword, location))
            return []

    glints.kumpulkan_lowongan(
        Bot(), ["inventory", "gudang"], 1, lokasi=["Bandung", "Jakarta"]
    )

    assert dipanggil == [("inventory", "Bandung"), ("gudang", "Bandung")]
