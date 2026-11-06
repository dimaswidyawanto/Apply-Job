"""Paritas aturan Glints dengan JobStreet.

JobStreet dianggap acuan. Tes ini menjaga aturan berikut tetap sama di Glints:
* lowongan yang sudah tercatat dilamar tidak pernah dilamar dua kali,
* setiap status dicatat ke database (applied/already_applied/login_required),
* login habis menghentikan sesi dan mengirim notifikasi,
* batas lamaran otomatis per sesi dihormati,
* laporan harian dikirim di akhir sesi,
* mode manual (AUTO_APPLY=false) membuka lowongan dan menunggu konfirmasi.
"""

import glints as glints_module
from auto_apply import ApplyResult
from config import config

KARTU = [
    {
        "job_id": f"glints:0000000{i}-1111-2222-3333-44444444444{i}",
        "title": f"Staff Gudang {i}",
        "company": f"PT Contoh {i}",
        "url": "https://glints.com/id/opportunities/jobs/staff/"
        f"0000000{i}-1111-2222-3333-44444444444{i}",
        "location": "Jakarta",
        "salary": "Rp 8.000.000",
        "has_logo": True,
        "khusus_aplikasi": False,
        "sudah_dilamar": False,
        "age_days": 1,
        "date_posted": "1 hari lalu",
        "description": "Staff gudang",
    }
    for i in range(3)
]


class DbPalsu:
    def __init__(self, sudah=()):
        self.sudah = set(sudah)
        self.dicatat = []
        self.job_baru = set()
        self.hari_ini = 0

    def is_already_applied(self, job_id):
        return job_id in self.sudah

    def add_job(self, job):
        if job["job_id"] in self.job_baru:
            return False
        self.job_baru.add(job["job_id"])
        return True

    def record_application(self, job_id, status="applied", notes=""):
        self.dicatat.append((job_id, status))

    def get_today_apply_count(self):
        return self.hari_ini

    def get_stats(self):
        return {"total_applied": 0}


class FilterPalsu:
    def should_apply(self, job):
        return True, ""


class NotifierPalsu:
    def __init__(self):
        self.sukses = []
        self.galat = []
        self.harian = 0

    def send_apply_success(self, job):
        self.sukses.append(job["job_id"])

    def send_error(self, pesan):
        self.galat.append(pesan)

    def send_daily_report(self, stats):
        self.harian += 1


class BotPalsu:
    def __init__(self, hasil=None):
        self.filters = FilterPalsu()
        self.dilamar = []
        self.login_expired = False
        self._hasil = hasil or ApplyResult(True, "applied", "Terkirim")
        self.driver = None

    def init_browser(self):
        pass

    def login(self):
        return True

    def cari(self, keyword, halaman=0):
        return [dict(job) for job in KARTU]

    def lamar(self, job):
        self.dilamar.append(job["job_id"])
        if self._hasil.status == "login_required":
            self.login_expired = True
        return self._hasil

    def tutup(self):
        pass


def _siapkan(monkeypatch, db=None, notifier=None, bot=None):
    db = db or DbPalsu()
    notifier = notifier or NotifierPalsu()
    monkeypatch.setattr(glints_module, "db", db)
    monkeypatch.setattr(glints_module, "notifier", notifier)
    monkeypatch.setattr(glints_module, "GlintsBot", lambda: bot or BotPalsu())
    monkeypatch.setattr(glints_module, "tampilkan_konfigurasi_glints", lambda: None)
    monkeypatch.setattr(
        glints_module, "tampilkan_perbandingan", lambda kandidat: None
    )
    monkeypatch.setattr(
        glints_module, "tampilkan_rincian_skor", lambda kandidat, maksimal=3: None
    )
    monkeypatch.setattr(
        glints_module, "pilih_teratas",
        lambda lowongan, batas=0: lowongan[:batas] if batas else lowongan,
    )

    monkeypatch.setattr(config, "locations", ["Jakarta"], raising=False)
    monkeypatch.setattr(config, "glints_min_salary", 0, raising=False)
    monkeypatch.setattr(config, "max_apply_per_day", 50, raising=False)
    monkeypatch.setattr(config, "auto_apply", True, raising=False)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0, raising=False)
    monkeypatch.setattr(config, "delay_between_apply", 0, raising=False)
    monkeypatch.setattr(config, "research_max_jobs", 0, raising=False)
    monkeypatch.setattr(config, "require_company_logo", True, raising=False)
    monkeypatch.setattr(glints_module.time, "sleep", lambda *_: None, raising=False)
    return db, notifier


