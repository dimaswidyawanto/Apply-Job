"""Pengiriman lamaran otomatis di halaman detail lowongan JobStreet.

Alur yang ditangani: klik "Lamar" -> halaman/modal lamaran -> tombol
"Lanjutkan"/"Kirim lamaran" -> konfirmasi berhasil.

Modul ini sengaja konservatif: bila menemukan hal yang tidak bisa dipastikan
(lamaran diarahkan ke situs perusahaan, perlu unggah berkas, ada pertanyaan
yang harus dijawab), proses dihentikan dan lowongan dikembalikan sebagai
"manual_required" supaya Anda yang menyelesaikan sendiri.
"""

import contextlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from rich.console import Console
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from config import config

console = Console()

# Tombol untuk masuk ke alur lamaran.
APPLY_SELECTORS = (
    "[data-automation='job-detail-apply']",
    "a[data-automation='applyButton']",
    "button[data-automation='applyButton']",
    "[data-testid='job-detail-apply']",
    "[data-automation='job-detail-apply-button']",
)

# Tombol final yang benar-benar mengirim lamaran.
SUBMIT_SELECTORS = (
    "[data-automation='job-apply-submit']",
    "[data-automation='submit-application']",
    "[data-automation='job-detail-submit']",
    "[data-testid='submit-application']",
)

# Tombol untuk maju ke langkah berikutnya.
CONTINUE_SELECTORS = (
    "[data-automation='job-apply-continue']",
    "[data-automation='continue-application']",
    "[data-automation='job-detail-continue']",
)

APPLY_TEXTS = ("lamar", "apply", "melamar")
SUBMIT_TEXTS = ("kirim lamaran", "kirim aplikasi", "submit application", "submit")
CONTINUE_TEXTS = ("lanjutkan", "continue", "berikutnya", "selanjutnya", "next")

SUCCESS_TEXTS = (
    "lamaran anda telah dikirim",
    "lamaran berhasil",
    "berhasil dikirim",
    "lamaran terkirim",
    "terima kasih telah melamar",
    "anda telah melamar",
    "lamaran telah dikirim",
    "lamaranmu telah dikirim",
    "lamaran kamu telah dikirim",
    "application submitted",
    "your application has been submitted",
    "you have successfully applied",
    "successfully applied",
    "application sent",
    "application has been sent",
    "your application has been sent",
    "application has been submitted",
    "lamaran berhasil dikirim",
    "berhasil melamar",
    "lamaran kamu terkirim",
    "thank you for applying",
    "we have received your application",
    "lamaran anda sudah kami terima",
)

# JobStreet kadang menolak submit dengan galat server, bukan validasi isian.
# Gejalanya banner merah "Something has gone wrong. Please try again...".
GALAT_SITUS_TEXTS = (
    "something has gone wrong",
    "something went wrong",
    "please try again",
    "contact customer service",
    "terjadi kesalahan",
    "silakan coba lagi",
    "hubungi customer service",
)

# Cukup dua percobaan kirim: lebih dari itu memperbesar risiko lamaran ganda.
MAKS_KLIK_KIRIM = 2

# Jeda sebelum klik Kirim pertama supaya formulir selesai dimuat.
JEDA_SEBELUM_KIRIM = 1.5

# Jeda sebelum boleh menekan Kirim lagi. Terlalu cepat = lamaran bisa terkirim
# dua kali (kejadian nyata di Glints: tombol "Kirim" diklik dua kali).
JEDA_KLIK_ULANG = 4.0

# Selama teks ini tampil, halaman masih memproses: jangan klik ulang dulu.
PROSES_TEXTS = (
    "mengirim",
    "memproses",
    "sedang diproses",
    "harap tunggu",
    "mohon tunggu",
    "please wait",
    "processing",
    "submitting",
    "loading",
)

ALREADY_TEXTS = (
    "anda sudah melamar",
    "sudah pernah melamar",
    "you have already applied",
    "application submitted",
)

# Pesan validasi JobStreet saat formulir belum lengkap.
# Kata yang menandakan sebuah kalimat adalah pertanyaan.
KATA_TANYA = (
    "berapa", "apakah", "bagaimana", "kapan", "dimana", "di mana", "mana",
    "how", "what", "which", "when", "where", "do you", "are you", "have you",
    "your", "kamu", "anda",
)

# Pertanyaan ya/tidak yang aman dijawab "Ya" (kesediaan/pengalaman).
KATA_SETUJU = (
    "bersedia", "siap", "willing", "pernah", "memiliki", "have you",
    "do you", "are you", "menguasai", "mampu",
)

# Penanda atribut internal JobStreet, bukan pertanyaan.
_ID_INTERNAL = re.compile(
    r"(questionnaire|\bID_Q_|\bQ_[0-9A-F]{6,}|\bquestion_?id\b)", re.IGNORECASE
)


def tampak_id_internal(teks: str) -> bool:
    """True bila teks itu ID internal (mis. questionnaire.ID_Q_…) bukan label."""
    return bool(_ID_INTERNAL.search(str(teks or "")))


def ambil_pertanyaan(teks: str, opsi=()) -> str:
    """Ambil baris pertanyaan dari teks wadah (mengabaikan teks opsi)."""
    opsi_norm = {_norm(item) for item in (opsi or [])}
    baris = [
        " ".join(item.split())
        for item in str(teks or "").splitlines()
        if item.strip()
    ]

    kandidat = [
        item
        for item in baris
        if _norm(item) not in opsi_norm
        and not tampak_id_internal(item)
        and len(item) >= 3
    ]

    for item in kandidat:
        if item.endswith("?") or any(k in item.lower() for k in KATA_TANYA):
            return item

    return kandidat[0] if kandidat else ""


