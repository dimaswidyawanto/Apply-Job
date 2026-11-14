from pathlib import Path

import pytest
from selenium.common.exceptions import NoSuchElementException

import auto_apply
import scraper
from auto_apply import APPLY_SELECTORS, SUBMIT_SELECTORS, AutoApplier
from config import config


@pytest.fixture(autouse=True)
def _bersihkan(monkeypatch, tmp_path):
    """Test tidak boleh menulis folder debug/ atau database di repo."""
    monkeypatch.setattr(config, "auto_apply_debug", False)
    monkeypatch.chdir(tmp_path)


class FakeElement:
    def __init__(
        self,
        text="",
        attrs=None,
        visible=True,
        enabled=True,
        selected=False,
        on_click=None,
        options=None,
        parent=None,
    ):
        self.text = text
        self.options = options or []
        self.parent = parent
        self._attrs = attrs or {}
        self._visible = visible
        self._enabled = enabled
        self._selected = selected
        self._on_click = on_click

    def is_displayed(self):
        return self._visible

    def is_enabled(self):
        return self._enabled

    def is_selected(self):
        return self._selected

    def get_attribute(self, name):
        return self._attrs.get(name)

    def click(self):
        if self._on_click:
            self._on_click()

    def send_keys(self, value):
        self._attrs["value"] = value
        self.text = str(value)

    def find_elements(self, by, selector):
        if selector == "option":
            return list(self.options)
        return []

    def find_element(self, by, selector):
        if selector == ".." and self.parent is not None:
            return self.parent
        raise NoSuchElementException(selector)


class FakeSelect:
    """Pengganti selenium Select untuk elemen palsu."""

    def __init__(self, element):
        self.element = element

    def select_by_visible_text(self, text):
        pilihan = [item.text for item in getattr(self.element, "options", [])]
        if text not in pilihan:
            raise ValueError(text)
        self.element._attrs["value"] = text

    @property
    def first_selected_option(self):
        """Selaras dengan selenium: opsi yang sedang terpilih."""
        teks = self.element._attrs.get("value", "")
        return FakeElement(text=teks)


class FakeDriver:
    def __init__(self, elements=None, body="", url="https://id.jobstreet.com/job/1"):
        self.elements = elements or {}
        self.body = body
        self.current_url = url
        self.window_handles = ["main"]
        self.switch_to = self
        self.opened_urls = []

    def get(self, url):
        self.opened_urls.append(url)
        self.current_url = url

    def find_elements(self, by, selector):
        return list(self.elements.get(selector, []))

    def find_element(self, by, selector):
        if selector == "body":
            return FakeElement(text=self.body)
        raise NoSuchElementException(selector)

    def execute_script(self, *args, **kwargs):
        return None

    def window(self, handle):
        return None

    def close(self):
        return None


class FakeWait:
    def until(self, condition):
        return True


@pytest.fixture(autouse=True)
def tanpa_jeda(monkeypatch):
    monkeypatch.setattr(auto_apply.time, "sleep", lambda *_: None)
    monkeypatch.setattr(scraper.time, "sleep", lambda *_: None)


def tombol_apply(driver, teks_sukses="Lamaran Anda telah dikirim"):
    def klik():
        driver.body = teks_sukses

    return FakeElement(text="Lamar", on_click=klik)


# ----------------------------------------------------------------------
# Umur lowongan
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "label, expected",
    [
        ("Hari ini", 0),
        ("Baru", 0),
        ("Kemarin", 1),
        ("3 hari yang lalu", 3),
        ("30+ hari yang lalu", 30),
        ("2 minggu yang lalu", 14),
        ("1 bulan yang lalu", 30),
        ("", None),
        ("tanpa tanggal", None),
    ],
)
def test_parse_listing_age(label, expected):
    assert scraper.JobStreetBot._parse_listing_age(label) == expected


def test_search_memakai_urutan_terbaru(monkeypatch):
    monkeypatch.setattr(config, "location", "Bandung")
    monkeypatch.setattr(config, "sort_mode", "ListedDate")
    monkeypatch.setattr(config, "max_age_days", 7)

    driver = FakeDriver()
    bot = scraper.JobStreetBot()
    bot.driver = driver
    bot.wait = FakeWait()

    bot.search_jobs("PPIC", page=2)

    url = driver.opened_urls[0]
    assert "sortmode=ListedDate" in url
    assert "daterange=7" in url
    assert "where=Bandung" in url
    assert "page=2" in url


# ----------------------------------------------------------------------
# Auto apply
# ----------------------------------------------------------------------
def test_auto_apply_sukses():
    driver = FakeDriver()
    driver.elements = {APPLY_SELECTORS[0]: [tombol_apply(driver)]}

    hasil = AutoApplier(driver).apply({"url": driver.current_url})

    assert hasil.applied is True
    assert hasil.status == "applied"


def test_auto_apply_tombol_tidak_ada(monkeypatch):
    monkeypatch.setattr(config, "auto_apply_step_timeout", 0)

    hasil = AutoApplier(FakeDriver()).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "tidak ditemukan" in hasil.reason.lower()


