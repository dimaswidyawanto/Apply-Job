"""Indeed memakai aturan yang sama persis dengan JobStreet.

Yang diuji: URL pencarian (urut terbaru + lokasi), pembentukan ID lowongan,
aturan penyaringan (sudah dilamar/lokasi/logo/judul), kuota bersama, batas per
sesi, serta peta tombol Indeed pada mesin lamaran.
"""

import indeed as indeed_module
import job_filter as aturan_module
from config import config
from indeed import IndeedApplier, IndeedBot, rapikan_kartu, url_pencarian


class DbPalsu:
    def __init__(self, sudah=(), hari_ini=0):
        self.sudah = set(sudah)
        self.hari_ini = hari_ini
        self.dicatat = []
        self.job_baru = set()

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


class NotifierPalsu:
    def __init__(self):
        self.galat = []
        self.harian = 0

    def send_apply_success(self, job):
        pass

    def send_error(self, pesan):
        self.galat.append(pesan)

    def send_daily_report(self, stats):
        self.harian += 1


KARTU_MENTAH = {
    "url": "https://id.indeed.com/viewjob?jk=abc123def456",
    "kunci": "abc123def456",
    "title": "Staff Gudang",
    "company": "PT Contoh",
    "location": "Bandung",
    "salary": "Rp 6.000.000",
    "text": "Staff Gudang PT Contoh Bandung Rp 6.000.000 3 hari lalu",
    "logo": [{"src": "https://id.indeed.com/logo/pt.png", "alt": ""}],
}


# ----------------------------------------------------------- pencarian ----
def test_url_pencarian_urut_terbaru_dan_memuat_lokasi():
    url = url_pencarian("inventory staff", "Bandung")

    assert url.startswith("https://id.indeed.com/jobs?q=")
    assert "sort=date" in url
    assert "inventory+staff" in url
    assert "Bandung" in url


def test_url_pencarian_tanpa_lokasi():
    url = url_pencarian("ppic", "")
    assert "ppic" in url
    assert "l=&" in url or url.endswith("l=&sort=date")


def test_rapikan_kartu_membentuk_id_dan_url():
    job = rapikan_kartu(KARTU_MENTAH)

    assert job["job_id"] == "indeed:abc123def456"
    assert job["url"] == "https://id.indeed.com/viewjob?jk=abc123def456"
    assert job["title"] == "Staff Gudang"
    assert job["has_logo"] is True
    assert job["source"] == "indeed"
    assert job["age_days"] == 3
    assert job["sudah_dilamar"] is False


def test_rapikan_kartu_menolak_tanpa_kunci_atau_judul():
    assert rapikan_kartu({"title": "Ada judul", "url": ""}) is None
    assert rapikan_kartu({"url": "https://id.indeed.com/viewjob?jk=abc"}) is None
    assert rapikan_kartu("bukan dict") is None


def test_rapikan_kartu_membaca_kunci_dari_url():
    job = rapikan_kartu({"url": "https://id.indeed.com/viewjob?jk=zz99", "title": "X"})
    assert job["job_id"] == "indeed:zz99"


def test_kartu_bertanda_sudah_dilamar_dikenali():
    mentah = dict(KARTU_MENTAH, text="Staff Gudang · Anda sudah melamar")
    assert rapikan_kartu(mentah)["sudah_dilamar"] is True


# ---------------------------------------------------------- penyaringan ----
def test_alasan_menolak_yang_sudah_tercatat(monkeypatch):
    basis = DbPalsu(sudah={"indeed:abc123def456"})
    monkeypatch.setattr(indeed_module, "db", basis)
    monkeypatch.setattr(aturan_module, "db", basis)
    job = rapikan_kartu(KARTU_MENTAH)

    assert indeed_module.alasan_tidak_layak(job) == "Sudah tercatat dilamar"


def test_lokasi_mengikuti_setelan_jobstreet(monkeypatch):
    """Tidak ada syarat lokasi tambahan; hanya STRICT_LOCATION seperti JobStreet."""
    basis = DbPalsu()
    monkeypatch.setattr(indeed_module, "db", basis)
    monkeypatch.setattr(aturan_module, "db", basis)
    monkeypatch.setattr(config, "locations", ["Jakarta"], raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "min_salary", 0, raising=False)
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)

    job = rapikan_kartu(KARTU_MENTAH)
    assert indeed_module.alasan_tidak_layak(job) == ""

    monkeypatch.setattr(config, "strict_location", True, raising=False)
    assert "okasi" in indeed_module.alasan_tidak_layak(job)