def pertanyaan_dari_galat(teks: str) -> str:
    """Ambil inti pesan validasi JobStreet tanpa embel-embel."""
    teks = " ".join(str(teks or "").split())

    for tanda in (
        "please address the following issues:",
        "harap lengkapi:",
        "harap lengkapi",
    ):
        posisi = teks.lower().find(tanda)
        if posisi >= 0:
            teks = teks[posisi + len(tanda):]
            break

    teks = re.split(r"\s*-\s*please make a selection", teks, flags=re.IGNORECASE)[0]
    teks = re.sub(r"\s*-\s*", " — ", teks).strip(" -—")

    if len(teks) > 110:
        return teks[:110] + "…"

    return teks


def pilih_jawaban_radio(pertanyaan: str, opsi, cfg=None) -> str:
    """Pilih opsi untuk pertanyaan radio (ya/tidak atau berskala)."""
    cfg = cfg or config
    opsi = [item for item in (opsi or []) if _norm(item)]

    if not opsi:
        return ""

    pilihan = pilih_jawaban(pertanyaan, opsi, cfg)
    if pilihan:
        return pilihan

    teks = _norm(pertanyaan)
    ya = [
        item for item in opsi
        if _norm(item) in ("ya", "yes", "iya", "benar", "true")
    ]

    if (
        ya
        and getattr(cfg, "auto_answer_yes", False)
        and any(kata in teks for kata in KATA_SETUJU)
    ):
        return ya[0]

    return ""


VALIDATION_TEXTS = (
    "please address the following issues",
    "please make a selection",
    "harap lengkapi",
    "wajib dipilih",
    "wajib diisi",
    "harus dipilih",
)

GAJI_KATA = ("gaji", "salary", "upah", "pendapatan", "remunerasi")
PENGALAMAN_KATA = ("pengalaman", "experience", "tahun", "years", "year")
PENDIDIKAN_KATA = (
    "kualifikasi", "pendidikan", "education", "ijazah", "jenjang",
    "degree", "qualification",
)
LEVEL_ATAS_KATA = (
    "kepala", "head", "manager", "manajer", "supervisor", "spv", "lead",
    "chief",
)
NOL_KATA = (
    "no experience", "belum", "tanpa pengalaman", "fresh", "none",
    "kurang dari 1", "less than 1",
)


def _norm(teks: str) -> str:
    return " ".join(str(teks or "").lower().split())


def parse_gaji_juta(teks: str) -> Optional[float]:
    """Ubah teks gaji menjadi angka juta (mis. "Rp 5 Jt" -> 5.0)."""
    teks = _norm(teks).replace(".", "").replace(",", ".")
    angka = re.findall(r"\d+(?:\.\d+)?", teks)

    if not angka:
        return None

    nilai = float(angka[0])
    if "jt" in teks or "juta" in teks or "million" in teks:
        return nilai
    if nilai >= 100_000:
        return nilai / 1_000_000
    return nilai


def parse_tahun(teks: str) -> Optional[tuple]:
    """Baca rentang pengalaman dari teks opsi (tahun)."""
    teks_awal = _norm(teks)

    if any(kata in teks_awal for kata in NOL_KATA):
        return (0.0, 0.99)

    angka = [float(item.replace(",", ".")) for item in
             re.findall(r"\d+(?:[.,]\d+)?", teks_awal.replace(".", ""))]

    if not angka:
        return None

    if len(angka) >= 2 and re.search(r"\d\s*(?:-|–|to|s/d|sampai)\s*\d", teks_awal):
        return (min(angka[0], angka[1]), max(angka[0], angka[1]))

    if any(tanda in teks_awal for tanda in ("more than", "lebih dari", "+")):
        return (angka[0], 99.0)

    return (angka[0], angka[0])


def klasifikasi_pertanyaan(teks: str) -> str:
    """Tentukan jenis pertanyaan: gaji / pengalaman / pendidikan."""
    teks = _norm(teks)

    if any(kata in teks for kata in PENDIDIKAN_KATA):
        return "pendidikan"

    if any(kata in teks for kata in GAJI_KATA):
        return "gaji"

    if any(kata in teks for kata in PENGALAMAN_KATA):
        return "pengalaman"

    return ""


def _pilih_gaji(opsi, target: float) -> str:
    terbaik = ""
    selisih = None

    for item in opsi:
        nilai = parse_gaji_juta(item)
        if nilai is None:
            continue
        beda = abs(nilai - target)
        if selisih is None or beda < selisih:
            terbaik, selisih = item, beda

    return terbaik


def _pilih_tahun(opsi, tahun: float, wajib_nol: bool = False) -> str:
    rentang = [(item, parse_tahun(item)) for item in opsi]
    rentang = [(item, nilai) for item, nilai in rentang if nilai]

    if not rentang:
        return ""

    for item, (bawah, atas) in rentang:
        if bawah <= tahun <= atas:
            return item

    if wajib_nol:
        # Tidak ada opsi yang menyatakan "belum berpengalaman": lebih baik
        # lowongan dilewati daripada mengarang angka pengalaman.
        return ""

    dibawah = [(item, nilai[1]) for item, nilai in rentang if nilai[1] <= tahun]
    if dibawah:
        return max(dibawah, key=lambda pasangan: pasangan[1])[0]

    return min(rentang, key=lambda pasangan: pasangan[1][0])[0]


def _pilih_pendidikan(opsi, level: str) -> str:
    level = _norm(level).replace("-", "").replace(" ", "")

    padanan = {
        "s1": ("s1", "sarjana", "bachelor", "strata 1"),
        "s2": ("s2", "magister", "master"),
        "d3": ("d3", "diploma 3", "ahli madya"),
        "sma": ("sma", "smk", "senior high"),
    }

    kunci = padanan.get(level, (level,))

    for item in opsi:
        teks = _norm(item).replace("-", "")
        if any(kata in teks for kata in kunci if kata):
            return item

    return ""