def test_auto_apply_berhenti_bila_perlu_unggah_berkas():
    driver = FakeDriver()
    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        "input[type='file']": [
            FakeElement(attrs={"value": "", "required": "true"})
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "unggah" in hasil.reason.lower()


def test_auto_apply_klik_kirim_lamaran():
    driver = FakeDriver()

    def klik_kirim():
        driver.body = "Terima kasih telah melamar"

    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        SUBMIT_SELECTORS[0]: [
            FakeElement(text="Kirim lamaran", on_click=klik_kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is True
    assert hasil.status == "applied"


def test_auto_apply_sudah_dilamar():
    driver = FakeDriver(body="Anda sudah melamar lowongan ini")

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "already_applied"


def test_auto_apply_lamar_di_situs_perusahaan():
    driver = FakeDriver()
    driver.elements = {
        "button": [FakeElement(text="Lamar di situs perusahaan")],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "situs perusahaan" in hasil.reason.lower()


def test_auto_apply_tab_eksternal():
    driver = FakeDriver()

    def buka_tab_luar():
        driver.window_handles = ["main", "luar"]
        driver.current_url = "https://karier.contoh.com/apply/123"

    driver.elements = {
        APPLY_SELECTORS[0]: [
            FakeElement(text="Lamar", on_click=buka_tab_luar)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "situs lain" in hasil.reason.lower()
    assert "karier.contoh.com" in hasil.reason


def test_auto_apply_berhenti_bila_halaman_login():
    driver = FakeDriver()
    driver.elements = {"input[type='password']": [FakeElement()]}

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "login_required"
    assert "login" in hasil.reason.lower()


def test_auto_apply_berhenti_bila_dialihkan_ke_signin():
    class DriverDialihkan(FakeDriver):
        def get(self, url):
            self.current_url = "https://id.jobstreet.com/signin?redirect=job"

    hasil = AutoApplier(DriverDialihkan()).apply(
        {"url": "https://id.jobstreet.com/job/1"}
    )

    assert hasil.status == "login_required"


def test_auto_apply_isi_cover_letter_otomatis(monkeypatch):
    monkeypatch.setattr(config, "cover_letter", "Saya siap bergabung.")
    monkeypatch.setattr(config, "resume_path", "")

    driver = FakeDriver()

    def klik_kirim():
        driver.body = "Lamaran Anda telah dikirim"

    textarea = FakeElement(attrs={"value": "", "required": "true"})
    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        "textarea": [textarea],
        SUBMIT_SELECTORS[0]: [
            FakeElement(text="Kirim lamaran", on_click=klik_kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is True
    assert textarea.get_attribute("value") == "Saya siap bergabung."


def test_auto_apply_unggah_cv_otomatis(monkeypatch, tmp_path):
    cv = tmp_path / "cv.pdf"
    cv.write_text("contoh", encoding="utf-8")

    monkeypatch.setattr(config, "cover_letter", "")
    monkeypatch.setattr(config, "resume_path", str(cv))

    driver = FakeDriver()

    def klik_kirim():
        driver.body = "Application submitted"

    berkas = FakeElement(attrs={"value": ""})
    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        "input[type='file']": [berkas],
        SUBMIT_SELECTORS[0]: [
            FakeElement(text="Kirim lamaran", on_click=klik_kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is True
    assert berkas.get_attribute("value") == str(cv)


def test_auto_apply_tanpa_konfigurasi_tetap_berhenti_aman(monkeypatch):
    monkeypatch.setattr(config, "cover_letter", "")
    monkeypatch.setattr(config, "resume_path", "")

    driver = FakeDriver()
    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        "input[type='file']": [
            FakeElement(attrs={"value": "", "required": "true"})
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "RESUME_PATH" in hasil.reason


def test_auto_apply_lewati_setelah_batas_waktu(monkeypatch):
    """Alur tidak dikenali dalam 3 detik -> dilewati, lanjut lowongan berikutnya."""
    monkeypatch.setattr(config, "auto_apply_step_timeout", 3)

    jam = {"t": 100.0}
    monkeypatch.setattr(auto_apply.time, "time", lambda: jam["t"])
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )

    driver = FakeDriver()
    driver.elements = {APPLY_SELECTORS[0]: [FakeElement(text="Lamar")]}

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "3 detik" in hasil.reason


def test_auto_apply_dialihkan_sebelum_klik():
    class DriverDialihkan(FakeDriver):
        def get(self, url):
            self.current_url = "https://karir.perusahaan.com/lowongan/9"

    hasil = AutoApplier(DriverDialihkan()).apply(
        {"url": "https://id.jobstreet.com/job/1"}
    )

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "dialihkan ke situs lain" in hasil.reason.lower()
    assert "karir.perusahaan.com" in hasil.reason


def test_auto_apply_dialihkan_setelah_klik():
    driver = FakeDriver()

    def pindah_ke_luar():
        driver.current_url = "https://jobs.workday.com/apply/123"

    driver.elements = {
        APPLY_SELECTORS[0]: [
            FakeElement(text="Lamar", on_click=pindah_ke_luar)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "dialihkan ke situs lain" in hasil.reason.lower()
    assert "jobs.workday.com" in hasil.reason


def test_unggah_berkas_opsional_tidak_menghalangi():
    """Bagian "Documents included" punya input file opsional -> jangan blokir."""
    driver = FakeDriver()

    def klik_kirim():
        driver.body = "Lamaran Anda telah dikirim"

    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        "input[type='file']": [FakeElement(attrs={"value": ""})],
        SUBMIT_SELECTORS[0]: [
            FakeElement(text="Kirim lamaran", on_click=klik_kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is True


def test_halaman_review_and_submit_dikirim():
    driver = FakeDriver()

    def ke_halaman_review():
        driver.current_url = (
            "https://id.jobstreet.com/job/95549275/apply/review"
        )
        driver.elements["button[type='submit']"] = [
            FakeElement(
                text="Submit application",
                on_click=lambda: setattr(
                    driver, "body", "Lamaran Anda telah dikirim"
                ),
            )
        ]

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_halaman_review)]
    }

    hasil = AutoApplier(driver).apply(
        {"url": "https://id.jobstreet.com/job/95549275"}
    )

    assert hasil.applied is True
    assert hasil.status == "applied"


def test_halaman_review_tanpa_tombol_kirim_dilewati(monkeypatch):
    monkeypatch.setattr(config, "auto_apply_submit_timeout", 20)
    monkeypatch.setattr(config, "auto_apply_debug", False)

    jam = {"t": 100.0}
    monkeypatch.setattr(auto_apply.time, "time", lambda: jam["t"])
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )

    driver = FakeDriver()

    def ke_halaman_review():
        driver.current_url = (
            "https://id.jobstreet.com/job/95549275/apply/review"
        )

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_halaman_review)]
    }

    hasil = AutoApplier(driver).apply(
        {"url": "https://id.jobstreet.com/job/95549275"}
    )

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "review and submit" in hasil.reason.lower()


def test_halaman_review_tombol_kirim_tanpa_penanda():
    """Tombol "Kirim" biasa di halaman review tetap harus diklik."""
    driver = FakeDriver()

    def ke_halaman_review():
        driver.current_url = (
            "https://id.jobstreet.com/job/95549275/apply/review"
        )
        driver.elements["button"] = [
            FakeElement(text="Kembali"),
            FakeElement(
                text="Kirim",
                on_click=lambda: setattr(
                    driver, "body", "Lamaran Anda telah dikirim"
                ),
            ),
        ]

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_halaman_review)]
    }

    hasil = AutoApplier(driver).apply(
        {"url": "https://id.jobstreet.com/job/95549275"}
    )

    assert hasil.applied is True


def test_dump_debug_menyimpan_berkas(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "auto_apply_debug", True)

    driver = FakeDriver()
    driver.page_source = "<html></html>"
    driver.save_screenshot = lambda path: Path(path).write_bytes(b"x")

    AutoApplier(driver)._dump_debug({"job_id": "123", "title": "Staff PPIC"})

    berkas = sorted(item.suffix for item in (tmp_path / "debug").iterdir())
    assert berkas == [".html", ".png", ".txt"]


def _select(pertanyaan, opsi):
    element = FakeElement(text="", attrs={"aria-label": pertanyaan, "value": ""})
    element.options = [FakeElement(text=teks) for teks in opsi]
    return element


def test_jawab_pertanyaan_otomatis(monkeypatch):
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)
    monkeypatch.setattr(config, "expected_salary", "5000000")
    monkeypatch.setattr(config, "years_experience", 3.0)
    monkeypatch.setattr(config, "education_level", "S1")

    gaji = _select(
        "Berapa gaji bulanan yang kamu inginkan?",
        ["Rp 4 Jt", "Rp 5 Jt", "Rp 6 Jt"],
    )
    pengalaman = _select(
        "How many years' experience do you have as an Inventory Controller?",
        ["0 years", "2 years", "3 years", "More than 5 years"],
    )
    kepala = _select(
        "Berapa tahun pengalaman kerjamu sebagai Kepala PPIC?",
        ["0 years", "1 year", "2 years"],
    )

    driver = FakeDriver(elements={"select": [gaji, pengalaman, kepala]})
    gagal = AutoApplier(driver).jawab_pertanyaan()

    assert gagal == []
    assert gaji.get_attribute("value") == "Rp 5 Jt"
    assert pengalaman.get_attribute("value") == "3 years"
    # Bukan jabatan yang pernah dipegang -> jawab 0 tahun, jangan mengarang.
    assert kepala.get_attribute("value") == "0 years"


def test_pertanyaan_tak_dikenal_tidak_dijawab():
    aneh = _select("Warna favorit kamu?", ["Merah", "Biru"])
    driver = FakeDriver(elements={"select": [aneh]})

    gagal = AutoApplier(driver).jawab_pertanyaan()

    assert gagal == ["Warna favorit kamu?"]
    assert aneh.get_attribute("value") == ""


def test_auto_answer_bisa_dimatikan(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_questions", False)

    gaji = _select("Berapa gaji yang diharapkan?", ["Rp 5 Jt"])
    driver = FakeDriver(elements={"select": [gaji]})

    assert AutoApplier(driver).jawab_pertanyaan() == []
    assert gaji.get_attribute("value") == ""


def test_lanjut_tidak_diklik_berulang(monkeypatch):
    jam = {"t": 100.0}
    monkeypatch.setattr(auto_apply.time, "time", lambda: jam["t"])
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )

    jumlah = {"klik": 0}

    def klik():
        jumlah["klik"] += 1

    lanjut = FakeElement(text="Continue", on_click=klik)

    driver = FakeDriver(
        elements={
            APPLY_SELECTORS[0]: [FakeElement(text="Lamar")],
            "button": [lanjut],
        },
        body="Before you can continue with the application, please address "
        "the following issues: Berapa tahun pengalaman kerjamu sebagai "
        "Kepala PPIC? - Please make a selection",
    )

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert jumlah["klik"] <= 2
    assert "please address" in hasil.reason.lower()


def test_id_internal_dikenali():
    assert auto_apply.tampak_id_internal(
        "questionnaire.ID_Q_2BF1D9EB5B90F6EECBD28603F9D89656_V_2"
    )
    assert auto_apply.tampak_id_internal("questionnaire.ID_Q_368_V_2")
    assert not auto_apply.tampak_id_internal(
        "Berapa tahun pengalaman kerjamu sebagai Kepala PPIC?"
    )


def test_ambil_pertanyaan_abaikan_teks_opsi():
    teks = "Rp 4 Jt\nBerapa gaji bulanan yang kamu inginkan?\nRp 5 Jt"

    assert auto_apply.ambil_pertanyaan(
        teks, ["Rp 4 Jt", "Rp 5 Jt"]
    ) == "Berapa gaji bulanan yang kamu inginkan?"


def test_pertanyaan_dari_galat_dibersihkan():
    galat = (
        "before you can continue with the application, please address the "
        "following issues: apakah kamu memiliki pengalaman pemrosesan "
        "dokumen? - please make a selection berapa tahun pengalaman "
        "kerjamu sebagai staff administrasi? tidak ada pengalaman"
    )

    teks = auto_apply.pertanyaan_dari_galat(galat)

    assert teks.startswith("apakah kamu memiliki pengalaman")
    assert "please make a selection" not in teks


def test_pertanyaan_dari_wadah_dipakai_bukan_id_internal(monkeypatch):
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)
    monkeypatch.setattr(config, "expected_salary", "5000000")
    monkeypatch.setattr(config, "years_experience", 3.0)

    wadah = FakeElement(
        text=(
            "Berapa tahun pengalaman kerjamu sebagai inventory controller?\n"
            "0 years\n2 years\n3 years"
        )
    )
    wadah.parent = None

    select = FakeElement(attrs={"name": "questionnaire.ID_Q_ABC123_V_2"})
    select.options = [
        FakeElement(text=teks) for teks in ("0 years", "2 years", "3 years")
    ]
    select.parent = wadah

    driver = FakeDriver(elements={"select": [select]})
    gagal = AutoApplier(driver).jawab_pertanyaan()

    assert select.get_attribute("value") == "3 years"
    assert gagal == []


def test_batas_17_id_internal_tidak_dilaporkan():
    """Pesan skip tidak boleh berisi ID internal saja."""
    wadah = FakeElement(text="Pilih warna kesukaanmu\nMerah\nBiru")
    select = FakeElement(attrs={"name": "questionnaire.ID_Q_XYZ789_V_1"})
    select.options = [FakeElement(text="Merah"), FakeElement(text="Biru")]
    select.parent = wadah

    driver = FakeDriver(elements={"select": [select]})
    gagal = AutoApplier(driver).jawab_pertanyaan()

    assert gagal == ["Pilih warna kesukaanmu"]


def test_radio_ya_tidak_dijawab(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_yes", True)

    wadah = FakeElement(text="Apakah kamu bersedia bekerja dalam shift?\nYa\nTidak")

    diklik = {}

    ya = FakeElement(attrs={"id": "r1", "name": "bersedia", "value": "ya"})
    tidak = FakeElement(attrs={"id": "r2", "name": "bersedia", "value": "tidak"})

    def pilih(item, nama):
        item._selected = True
        diklik[nama] = True

    ya._on_click = lambda: pilih(ya, "ya")
    tidak._on_click = lambda: pilih(tidak, "tidak")
    ya.parent = wadah
    tidak.parent = wadah

    driver = FakeDriver(elements={"input[type='radio']": [ya, tidak]})
    applier = AutoApplier(driver)
    monkeypatch.setattr(
        applier,
        "_label_untuk",
        lambda el: "Ya" if el is ya else "Tidak",
    )
    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: [ya, tidak] if selector == "input[type='radio']" else [],
    )

    gagal = applier.jawab_pertanyaan()

    assert gagal == []
    assert diklik == {"ya": True}


def test_kolom_teks_gaji_diisi(monkeypatch):
    monkeypatch.setattr(config, "expected_salary", "5000000")

    wadah = FakeElement(text="Berapa gaji yang kamu harapkan?")
    kolom = FakeElement(attrs={"value": ""})
    kolom.parent = wadah

    driver = FakeDriver(elements={"input[type='text']": [kolom]})
    AutoApplier(driver).jawab_pertanyaan()

    assert kolom.get_attribute("value") == "5000000"


def test_pengalaman_peran_lain_dijawab_nol(monkeypatch):
    from types import SimpleNamespace

    cfg = SimpleNamespace(
        education_level="S1",
        expected_salary="5000000",
        years_experience=3.0,
        experience_roles=["inventory", "ppic", "warehouse"],
        auto_answer_yes=True,
    )

    opsi = ["No experience", "1 year", "3 years", "5 years"]

    # Peran yang tidak pernah dijalani: jangan klaim 3 tahun.
    assert auto_apply.pilih_jawaban(
        "How many years' experience do you have as a Pharmacist in Charge?",
        opsi,
        cfg,
    ) == "No experience"

    # Peran yang sesuai pengalaman: 3 tahun.
    assert auto_apply.pilih_jawaban(
        "How many years' experience do you have as an Inventory Controller?",
        opsi,
        cfg,
    ) == "3 years"


def test_pengalaman_peran_lain_tanpa_opsi_nol_dilewati(monkeypatch):
    from types import SimpleNamespace

    cfg = SimpleNamespace(
        education_level="S1",
        expected_salary="5000000",
        years_experience=3.0,
        experience_roles=["inventory"],
        auto_answer_yes=True,
    )

    assert auto_apply.pilih_jawaban(
        "Berapa tahun pengalaman kerjamu sebagai perawat?",
        ["1 tahun", "3 tahun"],
        cfg,
    ) == ""


def test_sukses_terdeteksi_dari_modal():
    driver = FakeDriver(body="")
    driver.current_url = "https://id.jobstreet.com/job/1/apply"
    driver.elements = {
        "[role='dialog']": [FakeElement(text="Your application has been sent")]
    }

    assert AutoApplier(driver)._is_success() is True


def test_sukses_terdeteksi_dari_url():
    driver = FakeDriver(body="")
    driver.current_url = "https://id.jobstreet.com/my-application?success=1"

    assert AutoApplier(driver)._is_success() is True


def test_setelah_kirim_ditolak_validasi_berhenti(monkeypatch):
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)
    jam = {"t": 100.0}
    monkeypatch.setattr(auto_apply.time, "time", lambda: jam["t"])
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )

    driver = FakeDriver()

    jumlah = {"klik": 0}

    def kirim():
        jumlah["klik"] += 1
        driver.body = (
            "Before you can continue with the application, please address "
            "the following issues: what's your expected monthly salary? - "
            "please make a selection"
        )

    def ke_review():
        driver.current_url = "https://id.jobstreet.com/job/1/apply/review"

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_review)],
        "button[type='submit']": [
            FakeElement(text="Submit application", on_click=kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is False
    assert "isian wajib" in hasil.reason.lower()
    assert jumlah["klik"] == 1


def test_galat_server_diulang_sekali_lalu_berhasil(monkeypatch):
    """Banner "Something has gone wrong" -> muat ulang -> kirim kedua sukses."""
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)

    kelas = type("DriverMuatUlang", (FakeDriver,), {})

    driver = kelas()
    jumlah = {"klik": 0, "muat_ulang": 0}
    banner = (
        "Something has gone wrong. Please try again or contact "
        "Customer Service"
    )
    sukses = "Your application has been sent"

    def kirim():
        jumlah["klik"] += 1
        if jumlah["klik"] == 1:
            driver.body = banner
        else:
            driver.body = sukses

    def muat_ulang():
        jumlah["muat_ulang"] += 1
        driver.body = "Review and submit Documents included"

    driver.refresh = muat_ulang

    def ke_review():
        driver.current_url = "https://id.jobstreet.com/job/1/apply/review"

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_review)],
        "button[type='submit']": [
            FakeElement(text="Submit application", on_click=kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/1"})

    assert hasil.applied is True
    assert jumlah["klik"] == 2
    assert jumlah["muat_ulang"] == 1


def test_galat_server_dua_kali_dilewati(monkeypatch):
    """Galat server tetap ada setelah kirim kedua -> dilewati."""
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)

    kelas = type("DriverMuatUlangGagal", (FakeDriver,), {})
    driver = kelas()
    jumlah = {"klik": 0}
    banner = (
        "Something has gone wrong. Please try again or contact "
        "Customer Service"
    )

    def kirim():
        jumlah["klik"] += 1
        driver.body = banner

    def muat_ulang():
        driver.body = "Review and submit Documents included"

    driver.refresh = muat_ulang

    def ke_review():
        driver.current_url = "https://id.jobstreet.com/job/2/apply/review"

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_review)],
        "button[type='submit']": [
            FakeElement(text="Submit application", on_click=kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/2"})

    assert hasil.applied is False
    assert "something has gone wrong" in hasil.reason.lower()
    assert "2x" in hasil.reason
    assert jumlah["klik"] == 2


def test_galat_server_sebelum_klik_dimuat_ulang(monkeypatch):
    """Banner galat sudah tampil sejak halaman review dibuka -> dimuat ulang dulu."""
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)

    kelas = type("DriverBannerAwal", (FakeDriver,), {})
    driver = kelas()
    jumlah = {"klik": 0, "muat_ulang": 0}

    driver.body = "Something has gone wrong. Please try again"

    def muat_ulang():
        jumlah["muat_ulang"] += 1
        driver.body = "Review and submit Documents included"

    driver.refresh = muat_ulang

    def kirim():
        jumlah["klik"] += 1
        driver.body = "Your application has been sent"

    def ke_review():
        driver.current_url = "https://id.jobstreet.com/job/3/apply/review"

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_review)],
        "button[type='submit']": [
            FakeElement(text="Submit application", on_click=kirim)
        ],
    }

    hasil = AutoApplier(driver).apply({"url": "https://id.jobstreet.com/job/3"})

    assert hasil.applied is True
    assert jumlah["muat_ulang"] == 1
    assert jumlah["klik"] == 1