def test_tanpa_logo_tetap_layak_di_indeed(monkeypatch):
    """Ada/tidaknya gambar tidak pernah menjadi alasan melewati lowongan."""
    basis = DbPalsu()
    monkeypatch.setattr(indeed_module, "db", basis)
    monkeypatch.setattr(aturan_module, "db", basis)
    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    monkeypatch.setattr(config, "require_company_logo", True, raising=False)
    monkeypatch.setattr(config, "strict_location", False, raising=False)
    monkeypatch.setattr(config, "min_salary", 0, raising=False)
    monkeypatch.setattr(config, "require_keyword_match", False, raising=False)

    job = rapikan_kartu(dict(KARTU_MENTAH, logo=[]))

    assert job["has_logo"] is False
    assert indeed_module.alasan_tidak_layak(job) == ""


def test_logo_wajib_di_jobstreet_dan_glints_tapi_tidak_di_indeed():
    """Pasal 6.1: logo wajib; Indeed dikecualikan karena kartunya tanpa logo."""
    from glints import alasan_tidak_layak as alasan_glints
    from job_filter import JobFilter

    lama_logo = config.require_company_logo
    lama_kata = config.require_keyword_match
    config.require_company_logo = True
    config.require_keyword_match = False
    try:
        dasar = {
            "job_id": "x1",
            "title": "Staff Gudang",
            "location": "Bandung",
            "has_logo": False,
        }

        lolos, alasan = JobFilter().should_apply(dasar)
        assert lolos is False
        assert "logo" in alasan.lower()

        assert "logo" in alasan_glints(dict(dasar, job_id="glints:y")).lower()

        # Indeed: kartu tanpa logo tetap layak.
        assert indeed_module.alasan_tidak_layak(
            dict(dasar, job_id="indeed:z", logo_diabaikan=True)
        ) == ""
    finally:
        config.require_company_logo = lama_logo
        config.require_keyword_match = lama_kata


# --------------------------------------------------------------- melamar ----
def test_applier_mengenali_tombol_indeed():
    assert IndeedApplier.situs_host == "indeed.com"
    assert IndeedApplier.nama_situs == "Indeed"
    assert any("indeedApplyButton" in s for s in IndeedApplier.apply_selectors)
    assert "apply now" in IndeedApplier.apply_texts
    assert any("submit" in t for t in IndeedApplier.submit_texts)
    assert any("submitted" in t for t in IndeedApplier.success_texts)


def test_lamar_menolak_lowongan_yang_sudah_tercatat(monkeypatch):
    monkeypatch.setattr(
        indeed_module, "db", DbPalsu(sudah={"indeed:abc123def456"})
    )

    hasil = IndeedBot().lamar(rapikan_kartu(KARTU_MENTAH))

    assert hasil.status == "already_applied"


class BotPalsu:
    def __init__(self, kartu=None):
        self.kartu = kartu or [rapikan_kartu(KARTU_MENTAH)]
        self.dilamar = []
        self.login_expired = False
        self.driver = None
        self.filters = None

    def init_browser(self):
        pass

    def login(self):
        return True

    def cari(self, keyword, halaman=0, location=""):
        return [dict(job) for job in self.kartu]

    def lamar(self, job):
        self.dilamar.append(job["job_id"])
        from auto_apply import ApplyResult

        return ApplyResult(True, "applied", "Terkirim")

    def tutup(self):
        pass