def pilih_jawaban(pertanyaan: str, opsi, cfg=None) -> str:
    """Pilih teks opsi yang aman untuk sebuah pertanyaan ('' = tidak dijawab)."""
    cfg = cfg or config
    opsi = [item for item in (opsi or []) if _norm(item)]

    if not opsi:
        return ""

    jenis = klasifikasi_pertanyaan(pertanyaan)

    if jenis == "pendidikan":
        return _pilih_pendidikan(opsi, getattr(cfg, "education_level", ""))

    if jenis == "gaji":
        target = parse_gaji_juta(getattr(cfg, "expected_salary", "") or "")
        if target is None:
            return ""
        return _pilih_gaji(opsi, target)

    if jenis == "pengalaman":
        teks = _norm(pertanyaan)
        peran = getattr(cfg, "experience_roles", ()) or ()
        cocok = any(_norm(kata) in teks for kata in peran if _norm(kata))

        # Jabatan lebih tinggi (Kepala/Manager/Supervisor) atau bidang yang
        # belum pernah dijalani tidak boleh diklaim "3 tahun".
        nol = any(kata in teks for kata in LEVEL_ATAS_KATA) or not cocok

        tahun = 0.0 if nol else float(getattr(cfg, "years_experience", 0) or 0)
        return _pilih_tahun(opsi, tahun, wajib_nol=nol)

    return ""


ALREADY_SELECTORS = (
    "[data-automation='job-detail-applied-badge']",
    "[data-automation='appliedBadge']",
    "[data-testid='applied-badge']",
)

JOBSTREET_DOMAIN = "jobstreet.com"

EXTERNAL_BUTTON_TEXTS = (
    "lamar di situs perusahaan",
    "apply on company site",
    "apply on employer site",
    "apply on company website",
)


@dataclass
class ApplyResult:
    """Hasil satu percobaan melamar."""

    applied: bool
    status: str  # applied | already_applied | manual_required | error
    reason: str = ""


