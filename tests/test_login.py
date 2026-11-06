import pytest

import scraper
from config import config


class FakeElement:
    def __init__(self, visible=True):
        self._visible = visible

    def is_displayed(self):
        return self._visible


class FakeDriver:
    def __init__(self, elements=None, cookies=None):
        self.elements = elements or {}
        self.cookies = cookies or []
        self.opened_urls = []

    def get(self, url):
        self.opened_urls.append(url)

    def find_elements(self, by, selector):
        return list(self.elements.get(selector, []))

    def find_element(self, by, selector):
        return FakeElement()

    def get_cookies(self):
        return list(self.cookies)


@pytest.fixture(autouse=True)
def tanpa_jeda(monkeypatch):
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)


def buat_bot(elements):
    bot = scraper.JobStreetBot()
    bot.driver = FakeDriver(elements)
    return bot


def test_status_login_terdeteksi_belum_login():
    bot = buat_bot({"a[data-automation='signIn']": [FakeElement()]})
    assert bot._login_status() is False


def test_status_login_terdeteksi_sudah_login():
    bot = buat_bot({"[data-automation='accountMenu']": [FakeElement()]})
    assert bot._login_status() is True


def test_status_login_tidak_pasti():
    bot = buat_bot({})
    assert bot._login_status() is None


def test_login_langsung_lanjut_bila_sesi_tersimpan(monkeypatch):
    bot = buat_bot({"a[href*='/profile']": [FakeElement()]})

    def jangan_tanya(*args, **kwargs):
        raise AssertionError("input() tidak boleh dipanggil saat sudah login")

    monkeypatch.setattr("builtins.input", jangan_tanya)

    assert bot.login() is True


def test_login_berhenti_tanpa_menunggu_bila_belum_login(monkeypatch):
    monkeypatch.setattr(config, "login_wait", False)
    bot = buat_bot({"a[data-automation='signIn']": [FakeElement()]})

    def jangan_tanya(*args, **kwargs):
        raise AssertionError("input() tidak boleh dipanggil")

    monkeypatch.setattr("builtins.input", jangan_tanya)

    assert bot.login() is False


def test_login_menunggu_lalu_lanjut_saat_login_terdeteksi(monkeypatch):
    """Tanpa menekan Enter: program mendeteksi login sendiri."""
    monkeypatch.setattr(config, "login_wait", True)
    monkeypatch.setattr(config, "login_timeout", 60)

    bot = buat_bot({"a[data-automation='signIn']": [FakeElement()]})
    urutan = [False, False, True]

    def status_palsu():
        return urutan.pop(0) if urutan else True

    monkeypatch.setattr(bot, "_login_status", status_palsu)

    def jangan_tanya(*args, **kwargs):
        raise AssertionError("login tidak boleh memakai input()")

    monkeypatch.setattr("builtins.input", jangan_tanya)

    assert bot.login() is True


def test_login_berhenti_setelah_batas_waktu(monkeypatch):
    monkeypatch.setattr(config, "login_wait", True)
    monkeypatch.setattr(config, "login_timeout", 30)

    bot = buat_bot({})
    monkeypatch.setattr(bot, "_login_status", lambda: False)

    waktu = {"t": 1000}
    monkeypatch.setattr(scraper.time, "time", lambda: waktu["t"])
    monkeypatch.setattr(
        scraper.time,
        "sleep",
        lambda detik=0: waktu.__setitem__("t", waktu["t"] + detik),
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("tanpa input")),
    )

    assert bot.login() is False


def test_cookie_sesi_dianggap_sudah_login():
    bot = buat_bot({})
    bot.driver.cookies = [
        {"name": "JobStreetSession", "domain": ".jobstreet.com", "value": "x"}
    ]

    assert bot._has_session_cookie() is True
    assert bot._login_status() is True


def test_cookie_situs_lain_tidak_dihitung():
    bot = buat_bot({})
    bot.driver.cookies = [
        {"name": "session", "domain": ".google.com", "value": "x"}
    ]

    assert bot._has_session_cookie() is False
    assert bot._login_status() is None


def test_login_tidak_menanyakan_apa_pun_bila_cookie_ada(monkeypatch):
    bot = buat_bot({})
    bot.driver.cookies = [
        {"name": "JobStreetSession", "domain": ".jobstreet.com", "value": "x"}
    ]

    def jangan_tanya(*args, **kwargs):
        raise AssertionError("tidak boleh meminta input login")

    monkeypatch.setattr("builtins.input", jangan_tanya)

    assert bot.login() is True


def test_sesi_habis_menghentikan_seluruh_sesi(tmp_path, monkeypatch):
    import job_filter as job_filter_module
    import main as main_module
    from auto_apply import ApplyResult
    from database import Database

    database = Database(str(tmp_path / "berhenti.db"))
    monkeypatch.setattr(main_module, "db", database)
    monkeypatch.setattr(job_filter_module, "db", database)

    monkeypatch.setattr(config, "locations", ["Bandung"])
    monkeypatch.setattr(config, "keywords", ["satu", "dua"])
    monkeypatch.setattr(config, "max_pages", 1)
    monkeypatch.setattr(config, "delay_between_apply", 0)
    monkeypatch.setattr(config, "auto_apply", True)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 25)
    monkeypatch.setattr(config, "strict_location", False)
    monkeypatch.setattr(config, "max_age_days", 0)
    # Mode berurutan: kata kunci berikutnya tidak dicari setelah sesi habis.
    # Batas harian harus 0, karena batas > 0 memaksa mode riset lebih dulu
    # (riset selesai dulu, baru melamar) — perilaku itu diuji terpisah.
    monkeypatch.setattr(config, "collect_before_apply", False)
    monkeypatch.setattr(config, "max_apply_per_day", 0)

    class Bot:
        login_expired = False

        def __init__(self):
            self.panggilan = []

        def init_browser(self):
            pass

        def login(self):
            return True

        def search_jobs(self, keyword, page=1, location=None):
            self.panggilan.append((location, keyword, page))
            if page > 1:
                return []
            return [{
                "job_id": f"id-{keyword}",
                "title": "Inventory Control",
                "company": "PT Contoh",
                "location": "Bandung",
                "salary": "Rp 8.000.000",
                "description": "",
                "url": f"https://id.jobstreet.com/job/{keyword}",
                "date_posted": "Hari ini",
                "age_days": 0,
                "applied": False,
            }]

        def apply_job(self, job):
            self.login_expired = True
            return ApplyResult(False, "login_required", "Sesi habis")

        def close(self):
            pass

    engine = main_module.AutoApplyEngine()
    engine.bot = Bot()
    engine.run()

    assert engine.stop_requested is True
    # Kata kunci kedua tidak dijalankan lagi.
    assert len(engine.bot.panggilan) == 1
