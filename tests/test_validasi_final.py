"""Validasi final: matriks keputusan, kuota, duplikat, diagnosa, penahan kirim.

Semua data di berkas ini adalah **FIXTURE** (dibuat di tes), bukan data LIVE
dari JobStreet/Glints/Indeed. Platform asli tidak dapat diakses dari lingkungan
pengujian, jadi yang dibuktikan di sini adalah SCORING ENGINE dan aturan
keputusan — bukan perilaku server platform.

Yang dibuktikan:
* nama perusahaan pendek tidak lagi salah dianggap blacklist (false positive);
* judul peran lain (sales/driver/…) tidak lolos hanya karena satu kata kunci;
* matriks 8 kategori lowongan → keputusan yang sama di Glints dan Indeed;
* batas umur inklusif (7 terima, 8 tolak) dan kebijakan DATE_UNKNOWN;
* duplikat = SKIP, kuota hanya bertambah untuk status `applied`;
* diagnosa kontrol formulir aman (tanpa isi sensitif) dan lengkap;
* isian wajib yang gagal diverifikasi MENAHAN pengiriman;
* dry-run menampilkan FOUND→DUPLICATE→FILTER→SCORE→AGE→DECISION tanpa kirim.
"""

import pytest

import auto_apply
import cli
import jawaban
import job_filter as jf_modul
import kuota
import umur
from config import config
from database import Database
from job_filter import JobFilter

SUMBER_DATA = "FIXTURE"


@pytest.fixture
def basis(tmp_path, monkeypatch):
    """Database sementara + aturan tetap supaya hasil tes tidak berubah."""
    db = Database(str(tmp_path / "validasi.db"))
    monkeypatch.setattr(jf_modul, "db", db)
    monkeypatch.setattr(jawaban, "db", db)

    monkeypatch.setattr(config, "require_company_logo", True)
    monkeypatch.setattr(config, "require_keyword_match", True)
    monkeypatch.setattr(config, "strict_location", False)
    monkeypatch.setattr(config, "min_salary", 4_500_000)
    monkeypatch.setattr(config, "max_experience", 5)
    monkeypatch.setattr(config, "max_age_days", 7)
    monkeypatch.setattr(config, "tolak_umur_tak_diketahui", False)
    monkeypatch.setattr(config, "locations", ["Bandung", "Jakarta"])
    monkeypatch.setattr(config, "blocked_companies", ["royal abadi", "ifa"])
    monkeypatch.setattr(config, "blacklist_companies", [])
    return db


def lowongan(**ubah) -> dict:
    """Satu lowongan FIXTURE; ubah bagian mana pun lewat kata kunci."""
    job = {
        "job_id": "glints:fixture-1",
        "title": "Inventory Control Staff",
        "company": "PT Sumber Makmur",
        "location": "Bandung",
        "salary": "Rp 7.000.000",
        "description": "Mengelola stok gudang, PPIC, memakai SAP dan Excel",
        "url": "https://glints.com/id/opportunities/jobs/fixture-1",
        "date_posted": "1 hari lalu",
        "age_days": 1,
        "has_logo": True,
        "sumber_data": SUMBER_DATA,
    }
    job.update(ubah)
    return job


# --------------------------------------------------------------- blacklist ---
@pytest.mark.parametrize(
    "nama",
    ["PT A", "Abadi", "PT Abadi Jaya", "Kafifa", "PT Sumber Makmur", ""],
)
def test_nama_pendek_tidak_salah_dianggap_blacklist(basis, nama):
    """False positive: "pt a" → "a" pernah cocok dengan "royal abadi"."""
    assert JobFilter()._perusahaan_dikecualikan(nama) == ""


@pytest.mark.parametrize(
    "nama, kunci",
    [
        ("PT Royal Abadi Sejahtera", "royal abadi"),
        ("Royal Abadi", "royal abadi"),
        ("PT IFA Indonesia", "ifa"),
    ],
)
def test_nama_blacklist_tetap_ditolak(basis, nama, kunci):
    assert JobFilter()._perusahaan_dikecualikan(nama) == kunci


def test_lowongan_perusahaan_blacklist_dilewati(basis):
    lolos, alasan = JobFilter().should_apply(
        lowongan(company="PT Royal Abadi Sejahtera")
    )

    assert lolos is False
    assert "blacklist" in alasan.lower()


