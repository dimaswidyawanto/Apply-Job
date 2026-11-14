"""Indeed: kenali dinding login & halaman verifikasi saat membuka lowongan.

Latar belakang (data nyata 2026-11-08): 20 dari 20 lamaran Indeed berakhir
`manual_required` dengan alasan yang persis sama — "Tombol Lamar tidak
ditemukan di halaman" — padahal halaman lowongannya terbuka normal. Dugaan
yang masuk akal: Indeed menampilkan ajakan masuk (sesi habis) atau halaman
verifikasi, bukan tombol Lamar. Sebelumnya kondisi itu tidak dikenali,
sehingga sesi tidak berhenti dan alasannya menyesatkan.

Tes memakai driver tiruan; tidak ada Chrome di sini.
"""

import auto_apply
import config as config_modul
import indeed
from config import config

URL_INDEED = "https://id.indeed.com/viewjob?jk=080cf6995f3ad2db"
URL_JOBSTREET = "https://id.jobstreet.com/id/job/12345"


class Elemen:
    def __init__(self, teks="", tampil=True):
        self.teks = teks
        self.tampil = tampil

    def is_displayed(self):
        return self.tampil

    def is_enabled(self):
        return True

    def get_attribute(self, nama):
        if nama == "textContent":
            return self.teks
        return ""

    @property
    def text(self):
        return self.teks


class Badan(Elemen):
    pass


class SwitchTo:
    def default_content(self):
        return None

    def frame(self, elemen):
        return None


class Driver:
    def __init__(self, teks="", tombol=None, url=URL_INDEED):
        self.teks = teks
        self.tombol = tombol or {}
        self.current_url = url
        self.page_source = "<html><body>uji</body></html>"
        self.switch_to = SwitchTo()
        self.gambar = 0

    def get(self, url):
        self.current_url = url

    def find_element(self, by, selector):
        if selector == "body":
            return Badan(self.teks)
        raise RuntimeError("tidak ada elemen")

    def find_elements(self, by, selector):
        return list(self.tombol.get(selector, []))

    def execute_script(self, *argumen):
        return None

    def save_screenshot(self, path):
        self.gambar += 1
        with open(path, "wb") as berkas:
            berkas.write(b"png")


def _tombol_lamar():
    return {indeed.IndeedApplier.apply_selectors[0]: [Elemen("Lamar sekarang")]}


# ------------------------------------------------------------ dinding login ---
def test_login_terdeteksi_saat_tanpa_tombol_lamar():
    applier = indeed.IndeedApplier(Driver("Masuk untuk melamar lowongan ini"))

    assert applier._is_login_page() is True


def test_login_tidak_dilewati_bila_tombol_lamar_ada():
    applier = indeed.IndeedApplier(
        Driver("Masuk untuk melamar. Lamar sekarang", tombol=_tombol_lamar())
    )

    assert applier._is_login_page() is False


def test_halaman_lowongan_normal_bukan_login():
    applier = indeed.IndeedApplier(Driver("Deskripsi pekerjaan", _tombol_lamar()))

    assert applier._is_login_page() is False


def test_teks_biasa_bukan_login():
    applier = indeed.IndeedApplier(Driver("Inventory staff, gaji Rp 5 juta"))

    assert applier._is_login_page() is False


# --------------------------------------------------------------- verifikasi ---
def test_verifikasi_diberi_alasan_jelas():
    applier = indeed.IndeedApplier(
        Driver("Verifikasi Anda adalah manusia untuk melanjutkan")
    )

    alasan = applier._blocker()

    assert "verifikasi" in alasan.lower()


def test_login_diberi_alasan_jelas_saat_tombol_tidak_ada():
    applier = indeed.IndeedApplier(Driver("Masuk untuk melamar lowongan ini"))

    alasan = applier._blocker()

    assert "login" in alasan.lower()


def test_blocker_kosong_untuk_halaman_normal():
    applier = indeed.IndeedApplier(Driver("Deskripsi pekerjaan biasa"))

    assert applier._blocker() == ""


# ------------------------------------------------ JobStreet tidak terpengaruh ---
def test_jobstreet_tetap_tanpa_deteksi_teks_login():
    applier = auto_apply.AutoApplier(
        Driver("Masuk untuk melamar", url=URL_JOBSTREET)
    )

    assert applier._is_login_page() is False


# ------------------------------------------------------ "sudah dilamar" aman ---
def test_kata_applied_sendirian_tidak_berarti_sudah_dilamar():
    driver = Driver("Applied filters: gudang", url=URL_INDEED)
    applier = indeed.IndeedApplier(driver)

    assert applier.is_already_applied() is False


def test_frasa_sudah_dilamar_tetap_dikenali():
    driver = Driver("Anda sudah melamar lowongan ini", url=URL_INDEED)
    applier = indeed.IndeedApplier(driver)

    assert applier.is_already_applied() is True


# ----------------------------------------------------------- bukti halaman ---
def test_bukti_disimpan_saat_tombol_tidak_ditemukan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "auto_apply_debug", False)

    applier = auto_apply.AutoApplier(Driver("Deskripsi biasa", url=URL_JOBSTREET))
    applier.step_timeout = 0.05

    hasil = applier._apply_alur(
        {"url": URL_JOBSTREET, "title": "lowongan uji", "job_id": "jobstreet:1"}
    )

    assert hasil.status == "manual_required"
    berkas = sorted((tmp_path / "debug").glob("*.html"))
    assert len(berkas) == 1
    assert (tmp_path / "debug").glob("*.txt")


def test_bukti_menghormati_batas_berkas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    applier = auto_apply.AutoApplier(Driver("Deskripsi biasa", url=URL_JOBSTREET))
    applier.debug_dumps = 5

    applier._dump_debug({"job_id": "jobstreet:1", "title": "x"}, paksa=True)

    assert not (tmp_path / "debug").exists()


def test_bukti_tidak_disimpan_tanpa_paksa_saat_flag_mati(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "auto_apply_debug", False)

    applier = auto_apply.AutoApplier(Driver("Deskripsi biasa", url=URL_JOBSTREET))
    applier._dump_debug({"job_id": "jobstreet:2", "title": "x"})

    assert not (tmp_path / "debug").exists()


def test_bukti_tersimpan_bila_flag_hidup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "auto_apply_debug", True)

    applier = auto_apply.AutoApplier(Driver("Deskripsi biasa", url=URL_JOBSTREET))
    applier._dump_debug({"job_id": "jobstreet:3", "title": "x"})

    assert len(list((tmp_path / "debug").glob("*.html"))) == 1


def test_penjaga_config_utuh():
    assert config_modul.config is config
