"""Perbaikan dari LIVE VALIDATION (Windows, 17 Nov 2026).

Tiga temuan nyata dari layar pengguna:

1. `dry-run` menampilkan `AGE · tanggal tidak terbaca (DATE_UNKNOWN)` untuk
   SEMUA lowongan JobStreet, artinya `MAX_AGE_DAYS=7` tidak pernah bekerja.
   Penyebabnya: kartu JobStreet tidak lagi punya `jobListingDate`/`time`,
   sehingga `date_posted` kosong.
2. Banner `config` mencetak "Wajib ada logo perusahaan: Aktif" padahal
   `cek-logo` pada sesi yang sama mencetak `REQUIRE_COMPANY_LOGO=false`
   (teks banner dulu hardcoded).
3. `glints cari` mati dengan `ConnectionResetError WinError 10054` pada
   kombinasi ke-27 dari 126, lalu Ctrl+C memunculkan traceback berlapis.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from selenium.common.exceptions import NoSuchElementException

import cli
import glints
import job_filter as jf_modul
import umur
from config import config
from database import Database
from job_filter import JobFilter
from scraper import JobStreetBot


# --------------------------------------------------------------- perkakas ---
class ElemenTiruan:
    def __init__(self, teks="", attrs=None):
        self.text = teks
        self._attrs = dict(attrs or {})

    def get_attribute(self, nama):
        return self._attrs.get(nama)


class Tautan:
    text = "Inventory Control Staff"
    id = "tautan-1"

    def get_attribute(self, nama):
        return "/job/95928491" if nama == "href" else None


class Kartu:
    """Kartu JobStreet tiruan: tautan judul + (opsional) elemen tanggal."""

    def __init__(self, teks="", tanggal=None):
        self.text = teks
        self.tanggal = tanggal

    def find_element(self, by, selector):
        if self.tanggal is not None and selector in (
            "time[datetime]",
            "[data-automation='jobListingDate']",
        ):
            return self.tanggal
        raise NoSuchElementException(selector)

    def find_elements(self, by, selector):
        if selector in ("h3 a", "a[href*='/job/']"):
            return [Tautan()]
        return []


@pytest.fixture
def bot():
    bot = JobStreetBot()
    bot.driver = type(
        "Driver", (), {"current_url": "https://id.jobstreet.com/jobs?x=1"}
    )()
    return bot


@pytest.fixture
def basis(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "live.db"))
    monkeypatch.setattr(jf_modul, "db", db)
    monkeypatch.setattr(config, "require_company_logo", False)
    monkeypatch.setattr(config, "max_age_days", 7)
    monkeypatch.setattr(config, "strict_location", False)
    monkeypatch.setattr(config, "require_keyword_match", True)
    monkeypatch.setattr(config, "min_salary", 4_500_000)
    return db


# ------------------------------------------------ 1. tanggal kartu JobStreet ---
def test_tanggal_dibaca_dari_atribut_datetime(bot):
    """`<time datetime="2026-11-15T03:00:00Z">` → tanggal absolut, bukan kosong."""
    kartu = Kartu(
        "Inventory Control Staff\nPT Contoh\nBandung",
        ElemenTiruan("15 Nov 2026", {"datetime": "2026-11-15T03:00:00.000Z"}),
    )

    job = bot._parse_job_card(kartu)

    assert job["date_posted"] == "2026-11-15"
    assert isinstance(job["age_days"], int)


def test_label_umur_di_badan_kartu_dipakai_bila_tidak_ada_elemen_tanggal(bot):
    kartu = Kartu("Inventory Control Staff\nPT Contoh\nBandung\n3 hari yang lalu")

    job = bot._parse_job_card(kartu)

    assert job["date_posted"] == "3 hari yang lalu"
    assert job["age_days"] == 3


def test_label_baru_saja_berarti_nol_hari(bot):
    job = bot._parse_job_card(
        Kartu("Inventory Control Staff\nPT Contoh\nBandung\nBaru saja")
    )

    assert job["date_posted"] == "Baru saja"
    assert job["age_days"] == 0


def test_kartu_tanpa_tanggal_tetap_date_unknown(bot):
    """Jangan mengarang 0 hari: tanpa tanggal = None (DATE_UNKNOWN)."""
    job = bot._parse_job_card(
        Kartu("Inventory Control Staff\nPT Contoh\nBandung")
    )

    assert job["date_posted"] == ""
    assert job["age_days"] is None


def test_lowongan_9_hari_dari_kartu_ditolak_max_age_days(basis, bot):
    """Bukti ujung-ke-ujung: tanggal kartu → umur → SKIP (dulu selalu lolos)."""
    kemarin_sembilan = (
        datetime.now(ZoneInfo("Asia/Jakarta")) - timedelta(days=9)
    ).strftime("%Y-%m-%d")
    kartu = Kartu(
        "Inventory Control Staff\nPT Contoh\nBandung",
        ElemenTiruan(kemarin_sembilan, {"datetime": kemarin_sembilan}),
    )

    job = bot._parse_job_card(kartu)
    lolos, alasan = JobFilter().should_apply(job)

    assert job["age_days"] == 9
    assert lolos is False
    assert "MAX_AGE_DAYS=7" in alasan


def test_lowongan_7_hari_dari_kartu_tetap_diterima(basis, bot):
    tujuh = (
        datetime.now(ZoneInfo("Asia/Jakarta")) - timedelta(days=7)
    ).strftime("%Y-%m-%d")
    kartu = Kartu(
        "Inventory Control Staff\nPT Contoh\nBandung\n7 hari yang lalu",
        ElemenTiruan(tujuh, {"datetime": tujuh}),
    )

    assert JobFilter().should_apply(bot._parse_job_card(kartu))[0] is True


# ------------------------------------------------ 2. banner logo tidak bohong ---
def _teks_banner(keluaran: str) -> str:
    """Ratakan keluaran tabel Rich (garis kotak + pembungkusan per kata)."""
    bersih = keluaran.replace("│", " ").replace("┃", " ").replace("┏", " ")
    bersih = bersih.replace("┡", " ").replace("└", " ").replace("┗", " ")
    return " ".join(bersih.split())


def test_banner_logo_aktif_sesuai_config(capsys, monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", True)

    cli.show_config()
    keluaran = _teks_banner(capsys.readouterr().out)

    assert "Wajib ada logo perusahaan" in keluaran
    assert "Aktif (JobStreet & Glints; Indeed tanpa logo)" in keluaran


def test_banner_logo_mati_saat_require_company_logo_false(capsys, monkeypatch):
    """Dulu banner selalu 'Aktif' walau cek-logo mencetak false."""
    monkeypatch.setattr(config, "require_company_logo", False)

    cli.show_config()
    keluaran = _teks_banner(capsys.readouterr().out)

    # Baris logo harus menyatakan mati, bukan "Aktif" seperti versi lama.
    assert "Tidak aktif — lowongan tanpa logo tetap dilamar" in keluaran


def test_banner_run_memakai_config_yang_sama(capsys, monkeypatch):
    """Banner `run` (main.py) dulu punya teks 'Aktif' hardcoded sendiri."""
    import main

    monkeypatch.setattr(config, "require_company_logo", False)

    main.AutoApplyEngine._print_config(object.__new__(main.AutoApplyEngine))
    keluaran = _teks_banner(capsys.readouterr().out)

    assert "Tidak aktif — lowongan tanpa logo tetap dilamar" in keluaran
    assert "Aktif (JobStreet & Glints" not in keluaran


def test_teks_wajib_logo_satu_sumber(monkeypatch):
    monkeypatch.setattr(config, "require_company_logo", False)
    assert "Tidak aktif" in config.teks_wajib_logo()

    monkeypatch.setattr(config, "require_company_logo", True)
    assert config.teks_wajib_logo().startswith("Aktif")


# --------------------------------------------- 3. Chrome putus saat riset Glints ---
class CacheRisetKosong:
    def kunci(self, *args, **kwargs):
        return "kunci"

    def ambil(self, *args, **kwargs):
        return None

    def simpan(self, *args, **kwargs):
        return None


class BotCari:
    """Bot tiruan: `cari` melempar galat pada panggilan ke-`gagal_pada`."""

    lokasi_didukung = False

    def __init__(self, gagal_pada=0, galat=None, job_id="glints:1"):
        self.panggilan = 0
        self.gagal_pada = gagal_pada
        self.galat = galat or ConnectionResetError(10054, "reset")
        self.job_id = job_id

    def cari(self, keyword, halaman=0, location=""):
        self.panggilan += 1
        if self.panggilan == self.gagal_pada:
            raise self.galat
        return [
            {
                "job_id": f"{self.job_id}-{keyword}",
                "title": "Inventory Control Staff",
                "company": "PT Contoh",
                "location": "Bandung",
                "salary": "Rp 7.000.000",
                "description": "gudang, SAP",
                "url": f"https://glints.com/x/{keyword}",
                "date_posted": "1 hari lalu",
                "age_days": 1,
                "has_logo": True,
            }
        ]


@pytest.fixture(autouse=True)
def _cache_dan_jeda(monkeypatch):
    monkeypatch.setattr(glints, "cache_riset", CacheRisetKosong())
    monkeypatch.setattr(glints, "JEDA_PENCARIAN", 0)


def test_connection_reset_berhenti_rapi_dengan_hasil_sebagian(capsys):
    bot = BotCari(gagal_pada=2)

    hasil = glints.kumpulkan_lowongan(
        bot, ["inventory control", "ppic", "warehouse"], 1, lokasi=["Bandung"]
    )

    assert [job["job_id"] for job in hasil] == ["glints:1-inventory control"]
    assert "Koneksi ke Chrome terputus" in capsys.readouterr().out


def test_connection_reset_tidak_melempar_traceback():
    """Dulu `ConnectionResetError` naik sampai CLI dan mencetak traceback."""
    bot = BotCari(gagal_pada=1)

    assert glints.kumpulkan_lowongan(bot, ["ppic"], 1, lokasi=["Bandung"]) == []


@pytest.mark.parametrize(
    "galat",
    [
        ConnectionResetError(10054, "reset"),
        ConnectionRefusedError(10061, "refused"),
        OSError("socket ditutup"),
    ],
)
def test_semua_galat_koneksi_ditangani(galat):
    bot = BotCari(gagal_pada=1, galat=galat)

    assert glints.kumpulkan_lowongan(bot, ["ppic"], 1, lokasi=["Bandung"]) == []


def test_jeda_dipakai_antar_pencarian(monkeypatch):
    jeda = []
    monkeypatch.setattr(glints, "JEDA_PENCARIAN", 1.5)
    monkeypatch.setattr(glints.time, "sleep", lambda detik: jeda.append(detik))

    glints.kumpulkan_lowongan(
        BotCari(), ["inventory control", "ppic", "warehouse"], 1,
        lokasi=["Bandung"],
    )

    # Pencarian pertama langsung jalan; sisanya diberi jeda.
    assert jeda == [1.5, 1.5]


def test_ctrl_c_saat_riset_tidak_mencetak_traceback(monkeypatch, capsys):
    bot = BotCari(gagal_pada=1, galat=KeyboardInterrupt())

    class BotUji(BotCari):
        def init_browser(self):
            return None

        def tutup(self):
            self.ditutup = True

    bot = BotUji(gagal_pada=1, galat=KeyboardInterrupt())
    monkeypatch.setattr(glints, "GlintsBot", lambda: bot)

    hasil = glints.daftar_kandidat(["ppic"], max_pages=1)

    assert hasil == []
    assert bot.ditutup is True
    assert "Dihentikan oleh Anda" in capsys.readouterr().out


def test_umur_modul_dipakai_untuk_label_relatif():
    """Sanity: label yang dipakai kartu memang dikenali parser umur bersama."""
    assert umur.umur_dari_teks("3 hari yang lalu") == 3
    assert umur.umur_dari_teks("Baru saja") == 0
    assert umur.umur_dari_teks("30+ hari yang lalu") == 30


# ------------------------------------------- 4. ringkasan dry-run per situs ---
def test_dry_run_menghitung_per_situs_dan_tanpa_tanggal(basis, monkeypatch):
    monkeypatch.setattr(cli, "db", basis)
    monkeypatch.setattr(jf_modul, "db", basis)

    def simpan(job_id, title, sumber, date_posted):
        basis.add_job(
            {
                "job_id": job_id,
                "title": title,
                "company": "PT Contoh",
                "location": "Bandung",
                "salary": "Rp 7.000.000",
                "description": "stok gudang, SAP",
                "url": f"https://{sumber}.com/x/{job_id[-1]}",
                "date_posted": date_posted,
                "has_logo": 1,
            }
        )

    simpan("glints:a", "Inventory Control Staff", "glints", "1 hari lalu")
    simpan("indeed:b", "Sales Executive", "indeed", "2 hari lalu")
    simpan("jobstreet:c", "Inventory Control Staff", "jobstreet", "20 hari lalu")
    simpan("jobstreet:d", "Staff PPIC", "jobstreet", "")

    hasil = cli.dry_run("", 10)

    assert hasil["per_situs"]["glints"]["apply"] == 1
    assert hasil["per_situs"]["indeed"].get("judul") == 1
    assert hasil["per_situs"]["jobstreet"].get("terlalu_tua") == 1
    assert hasil["tanpa_tanggal"] == 1
    # Kolom "Tanpa tgl" menghitung baris yang tanggalnya tak terbaca
    # (diloloskan, bukan ditolak) — dulu kolom ini selalu 0.
    assert hasil["per_situs"]["jobstreet"]["tanpa_tgl"] == 1
    assert hasil["per_situs"]["glints"]["tanpa_tgl"] == 0
    assert hasil["per_situs"]["indeed"]["tanpa_tgl"] == 0


# ------------------------------- 5. `cek-tanggal`: asal-usul tanggal per kartu ---
def test_diagnosa_tanggal_menyebut_sumber_dan_nilai(bot):
    kartu = Kartu(
        "Inventory Control Staff\nPT Contoh",
        ElemenTiruan("15 Nov 2026", {"datetime": "2026-11-15T03:00:00.000Z"}),
    )

    info = bot._diagnosa_tanggal(kartu)

    assert info["hasil"] == "2026-11-15"
    assert info["sumber"] != "tidak ada"
    assert info["elemen"], "elemen tanggal yang ditemukan harus dilaporkan"


def test_diagnosa_tanggal_label_kartu_dilaporkan(bot):
    info = bot._diagnosa_tanggal(Kartu("Staff PPIC\nPT Lain\n3 hari yang lalu"))

    assert info["hasil"] == "3 hari yang lalu"
    assert info["sumber"] == "label kartu"
    assert info["label"] == "3 hari yang lalu"


def test_diagnosa_tanggal_tanpa_tanggal(bot):
    info = bot._diagnosa_tanggal(Kartu("Staff PPIC\nPT Lain\nBandung"))

    assert info["hasil"] == ""
    assert info["sumber"] == "tidak ada"


def test_cek_tanggal_menampilkan_tabel_dan_hitungan(capsys, monkeypatch, bot):
    """Perintah baru harus melaporkan kartu bertanggal dan tanpa tanggal."""
    import scraper

    kartu_bertanggal = Kartu(
        "Inventory Control Staff\nPT Contoh",
        ElemenTiruan("15 Nov 2026", {"datetime": "2026-11-15T03:00:00.000Z"}),
    )
    kartu_tanpa = Kartu("Staff PPIC\nPT Lain\nBandung")

    class BotTiruan:
        def __init__(self):
            pass

        def init_browser(self):
            pass

        def login(self):
            return True

        def close(self):
            pass

        def search_jobs(self, keyword, page=1, location=None, saat_kartu=None):
            for kartu in (kartu_bertanggal, kartu_tanpa):
                if saat_kartu:
                    saat_kartu(kartu, bot._parse_job_card(kartu))
            return []

        def _diagnosa_tanggal(self, kartu):
            return bot._diagnosa_tanggal(kartu)

    monkeypatch.setattr(scraper, "JobStreetBot", BotTiruan)

    cli.cek_tanggal(limit=5, max_pages=1, keywords="inventory")

    keluaran = _teks_banner(capsys.readouterr().out)
    assert "Pembacaan tanggal lowongan" in keluaran
    assert "DATE_UNKNOWN" in keluaran
    assert "1 dari 2 kartu" in keluaran
    assert "tidak ada lamaran dikirim" in keluaran


# ------------------------- 6. `laporan-bukti`: tabel bukti dari database nyata ---
def _isi_db(db):
    for jid, judul, pt, lok, tgl in (
        ("jobstreet:a", "Team Fleet Warehouse - Bogor", "Astro", "Bogor", "2026-11-01"),
        ("jobstreet:b", "Staff PPIC", "PT Tanpa Tanggal", "Bandung", ""),
        ("glints:d", "Inventory Controller", "PT Glints", "Bandung", "3 hari lalu"),
        ("indeed:e", "Sales Executive", "PT Sales", "Bandung", "1 hari lalu"),
    ):
        db.add_job(
            {
                "job_id": jid,
                "title": judul,
                "company": pt,
                "location": lok,
                "salary": "Rp 7.000.000",
                "description": "stok gudang, SAP",
                "url": f"https://x/{jid}",
                "date_posted": tgl,
                "has_logo": 1,
            }
        )


def test_laporan_bukti_menghasilkan_markdown_dari_database(
    basis, capsys, monkeypatch
):
    tetap = datetime(2026, 11, 17, 9, 0)
    monkeypatch.setattr(umur, "sekarang_wib", lambda *a, **k: tetap)
    monkeypatch.setattr(cli, "db", basis)
    _isi_db(basis)

    hasil = cli.laporan_bukti("", 10)

    keluaran = capsys.readouterr().out
    assert "## Tabel bukti per lowongan" in keluaran
    assert "| platform | job_id | judul |" in keluaran
    assert "| jobstreet | jobstreet:a |" in keluaran
    assert "## Ringkasan per situs" in keluaran
    assert "| jobstreet | 2 |" in keluaran
    assert "tanpa tanggal tersimpan" in keluaran  # 1 baris DATE_UNKNOWN
    assert hasil["total"] == 4
    assert hasil["per_situs"]["jobstreet"]["tanpa_tgl"] == 1


def test_laporan_bukti_menyaring_situs(basis, capsys, monkeypatch):
    monkeypatch.setattr(cli, "db", basis)
    _isi_db(basis)

    hasil = cli.laporan_bukti("glints", 10)
    keluaran = capsys.readouterr().out

    assert hasil["total"] == 1
    assert "glints:d" in keluaran
    assert "jobstreet:a" not in keluaran


def test_laporan_bukti_simpan_ke_reports(basis, capsys, monkeypatch, tmp_path):
    import laporan as laporan_modul

    monkeypatch.setattr(cli, "db", basis)
    monkeypatch.setattr(laporan_modul, "FOLDER_LAPORAN", tmp_path)
    _isi_db(basis)

    cli.laporan_bukti("", 5, simpan=True)

    berkas = list(tmp_path.glob("bukti-live-*.md"))
    assert len(berkas) == 1
    isi = berkas[0].read_text(encoding="utf-8")
    assert isi.startswith("# Bukti validasi dari database")
    assert "| platform | job_id |" in isi
    assert "Tersimpan" in capsys.readouterr().out
