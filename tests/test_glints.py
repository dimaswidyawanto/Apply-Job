"""Uji modul Glints: pembacaan kartu, filter lokasi, dan peta tombol."""

import pytest
from selenium.common.exceptions import NoSuchElementException

import auto_apply
import glints
from auto_apply import AutoApplier
from glints import GlintsApplier, id_dari_url, lokasi_cocok, rapikan_kartu


class Elemen:
    def __init__(self, text="", on_click=None):
        self.text = text
        self._on_click = on_click

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def get_attribute(self, name):
        return None

    def click(self):
        if self._on_click:
            self._on_click()

    def send_keys(self, value):  # noqa: ARG002
        return None


class Driver:
    """Driver tiruan minimal untuk memanggil AutoApplier.apply()."""

    def __init__(self, body="", url="https://glints.com/id/opportunities/jobs/x/"):
        self.body = body
        self.current_url = url
        self.window_handles = ["main"]
        self.switch_to = self
        self.elements = {}

    def get(self, url):
        self.current_url = url

    def find_elements(self, by, selector):
        return list(self.elements.get(selector, []))

    def find_element(self, by, selector):
        if selector == "body":
            return Elemen(text=self.body)
        raise NoSuchElementException(selector)

    def execute_script(self, *args, **kwargs):
        return None

    def window(self, handle):  # noqa: ARG002
        return None


URL_UJI = (
    "https://glints.com/id/opportunities/jobs/admin-warehouse/"
    "b5f8d754-afd9-4f0c-a618-360afe12248c"
)


@pytest.fixture(autouse=True)
def tanpa_jeda(monkeypatch):
    """Jangan benar-benar menunggu: waktu di mesin lamaran dibuat palsu."""
    monkeypatch.setattr(glints.time, "sleep", lambda *_: None)

    jam = {"t": 100.0}
    monkeypatch.setattr(auto_apply.time, "time", lambda: jam["t"])
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )


# ----------------------------------------------------------------------
# URL & kartu lowongan
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "url, expected",
    [
        (URL_UJI, "b5f8d754-afd9-4f0c-a618-360afe12248c"),
        (URL_UJI + "?utm_referrer=explore&traceInfo=abc",
         "b5f8d754-afd9-4f0c-a618-360afe12248c"),
        ("https://glints.com/id/opportunities/jobs/warehouse", ""),
        ("https://id.jobstreet.com/job/95678629", ""),
        ("", ""),
    ],
)
def test_id_dari_url(url, expected):
    assert id_dari_url(url) == expected


def test_rapikan_kartu_lengkap():
    job = rapikan_kartu(
        {
            "url": URL_UJI,
            "title": "  Admin   Warehouse ",
            "company": "PT Bangun Selaras Bersama",
            "location": "Bekasi, Jawa Barat",
            "salary": "Rp 2-3jt",
            "text": "Admin Warehouse Rp 2-3jt Penuh Waktu",
        }
    )

    assert job["job_id"] == "glints:b5f8d754-afd9-4f0c-a618-360afe12248c"
    assert job["title"] == "Admin Warehouse"
    assert job["company"] == "PT Bangun Selaras Bersama"
    assert job["location"] == "Bekasi, Jawa Barat"
    assert job["source"] == "glints"
    assert job["sudah_dilamar"] is False


def test_rapikan_kartu_menandai_sudah_dilamar():
    job = rapikan_kartu(
        {
            "url": URL_UJI,
            "title": "Warehouse",
            "text": "Warehouse Sudah Dilamar",
        }
    )

    assert job["sudah_dilamar"] is True


def test_rapikan_kartu_tanpa_judul_diabaikan():
    assert rapikan_kartu({"url": URL_UJI, "title": "  "}) is None
    assert rapikan_kartu({"url": "https://glints.com/id/", "title": "X"}) is None
    assert rapikan_kartu("bukan dict") is None


# ----------------------------------------------------------------------
# Filter lokasi
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "lokasi, daftar, expected",
    [
        ("Bekasi, Jawa Barat", ["Bandung", "Bekasi"], True),
        ("Kab. Tangerang, Banten", ["Tangerang"], True),
        ("Surabaya, Jawa Timur", ["Bandung", "Bekasi"], False),
        ("", ["Bandung"], True),
        ("Bekasi", [], True),
    ],
)
def test_lokasi_cocok(lokasi, daftar, expected):
    assert lokasi_cocok(lokasi, daftar) is expected