def test_tidak_klik_kirim_dua_kali_saat_masih_memproses(monkeypatch):
    """Selama halaman menampilkan "mengirim", tombol Kirim tidak ditekan lagi."""
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)

    jam = {"t": 500.0}
    driver = FakeDriver()
    jumlah = {"klik": 0}

    def jam_sekarang():
        # Setelah 6 detik, halaman menyatakan lamaran terkirim.
        if jam["t"] >= 506.0:
            driver.body = "Your application has been sent"
        return jam["t"]

    def tidur(detik=0):
        jam["t"] += detik

    monkeypatch.setattr(auto_apply.time, "time", jam_sekarang)
    monkeypatch.setattr(auto_apply.time, "sleep", tidur)

    def kirim():
        jumlah["klik"] += 1
        driver.body = "Mengirim lamaran, harap tunggu..."

    def ke_review():
        driver.current_url = "https://id.jobstreet.com/job/9/apply/review"

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_review)],
        "button[type='submit']": [
            FakeElement(text="Submit application", on_click=kirim)
        ],
    }

    hasil = AutoApplier(driver).apply(
        {"url": "https://id.jobstreet.com/job/9"}
    )

    assert hasil.applied is True
    assert jumlah["klik"] == 1


def test_klik_ulang_dibatasi_dua_kali(monkeypatch):
    """Bila tidak ada kemajuan, kirim hanya dicoba dua kali lalu berhenti."""
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)

    jam = {"t": 700.0}
    driver = FakeDriver()
    jumlah = {"klik": 0}

    monkeypatch.setattr(auto_apply.time, "time", lambda: jam["t"])
    monkeypatch.setattr(
        auto_apply.time,
        "sleep",
        lambda detik=0: jam.__setitem__("t", jam["t"] + detik),
    )

    def kirim():
        jumlah["klik"] += 1

    def ke_review():
        driver.current_url = "https://id.jobstreet.com/job/10/apply/review"

    driver.elements = {
        APPLY_SELECTORS[0]: [FakeElement(text="Lamar", on_click=ke_review)],
        "button[type='submit']": [
            FakeElement(text="Submit application", on_click=kirim)
        ],
    }

    hasil = AutoApplier(driver).apply(
        {"url": "https://id.jobstreet.com/job/10"}
    )

    assert hasil.applied is False
    assert jumlah["klik"] == 2
    assert "konfirmasi tidak muncul" in hasil.reason.lower()