class AutoApplier:
    # Situs yang dilayani (ditimpa subclass untuk situs lain, mis. Glints).
    situs_host = JOBSTREET_DOMAIN
    nama_situs = "JobStreet"

    # Daftar selector/teks diambil dari konstanta modul agar subclass bisa
    # menggantinya tanpa menyentuh logika alur.
    apply_selectors = APPLY_SELECTORS
    apply_texts = APPLY_TEXTS
    submit_selectors = SUBMIT_SELECTORS
    submit_texts = SUBMIT_TEXTS
    continue_selectors = CONTINUE_SELECTORS
    continue_texts = CONTINUE_TEXTS
    success_texts = SUCCESS_TEXTS
    already_texts = ALREADY_TEXTS
    galat_situs_texts = GALAT_SITUS_TEXTS

    def __init__(self, driver, wait=None):
        self.driver = driver
        self.wait = wait
        self.step_timeout = config.auto_apply_step_timeout
        self.submit_timeout = config.auto_apply_submit_timeout
        self.debug_dumps = 0

    # ------------------------------------------------------------------
    # Utilitas elemen
    # ------------------------------------------------------------------
    @staticmethod
    def _visible(element) -> bool:
        try:
            return element.is_displayed()
        except Exception:
            return False

    @staticmethod
    def _enabled(element) -> bool:
        try:
            return element.is_enabled()
        except Exception:
            return True

    @staticmethod
    def _text(element) -> str:
        try:
            value = element.text or element.get_attribute("textContent") or ""
        except Exception:
            value = ""
        return " ".join(str(value).split()).strip().lower()

    def _url(self) -> str:
        try:
            return str(self.driver.current_url or "")
        except Exception:
            return ""

    def _body_text(self) -> str:
        try:
            element = self.driver.find_element(By.TAG_NAME, "body")
            return " ".join((element.text or "").split()).lower()
        except Exception:
            return ""

    def _find_all(self, selector: str) -> list:
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            return []

    def _find_clickable(self, selectors, texts=()) -> Optional[object]:
        """Cari elemen pertama yang terlihat dan cocok dengan selector/teks."""
        for selector in selectors:
            for element in self._find_all(selector):
                if self._visible(element) and self._enabled(element):
                    return element

        if not texts:
            return None

        for selector in ("button", "a", "[role='button']"):
            for element in self._find_all(selector):
                if not self._visible(element) or not self._enabled(element):
                    continue

                label = self._text(element)
                if not label:
                    continue

                if any(label == text or label.startswith(text) for text in texts):
                    return element

        return None

    def _click(self, element) -> bool:
        with contextlib.suppress(Exception):
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )

        try:
            element.click()
            return True
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False

    # ------------------------------------------------------------------
    # Deteksi status
    # ------------------------------------------------------------------
    def is_already_applied(self) -> bool:
        for selector in ALREADY_SELECTORS:
            for element in self._find_all(selector):
                if self._visible(element):
                    return True

        body = self._body_text()
        return any(text in body for text in self.already_texts)

    def _is_situs_url(self, url: str) -> bool:
        try:
            host = (urlparse(url or "").netloc or "").lower()
        except Exception:
            return True

        if not host:
            return True

        return self.situs_host in host

    def _is_external_page(self) -> bool:
        try:
            url = self.driver.current_url or ""
        except Exception:
            return False

        return bool(url) and not self._is_situs_url(url)

    def _external_host(self) -> str:
        try:
            return (urlparse(self.driver.current_url or "").netloc or "").lower()
        except Exception:
            return ""

    def _cari_tombol_lamar(self):
        """Tombol untuk masuk ke alur lamaran."""
        return self._find_clickable(self.apply_selectors, self.apply_texts)

    def _sedang_memproses(self) -> bool:
        """True bila halaman menampilkan penanda "sedang dikirim"."""
        gabungan = f"{self._body_text()} {self._teks_modal()}"

        return any(tanda in gabungan for tanda in PROSES_TEXTS)

    def _pesan_alur_tidak_dikenali(self) -> str:
        """Pesan saat alur lamaran tidak bisa dilanjutkan otomatis."""
        return (
            "Alur lamaran tidak dikenali dalam "
            f"{self.step_timeout} detik"
        )

    def _alasan_lewati(self) -> str:
        """Alasan lowongan harus dilewati sebelum menekan Lamar.

        Subclass situs lain (mis. Glints) bisa menimpa: lowongan yang hanya
        bisa dilamar lewat aplikasi mobile tidak mungkin diproses di sini.
        """
        return ""

    def _is_review_page(self) -> bool:
        """Halaman terakhir "Review and submit"."""
        try:
            url = (self.driver.current_url or "").lower()
        except Exception:
            url = ""

        if "/apply/review" in url or "review-and-submit" in url:
            return True

        body = self._body_text()
        return any(
            text in body
            for text in ("review and submit", "review & submit",
                         "tinjau dan kirim")
        )

    def _dump_debug(self, job: dict):
        """Simpan HTML + screenshot agar selector mudah diperbaiki."""
        if not config.auto_apply_debug or self.debug_dumps >= 5:
            return

        try:
            folder = Path("debug")
            folder.mkdir(exist_ok=True)

            stamp = time.strftime("%Y%m%d-%H%M%S")
            nama = f"{stamp}-{job.get('job_id') or 'lowongan'}"
            dasar = folder / nama

            try:
                url = self.driver.current_url or ""
            except Exception:
                url = ""

            tombol = []
            for selector in ("button", "a[role='button']", "[role='dialog']"):
                for element in self._find_all(selector)[:25]:
                    if not self._visible(element):
                        continue
                    label = self._raw_text(element)
                    if label:
                        tombol.append(label[:60])

            (dasar.with_suffix(".txt")).write_text(
                f"URL: {url}\n"
                f"Job: {job.get('title') or '-'}\n"
                f"Modal: {self._teks_modal()[:300]}\n"
                f"Galat server: {self._galat_situs() or '-'}\n"
                f"Cuplikan halaman: {self._body_text()[:400]}\n"
                f"Tombol terlihat: {tombol}\n",
                encoding="utf-8",
            )
            (dasar.with_suffix(".html")).write_text(
                self.driver.page_source or "", encoding="utf-8"
            )
            self.driver.save_screenshot(str(dasar.with_suffix(".png")))
            self.debug_dumps += 1
            console.print(
                f"[dim]Halaman tidak dikenali; debug disimpan di "
                f"debug/{nama}.html[/]"
            )
        except Exception:
            pass

    def _find_submit_button(self, review_page: bool = False):
        """Cari tombol kirim. Di halaman review, cakupannya lebih luas."""
        button = self._find_clickable(self.submit_selectors, self.submit_texts)
        if button is not None:
            return button

        if not review_page:
            return None

        negatif = ("back", "kembali", "batal", "cancel", "hapus", "delete")

        # Tombol kirim di halaman review hampir selalu bertipe submit.
        for element in self._find_all("button[type='submit']"):
            if not self._visible(element) or not self._enabled(element):
                continue
            if any(kata in self._text(element) for kata in negatif):
                continue
            return element

        # Hindari kata "lamar"/"apply": di halaman review tombol itu bisa
        # berarti memulai ulang lamaran.
        kata_kunci = ("submit", "kirim", "send application")

        for selector in ("button", "[role='button']", "a"):
            for element in self._find_all(selector):
                if not self._visible(element) or not self._enabled(element):
                    continue
                label = self._text(element)
                if any(kata in label for kata in negatif):
                    continue
                if any(kata in label for kata in kata_kunci):
                    return element

        return None

    def _is_login_page(self) -> bool:
        try:
            url = (self.driver.current_url or "").lower()
        except Exception:
            url = ""

        if "signin" in url or "/login" in url:
            return True

        return bool(self._find_all("input[type='password']"))

    def _teks_modal(self) -> str:
        """Teks dialog/modal yang tampil setelah klik Kirim."""
        potongan = []
        for selector in (
            "[role='dialog']",
            "[data-automation*='modal']",
            "[data-automation*='confirmation']",
        ):
            for element in self._find_all(selector):
                if not self._visible(element):
                    continue
                teks = self._raw_text(element)
                if teks:
                    potongan.append(teks)

        return " ".join(potongan).lower()

    def _is_success(self) -> bool:
        try:
            url = (self.driver.current_url or "").lower()
        except Exception:
            url = ""

        if any(tanda in url for tanda in (
            "success", "submitted", "confirmation", "my-application",
            "application-submi",
        )):
            return True

        body = self._body_text()
        if any(text in body for text in self.success_texts):
            return True

        modal = self._teks_modal()
        return any(text in modal for text in self.success_texts)

    def _autofill(self) -> bool:
        """Isi cover letter dan unggah CV bila formulir memintanya.

        Hanya berjalan bila COVER_LETTER / RESUME_PATH diisi di .env.
        """
        terisi = False

        if config.cover_letter:
            for element in self._find_all("textarea"):
                if not self._visible(element):
                    continue
                if (element.get_attribute("value") or "").strip():
                    continue
                try:
                    element.send_keys(config.cover_letter)
                    terisi = True
                except Exception:
                    continue

        if config.resume_path:
            berkas = Path(config.resume_path).expanduser()

            if berkas.is_file():
                for element in self._find_all("input[type='file']"):
                    if not self._visible(element):
                        continue
                    if (element.get_attribute("value") or "").strip():
                        continue
                    try:
                        element.send_keys(str(berkas))
                        terisi = True
                    except Exception:
                        continue

        return terisi

    @staticmethod
    def _raw_text(element) -> str:
        """Teks elemen apa adanya; baris dipertahankan agar label bisa dipisah."""
        try:
            baris = [
                " ".join(item.split())
                for item in (element.text or "").splitlines()
                if item.strip()
            ]
        except Exception:
            return ""

        return "\n".join(baris)

    def _label_untuk(self, element) -> str:
        """Teks label untuk satu input (radio/checkbox)."""
        try:
            id_el = (element.get_attribute("id") or "").strip()
        except Exception:
            id_el = ""

        if id_el:
            for label in self._find_all(f"label[for='{id_el}']"):
                teks = " ".join(self._raw_text(label).split())
                if teks:
                    return teks

        try:
            label = " ".join((element.get_attribute("aria-label") or "").split())
        except Exception:
            label = ""

        if label and not tampak_id_internal(label):
            return label

        return ""

    def _pertanyaan(self, element, opsi=()) -> str:
        """Teks pertanyaan sesungguhnya untuk sebuah input.

        JobStreet menaruh pertanyaan di elemen lain (aria-labelledby, label,
        legend, atau wadah di atasnya), sedangkan atribut `name`/`id` hanya
        berisi ID internal seperti `questionnaire.ID_Q_...`. Karena itu ID
        internal tidak pernah dipakai sebagai teks pertanyaan.
        """
        opsi = list(opsi or [])

        # 1. aria-labelledby -> teks elemen yang dirujuk
        try:
            ids = (element.get_attribute("aria-labelledby") or "").split()
        except Exception:
            ids = []

        for id_rujukan in ids:
            for label in self._find_all(f"[id='{id_rujukan}']"):
                teks = " ".join(self._raw_text(label).split())
                if teks and not tampak_id_internal(teks):
                    return teks

        # 2. aria-label
        try:
            label = " ".join((element.get_attribute("aria-label") or "").split())
        except Exception:
            label = ""

        if label and not tampak_id_internal(label):
            return label

        # 3. label[for=id]
        try:
            id_el = (element.get_attribute("id") or "").strip()
        except Exception:
            id_el = ""

        if id_el:
            for label_el in self._find_all(f"label[for='{id_el}']"):
                teks = " ".join(self._raw_text(label_el).split())
                if teks:
                    return teks

        # 4. teks di sekitar input (naik maksimum empat tingkat)
        induk = element

        for _ in range(4):
            try:
                induk = induk.find_element(By.XPATH, "..")
            except Exception:
                break

            teks = self._raw_text(induk)
            if not teks:
                continue

            kandidat = ambil_pertanyaan(teks, opsi)
            if kandidat and not tampak_id_internal(kandidat):
                return kandidat

        return ""

    @staticmethod
    def _teks_opsi(element) -> list:
        try:
            opsi = element.find_elements(By.TAG_NAME, "option")
        except Exception:
            return []

        hasil = []
        for item in opsi:
            try:
                teks = " ".join((item.text or "").split())
            except Exception:
                continue
            if teks and teks.lower() not in (
                "pilih", "select", "please select", "-", "--",
            ):
                hasil.append(teks)

        return hasil

    def _pilih_opsi(self, element, teks: str) -> bool:
        try:
            Select(element).select_by_visible_text(teks)
            return True
        except Exception:
            pass

        try:
            for item in element.find_elements(By.TAG_NAME, "option"):
                if " ".join((item.text or "").split()) == teks:
                    return self._click(item)
        except Exception:
            pass

        return False

    def _jawab_select(self, element) -> str:
        """Isi satu dropdown. Kembalikan teks jawaban ('' bila tidak dijawab)."""
        try:
            terisi = (element.get_attribute("value") or "").strip()
        except Exception:
            terisi = ""

        if terisi:
            return ""

        opsi = self._teks_opsi(element)
        pertanyaan = self._pertanyaan(element, opsi)
        pilihan = pilih_jawaban(pertanyaan, opsi)

        if pilihan and self._pilih_opsi(element, pilihan):
            console.print(
                f'[dim]   jawab "{pilihan}" untuk: '
                f'{pertanyaan[:70] or "pertanyaan"}[/]'
            )
            return pilihan

        return "" if not opsi else "-"

    def _jawab_radio(self) -> list:
        """Jawab pertanyaan radio (ya/tidak) yang polanya dikenali."""
        grup = {}

        for element in self._find_all("input[type='radio']"):
            if not self._visible(element) or not self._enabled(element):
                continue

            try:
                nama = (element.get_attribute("name") or "").strip()
            except Exception:
                nama = ""

            if nama:
                grup.setdefault(nama, []).append(element)

        gagal = []

        for element_grup in grup.values():
            if any(self._selected(item) for item in element_grup):
                continue

            opsi = []
            for item in element_grup:
                label = self._label_untuk(item)
                if label:
                    opsi.append(label)

            pertanyaan = self._pertanyaan(element_grup[0], opsi)
            pilihan = pilih_jawaban_radio(pertanyaan, opsi)

            if not pilihan:
                gagal.append(pertanyaan or "pertanyaan pilihan")
                continue

            diklik = False
            for item in element_grup:
                if _norm(self._label_untuk(item)) == _norm(pilihan):
                    diklik = self._click(item)
                    break

            if diklik:
                console.print(
                    f'[dim]   jawab "{pilihan}" untuk: '
                    f'{pertanyaan[:70] or "pertanyaan"}[/]'
                )
            else:
                gagal.append(pertanyaan or "pertanyaan pilihan")

        return gagal

    def _jawab_teks(self) -> list:
        """Isi kolom teks/nomor untuk pertanyaan gaji atau pengalaman."""
        gagal = []

        for selector in ("input[type='text']", "input[type='number']"):
            for element in self._find_all(selector):
                if not self._visible(element) or not self._enabled(element):
                    continue

                try:
                    terisi = (element.get_attribute("value") or "").strip()
                except Exception:
                    terisi = ""

                if terisi:
                    continue

                pertanyaan = self._pertanyaan(element)
                jenis = klasifikasi_pertanyaan(pertanyaan)

                if jenis == "gaji":
                    nilai = str(config.expected_salary or "").strip()
                elif jenis == "pengalaman":
                    nilai = f"{float(config.years_experience or 0):g}"
                else:
                    continue

                if not nilai:
                    gagal.append(pertanyaan)
                    continue

                try:
                    element.send_keys(nilai)
                    console.print(
                        f'[dim]   isi "{nilai}" untuk: {pertanyaan[:70]}[/]'
                    )
                except Exception:
                    gagal.append(pertanyaan)

        return gagal

    def jawab_pertanyaan(self) -> list:
        """Jawab pertanyaan formulir yang polanya dikenali.

        Kembalikan daftar pertanyaan yang belum bisa dijawab otomatis.
        """
        if not config.auto_answer_questions:
            return []

        gagal = []

        for element in self._find_all("select"):
            if not self._visible(element) or not self._enabled(element):
                continue

            hasil = self._jawab_select(element)

            if hasil == "-":
                opsi = self._teks_opsi(element)
                gagal.append(
                    self._pertanyaan(element, opsi) or "pertanyaan pilihan"
                )

        gagal.extend(self._jawab_radio())
        gagal.extend(self._jawab_teks())

        return gagal

    def _tunggu_jawaban(self, rinci: str = "") -> str:
        """Beri waktu pengguna mengisi kuesioner di jendela Chrome.

        Kembalikan:
          "applied" — lamaran ternyata sudah terkirim,
          "lanjut"  — isian sudah lengkap, alur boleh diteruskan,
          "habis"   — waktu tunggu selesai dan isian masih belum lengkap.
        """
        batas = max(0, int(config.auto_answer_wait or 0))

        if batas <= 0:
            return "habis"

        console.print(
            "[bold yellow]Ada pertanyaan yang belum terisi:[/] "
            f"{(rinci or 'kuesioner perusahaan')[:100]}"
        )
        console.print(
            "   Silakan isi di jendela Chrome sekarang — menunggu sampai "
            f"{batas} detik..."
        )

        for sisa in range(batas, 0, -1):
            time.sleep(1)

            if self._is_success():
                return "applied"

            # Lanjut hanya bila tidak ada pertanyaan tersisa DAN tidak ada
            # peringatan validasi — supaya tidak mengklik Kirim berulang kali.
            if not self.jawab_pertanyaan() and not self._validation_error():
                console.print(
                    "[green]   isian sudah lengkap — melanjutkan pengiriman "
                    "lamaran.[/]"
                )
                return "lanjut"

            if sisa % 5 == 0:
                console.print(f"[dim]   menunggu... sisa {sisa} detik[/]")

        console.print(
            "[yellow]   waktu tunggu habis — lamaran ini dilewati dan "
            "dikembalikan ke daftar manual.[/]"
        )
        return "habis"

    def _validation_error(self) -> str:
        """Teks peringatan validasi formulir lamaran ('' bila tidak ada)."""
        body = self._body_text()

        for tanda in VALIDATION_TEXTS:
            posisi = body.find(tanda)
            if posisi >= 0:
                potong = " ".join(body[posisi:posisi + 220].split())
                return potong

        return ""

    def _galat_situs(self) -> str:
        """Banner galat server JobStreet ('' bila tidak ada)."""
        gabungan = f"{self._body_text()} {self._teks_modal()}"

        for tanda in self.galat_situs_texts:
            if tanda in gabungan:
                return tanda

        return ""

    def _muat_ulang(self) -> bool:
        """Muat ulang halaman saat ini (False bila tidak bisa)."""
        try:
            self.driver.refresh()
        except Exception:
            return False

        time.sleep(1.0)
        return True

    @staticmethod
    def _is_required(element) -> bool:
        """True bila elemen benar-benar wajib (termasuk `required` kosong)."""
        try:
            if (element.get_attribute("aria-required") or "") == "true":
                return True
            return element.get_attribute("required") is not None
        except Exception:
            return False

    def _blocker(self) -> str:
        """Alasan alur tidak boleh dilanjutkan otomatis ("" = aman)."""
        for element in self._find_all("input[type='file']"):
            if not self._visible(element):
                continue

            # Unggah berkas biasanya OPSIONAL ("Documents included").
            # Hanya anggap penghalang bila memang wajib.
            value = (element.get_attribute("value") or "").strip()

            if self._is_required(element) and not value:
                return (
                    "Alur lamaran mewajibkan unggah berkas "
                    "(isi RESUME_PATH di .env agar otomatis)"
                )

        for element in self._find_all("textarea"):
            if not self._visible(element):
                continue
            value = (element.get_attribute("value") or "").strip()
            if self._is_required(element) and not value:
                return (
                    "Ada pertanyaan/cover letter wajib "
                    "(isi COVER_LETTER di .env agar otomatis)"
                )

        for element in self._find_all("select[required]"):
            if not self._visible(element):
                continue
            value = (element.get_attribute("value") or "").strip()
            if not value:
                return "Ada pertanyaan pilihan yang wajib dijawab"

        for element in self._find_all("input[type='radio'][required]"):
            if not self._visible(element):
                continue
            name = element.get_attribute("name") or ""
            if not name:
                return "Ada pertanyaan yang wajib dijawab"

            group = self._find_all(f"input[type='radio'][name='{name}']")
            if not any(self._selected(item) for item in group):
                return "Ada pertanyaan yang wajib dijawab"

        return ""

    @staticmethod
    def _selected(element) -> bool:
        try:
            return bool(element.is_selected())
        except Exception:
            return False

    def _external_button_present(self) -> bool:
        for selector in ("button", "a", "[role='button']"):
            for element in self._find_all(selector):
                if not self._visible(element):
                    continue
                label = self._text(element)
                if any(text in label for text in EXTERNAL_BUTTON_TEXTS):
                    return True
        return False

    # ------------------------------------------------------------------
    # Jendela / tab baru
    # ------------------------------------------------------------------
    def _handle_new_window(self, handles_before: set) -> str:
        """Tangani tab baru. Kembalikan alasan jika harus berhenti."""
        try:
            handles = set(self.driver.window_handles)
        except Exception:
            return ""

        new_handles = handles - handles_before
        if not new_handles:
            return ""

        try:
            self.driver.switch_to.window(new_handles.pop())
            time.sleep(0.3)
            url = self.driver.current_url or ""
        except Exception:
            return "Gagal berpindah ke tab lamaran"

        if self._is_situs_url(url):
            return ""

        # Simpan domain sebelum tab ditutup, agar pesannya tetap benar.
        try:
            host = (urlparse(url).netloc or "").lower()
        except Exception:
            host = ""

        # Lamaran dibuka di situs perusahaan (ATS eksternal).
        try:
            self.driver.close()
            if handles_before:
                self.driver.switch_to.window(list(handles_before)[0])
        except Exception:
            pass

        return (
            "Lamaran diarahkan ke situs lain "
            f"({host or 'situs perusahaan'}) — dilewati"
        )

    # ------------------------------------------------------------------
    # Alur utama
    # ------------------------------------------------------------------
    def apply(self, job: dict) -> ApplyResult:
        url = (job.get("url") or "").strip()

        if not url:
            return ApplyResult(False, "error", "URL lowongan kosong")

        try:
            self.driver.get(url)
            time.sleep(0.8)

            if self._is_login_page():
                return ApplyResult(
                    False,
                    "login_required",
                    f"Sesi login {self.nama_situs} sudah habis",
                )

            if self._is_external_page():
                return ApplyResult(
                    False,
                    "manual_required",
                    "Lowongan dialihkan ke situs lain "
                    f"({self._external_host()}) — dilewati",
                )

            if self.is_already_applied():
                return ApplyResult(
                    False,
                    "already_applied",
                    f"{self.nama_situs} menandai lowongan ini sudah "
                    "pernah dilamar",
                )

            alasan = self._alasan_lewati()
            if alasan:
                return ApplyResult(False, "manual_required", alasan)

            if self._external_button_present():
                return ApplyResult(
                    False,
                    "manual_required",
                    "Lowongan menggunakan 'Lamar di situs perusahaan'",
                )

            # Tunggu tombol Lamar muncul, maksimal sepanjang batas waktu.
            apply_button = self._cari_tombol_lamar()
            batas_tombol = time.time() + self.step_timeout

            while apply_button is None and time.time() < batas_tombol:
                time.sleep(0.3)
                apply_button = self._cari_tombol_lamar()

            if apply_button is None:
                # Bisa jadi halaman memang tidak menawarkan lamar di web
                # (mis. Glints "Lamar 1x tap di aplikasi").
                alasan = self._blocker()

                return ApplyResult(
                    False,
                    "manual_required",
                    alasan or "Tombol Lamar tidak ditemukan di halaman",
                )

            handles_before = set(self.driver.window_handles)
            self._click(apply_button)
            time.sleep(0.5)

            external_reason = self._handle_new_window(handles_before)
            if external_reason:
                return ApplyResult(False, "manual_required", external_reason)

            if self._is_external_page():
                return ApplyResult(
                    False,
                    "manual_required",
                    "Lamaran dialihkan ke situs lain "
                    f"({self._external_host()}) — dilewati",
                )

            review_page = self._is_review_page()
            deadline = time.time() + (
                self.submit_timeout if review_page else self.step_timeout
            )
            sudah_klik_kirim = False
            percobaan_kirim = 0
            jumlah_muat_ulang = 0
            kirim_terakhir = 0.0
            jejak_lanjut = ""
            klik_lanjut = 0

            while time.time() < deadline:
                time.sleep(0.4)

                if self._is_external_page():
                    return ApplyResult(
                        False,
                        "manual_required",
                        "Lamaran dialihkan ke situs lain "
                        f"({self._external_host()}) — dilewati",
                    )

                if self._is_success():
                    return ApplyResult(True, "applied", "Terkirim otomatis")

                # Halaman "Review and submit" sering muncul setelah beberapa
                # detik; beri waktu lebih panjang untuk mengenalinya.
                if not review_page and self._is_review_page():
                    review_page = True
                    deadline = max(
                        deadline, time.time() + self.submit_timeout
                    )
                    console.print(
                        '[dim]   halaman "Review and submit" terdeteksi; '
                        f"menunggu tombol kirim s.d. {self.submit_timeout} "
                        "detik[/]"
                    )

                # Isi otomatis cover letter / unggah CV bila dikonfigurasi.
                self._autofill()

                if not review_page:
                    belum_terjawab = self.jawab_pertanyaan()

                    galat = self._validation_error()
                    if galat and belum_terjawab:
                        rinci = (
                            pertanyaan_dari_galat(galat)
                            or belum_terjawab[0][:80]
                        )
                        console.print(
                            f"[dim]   belum bisa dijawab otomatis: {rinci}[/]"
                        )

                        # Beri waktu pengguna mengisi kuesioner di Chrome.
                        hasil_tunggu = self._tunggu_jawaban(rinci)
                        if hasil_tunggu == "applied":
                            return ApplyResult(
                                True, "applied", "Terkirim otomatis"
                            )
                        if hasil_tunggu == "lanjut":
                            deadline = max(
                                deadline, time.time() + self.step_timeout
                            )
                            continue

                        self._dump_debug(job)
                        return ApplyResult(
                            False,
                            "manual_required",
                            "Formulir meminta isian yang belum bisa dijawab "
                            f"otomatis: {rinci} — dilewati",
                        )

                    blocker = self._blocker()
                    if blocker:
                        # Pastikan bukan halaman yang masih memuat.
                        time.sleep(0.4)
                        if self._blocker() == blocker:
                            self._dump_debug(job)
                            return ApplyResult(
                                False, "manual_required", blocker
                            )

                if sudah_klik_kirim:
                    # Setelah Kirim ditekan, JobStreet bisa gagal di sisi
                    # server ("Something has gone wrong"). Muat ulang sekali
                    # lalu coba kirim lagi; jangan menunggu 20 detik buta.
                    galat_situs = self._galat_situs()
                    if galat_situs:
                        if jumlah_muat_ulang < 1 and self._muat_ulang():
                            jumlah_muat_ulang += 1
                            sudah_klik_kirim = False
                            deadline = time.time() + self.submit_timeout
                            console.print(
                                f'[dim]   {self.nama_situs}: "{galat_situs}"'
                                " — halaman dimuat ulang, coba kirim sekali "
                                "lagi[/]"
                            )
                            continue

                        self._dump_debug(job)
                        return ApplyResult(
                            False,
                            "manual_required",
                            f'{self.nama_situs} menolak kirim: '
                            f'"{galat_situs}" '
                            f"(dicoba {percobaan_kirim}x, halaman dimuat "
                            "ulang) — dilewati",
                        )

                    # Masih ada isian wajib yang belum terisi: berhenti.
                    galat = self._validation_error()
                    if galat:
                        rinci = pertanyaan_dari_galat(galat)
                        console.print(
                            f"[dim]   formulir menolak dikirim: {rinci}[/]"
                        )

                        hasil_tunggu = self._tunggu_jawaban(rinci)
                        if hasil_tunggu == "applied":
                            return ApplyResult(
                                True, "applied", "Terkirim otomatis"
                            )
                        if hasil_tunggu == "lanjut":
                            sudah_klik_kirim = False
                            deadline = max(
                                deadline, time.time() + self.submit_timeout
                            )
                            continue

                        self._dump_debug(job)
                        return ApplyResult(
                            False,
                            "manual_required",
                            "Formulir menolak dikirim karena isian wajib: "
                            f"{rinci} — dilewati",
                        )

                if review_page and not sudah_klik_kirim:
                    # Banner galat bisa sudah ada sejak halaman dibuka.
                    galat_situs = self._galat_situs()
                    if galat_situs:
                        if jumlah_muat_ulang < 1 and self._muat_ulang():
                            jumlah_muat_ulang += 1
                            deadline = time.time() + self.submit_timeout
                            console.print(
                                f'[dim]   halaman review menampilkan '
                                f'"{galat_situs}" — dimuat ulang[/]'
                            )
                            continue

                        self._dump_debug(job)
                        return ApplyResult(
                            False,
                            "manual_required",
                            f"Halaman review menampilkan galat "
                            f"{self.nama_situs}: "
                            f'"{galat_situs}" — dilewati',
                        )

                submit_button = self._find_submit_button(review_page)
                if submit_button is not None:
                    # Hindari klik ganda: beri jeda 2 detik sebelum mencoba
                    # lagi bila tombol masih terlihat (halaman lambat).
                    boleh_klik = (
                        not sudah_klik_kirim
                        or (
                            time.time() - kirim_terakhir >= JEDA_KLIK_ULANG
                            and not self._sedang_memproses()
                        )
                    )
                    if boleh_klik and percobaan_kirim < MAKS_KLIK_KIRIM:
                        if percobaan_kirim == 0:
                            # Formulir JobStreet butuh waktu selesai dimuat;
                            # klik terlalu cepat membuat server menolak.
                            time.sleep(JEDA_SEBELUM_KIRIM)
                            submit_button = (
                                self._find_submit_button(review_page)
                                or submit_button
                            )
                        if not self._click(submit_button):
                            return ApplyResult(
                                False,
                                "error",
                                "Tombol kirim lamaran gagal diklik",
                            )
                        console.print(
                            "[dim]   klik tombol kirim "
                            f'"{self._text(submit_button) or "tanpa teks"}"'
                            f" (percobaan {percobaan_kirim + 1})[/]"
                        )
                        sudah_klik_kirim = True
                        percobaan_kirim += 1
                        kirim_terakhir = time.time()
                        review_page = True
                        deadline = time.time() + self.submit_timeout
                        continue

                continue_button = self._find_clickable(
                    self.continue_selectors, self.continue_texts
                )
                if continue_button is not None:
                    jejak = (
                        f"{self._url()}|{len(self._body_text())}"
                    )
                    if jejak == jejak_lanjut:
                        klik_lanjut += 1
                    else:
                        jejak_lanjut = jejak
                        klik_lanjut = 1

                    if klik_lanjut > 2:
                        galat = self._validation_error()
                        self._dump_debug(job)
                        return ApplyResult(
                            False,
                            "manual_required",
                            galat
                            or "Halaman tidak maju setelah tombol Lanjut "
                            "diklik 3 kali — dilewati",
                        )

                    console.print(
                        "[dim]   klik lanjut "
                        f'"{self._text(continue_button) or "tanpa teks"}"[/]'
                    )
                    if not self._click(continue_button):
                        return ApplyResult(
                            False, "error", "Tombol lanjut gagal diklik"
                        )
                    deadline = time.time() + self.step_timeout
                    continue

            if self._is_success():
                return ApplyResult(True, "applied", "Terkirim otomatis")

            self._dump_debug(job)

            if sudah_klik_kirim:
                galat_situs = self._galat_situs()
                if galat_situs:
                    return ApplyResult(
                        False,
                        "manual_required",
                        f'{self.nama_situs}: "{galat_situs}" setelah '
                        "Kirim diklik "
                        f"{percobaan_kirim}x — dilewati "
                        "(periksa riwayat lamaran)",
                    )
                return ApplyResult(
                    False,
                    "manual_required",
                    "Tombol Kirim sudah diklik, tetapi konfirmasi tidak "
                    f"muncul dalam {self.submit_timeout} detik "
                    f"(periksa riwayat lamaran di {self.nama_situs})",
                )

            if review_page:
                return ApplyResult(
                    False,
                    "manual_required",
                    "Halaman Review and submit tidak menampilkan tombol "
                    "kirim yang dikenali",
                )

            return ApplyResult(
                False,
                "manual_required",
                self._pesan_alur_tidak_dikenali(),
            )

        except (KeyboardInterrupt, SystemExit):
            raise

        except Exception as exc:
            return ApplyResult(False, "error", str(exc))