# ----------------------------------------------------------------------
# Peta situs pada mesin lamaran
# ----------------------------------------------------------------------
def test_glints_mengenali_domainnya_sendiri():
    applier = GlintsApplier(Driver())

    assert applier._is_situs_url(URL_UJI) is True
    assert applier._is_situs_url("https://id.jobstreet.com/job/1") is False


def test_auto_applier_bawaan_tetap_jobstreet():
    applier = AutoApplier(Driver())

    assert applier._is_situs_url("https://id.jobstreet.com/job/1") is True
    assert applier._is_situs_url(URL_UJI) is False


def test_lowongan_khusus_aplikasi_dilewati():
    driver = Driver(body="Lamar 1x tap di aplikasi")
    hasil = GlintsApplier(driver).apply({"url": URL_UJI, "title": "Warehouse"})

    assert hasil.applied is False
    assert "aplikasi mobile" in hasil.reason.lower()


def test_tombol_lamar_sekarang_dikenali_sebagai_kirim():
    """Glints memakai "Lamar Sekarang" sebagai tombol kirim sesungguhnya."""
    assert "lamar sekarang" in GlintsApplier.submit_texts
    assert "lamar" in GlintsApplier.apply_texts


def test_glints_memakai_teks_sukses_bahasa_indonesia():
    driver = Driver(body="Lamaran berhasil dikirim")
    applier = GlintsApplier(driver)

    assert applier._is_success() is True


# ----------------------------------------------------------------------
# Aturan gaji minimal
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Waktu tunggu & pesan diagnostik (dari uji nyata di PC pengguna)
# ----------------------------------------------------------------------
def test_glints_memakai_waktu_tunggu_lebih_panjang():
    """Formulir Glints berupa modal; 3 detik terlalu singkat."""
    applier = GlintsApplier(Driver())

    assert applier.step_timeout >= 12
    assert applier.submit_timeout >= 30


def test_penghalang_profil_belum_lengkap_terdeteksi():
    driver = Driver(body="Lengkapi profil kamu dulu untuk melamar")
    alasan = GlintsApplier(driver)._blocker()

    assert "profil" in alasan.lower()


def test_penghalang_unggah_cv_terdeteksi():
    driver = Driver(body="Silakan unggah CV terbaru kamu")
    alasan = GlintsApplier(driver)._blocker()

    assert "cv" in alasan.lower()


def test_pesan_alur_tidak_dikenali_menyebut_tombol():
    driver = Driver()
    driver.elements = {
        "button": [Elemen(text="Simpan"), Elemen(text="Bagikan")],
    }

    pesan = GlintsApplier(driver)._pesan_alur_tidak_dikenali()

    assert "simpan" in pesan.lower()
    assert "bagikan" in pesan.lower()


def test_chrome_tertutup_jadi_pesan_jelas():
    class DriverMati(Driver):
        def get(self, url):
            raise glints.WebDriverException(
                "invalid session id: session deleted as the browser has closed"
            )

    bot = glints.GlintsBot()
    bot.driver = DriverMati()

    with pytest.raises(glints.ChromeTertutup):
        bot.lamar({"url": URL_UJI, "title": "Uji"})


# ----------------------------------------------------------------------
# Lowongan yang hanya bisa dilamar lewat aplikasi Glints
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "teks, expected",
    [
        # Badge "Lamar & chat di aplikasi" juga muncul pada lowongan yang
        # bisa dilamar di web, jadi BUKAN alasan melewati lowongan.
        ("LAMAR & CHAT DI APLIKASI", ""),
        ("Lamar 1x tap di aplikasi", "lamar 1x tap di aplikasi"),
        ("1x tap di aplikasi", "1x tap di aplikasi"),
        ("Lamar", ""),
        ("", ""),
    ],
)
def test_khusus_aplikasi(teks, expected):
    assert glints.khusus_aplikasi(teks) == expected


def test_kartu_menandai_lowongan_khusus_aplikasi():
    job = rapikan_kartu(
        {
            "url": URL_UJI,
            "title": "Admin Warehouse",
            "text": "Admin Warehouse Rp 2-3jt Lamar 1x tap di aplikasi",
        }
    )

    assert job["khusus_aplikasi"] is True