def _siapkan_sesi(monkeypatch, hari_ini=0, batas_harian=50):
    db = DbPalsu(hari_ini=hari_ini)
    notifier = NotifierPalsu()
    bot = BotPalsu()

    monkeypatch.setattr(indeed_module, "db", db)
    monkeypatch.setattr(indeed_module, "notifier", notifier)
    monkeypatch.setattr(indeed_module, "IndeedBot", lambda: bot)
    monkeypatch.setattr(indeed_module, "tampilkan_konfigurasi", lambda: None)
    monkeypatch.setattr(
        indeed_module, "tampilkan_perbandingan",
        lambda kandidat, maksimal=10, situs="Indeed": None,
    )
    monkeypatch.setattr(
        indeed_module, "tampilkan_rincian_skor",
        lambda kandidat, maksimal=3, situs="Indeed": None,
    )
    monkeypatch.setattr(
        indeed_module, "kumpulkan_lowongan",
        lambda bot_, kata, halaman, lokasi=None: [dict(job) for job in bot_.kartu],
    )

    monkeypatch.setattr(config, "locations", ["Bandung"], raising=False)
    monkeypatch.setattr(config, "max_apply_per_day", batas_harian, raising=False)
    monkeypatch.setattr(config, "auto_apply", True, raising=False)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 0, raising=False)
    monkeypatch.setattr(config, "delay_between_apply", 0, raising=False)
    monkeypatch.setattr(config, "research_max_jobs", 0, raising=False)
    monkeypatch.setattr(config, "require_company_logo", True, raising=False)
    monkeypatch.setattr(indeed_module.time, "sleep", lambda *_: None, raising=False)
    return db, notifier, bot


def test_sesi_berhenti_bila_kuota_habis(monkeypatch):
    _, notifier, bot = _siapkan_sesi(monkeypatch, hari_ini=50, batas_harian=50)

    laporan = indeed_module.jalankan_indeed(
        max_pages=1, keywords=["inventory"], batas=10
    )

    assert bot.dilamar == []
    assert laporan["dilamar"] == 0
    assert notifier.harian == 1


def test_batas_per_sesi_dihormati(monkeypatch):
    _, _, bot = _siapkan_sesi(monkeypatch)
    monkeypatch.setattr(config, "auto_apply_max_per_session", 1, raising=False)

    laporan = indeed_module.jalankan_indeed(
        max_pages=1, keywords=["inventory"], batas=10
    )

    assert len(bot.dilamar) == 1
    assert laporan["dilamar"] == 1


def test_lowongan_sudah_dilamar_dilewati(monkeypatch):
    _, _, bot = _siapkan_sesi(monkeypatch)
    monkeypatch.setattr(
        indeed_module, "db", DbPalsu(sudah={"indeed:abc123def456"})
    )

    laporan = indeed_module.jalankan_indeed(
        max_pages=1, keywords=["inventory"], batas=10
    )

    assert bot.dilamar == []
    assert laporan["sudah"] == 1


# ------------------------------------------------------------- logo ----
def test_logo_dari_cdn_tanpa_kata_logo_diterima():
    """Logo Indeed sering dari CDN perusahaan, tanpa kata "logo" di URL."""
    from indeed import logo_kartu_indeed

    gambar = [{"src": "https://cdn.affinity.com/foto/abc123.png", "alt": ""}]
    punya, _ = logo_kartu_indeed(gambar, "PT Contoh")
    assert punya is True


def test_gambar_placeholder_bukan_logo():
    from indeed import logo_kartu_indeed

    for src in (
        "https://id.indeed.com/images/company-logo-placeholder.png",
        "https://id.indeed.com/no-logo.png",
        "data:image/gif;base64,R0lGOD",
        "https://example.com/spacer.gif",
    ):
        punya, _ = logo_kartu_indeed([{"src": src, "alt": ""}], "PT Contoh")
        assert punya is False, src


def test_placeholder_lewat_class_juga_ditolak():
    from indeed import logo_kartu_indeed

    gambar = [{
        "src": "https://cdn.example.com/x.png",
        "alt": "",
        "penanda": "companyLogo placeholder",
    }]
    punya, _ = logo_kartu_indeed(gambar, "PT Contoh")
    assert punya is False


def test_logo_dari_alt_nama_perusahaan():
    from indeed import logo_kartu_indeed

    punya, _ = logo_kartu_indeed(
        [{"src": "", "alt": "Logo PT Contoh"}], "PT Contoh"
    )
    assert punya is True


def test_tanpa_gambar_sama_sekali():
    from indeed import logo_kartu_indeed

    assert logo_kartu_indeed([], "PT Contoh")[0] is False
    assert logo_kartu_indeed(None, "PT Contoh")[0] is False


def test_rapikan_kartu_memakai_deteksi_logo_indeed():
    mentah = dict(KARTU_MENTAH)
    mentah["logo"] = [{"src": "https://cdn.affinity.com/foto/abc.png", "alt": ""}]
    assert rapikan_kartu(mentah)["has_logo"] is True