# ----------------------------------------------------------------------
# Kuesioner yang belum terisi: beri waktu pengguna mengisinya
# ----------------------------------------------------------------------
def test_tunggu_jawaban_lanjut_setelah_diisi(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_wait", 5)
    applier = AutoApplier(FakeDriver())
    panggilan = {"n": 0}

    def jawab():
        panggilan["n"] += 1
        return ["Warna favorit?"] if panggilan["n"] < 3 else []

    monkeypatch.setattr(applier, "jawab_pertanyaan", jawab)
    monkeypatch.setattr(applier, "_validation_error", lambda: "")

    assert applier._tunggu_jawaban("Warna favorit?") == "lanjut"
    # Dua detik pertama masih kosong, detik ketiga sudah diisi pengguna.
    assert panggilan["n"] == 3


def test_tunggu_jawaban_habis_bila_tidak_diisi(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_wait", 3)
    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(applier, "jawab_pertanyaan", lambda: ["Warna favorit?"])
    monkeypatch.setattr(applier, "_validation_error", lambda: "wajib diisi")

    jeda = {"n": 0}

    def tidur(detik=0):
        jeda["n"] += 1

    monkeypatch.setattr(auto_apply.time, "sleep", tidur)

    assert applier._tunggu_jawaban("Warna favorit?") == "habis"
    assert jeda["n"] == 3


def test_tunggu_jawaban_nol_langsung_dilewati(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_wait", 0)
    applier = AutoApplier(FakeDriver())

    jeda = {"n": 0}
    monkeypatch.setattr(
        auto_apply.time, "sleep", lambda *_: jeda.__setitem__("n", jeda["n"] + 1)
    )

    assert applier._tunggu_jawaban("Warna favorit?") == "habis"
    assert jeda["n"] == 0


def test_tunggu_jawaban_mendeteksi_lamaran_terkirim(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_wait", 5)
    driver = FakeDriver()
    applier = AutoApplier(driver)

    def jawab():
        # Pengguna menekan Kirim sendiri di jendela Chrome.
        driver.body = "Lamaran Anda telah dikirim"
        return ["Warna favorit?"]

    monkeypatch.setattr(applier, "jawab_pertanyaan", jawab)

    assert applier._tunggu_jawaban("Warna favorit?") == "applied"


def test_kuesioner_diisi_pengguna_lalu_terkirim(monkeypatch):
    """Alur penuh: bot menunggu pengguna mengisi kuesioner, lalu Kirim diklik."""
    monkeypatch.setattr(config, "auto_answer_wait", 4)
    monkeypatch.setattr(config, "auto_apply_step_timeout", 2)
    monkeypatch.setattr(config, "auto_apply_submit_timeout", 2)

    driver = FakeDriver()

    def klik_kirim():
        driver.body = "Lamaran Anda telah dikirim"

    driver.elements = {
        APPLY_SELECTORS[0]: [tombol_apply(driver, teks_sukses="")],
        SUBMIT_SELECTORS[0]: [
            FakeElement(text="Kirim lamaran", on_click=klik_kirim)
        ],
    }

    applier = AutoApplier(driver)
    keadaan = {
        "pertanyaan": ["Warna favorit kamu?"],
        "galat": "please address the following issues",
        "menunggu": False,
        "tidur": 0,
    }

    monkeypatch.setattr(
        applier, "jawab_pertanyaan", lambda: list(keadaan["pertanyaan"])
    )
    monkeypatch.setattr(applier, "_validation_error", lambda: keadaan["galat"])

    panggilan = {"tunggu": 0}
    asli_tunggu = applier._tunggu_jawaban

    def bungkus_tunggu(rinci=""):
        panggilan["tunggu"] += 1
        keadaan["menunggu"] = True
        return asli_tunggu(rinci)

    monkeypatch.setattr(applier, "_tunggu_jawaban", bungkus_tunggu)

    def tidur(detik=0):
        # Pengguna mengisi kuesioner setelah dua detik menunggu.
        if not keadaan["menunggu"]:
            return
        keadaan["tidur"] += 1
        if keadaan["tidur"] >= 2:
            keadaan["pertanyaan"] = []
            keadaan["galat"] = ""

    monkeypatch.setattr(auto_apply.time, "sleep", tidur)

    hasil = applier.apply({"url": driver.current_url})

    assert panggilan["tunggu"] >= 1, "jalur tunggu pengguna tidak dipakai"
    assert hasil.applied is True
    assert hasil.status == "applied"


# ---------------------------------------------- radio tersembunyi (JobStreet) ---
def test_radio_tersembunyi_tetap_dijawab(monkeypatch):
    """JobStreet menyembunyikan input asli; labelnya yang terlihat.

    Tanpa toleransi ini, pertanyaan "do you have ... experience?" tidak pernah
    dijawab dan lamaran berakhir di daftar manual.
    """
    monkeypatch.setattr(config, "auto_answer_yes", True)

    wadah = FakeElement(
        text="Do you have production support experience?\nYes\nNo"
    )
    ya = FakeElement(
        attrs={"id": "a1", "name": "dukungan", "value": "yes"}, visible=False
    )
    tidak = FakeElement(
        attrs={"id": "a2", "name": "dukungan", "value": "no"}, visible=False
    )
    label_ya = FakeElement(text="Yes")
    label_tidak = FakeElement(text="No")

    ya.parent = tidak.parent = wadah
    label_ya._on_click = lambda: setattr(ya, "_selected", True)
    label_tidak._on_click = lambda: setattr(tidak, "_selected", True)

    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: {
            "input[type='radio']": [ya, tidak],
            "label[for='a1']": [label_ya],
            "label[for='a2']": [label_tidak],
        }.get(selector, []),
    )
    monkeypatch.setattr(
        applier, "_label_untuk", lambda el: "Yes" if el is ya else "No"
    )

    gagal = applier.jawab_pertanyaan()

    assert gagal == []
    assert ya.is_selected() is True


def test_pilih_opsi_mengirim_event_perubahan(monkeypatch):
    """Nilai dropdown harus disertai event input+change agar form React ikut."""
    monkeypatch.setattr(auto_apply, "Select", FakeSelect)

    skrip = []

    class DriverEvent(FakeDriver):
        def execute_script(self, *args, **kwargs):
            skrip.append(args[0] if args else "")

    select = FakeElement(attrs={"name": "q"}, options=[])
    select.options = [
        FakeElement(text=teks) for teks in ("0 years", "2 years", "3 years")
    ]

    applier = AutoApplier(DriverEvent())
    berhasil = applier._pilih_opsi(select, "3 years")

    assert berhasil is True
    assert select.get_attribute("value") == "3 years"
    assert any("dispatchEvent" in str(item) for item in skrip)


# ---------------------------------------- label opsi dari wadah (JobStreet) ---
def test_label_opsi_diambil_dari_wadah_induk(monkeypatch):
    """Opsi JobStreet kadang hanya berupa teks di wadah, tanpa label[for].

    Tanpa fallback ini, daftar opsi kosong sehingga pertanyaan ya/tidak tidak
    pernah dijawab walau polanya sudah dikenali.
    """
    wadah_ya = FakeElement(text="Yes")
    wadah_tidak = FakeElement(text="No")
    ya = FakeElement(attrs={"name": "dukungan"}, visible=False, parent=wadah_ya)
    tidak = FakeElement(attrs={"name": "dukungan"}, visible=False, parent=wadah_tidak)

    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(applier, "_find_all", lambda selector: [])

    assert applier._label_untuk(ya) == "Yes"
    assert applier._label_untuk(tidak) == "No"


def test_aria_labelledby_dipakai_untuk_label_opsi(monkeypatch):
    rujukan = FakeElement(text="Tidak")
    opsi = FakeElement(attrs={"aria-labelledby": "opsi-tidak"})

    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: [rujukan] if selector == "[id='opsi-tidak']" else [],
    )

    assert applier._label_untuk(opsi) == "Tidak"


def test_wadah_banyak_input_tidak_dipakai_sebagai_label(monkeypatch):
    """Wadah pertanyaan (memuat semua opsi) tidak boleh jadi label opsi."""

    class WadahBanyakInput(FakeElement):
        def find_elements(self, by, selector):
            if selector == "input":
                return [FakeElement(), FakeElement()]
            return super().find_elements(by, selector)

    wadah = WadahBanyakInput(text="Do you have experience? Yes No")
    opsi = FakeElement(attrs={"name": "q"}, parent=wadah)

    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(applier, "_find_all", lambda selector: [])

    assert applier._label_untuk(opsi) == ""


def test_radio_dengan_label_dari_wadah_dijawab(monkeypatch):
    monkeypatch.setattr(config, "auto_answer_yes", True)

    pertanyaan = FakeElement(text="Do you have purchasing experience?")
    wadah_ya = FakeElement(text="Yes")
    wadah_tidak = FakeElement(text="No")
    ya = FakeElement(attrs={"name": "beli"}, visible=False, parent=wadah_ya)
    tidak = FakeElement(attrs={"name": "beli"}, visible=False, parent=wadah_tidak)
    pertanyaan.parent = None
    wadah_ya.parent = pertanyaan
    wadah_tidak.parent = pertanyaan

    def klik(item):
        item._selected = True

    ya._on_click = lambda: klik(ya)
    tidak._on_click = lambda: klik(tidak)

    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: [ya, tidak] if selector == "input[type='radio']" else [],
    )
    monkeypatch.setattr(
        applier,
        "_raw_text",
        lambda el: el.text if el.text else "",
    )
    monkeypatch.setattr(
        applier,
        "_pertanyaan",
        lambda el, opsi=(): "Do you have purchasing experience?",
    )

    gagal = applier.jawab_pertanyaan()

    assert gagal == []
    assert ya.is_selected() is True


# ------------------------------------------------- P1: perbaikan audit 15-20 ---
def test_karakter_tak_terlihat_dibuang_dari_label_tombol():
    """E-2: JobStreet menempelkan U+2060 pada label tombol.

    Sebelum diperbaiki, label "Submit application" tidak dikenali sehingga
    lamaran tidak pernah terkirim.
    """
    applier = AutoApplier(FakeDriver())

    assert applier._text(FakeElement(text="\u2060Submit application")) == (
        "submit application"
    )
    assert applier._text(FakeElement(text="Kirim\u200b lamaran\u00a0")) == (
        "kirim lamaran"
    )


def test_kunci_pertanyaan_abaikan_karakter_tak_terlihat():
    """E-2: kunci pertanyaan harus sama walau ada U+2060/NBSP."""
    import jawaban

    assert jawaban.kunci_pertanyaan("\u2060Do you have SAP experience?\u00a0") == (
        jawaban.kunci_pertanyaan("Do you have SAP experience?")
    )


def test_tombol_kirim_pilih_paling_bawah():
    """E-1: beberapa tombol cocok; yang diklik harus yang paling bawah."""
    atas = FakeElement(text="Submit application", attrs={"type": "button"})
    bawah = FakeElement(text="Submit application", attrs={"type": "button"})
    applier = AutoApplier(FakeDriver())

    class DriverAtasBawah(FakeDriver):
        def find_elements(self, by, selector):
            return [atas, bawah] if selector == "button" else []

    applier = AutoApplier(DriverAtasBawah())

    assert applier._find_submit_button(review_page=True) is bawah


def test_tombol_navigasi_ditolak_sebagai_tombol_kirim():
    """E-1: "Lanjut"/"Kembali"/"Review" bukan tombol kirim."""
    applier = AutoApplier(FakeDriver())

    for label in ("Lanjut", "Kembali", "Back", "Review application", "Batal"):
        assert applier._boleh_jadi_tombol_kirim(FakeElement(text=label)) is False

    assert applier._boleh_jadi_tombol_kirim(
        FakeElement(text="Submit application")
    ) is True


def test_skala_dijawab_tingkat_terendah():
    """E-4: pertanyaan berskala dijawab jujur dengan tingkat terendah."""
    assert auto_apply.pilih_jawaban_radio(
        "How would you rate your Japanese language skills?",
        ["Fluent", "Beginner", "Native"],
    ) == "Beginner"

    assert auto_apply.pilih_jawaban_radio(
        "Seberapa mahir kamu dengan Microsoft Excel?",
        ["Ahli", "Menengah", "Dasar"],
    ) == "Dasar"


def test_ya_tidak_varian_dikenali(monkeypatch):
    """E-4: varian "Yes, I have" / "Ya, benar" tetap dijawab Ya."""
    monkeypatch.setattr(config, "auto_answer_yes", True)

    assert auto_apply.pilih_jawaban_radio(
        "Do you have production scheduling experience?",
        ["Yes, I have", "No, I don't"],
    ) == "Yes, I have"

    assert auto_apply.pilih_jawaban_radio(
        "Apakah kamu memiliki pengalaman pembelian?",
        ["Ya", "Tidak"],
    ) == "Ya"


def test_radio_tanpa_name_dikelompokkan_per_pertanyaan(monkeypatch):
    """E-4: JobStreet kadang tidak memberi atribut name pada radio.

    Sebelum diperbaiki, radio seperti ini diabaikan total.
    """
    monkeypatch.setattr(config, "auto_answer_yes", True)

    ya = FakeElement(attrs={"id": "b1"}, visible=False)
    tidak = FakeElement(attrs={"id": "b2"}, visible=False)
    ya._on_click = lambda: setattr(ya, "_selected", True)
    tidak._on_click = lambda: setattr(tidak, "_selected", True)

    applier = AutoApplier(FakeDriver())
    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: [ya, tidak] if selector == "input[type='radio']" else [],
    )
    monkeypatch.setattr(
        applier, "_label_untuk", lambda el: "Ya" if el is ya else "Tidak"
    )
    monkeypatch.setattr(applier, "_label_terlihat", lambda el: True)
    monkeypatch.setattr(
        applier,
        "_pertanyaan",
        lambda el, opsi=(): "Apakah kamu memiliki pengalaman pembelian?",
    )

    gagal = applier.jawab_pertanyaan()

    assert gagal == []
    assert ya.is_selected() is True