# ------------------------------------------------------- judul peran lain ---
@pytest.mark.parametrize(
    "judul",
    ["Warehouse Sales Executive", "Driver Gudang", "Kasir Toko", "Teller"],
)
def test_judul_peran_lain_ditolak(basis, judul):
    """Satu kata kunci yang kebetulan sama tidak boleh meloloskan peran lain."""
    lolos, alasan = JobFilter().should_apply(lowongan(title=judul))

    assert lolos is False
    assert "minat" in alasan.lower() or "peran lain" in alasan.lower()


def test_judul_peran_lain_bisa_dimatikan(basis, monkeypatch):
    monkeypatch.setattr(config, "require_keyword_match", False)

    assert JobFilter().should_apply(
        lowongan(title="Warehouse Sales Executive")
    )[0] is True


@pytest.mark.parametrize(
    "judul",
    ["Inventory Control Staff", "Staff PPIC", "Warehouse Staff", "Material Planner"],
)
def test_judul_relevan_tetap_diterima(basis, judul):
    assert JobFilter().should_apply(lowongan(title=judul))[0] is True


# -------------------------------------------------------- matriks 8 kategori ---
MATRIKS = (
    # nama, perubahan FIXTURE, lolos, potongan alasan
    ("strong", {}, True, ""),
    ("weak", {"description": "", "salary": ""}, True, ""),
    ("wrong title", {"title": "Sales Executive"}, False, "minat"),
    ("wrong location", {"location": "Surabaya"}, False, "Lokasi"),
    ("too old", {"age_days": 9}, False, "MAX_AGE_DAYS=7"),
    ("unknown age", {"age_days": None}, True, ""),
    ("duplicate", {"sudah_dilamar": True}, False, "dilamar"),
)


@pytest.mark.parametrize("awalan", ["glints", "indeed"])
@pytest.mark.parametrize("nama, ubahan, lolos, potongan", MATRIKS)
def test_matriks_keputusan_sama_di_semua_platform(
    basis, monkeypatch, awalan, nama, ubahan, lolos, potongan
):
    """Aturan tunggal dipakai Glints dan Indeed (data FIXTURE)."""
    import glints
    import indeed

    if nama == "wrong location":
        monkeypatch.setattr(config, "strict_location", True)

    aturan = {"glints": glints.alasan_tidak_layak, "indeed": indeed.alasan_tidak_layak}
    job = lowongan(job_id=f"{awalan}:fixture-1", **dict(ubahan))
    alasan = aturan[awalan](job, JobFilter())

    assert job["sumber_data"] == SUMBER_DATA
    assert (alasan == "") is lolos, f"{nama} ({awalan}): {alasan}"
    assert potongan.lower() in alasan.lower(), f"{nama}: {alasan}"


def test_duplikat_database_dilewati(basis):
    basis.record_application("glints:fixture-1", "applied")

    lolos, alasan = JobFilter().should_apply(lowongan())

    assert lolos is False
    assert "sudah" in alasan.lower()


def test_cloudflare_lalu_retry_bukan_duplikat_dan_tanpa_kuota(basis, monkeypatch):
    """Blokir Cloudflare tidak dihitung lamaran: boleh dicoba lagi, kuota utuh."""
    monkeypatch.setattr(config, "max_apply_per_day", 50)
    basis.record_application("glints:fixture-1", "requires_human", "Cloudflare")

    assert basis.is_already_applied("glints:fixture-1") is False
    assert kuota.terpakai(basis, "glints") == 0
    assert JobFilter().should_apply(lowongan())[0] is True


# ------------------------------------------------------------------- umur ---
def test_batas_umur_inklusif(basis):
    assert JobFilter().should_apply(lowongan(age_days=7))[0] is True
    lolos, alasan = JobFilter().should_apply(lowongan(age_days=8))

    assert lolos is False
    assert "8 hari" in alasan and "MAX_AGE_DAYS=7" in alasan


def test_umur_tidak_terbaca_mengikuti_kebijakan(basis, monkeypatch):
    assert JobFilter().should_apply(lowongan(age_days=None))[0] is True

    monkeypatch.setattr(config, "tolak_umur_tak_diketahui", True)
    lolos, alasan = JobFilter().should_apply(lowongan(age_days=None))

    assert lolos is False
    assert "DATE_UNKNOWN" in alasan


def test_umur_tanpa_batas_tidak_menolak(basis, monkeypatch):
    monkeypatch.setattr(config, "max_age_days", 0)

    assert JobFilter().should_apply(lowongan(age_days=400))[0] is True
    assert umur.batas_umur(400, 0) == ""


