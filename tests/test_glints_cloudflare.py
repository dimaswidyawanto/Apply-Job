"""Halaman "Just a moment..." (Cloudflare) di Glints.

Kasus nyata: Chrome terbuka, judul halaman "Just a moment...", 0 kartu
terbaca. Bot harus mengenali itu sebagai verifikasi Cloudflare (bukan situs
yang berubah), menunggu sebentar, lalu memberi cara mengatasinya
(chrome-debug.bat + CHROME_DEBUG_PORT).
"""

import glints as glints_module


class DriverCloudflare:
    def __init__(self, judul="Just a moment...", tautan=None):
        self._judul = judul
        self.teks = "Checking your browser before accessing glints.com"
        self.tautan = tautan or []

    @property
    def title(self):
        return self._judul

    def get(self, url):
        return None

    def find_elements(self, by, selector):
        if "opportunities/jobs" not in selector:
            return []

        class Elemen:
            def __init__(self, href):
                self.href = href

            def get_attribute(self, nama):
                return self.href if nama == "href" else ""

        return [Elemen(href) for href in self.tautan]

    def find_element(self, by, selector):
        driver = self

        class Badan:
            text = driver.teks

        return Badan()

    def execute_script(self, *args, **kwargs):
        return []


def test_kena_cloudflare_dikenali():
    bot = glints_module.GlintsBot()
    bot.driver = DriverCloudflare()

    assert bot.kena_cloudflare() is True


def test_halaman_normal_bukan_cloudflare():
    bot = glints_module.GlintsBot()
    driver = DriverCloudflare(judul="Lowongan Kerja Glints")
    driver.teks = ""
    bot.driver = driver

    assert bot.kena_cloudflare() is False


def test_tunggu_cloudflare_berhenti_saat_halaman_lolos(monkeypatch, capsys):
    bot = glints_module.GlintsBot()
    driver = DriverCloudflare()
    bot.driver = driver

    panggilan = {"n": 0}

    def tidur_palsu(detik):
        # Verifikasi selesai setelah pemeriksaan kedua.
        panggilan["n"] += 1
        if panggilan["n"] >= 2:
            driver._judul = "Lowongan Kerja Glints"
            driver.teks = ""

    monkeypatch.setattr(glints_module.time, "sleep", tidur_palsu)
    jam = {"t": 0.0}

    def waktu():
        jam["t"] += 1
        return jam["t"]

    monkeypatch.setattr(glints_module.time, "time", waktu)

    assert bot._tunggu_cloudflare(detik=5) is True
    assert "verifikasi" in capsys.readouterr().out.lower()


def test_tunggu_cloudflare_menyerah_dan_memberi_solusi(monkeypatch, capsys):
    bot = glints_module.GlintsBot()
    bot.driver = DriverCloudflare()
    monkeypatch.setattr(glints_module.time, "sleep", lambda *_: None)

    jam = {"t": 0.0}

    def waktu():
        jam["t"] += 10
        return jam["t"]

    monkeypatch.setattr(glints_module.time, "time", waktu)

    assert bot._tunggu_cloudflare(detik=5) is False

    keluaran = " ".join(capsys.readouterr().out.lower().split())
    assert "chrome-debug.bat" in keluaran
    assert "chrome_debug_port" in keluaran


def test_diagnosa_mencatat_cloudflare(monkeypatch, tmp_path, capsys):
    bot = glints_module.GlintsBot()
    bot.driver = DriverCloudflare()
    monkeypatch.setattr(glints_module, "folder_debug", lambda: tmp_path)

    info = bot.simpan_diagnosa("diagnosa", "inventory staff")

    assert info["cloudflare"] is True
    assert "cloudflare" in " ".join(capsys.readouterr().out.lower().split())


def test_sudah_login_tidak_tertipu_halaman_cloudflare():
    bot = glints_module.GlintsBot()
    bot.driver = DriverCloudflare()
    bot._url = lambda: "https://glints.com/id/opportunities/jobs/explore"
    assert bot.kena_cloudflare() is True
    assert bot.sudah_login() is False