def _checkbox_driver(opsi, monkeypatch, applier):
    kotak = [
        FakeElement(text=label, attrs={"name": "keahlian", "value": label},
                    visible=False)
        for label in opsi
    ]
    for item in kotak:
        item._on_click = lambda el=item: setattr(el, "_selected", True)

    monkeypatch.setattr(
        applier,
        "_find_all",
        lambda selector: kotak if selector == "input[type='checkbox']" else [],
    )
    monkeypatch.setattr(
        applier, "_label_untuk", lambda el: el.get_attribute("value") or ""
    )
    monkeypatch.setattr(applier, "_label_terlihat", lambda el: True)
    monkeypatch.setattr(
        applier,
        "_pertanyaan",
        lambda el, opsi=(): "Which skills do you have?",
    )
    return kotak


def test_checkbox_skill_pengguna_dicentang(monkeypatch):
    """E-3: kotak centang keterampilan yang dikuasai pengguna dicentang."""
    monkeypatch.setattr(config, "auto_answer_yes", True)
    monkeypatch.setattr(config, "skill_keywords", ["Excel", "SAP"])
    monkeypatch.setattr(config, "title_keywords", [])

    applier = AutoApplier(FakeDriver())
    kotak = _checkbox_driver(["Excel", "SAP", "AutoCAD"], monkeypatch, applier)

    gagal = applier.jawab_pertanyaan()

    assert gagal == []
    assert [item.is_selected() for item in kotak] == [True, True, False]