# ------------------------------------------------------------------ kuota ---
@pytest.mark.parametrize(
    "status, terpakai",
    [
        ("applied", 1),
        ("failed", 0),
        ("requires_human", 0),
        ("duplicate", 0),
        ("skipped", 0),
    ],
)
def test_kuota_hanya_bertambah_untuk_applied(basis, monkeypatch, status, terpakai):
    monkeypatch.setattr(config, "max_apply_per_day", 50)
    basis.record_application("glints:fixture-1", status)

    assert kuota.terpakai(basis, "glints") == terpakai
    assert kuota.sisa(basis, config, "glints") == 50 - terpakai


def test_kuota_habis_tidak_memotong_kandidat_lain(basis, monkeypatch):
    monkeypatch.setattr(config, "max_apply_per_day", 1)
    basis.record_application("glints:fixture-0", "applied")

    assert kuota.potong([lowongan()], basis, config, "glints") == []


# --------------------------------------------------------------- diagnosa ---
class Elemen:
    """Elemen tiruan: tag, atribut, dan status terpilih."""

    def __init__(self, tag="div", teks="", attrs=None, terpilih=False):
        self.tag_name = tag
        self.text = teks
        self._attrs = dict(attrs or {})
        self._selected = terpilih

    def get_attribute(self, nama):
        return self._attrs.get(nama)

    def is_selected(self):
        return self._selected

    def is_displayed(self):
        return True

    def is_enabled(self):
        return True

    def click(self):
        return None

    def find_elements(self, by, selector):
        return []

    def find_element(self, by, selector):
        from selenium.common.exceptions import NoSuchElementException

        raise NoSuchElementException(selector)


def test_diagnosa_memuat_bidang_lengkap():
    catatan = auto_apply.diagnosa_kontrol(
        Elemen(
            tag="div",
            attrs={
                "role": "radio",
                "aria-label": "Opsi Ya",
                "name": "pengalaman",
                "aria-required": "true",
            },
        ),
        control_type="radio",
        text="Apakah Anda punya pengalaman ERP?",
        options=["Ya", "Tidak"],
        expected="Ya",
        detected="not_selected",
        verification="failed",
        failure="click_not_verified",
        wajib=True,
    )

    for bidang in auto_apply.BIDANG_DIAGNOSA:
        assert bidang in catatan

    assert catatan["CONTROL_TYPE"] == "radio"
    assert catatan["TAG"] == "div"
    assert catatan["ROLE"] == "radio"
    # `_atribut` menormalkan atribut ke huruf kecil (dipakai untuk pencocokan).
    assert catatan["ARIA_LABEL"] == "opsi ya"
    assert catatan["NAME"] == "pengalaman"
    assert catatan["AVAILABLE_OPTIONS"] == ["Ya", "Tidak"]
    assert catatan["VERIFICATION_RESULT"] == "failed"
    assert catatan["FAILURE_REASON"] == "click_not_verified"
    assert catatan["WAJIB"] is True

    baris = auto_apply.format_diagnosa(catatan)
    assert "CONTROL_TYPE=radio" in baris
    assert "AVAILABLE_OPTIONS=['Ya', 'Tidak']" in baris


def test_diagnosa_tidak_membocorkan_isi_sensitif():
    """Isi kolom (value), kata sandi, token, dan cookie tidak ikut dicatat."""
    isi_rahasia = Elemen(
        tag="input",
        attrs={
            "type": "password",
            "name": "kata_sandi",
            "value": "RahasiaSekali123",
            "data-token": "token-rahasia",
            "cookie": "sesi=abc",
        },
    )

    catatan = auto_apply.diagnosa_kontrol(
        isi_rahasia,
        control_type="teks",
        text="Kata sandi akun",
        expected="",
        failure="value_not_verified",
    )
    baris = auto_apply.format_diagnosa(catatan)

    assert "RahasiaSekali123" not in baris
    assert "token-rahasia" not in baris
    assert "sesi=abc" not in baris
    assert catatan["NAME"] == "kata_sandi"


def test_label_opsi_dibatasi_enam():
    catatan = auto_apply.diagnosa_kontrol(
        Elemen(tag="div", attrs={"role": "checkbox"}),
        control_type="checkbox",
        options=[f"Opsi {nomor}" for nomor in range(10)],
    )

    assert len(catatan["AVAILABLE_OPTIONS"]) == 6


# ------------------------------------------------- penahan kirim (guard) ---
class DriverPalsu:
    window_handles = ["utama"]

    def get(self, url):
        return None

    def find_elements(self, by, selector):
        return []

    def execute_script(self, *args, **kwargs):
        return None