# ---------------------------------------------------------------- riset ----
def test_riset_melewati_lowongan_yang_sudah_tercatat(monkeypatch):
    sudah = KARTU[0]["job_id"]
    bot = BotPalsu()
    _, _ = _siapkan(monkeypatch, db=DbPalsu(sudah={sudah}), bot=bot)

    laporan = glints_module.jalankan_glints(
        max_pages=1, keywords=["inventory staff"], batas=10
    )

    assert laporan["dilamar"] == 2
    assert laporan["sudah"] == 1
    assert sudah not in bot.dilamar


def test_riset_tidak_melamar_dua_kali(monkeypatch):
    bot = BotPalsu()
    _, notifier = _siapkan(monkeypatch, bot=bot)

    laporan = glints_module.jalankan_glints(
        max_pages=1, keywords=["inventory staff"], batas=10
    )

    assert laporan["dilamar"] == len(KARTU)
    assert bot.dilamar == [job["job_id"] for job in KARTU]
    assert len(notifier.sukses) == len(KARTU)


def test_batas_otomatis_per_sesi_dihormati(monkeypatch):
    _siapkan(monkeypatch)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 1, raising=False)

    laporan = glints_module.jalankan_glints(
        max_pages=1, keywords=["inventory"], batas=10
    )
    assert laporan["dilamar"] == 1


def test_login_habis_menghentikan_sesi_dan_memberi_notifikasi(monkeypatch):
    _siapkan(
        monkeypatch,
        bot=BotPalsu(ApplyResult(False, "login_required", "Login Glints habis")),
    )
    laporan = glints_module.jalankan_glints(
        max_pages=1, keywords=["inventory"], batas=10
    )

    assert laporan["dilamar"] == 0
    assert laporan["gagal"] == 1


def test_laporan_harian_dikirim_di_akhir(monkeypatch):
    _, notifier = _siapkan(monkeypatch)
    glints_module.jalankan_glints(max_pages=1, keywords=["inventory"], batas=10)
    assert notifier.harian == 1


# --------------------------------------------------------------- lamar ----
def test_lamar_menolak_yang_sudah_tercatat_tanpa_membuka_browser(monkeypatch):
    db = DbPalsu(sudah={KARTU[0]["job_id"]})
    monkeypatch.setattr(glints_module, "db", db)

    hasil = glints_module.GlintsBot().lamar(dict(KARTU[0]))

    assert hasil.status == "already_applied"
    assert hasil.reason == "Sudah tercatat dilamar"


def test_lamar_otomatis_mencatat_status(monkeypatch):
    db = DbPalsu()
    monkeypatch.setattr(glints_module, "db", db)
    monkeypatch.setattr(config, "auto_apply", True, raising=False)

    class ApplierPalsu:
        def __init__(self, driver):
            pass

        def apply(self, job):
            return ApplyResult(True, "applied", "Terkirim otomatis")

    monkeypatch.setattr(glints_module, "GlintsApplier", ApplierPalsu)

    hasil = glints_module.GlintsBot().lamar(dict(KARTU[0]))

    assert hasil.applied is True
    assert ("glints:00000000-1111-2222-3333-444444444440", "applied") in db.dicatat


def test_lamar_login_required_menandai_sesi_habis(monkeypatch):
    monkeypatch.setattr(glints_module, "db", DbPalsu())
    monkeypatch.setattr(config, "auto_apply", True, raising=False)

    class ApplierPalsu:
        def __init__(self, driver):
            pass

        def apply(self, job):
            return ApplyResult(False, "login_required", "Login Glints belum selesai")

    monkeypatch.setattr(glints_module, "GlintsApplier", ApplierPalsu)

    bot = glints_module.GlintsBot()
    hasil = bot.lamar(dict(KARTU[0]))

    assert hasil.status == "login_required"
    assert bot.login_expired is True


def test_mode_manual_menunggu_konfirmasi(monkeypatch):
    db = DbPalsu()
    monkeypatch.setattr(glints_module, "db", db)
    monkeypatch.setattr(config, "auto_apply", False, raising=False)

    class DriverPalsu:
        def get(self, url):
            self.url = url

        def find_element(self, *args, **kwargs):
            raise RuntimeError("tidak dipakai")

    bot = glints_module.GlintsBot()
    bot.driver = DriverPalsu()
    monkeypatch.setattr(bot, "_teks_halaman", lambda: "halaman lowongan")
    monkeypatch.setattr("builtins.input", lambda *_: "y")

    hasil = bot.lamar(dict(KARTU[0]))

    assert hasil.applied is True
    assert db.dicatat[-1][1] == "applied"


def test_alasan_tidak_layak_memeriksa_database(monkeypatch):
    import job_filter as aturan

    basis = DbPalsu(sudah={KARTU[0]["job_id"]})
    monkeypatch.setattr(glints_module, "db", basis)
    monkeypatch.setattr(aturan, "db", basis)

    alasan = glints_module.alasan_tidak_layak(dict(KARTU[0]))

    assert alasan == "Sudah tercatat dilamar"