def test_kartu_biasa_tidak_ditandai():
    job = rapikan_kartu(
        {
            "url": URL_UJI,
            "title": "Admin Warehouse",
            "text": "Admin Warehouse Rp 5-6jt Lamar",
        }
    )

    assert job["khusus_aplikasi"] is False


def test_lowongan_hanya_aplikasi_dilewati(monkeypatch):
    """Halaman yang hanya menawarkan lamar lewat aplikasi -> dilewati jelas."""
    jam = {"t": 200.0}
    monkeypatch.setattr(
        auto_apply.time, "time", lambda: jam["t"]
    )
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )

    driver = Driver(body="Lamar 1x tap di aplikasi")
    hasil = GlintsApplier(driver).apply({"url": URL_UJI, "title": "Warehouse"})

    assert hasil.applied is False
    assert "aplikasi mobile" in hasil.reason.lower()
    assert "1x tap" in hasil.reason.lower()


def test_tombol_lamar_dipilih_yang_persis():
    """"Lamar 1x tap di aplikasi" bukan tombol lamar di web."""
    driver = Driver()
    aplikasi = Elemen(text="Lamar 1x tap di aplikasi")
    biasa = Elemen(text="Lamar")
    driver.elements = {"button": [aplikasi, biasa]}

    tombol = GlintsApplier(driver)._cari_tombol_lamar()

    assert tombol is biasa


def test_tombol_lamar_hanya_aplikasi_tidak_dipilih():
    driver = Driver()
    driver.elements = {"button": [Elemen(text="Lamar 1x tap di aplikasi")]}

    assert GlintsApplier(driver)._cari_tombol_lamar() is None


def test_tombol_kirim_pesan_bukan_kirim_lamaran():
    """Tombol "Kirim pesan" di Glints tidak boleh dianggap kirim lamaran."""
    driver = Driver(body="Lamar pekerjaan ini")
    driver.elements = {
        "button[type='submit']": [Elemen(text="Kirim pesan")],
    }

    assert GlintsApplier(driver)._find_submit_button() is None


def test_tombol_kirim_lamaran_tetap_ditemukan():
    driver = Driver(body="Lamar pekerjaan ini")
    driver.elements = {
        "button[type='submit']": [Elemen(text="Kirim")],
    }

    tombol = GlintsApplier(driver)._find_submit_button()

    assert tombol is not None
    assert tombol.text == "Kirim"


# ---------------------------------------------- banner "sudah melamar" (Glints) ---
def test_banner_sudah_melamar_dihitung_terkirim(monkeypatch):
    """Kasus nyata 2026-11-11: Kirim diklik, Glints menampilkan banner

    "Kamu sudah melamar pekerjaan ini. Silakan cek aplikasi..." Sebelum
    diperbaiki, bot menunggu 45 detik lalu menandai lowongan "perlu manual"
    padahal lamarannya sudah masuk.
    """
    monkeypatch.setattr(auto_apply.config, "auto_apply_submit_timeout", 45)

    driver = Driver()
    banner = (
        "Kamu sudah melamar pekerjaan ini. Silakan cek aplikasi untuk "
        "pantau statusnya. Cek lamaran saya"
    )

    def kirim():
        driver.body = banner

    driver.elements = {
        GlintsApplier.apply_selectors[0]: [
            Elemen(text="Lamar", on_click=lambda: None)
        ],
        "button[type='submit']": [Elemen(text="Kirim", on_click=kirim)],
    }

    hasil = GlintsApplier(driver).apply(
        {"url": URL_UJI, "title": "PPIC", "job_id": "glints:abc"}
    )

    assert hasil.applied is True
    assert hasil.status == "applied"


def test_banner_sudah_melamar_dikenali_sebagai_sukses():
    driver = Driver(body="Kamu sudah melamar pekerjaan ini. Cek lamaran saya")
    applier = GlintsApplier(driver)

    assert applier._is_success() is True
    assert applier.is_already_applied() is True


def test_already_applied_tetap_dilewati_sebelum_klik():
    """Banner yang sudah ada sejak awal tetap "sudah dilamar", bukan "terkirim"."""
    driver = Driver(
        body="Kamu sudah melamar pekerjaan ini. Cek lamaran saya"
    )

    hasil = GlintsApplier(driver).apply({"url": URL_UJI, "title": "PPIC"})

    assert hasil.applied is False
    assert hasil.status == "already_applied"