class ApplierUji(auto_apply.AutoApplier):
    """AutoApplier tanpa browser: hanya menguji urutan keputusan."""

    def __init__(self, klik, diagnosa, jawaban_gagal=None):
        super().__init__(DriverPalsu())
        self.klik = klik
        self.diagnosa = diagnosa
        self._jawaban = list(jawaban_gagal or [])
        self.step_timeout = 1
        self.submit_timeout = 1

    # --- tahap sebelum formulir
    def _keluar_kerangka(self):
        return None

    def _is_login_page(self):
        return False

    def _is_external_page(self):
        return False

    def is_already_applied(self):
        return False

    def _alasan_lewati(self):
        return ""

    def _external_button_present(self):
        return False

    def _cari_tombol_lamar(self):
        return Elemen(tag="button", teks="Lamar")

    def _click(self, element):
        self.klik.append("klik")
        return True

    def _handle_new_window(self, handles_before):
        return ""

    def _masuk_kerangka_lamaran(self):
        return ""

    def _is_review_page(self):
        return False

    def _is_success(self):
        return False

    def _autofill(self):
        return None

    # --- formulir
    def jawab_pertanyaan(self):
        self._diagnosa_gagal = list(self.diagnosa)
        return self._jawaban

    def _validation_error(self):
        return ""

    def _blocker(self):
        return "berhenti-untuk-tes"

    def _find_submit_button(self, review_page):
        return Elemen(tag="button", teks="Kirim Lamaran")

    def _dump_debug(self, job, paksa=False):
        return None

    def _is_required(self, element):
        return (element.get_attribute("aria-required") or "") == "true"


def _diagnosa_wajib():
    return auto_apply.diagnosa_kontrol(
        Elemen(tag="div", attrs={"role": "radio", "aria-required": "true"}),
        control_type="radio",
        text="Apakah Anda bersedia ditempatkan di luar kota?",
        options=["Ya", "Tidak"],
        expected="Tidak",
        detected="not_selected",
        verification="failed",
        failure="click_not_verified",
        wajib=True,
    )


def test_isian_wajib_gagal_menahan_pengiriman():
    klik = []
    applier = ApplierUji(
        klik,
        diagnosa=[_diagnosa_wajib()],
        jawaban_gagal=["Apakah Anda bersedia ditempatkan di luar kota?"],
    )

    hasil = applier._apply_alur(lowongan())

    assert hasil.applied is False
    assert hasil.status == "manual_required"
    assert "TIDAK dikirim" in hasil.reason
    assert "FAILURE_REASON=click_not_verified" in hasil.reason
    # Tidak ada klik kirim: hanya klik tombol "Lamar".
    assert klik == ["klik"]


def test_diagnosa_opsional_tidak_menahan_pengiriman():
    klik = []
    opsional = dict(_diagnosa_wajib())
    opsional["WAJIB"] = False
    applier = ApplierUji(klik, diagnosa=[opsional])

    hasil = applier._apply_alur(lowongan())

    # Lolos penahan kirim, berhenti di blocker yang dipasang tes.
    assert hasil.status == "manual_required"
    assert hasil.reason == "berhenti-untuk-tes"


def test_tanpa_diagnosa_alur_berjalan_normal():
    applier = ApplierUji([], diagnosa=[])

    assert applier._diagnosa_wajib_gagal() == []
    assert applier._apply_alur(lowongan()).reason == "berhenti-untuk-tes"


# ------------------------------------------------------------ jejak/dry-run ---
def test_telusuri_keputusan_memuat_semua_tahap(basis):
    hasil = jf_modul.telusuri_keputusan(lowongan())

    assert [tahap["tahap"] for tahap in hasil["tahapan"]] == list(
        jf_modul.TAHAP_DRY_RUN
    )
    assert hasil["keputusan"] == "APPLY"
    assert hasil["platform"] == "glints"
    assert hasil["skor"] > 0


def test_telusuri_keputusan_menandai_tahap_penolak(basis):
    hasil = jf_modul.telusuri_keputusan(lowongan(age_days=9))
    tahap = {baris["tahap"]: baris for baris in hasil["tahapan"]}

    assert hasil["keputusan"] == "SKIP"
    assert tahap["AGE"]["status"] == "SKIP"
    assert tahap["FILTER"]["status"] == "OK"
    assert "MAX_AGE_DAYS=7" in tahap["DECISION"]["alasan"]


