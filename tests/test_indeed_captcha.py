"""Indeed: hentikan riset setelah captcha berulang (bukan 180 kombinasi)."""

import indeed


class BotCaptcha:
    """Bot tiruan: setiap pencarian langsung membuat captcha menumpuk."""

    BATAS_CAPTCHA_BERTURUT = 2

    def __init__(self):
        self.panggilan = 0
        self.captcha_berturut = 0

    def cari(self, kata, halaman=0, location=""):
        self.panggilan += 1
        self.captcha_berturut += 1
        return []


class BotNormal:
    BATAS_CAPTCHA_BERTURUT = 2

    def __init__(self):
        self.panggilan = 0
        self.captcha_berturut = 0

    def cari(self, kata, halaman=0, location=""):
        self.panggilan += 1
        self.captcha_berturut = 0
        return [
            {
                "job_id": f"indeed:{self.panggilan}",
                "title": "PPIC",
                "company": "PT Contoh",
                "location": location or "Bandung",
                "url": f"https://id.indeed.com/viewjob?jk={self.panggilan}",
            }
        ]


def test_riset_berhenti_setelah_dua_captcha(monkeypatch):
    import cache_riset

    monkeypatch.setattr(cache_riset, "ttl_detik", lambda cfg=None: 0)

    bot = BotCaptcha()
    indeed.kumpulkan_lowongan(
        bot, ["ppic", "inventory", "warehouse"], 1, lokasi=["Bandung", "Jakarta"]
    )

    # Tanpa penghentian: 3 kata kunci × 2 lokasi = 6 panggilan.
    assert bot.panggilan == 2


def test_tanpa_captcha_semua_kombinasi_tetap_dijalankan(monkeypatch):
    import cache_riset

    monkeypatch.setattr(cache_riset, "ttl_detik", lambda cfg=None: 0)

    bot = BotNormal()
    hasil = indeed.kumpulkan_lowongan(
        bot, ["ppic", "inventory"], 1, lokasi=["Bandung", "Jakarta"]
    )

    assert bot.panggilan == 4
    assert len(hasil) == 4