def test_checkbox_tanpa_kecocokan_pilih_none(monkeypatch):
    """E-3: bila tak ada yang cocok, jawab jujur "None of the above"."""
    monkeypatch.setattr(config, "auto_answer_yes", True)
    monkeypatch.setattr(config, "skill_keywords", ["Excel"])
    monkeypatch.setattr(config, "title_keywords", [])

    applier = AutoApplier(FakeDriver())
    kotak = _checkbox_driver(
        ["AutoCAD", "None of the above"], monkeypatch, applier
    )

    gagal = applier.jawab_pertanyaan()

    assert gagal == []
    assert kotak[0].is_selected() is False
    assert kotak[1].is_selected() is True


def test_checkbox_tak_dikenal_masuk_manual(monkeypatch):
    """E-3: kotak centang tanpa opsi jujur tidak ditebak, masuk daftar manual."""
    monkeypatch.setattr(config, "auto_answer_yes", True)
    monkeypatch.setattr(config, "skill_keywords", ["Excel"])
    monkeypatch.setattr(config, "title_keywords", [])

    applier = AutoApplier(FakeDriver())
    kotak = _checkbox_driver(["AutoCAD", "Photoshop"], monkeypatch, applier)

    gagal = applier.jawab_pertanyaan()

    assert gagal == ["Which skills do you have?"]
    assert [item.is_selected() for item in kotak] == [False, False]


def test_nama_berkas_debug_aman_untuk_glints():
    """job_id Glints berbentuk "glints:<uuid>" — titik dua tidak sah di Windows.

    Dulu dump debug Glints selalu gagal ditulis tanpa pesan.
    """
    assert auto_apply.nama_berkas_aman("glints:441c0814-5d02") == (
        "glints-441c0814-5d02"
    )
    assert auto_apply.nama_berkas_aman("") == "lowongan"
    assert auto_apply.nama_berkas_aman("  a/b\\c  ") == "a-b-c"


def test_dump_debug_tersimpan_untuk_job_id_glints(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "auto_apply_debug", True)
    monkeypatch.chdir(tmp_path)

    applier = AutoApplier(FakeDriver(body="Halaman aneh"))
    applier._dump_debug({"job_id": "glints:441c0814", "title": "PPIC"})

    berkastxt = list((tmp_path / "debug").glob("*.txt"))

    assert len(berkastxt) == 1
    assert ":" not in berkastxt[0].name
    assert berkastxt[0].read_text(encoding="utf-8").startswith("URL:")