def test_dry_run_tidak_mengirim_lamaran(basis, monkeypatch):
    monkeypatch.setattr(cli, "db", basis)
    monkeypatch.setattr(jf_modul, "db", basis)

    basis.add_job(
        {
            "job_id": "glints:fixture-1",
            "title": "Inventory Control Staff",
            "company": "PT Sumber Makmur",
            "location": "Bandung",
            "salary": "Rp 7.000.000",
            "description": "stok gudang, SAP",
            "url": "https://glints.com/id/opportunities/jobs/fixture-1",
            "date_posted": "1 hari lalu",
            "has_logo": 1,
        }
    )
    basis.add_job(
        {
            "job_id": "indeed:fixture-2",
            "title": "Sales Executive",
            "company": "PT Lain",
            "location": "Surabaya",
            "salary": "",
            "description": "",
            "url": "https://id.indeed.com/viewjob?jk=fixture-2",
            "date_posted": "30 hari lalu",
            "has_logo": 1,
        }
    )

    hasil = cli.dry_run("", 5)

    assert hasil["total"] == 2
    assert hasil["apply"] == 1
    assert hasil["skip"] == 1
    assert basis.is_already_applied("glints:fixture-1") is False
    assert basis.is_already_applied("indeed:fixture-2") is False
    assert kuota.terpakai(basis, "glints") == 0
    assert kuota.terpakai(basis, "indeed") == 0
    assert basis.get_today_apply_count() == 0


# ------------------------------------------- diagnosa dari alur radio nyata ---
class DriverRadio:
    """Driver tiruan yang mengembalikan opsi radio untuk selector apa pun."""

    window_handles = ["utama"]

    def __init__(self, opsi):
        self.opsi = opsi

    def get(self, url):
        return None

    def find_elements(self, by, selector):
        # Hanya selector radio yang mengembalikan opsi; selector lain kosong
        # supaya kolom teks/checkbox tidak "berisi" elemen tiruan ini.
        return list(self.opsi) if "radio" in selector else []

    def execute_script(self, *args, **kwargs):
        return None


def _applier_radio(monkeypatch, opsi, pertanyaan):
    applier = auto_apply.AutoApplier(DriverRadio(opsi))
    monkeypatch.setattr(auto_apply.time, "sleep", lambda *_: None)
    monkeypatch.setattr(applier, "_visible", lambda *_: True)
    monkeypatch.setattr(applier, "_enabled", lambda *_: True)
    monkeypatch.setattr(applier, "_label_terlihat", lambda *_: True)
    monkeypatch.setattr(applier, "_pertanyaan", lambda el, pilihan=(): pertanyaan)
    monkeypatch.setattr(
        applier,
        "_label_untuk",
        lambda el: el.text or (el.get_attribute("aria-label") or ""),
    )
    return applier


def test_radio_wajib_yang_tidak_terjawab_merekam_diagnosa(monkeypatch, basis):
    monkeypatch.setattr(config, "auto_answer_questions", True)
    opsi = [
        Elemen(
            "div",
            "Ya",
            {"role": "radio", "aria-checked": "false", "aria-required": "true"},
        ),
        Elemen("div", "Tidak", {"role": "radio", "aria-checked": "false"}),
    ]
    applier = _applier_radio(monkeypatch, opsi, "Bersedia lembur?")

    gagal = applier.jawab_pertanyaan()
    wajib = applier._diagnosa_wajib_gagal()

    assert gagal, "pertanyaan radio yang gagal harus dilaporkan"
    assert wajib, "isian wajib yang gagal harus tercatat sebagai penahan kirim"
    assert wajib[0]["CONTROL_TYPE"] == "radio"
    assert wajib[0]["VERIFICATION_RESULT"] == "failed"
    assert wajib[0]["FAILURE_REASON"] in (
        "no_safe_answer",
        "click_not_verified",
        "no_option_label_read",
    )
    assert wajib[0]["TEXT"] == "Bersedia lembur?"
    assert wajib[0]["AVAILABLE_OPTIONS"] == ["Ya", "Tidak"]


def test_radio_terjawab_tanpa_diagnosa(monkeypatch, basis):
    monkeypatch.setattr(config, "auto_answer_questions", True)

    opsi = [
        Elemen("div", "Ya", {"role": "radio", "aria-checked": "false"}),
        Elemen("div", "Tidak", {"role": "radio", "aria-checked": "false"}),
    ]

    def pilih(el):
        for lain in opsi:
            lain._attrs["aria-checked"] = "false"
        el._attrs["aria-checked"] = "true"

    for el in opsi:
        el.click = lambda el=el: pilih(el)

    jawaban.ingat("Bersedia lembur?", "Ya")
    applier = _applier_radio(monkeypatch, opsi, "Bersedia lembur?")

    assert applier.jawab_pertanyaan() == []
    assert applier._diagnosa_wajib_gagal() == []
    assert opsi[0].get_attribute("aria-checked") == "true"
