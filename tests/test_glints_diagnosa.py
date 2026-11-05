"""Diagnosa pembacaan kartu Glints.

Kasus nyata: `glints run` melaporkan "Terbaca 0 lowongan" untuk semua kata
kunci. Penyebabnya bisa halaman login, URL pencarian berubah, atau pola
tautan lowongan berubah. Tes ini memastikan sistem mencoba URL cadangan,
punya pembaca cadangan tanpa JavaScript, dan menyimpan HTML + screenshot
beserta ringkasan yang bisa dilaporkan.
"""

from pathlib import Path

import glints as glints_module
from config import config

UUID = "b5f8d754-afd9-4f0c-a618-360afe12248c"
URL_LOWONGAN = f"https://glints.com/id/opportunities/jobs/inventory-staff/{UUID}"


class ElemenPalsu:
    def __init__(self, href, teks="Inventory Staff"):
        self.href = href
        self.text = teks

    def get_attribute(self, nama):
        return self.href if nama == "href" else ""


class DriverPalsu:
    """Driver yang hanya menampilkan tautan pada URL tertentu."""

    def __init__(self, tautan_per_url=None, tautan_default=None):
        self.tautan_per_url = tautan_per_url or {}
        self.tautan_default = tautan_default or []
        self.url = ""
        self.page_source = "<html><body>Glints</body></html>"
        self.title = "Lowongan Kerja Glints"

    def get(self, url):
        self.url = url

    def find_elements(self, by, selector):
        if "opportunities/jobs" not in selector:
            return []

        tautan = self.tautan_per_url.get(self.url, self.tautan_default)
        return [ElemenPalsu(href) for href in tautan]

    def execute_script(self, *args, **kwargs):
        return []

    def save_screenshot(self, path):
        Path(path).write_bytes(b"png-palsu")


def bot_dengan(driver):
    bot = glints_module.GlintsBot()
    bot.driver = driver
    bot._tunggu_kartu = lambda detik=None: len(bot._tautan_kartu())
    return bot


def test_tautan_lowongan_tanpa_slug_tetap_dikenali():
    tanpa_slug = f"https://glints.com/id/opportunities/jobs/{UUID}"

    assert glints_module.id_dari_url(tanpa_slug) == UUID
    assert glints_module.id_dari_url(URL_LOWONGAN) == UUID
    assert glints_module.id_dari_url(
        "https://glints.com/id/opportunities/jobs/warehouse"
    ) == ""


def test_tautan_pencarian_bukan_lowongan_diabaikan():
    driver = DriverPalsu(tautan_default=[
        "https://glints.com/id/opportunities/jobs/explore?keyword=inventory",
        URL_LOWONGAN,
    ])
    bot = bot_dengan(driver)

    tautan = bot._tautan_kartu()

    assert tautan == [URL_LOWONGAN]


def test_buka_pencarian_mencoba_url_cadangan(monkeypatch):
    """Bila bentuk URL pertama kosong, bentuk berikutnya dicoba."""
    monkeypatch.setattr(config, "search_wait", 3)

    cadangan = glints_module.SEARCH_URL_CANDIDATES[2].format(
        keyword="inventory"
    )
    driver = DriverPalsu(tautan_per_url={cadangan: [URL_LOWONGAN]})
    bot = bot_dengan(driver)

    assert bot.buka_pencarian("inventory") is True
    # Bentuk URL yang berhasil diingat untuk kata kunci berikutnya.
    assert bot.search_url == glints_module.SEARCH_URL_CANDIDATES[2]


def test_cari_memakai_pembaca_cadangan_bila_skrip_gagal(monkeypatch):
    """JavaScript tidak menemukan kartu -> dibaca langsung dari elemen <a>."""
    driver = DriverPalsu(tautan_default=[URL_LOWONGAN])
    bot = bot_dengan(driver)
    monkeypatch.setattr(bot, "buka_pencarian", lambda keyword: True)
    monkeypatch.setattr(bot, "urutkan_terbaru", lambda: False)
    monkeypatch.setattr(bot, "muat_lebih", lambda: False)

    lowongan = bot.cari("inventory", 0)

    assert len(lowongan) == 1
    assert lowongan[0]["job_id"] == f"glints:{UUID}"


def test_diagnosa_menyimpan_html_dan_png(monkeypatch, tmp_path, capsys):
    driver = DriverPalsu()
    bot = bot_dengan(driver)
    monkeypatch.setattr(glints_module, "folder_debug", lambda: tmp_path)

    info = bot.simpan_diagnosa("pencarian", "inventory control")

    assert info["jumlah_tautan"] == 0
    assert info["jumlah_kartu"] == 0
    assert Path(info["berkas_html"]).exists()
    assert Path(info["berkas_png"]).exists()
    assert "inventory-control" in Path(info["berkas_png"]).name

    keluaran = " ".join(capsys.readouterr().out.lower().split())
    assert "diagnosa halaman glints" in keluaran
    assert "tautan lowongan ditemukan: 0" in keluaran


def test_pencarian_tanpa_kartu_menyimpan_diagnosa(monkeypatch, tmp_path, capsys):
    driver = DriverPalsu()
    bot = bot_dengan(driver)
    monkeypatch.setattr(glints_module, "folder_debug", lambda: tmp_path)

    assert bot.buka_pencarian("inventory") is False
    assert bot.diagnosa_terakhir["jumlah_tautan"] == 0

    keluaran = " ".join(capsys.readouterr().out.lower().split())
    assert "tidak ada kartu lowongan" in keluaran
