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
from urllib.parse import urlparse

from rich.console import Console
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

import jawaban
import log_aktivitas
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

# Pertanyaan berskala ("how would you rate your japanese language skills?").
# Dijawab dengan tingkat TERENDAH yang jujur, bukan dikosongkan dan bukan
# dilebih-lebihkan.
SKALA_KATA = (
    "rate", "rating", "level", "tingkat", "skala", "proficiency",
    "kemampuan", "how would you rate", "seberapa", "mahir",
)
SKALA_URUT = (
    "no experience", "tidak ada pengalaman", "tanpa pengalaman", "belum ada",
    "none", "tidak ada", "not at all",
    "pemula", "beginner", "basic", "dasar", "novice", "elementary",
    "intermediate", "menengah", "conversational", "cukup",
    "advanced", "lanjutan", "upper intermediate",
    "fluent", "mahir", "native", "expert", "ahli",
)

# Penanda atribut internal JobStreet, bukan pertanyaan.
_ID_INTERNAL = re.compile(
    r"(questionnaire|\bID_Q_|\bQ_[0-9A-F]{6,}|\bquestion_?id\b)", re.IGNORECASE
)


def nama_berkas_aman(teks: str, maks: int = 80) -> str:
    """Ubah teks menjadi nama berkas yang sah di Windows/Linux.

    `job_id` Glints berbentuk `glints:<uuid>`. Titik dua tidak sah pada nama
    berkas Windows, sehingga seluruh dump debug Glints sebelumnya gagal
    ditulis tanpa pesan (padahal konsol mengaku sudah menyimpannya).
    """
    aman = re.sub(r"[^A-Za-z0-9._-]+", "-", str(teks or "")).strip("-.")
    return (aman or "lowongan")[:maks]


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
        if re.match(r"^(ya|yes|iya|benar|true)\b", _norm(item))
        and "belum" not in _norm(item)
        and "not" not in _norm(item)
    ]

    if (
        ya
        and getattr(cfg, "auto_answer_yes", False)
        and any(kata in teks for kata in KATA_SETUJU)
    ):
        return ya[0]

    # Pertanyaan berskala: pilih tingkat terendah (jujur, tanpa melebihkan).
    if any(kata in teks for kata in SKALA_KATA):
        return _pilih_skala_terendah(opsi)

    return ""


def _pilih_skala_terendah(opsi) -> str:
    """Pilih tingkat terendah pada pertanyaan berskala."""
    terbaik = ""
    peringkat = None

    for item in opsi:
        teks = _norm(item)
        for posisi, kata in enumerate(SKALA_URUT):
            if kata in teks and (peringkat is None or posisi < peringkat):
                terbaik, peringkat = item, posisi
                break

    return terbaik


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
    """Bentuk baku teks untuk perbandingan (huruf kecil, tanpa karakter gaib)."""
    return jawaban.bersihkan_teks(teks).lower()


def parse_gaji_juta(teks: str) -> float | None:
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


def parse_tahun(teks: str) -> tuple | None:
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

    # Formulir lamaran yang berada di dalam iframe (Indeed Apply / smartapply).
    # JobStreet memakai satu halaman penuh, jadi daftar ini kosong di sana dan
    # seluruh alur lama berjalan seperti sebelumnya.
    kerangka_lamaran_selectors: tuple = ()
    kerangka_lamaran_host: tuple = ()
    kerangka_timeout: float = 8.0

    def __init__(self, driver, wait=None):
        self.driver = driver
        self.wait = wait
        self.step_timeout = config.auto_apply_step_timeout
        self.submit_timeout = config.auto_apply_submit_timeout
        self.debug_dumps = 0
        self.di_kerangka = False

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
        return jawaban.bersihkan_teks(value).lower()

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

    def _find_clickable(self, selectors, texts=()) -> object | None:
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

    def _keluar_kerangka(self) -> None:
        """Kembali ke dokumen utama sebelum membuka lowongan berikutnya."""
        self.di_kerangka = False
        with contextlib.suppress(Exception):
            self.driver.switch_to.default_content()

    def _masuk_kerangka_lamaran(self) -> str:
        """Masuk ke iframe formulir lamaran bila situs memakainya.

        Beberapa situs (Indeed Apply / smartapply.indeed.com) menaruh formulir
        lamaran di dalam iframe. Tanpa masuk ke iframe, seluruh pencarian
        tombol dan isian hanya melihat halaman luar, sehingga alur berakhir
        "tidak dikenali" dan lamaran tidak pernah terkirim.

        Kembalikan "" bila tidak ada iframe (perilaku JobStreet tidak berubah)
        atau bila berhasil masuk; kembalikan alasan bila gagal.
        """
        selectors = getattr(self, "kerangka_lamaran_selectors", ())
        if not selectors:
            return ""

        batas = time.time() + self.kerangka_timeout
        galat = ""

        while time.time() < batas:
            for selector in selectors:
                for element in self._find_all(selector):
                    if not self._visible(element):
                        continue

                    alamat = ""
                    with contextlib.suppress(Exception):
                        alamat = (element.get_attribute("src") or "").strip()

                    if not self._kerangka_diizinkan(alamat):
                        continue

                    try:
                        self.driver.switch_to.frame(element)
                    except Exception as exc:
                        galat = (
                            "Formulir lamaran ada di dalam iframe tetapi tidak "
                            f"bisa dibuka otomatis: {exc}"
                        )
                        continue

                    self.di_kerangka = True
                    console.print(
                        "[dim]   formulir lamaran ada di iframe; masuk ke iframe[/]"
                    )
                    return ""

            time.sleep(0.4)

        return galat

    def _kerangka_diizinkan(self, alamat: str) -> bool:
        """Saring iframe: hanya iframe formulir milik situs ini."""
        host = getattr(self, "kerangka_lamaran_host", ())
        if not host:
            return True
        if not alamat:
            return True
        return any(nama in alamat for nama in host)

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

    def _dump_debug(self, job: dict, paksa: bool = False):
        """Simpan HTML + screenshot agar selector mudah diperbaiki.

        `paksa=True` dipakai saat tombol Lamar tidak ditemukan: justru jalur
        itulah yang paling sering gagal (Indeed 84 dari 84 percobaan), jadi
        bukti halaman harus tersimpan walau AUTO_APPLY_DEBUG tidak diisi.
        Batas 5 berkas per sesi tetap berlaku.
        """
        if (not config.auto_apply_debug and not paksa) or self.debug_dumps >= 5:
            return

        try:
            folder = Path("debug")
            folder.mkdir(exist_ok=True)

            stamp = time.strftime("%Y%m%d-%H%M%S")
            nama = f"{stamp}-{nama_berkas_aman(job.get('job_id'))}"
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
            with contextlib.suppress(Exception):
                self.driver.save_screenshot(str(dasar.with_suffix(".png")))
            self.debug_dumps += 1
            console.print(
                f"[dim]Halaman tidak dikenali; debug disimpan di "
                f"debug/{nama}.html[/]"
            )
        except Exception as exc:
            console.print(
                f"[dim]Debug gagal disimpan: {exc}[/]"
            )

    # Label yang TIDAK mungkin tombol kirim: langkah navigasi, tautan aplikasi,
    # tombol kembali. "review and submit" adalah judul langkah di bilah kemajuan
    # JobStreet, bukan tombol — dulu ia terpilih karena muncul lebih dulu di
    # halaman sehingga lamaran tidak pernah benar-benar terkirim.
    LABEL_BUKAN_KIRIM = (
        "review",
        "tinjau",
        "open app",
        "buka aplikasi",
        "back",
        "kembali",
        "batal",
        "cancel",
        "hapus",
        "delete",
        "continue",
        "lanjut",
    )

    def _boleh_jadi_tombol_kirim(self, element) -> bool:
        label = self._text(element)
        if not label:
            return False
        return not any(kata in label for kata in self.LABEL_BUKAN_KIRIM)

    def _find_submit_button(self, review_page: bool = False):
        """Cari tombol kirim. Di halaman review, cakupannya lebih luas.

        Urutan: selector resmi -> tombol bertipe submit -> pencocokan teks.
        Setiap kandidat harus lulus saringan label (bukan langkah navigasi).
        Bila ada beberapa kandidat teks, dipilih yang PALING BAWAH karena
        tombol kirim selalu berada di ujung formulir.
        """
        if review_page:
            # Di halaman review ada beberapa tombol mirip (mis. tombol
            # "Submit" di tengah dan di ujung formulir). Yang benar adalah
            # yang paling bawah, jadi seluruh kandidat dikumpulkan dulu.
            kandidat = self._kandidat_tombol_kirim()
            if kandidat:
                return kandidat[-1]
            return None

        button = self._find_clickable(self.submit_selectors, self.submit_texts)
        if button is not None and self._boleh_jadi_tombol_kirim(button):
            return button

        return None

    def _kandidat_tombol_kirim(self) -> list:
        """Semua tombol kirim yang layak, urut sesuai dokumen (atas -> bawah).

        Kandidat = tombol bertipe submit, atau tombol yang teksnya cocok
        dengan SUBMIT_TEXTS / memuat kata kunci kirim.
        """
        kata_kunci = ("submit", "kirim", "send application")
        kandidat = []
        terlihat = set()

        for selector in ("button[type='submit']", *self.submit_selectors,
                         "button", "[role='button']", "a"):
            for element in self._find_all(selector):
                if id(element) in terlihat:
                    continue
                if not self._visible(element) or not self._enabled(element):
                    continue
                if not self._boleh_jadi_tombol_kirim(element):
                    continue

                label = self._text(element)
                cocok_teks = any(
                    label == teks or label.startswith(teks)
                    for teks in self.submit_texts
                )
                if selector == "button[type='submit']" or cocok_teks or any(
                    kata in label for kata in kata_kunci
                ):
                    terlihat.add(id(element))
                    kandidat.append(element)

        return kandidat

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

    def _label_terlihat(self, element) -> bool:
        """True bila label/induk input terlihat.

        JobStreet menyembunyikan `<input type="radio">` asli (opacity 0 /
        ukuran 1 px) dan hanya menampilkan label-nya. Tanpa pemeriksaan ini,
        seluruh pertanyaan pilihan dianggap tidak ada.
        """
        with contextlib.suppress(Exception):
            id_el = (element.get_attribute("id") or "").strip()
            if id_el:
                for label in self._find_all(f"label[for='{id_el}']"):
                    if self._visible(label):
                        return True

        with contextlib.suppress(Exception):
            induk = element.find_element(By.XPATH, "..")
            if induk is not None and self._visible(induk):
                return True

        return False

    def _picu_perubahan(self, element) -> None:
        """Kirim event input+change (formulir React tidak membaca nilai diam-diam)."""
        with contextlib.suppress(Exception):
            self.driver.execute_script(
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                element,
            )

    def _pilih_radio(self, element, pilihan: str = "") -> bool:
        """Klik satu opsi radio dan pastikan benar-benar terpilih.

        Urutan: klik input → klik label for=id → klik elemen induk. Dipakai
        karena input asli sering tidak bisa diklik langsung.
        """
        if self._click(element) and self._selected(element):
            self._picu_perubahan(element)
            return True

        with contextlib.suppress(Exception):
            id_el = (element.get_attribute("id") or "").strip()
            if id_el:
                for label in self._find_all(f"label[for='{id_el}']"):
                    if self._click(label) and self._selected(element):
                        self._picu_perubahan(element)
                        return True

        with contextlib.suppress(Exception):
            induk = element.find_element(By.XPATH, "..")
            if induk is not None and self._click(induk) and self._selected(element):
                self._picu_perubahan(element)
                return True

        return self._selected(element)

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

        # 3. aria-labelledby -> teks elemen yang dirujuk
        with contextlib.suppress(Exception):
            ids = (element.get_attribute("aria-labelledby") or "").split()
            for id_rujukan in ids:
                for rujukan in self._find_all(f"[id='{id_rujukan}']"):
                    teks = " ".join(self._raw_text(rujukan).split())
                    if teks and not tampak_id_internal(teks):
                        return teks

        # 4. input dibungkus <label> (JobStreet sering memakai pola ini)
        with contextlib.suppress(Exception):
            induk_label = element.find_element(By.XPATH, "ancestor::label[1]")
            teks = " ".join(self._raw_text(induk_label).split())
            if teks and not tampak_id_internal(teks):
                return teks

        # 5. teks wadah induk — hanya bila wadah itu memuat SATU input saja.
        #    Tanpa syarat ini, wadah pertanyaan (yang memuat semua opsi) akan
        #    terbaca sebagai label dan seluruh opsi jadi sama.
        with contextlib.suppress(Exception):
            wadah = element.find_element(By.XPATH, "..")
            if wadah is not None:
                jumlah = len(wadah.find_elements(By.CSS_SELECTOR, "input"))
                teks = " ".join(self._raw_text(wadah).split())
                if (
                    jumlah <= 1
                    and 0 < len(teks) <= 60
                    and not tampak_id_internal(teks)
                ):
                    return teks

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
            kunci_opsi = {_norm(item) for item in opsi if item}

            for label_el in self._find_all(f"label[for='{id_el}']"):
                teks = " ".join(self._raw_text(label_el).split())

                # Label milik input radio biasanya adalah TEKS OPSI ("Ya"),
                # bukan pertanyaan. Jangan sampai dipakai sebagai pertanyaan.
                if teks and _norm(teks) not in kunci_opsi:
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

    def _teks_terpilih(self, element) -> str:
        """Teks opsi yang saat ini benar-benar terpilih di sebuah dropdown."""
        try:
            opsi = Select(element).first_selected_option
            return " ".join((opsi.text or "").split())
        except Exception:
            return ""

    def _pilih_opsi(self, element, teks: str) -> bool:
        """Pilih opsi dropdown dan pastikan nilainya benar-benar berubah."""
        target = " ".join(str(teks or "").split())

        try:
            Select(element).select_by_visible_text(target)
            if _norm(self._teks_terpilih(element)) == _norm(target):
                self._picu_perubahan(element)
                return True
        except Exception:
            pass

        try:
            for item in element.find_elements(By.TAG_NAME, "option"):
                if " ".join((item.text or "").split()) == target:
                    self._click(item)
                    if _norm(self._teks_terpilih(element)) == _norm(target):
                        self._picu_perubahan(element)
                        return True
                    break
        except Exception:
            pass

        # Jalan terakhir: set nilai + kirim event supaya state formulir ikut.
        try:
            berhasil = self.driver.execute_script(
                """
                const el = arguments[0], cari = arguments[1];
                const opsi = Array.from(el.options || []).find(
                    (o) => (o.textContent || '').trim() === cari);
                if (!opsi) { return false; }
                el.value = opsi.value;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                return true;
                """,
                element,
                target,
            )
        except Exception:
            return False

        if not berhasil:
            return False

        return _norm(self._teks_terpilih(element)) in ("", _norm(target))


    def _kunci_grup_tanpa_nama(self, element) -> str:
        """Kunci kelompok untuk input tanpa atribut `name`.

        Formulir Glints kadang tidak memberi `name` pada radio/checkbox.
        Mengelompokkannya berdasarkan teks pertanyaan saja salah untuk
        formulir skala: satu judul dipakai beberapa keahlian, sehingga semua
        kelompok menyatu. Wadah terdekat yang teksnya berbeda dari label opsi
        (yaitu kartu keahliannya) dipakai sebagai kunci.
        """
        label = _norm(self._label_untuk(element))
        induk = element

        for _ in range(3):
            try:
                induk = induk.find_element(By.XPATH, "..")
            except Exception:
                break

            teks = _norm(self._raw_text(induk))
            if teks and teks != label:
                return teks[:160]

        return _norm(self._pertanyaan(element, ())) or "tanpa-nama"

    def _pertanyaan_grup(self, element, opsi=()) -> str:
        """Pertanyaan + pembeda kelompok (mis. nama keahlian).

        Glints menampilkan satu judul untuk beberapa keahlian sekaligus
        ("Seberapa mahir kamu dengan keahlian berikut ini?") dengan kelompok
        radio terpisah per keahlian. Tanpa pembeda, ingatan jawaban keahlian
        yang satu menimpa keahlian lain sehingga jawaban tidak pernah dipakai
        ulang.
        """
        pertanyaan = self._pertanyaan(element, opsi)
        pembeda = self._pembeda_grup(element, pertanyaan, opsi)

        if not pembeda:
            return pertanyaan
        if not pertanyaan:
            return pembeda

        return f"{pertanyaan} — {pembeda}"

    def _pembeda_grup(self, element, pertanyaan: str, opsi=()) -> str:
        """Teks pembeda milik satu kelompok opsi (hanya untuk pertanyaan skala).

        Dibatasi pada kelompok berskala (>= 2 opsi tingkat) agar pertanyaan
        ya/tidak tidak ikut berubah kuncinya.
        """
        opsi = [item for item in opsi or [] if item]

        if len(opsi) < 3:
            return ""

        jumlah_skala = sum(
            1
            for item in opsi
            if any(kata in _norm(item) for kata in SKALA_URUT)
        )
        if jumlah_skala < 2:
            return ""

        kunci_pertanyaan = _norm(pertanyaan)
        kunci_opsi = {_norm(item) for item in opsi}
        induk = element

        for _ in range(4):
            try:
                induk = induk.find_element(By.XPATH, "..")
            except Exception:
                break

            teks = " ".join(self._raw_text(induk).split())
            if not teks:
                continue

            sisa = teks
            for label in opsi:
                sisa = re.sub(
                    re.escape(label), " ", sisa, flags=re.IGNORECASE
                )
            if pertanyaan:
                sisa = re.sub(
                    re.escape(pertanyaan), " ", sisa, flags=re.IGNORECASE
                )
            sisa = " ".join(sisa.split())
            kunci_sisa = _norm(sisa)

            if not kunci_sisa or kunci_sisa in kunci_opsi:
                continue
            if kunci_pertanyaan and kunci_sisa in kunci_pertanyaan:
                continue
            if len(sisa) > 120:
                continue

            return sisa

        return ""

    @staticmethod
    def _dari_ingatan(pertanyaan: str, opsi) -> tuple:
        """Pilih opsi dari ingatan jawaban pengguna. (pilihan, dari_ingatan)."""
        ingat = jawaban.cari(pertanyaan)

        if not ingat:
            return "", False

        kunci_ingat = jawaban.kunci_pertanyaan(ingat)
        for item in opsi or []:
            if jawaban.kunci_pertanyaan(item) == kunci_ingat:
                return item, True

        # Toleransi ejaan: "Menengah" vs "menengah " / "Ahli" vs "ahli".
        for item in opsi or []:
            kunci_opsi = jawaban.kunci_pertanyaan(item)
            if kunci_ingat and kunci_opsi and (
                kunci_ingat in kunci_opsi or kunci_opsi in kunci_ingat
            ):
                return item, True

        # Toleransi angka: "Rp 5 Jt" == "Rp 5 jt" == "Rp 5 million" ==
        # "Rp 5.000.000". Ini yang membuat pertanyaan gaji berhenti dilewati
        # padahal jawabannya sudah pernah diberikan.
        for item in opsi or []:
            if jawaban.sama_nilai(ingat, item):
                return item, True

        return "", False

    def _potret_jawaban(self) -> dict:
        """Isian formulir saat ini: {kunci pertanyaan: (pertanyaan, jawaban)}."""
        potret = {}

        # Radio dikelompokkan seperti pada _jawab_radio: menerima input asli
        # yang tersembunyi (label-nya terlihat) maupun yang tanpa atribut
        # `name`. Dulu keduanya dilewati, sehingga jawaban yang diisi pengguna
        # di formulir Glints tidak pernah terekam.
        grup = {}
        for element in self._find_all("input[type='radio']"):
            if not self._enabled(element):
                continue
            if not self._visible(element) and not self._label_terlihat(element):
                continue

            try:
                nama = (element.get_attribute("name") or "").strip()
            except Exception:
                nama = ""

            if nama:
                grup.setdefault("nama:" + nama, []).append(element)
            else:
                kunci = self._kunci_grup_tanpa_nama(element)
                grup.setdefault("grup:" + kunci, []).append(element)

        for elemen in grup.values():
            terpilih = [item for item in elemen if self._selected(item)]
            if not terpilih:
                continue

            opsi = [self._label_untuk(item) for item in elemen]
            opsi = [item for item in opsi if item]
            pertanyaan = self._pertanyaan_grup(elemen[0], opsi)
            kunci = jawaban.kunci_pertanyaan(pertanyaan)
            label = self._label_untuk(terpilih[0])

            if kunci and label:
                potret[kunci] = (pertanyaan, label)

        # Kotak centang multi-pilih: jawaban disimpan sebagai daftar
        # dipisah titik koma ("Excel; SAP").
        for elemen in self._kelompok_checkbox().values():
            terpilih = [
                self._label_untuk(item)
                for item in elemen
                if self._selected(item)
            ]
            terpilih = [item for item in terpilih if item]
            if not terpilih:
                continue

            opsi = [self._label_untuk(item) for item in elemen]
            opsi = [item for item in opsi if item]
            pertanyaan = self._pertanyaan_grup(elemen[0], opsi)
            kunci = jawaban.kunci_pertanyaan(pertanyaan)

            if kunci:
                potret[kunci] = (pertanyaan, "; ".join(terpilih))

        for element in self._find_all("select"):
            if not self._visible(element):
                continue

            try:
                terisi = (element.get_attribute("value") or "").strip()
            except Exception:
                continue

            if not terisi:
                continue

            label = ""
            try:
                terpilih = Select(element).first_selected_option
                label = " ".join((terpilih.text or "").split())
            except Exception:
                label = terisi

            if not label or label.strip("-— ") == "":
                continue

            pertanyaan = self._pertanyaan(element, self._teks_opsi(element))
            kunci = jawaban.kunci_pertanyaan(pertanyaan)
            if kunci:
                potret[kunci] = (pertanyaan, label)

        for selector in ("input[type='text']", "input[type='number']"):
            for element in self._find_all(selector):
                if not self._visible(element):
                    continue

                try:
                    isi = (element.get_attribute("value") or "").strip()
                except Exception:
                    continue

                if not isi:
                    continue

                pertanyaan = self._pertanyaan(element)
                kunci = jawaban.kunci_pertanyaan(pertanyaan)
                if kunci:
                    potret[kunci] = (pertanyaan, isi)

        return potret

    def _rekam_jawaban_pengguna(self, sebelum: dict) -> int:
        """Simpan isian yang baru atau berubah — itulah jawaban pengguna.

        Hanya yang berbeda dari potret awal yang dicatat, supaya jawaban hasil
        tebakan bot tidak ikut "diingat" sebagai jawaban pengguna.
        """
        if not getattr(config, "ingat_jawaban", True):
            return 0

        sesudah = self._potret_jawaban()
        baru = 0

        for kunci, (pertanyaan, jawaban_baru) in sesudah.items():
            lama = sebelum.get(kunci)
            if lama and jawaban.kunci_pertanyaan(lama[1]) == jawaban.kunci_pertanyaan(
                jawaban_baru
            ):
                continue

            if jawaban.ingat(pertanyaan, jawaban_baru):
                baru += 1
                tanda = "diperbarui" if lama else "diingat"
                console.print(
                    f'[dim green]   {tanda}: "{pertanyaan[:50]}" = '
                    f'"{jawaban_baru[:30]}"[/]'
                )

        if baru:
            console.print(
                f"[dim green]   {baru} jawaban disimpan — lain kali terisi "
                "otomatis.[/]"
            )

        return baru

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
        pilihan, dari_ingatan = self._dari_ingatan(pertanyaan, opsi)

        if not pilihan:
            pilihan = pilih_jawaban(pertanyaan, opsi)

        if pilihan and self._pilih_opsi(element, pilihan):
            catatan = " (ingatan)" if dari_ingatan else ""
            console.print(
                f'[dim]   jawab "{pilihan}"{catatan} untuk: '
                f'{pertanyaan[:70] or "pertanyaan"}[/]'
            )
            return pilihan

        return "" if not opsi else "-"

    def _jawab_radio(self) -> list:
        """Jawab pertanyaan radio (ya/tidak) yang polanya dikenali."""
        grup = {}

        for element in self._find_all("input[type='radio']"):
            if not self._enabled(element):
                continue

            # Input asli boleh tersembunyi selama labelnya terlihat.
            if not self._visible(element) and not self._label_terlihat(element):
                continue

            try:
                nama = (element.get_attribute("name") or "").strip()
            except Exception:
                nama = ""

            if nama:
                grup.setdefault("nama:" + nama, []).append(element)
            else:
                # Sebagian formulir menghilangkan atribut name. Dulu radio
                # seperti itu diabaikan total sehingga pertanyaannya tidak
                # pernah dijawab. Sekarang dikelompokkan menurut wadahnya
                # (kartu keahlian), bukan hanya judul yang dipakai bersama.
                kunci = self._kunci_grup_tanpa_nama(element)
                grup.setdefault("grup:" + kunci, []).append(element)

        gagal = []

        for element_grup in grup.values():
            if len(element_grup) < 2:
                continue

            if any(self._selected(item) for item in element_grup):
                continue

            # Pasangan (elemen, label) dijaga agar indeks tidak bergeser bila
            # ada opsi tanpa label.
            pasangan = []
            for item in element_grup:
                label = self._label_untuk(item)
                if label:
                    pasangan.append((item, label))

            opsi = [label for _, label in pasangan]

            pertanyaan = self._pertanyaan_grup(element_grup[0], opsi)

            # Pasal 8.4: persetujuan/hukum wajib dikonfirmasi pengguna.
            if jawaban.perlu_konfirmasi(pertanyaan):
                console.print(
                    f"[yellow]   perlu konfirmasi Anda:[/] {pertanyaan[:70]}"
                )
                log_aktivitas.catat(
                    f"Perlu konfirmasi (persetujuan/hukum): {pertanyaan[:120]}",
                    "warning",
                )
                gagal.append(pertanyaan or "pertanyaan persetujuan")
                continue

            pilihan, dari_ingatan = self._dari_ingatan(pertanyaan, opsi)

            if not pilihan:
                pilihan = pilih_jawaban_radio(pertanyaan, opsi)

            if not pilihan:
                gagal.append(pertanyaan or "pertanyaan pilihan")
                continue

            diklik = False
            for item in element_grup:
                if _norm(self._label_untuk(item)) == _norm(pilihan):
                    diklik = self._pilih_radio(item, pilihan)
                    break

            if diklik:
                catatan = " (ingatan)" if dari_ingatan else ""
                console.print(
                    f'[dim]   jawab "{pilihan}"{catatan} untuk: '
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

                if jawaban.perlu_konfirmasi(pertanyaan):
                    console.print(
                        f"[yellow]   perlu konfirmasi Anda:[/] {pertanyaan[:70]}"
                    )
                    log_aktivitas.catat(
                        "Perlu konfirmasi (persetujuan/hukum): "
                        f"{pertanyaan[:120]}",
                        "warning",
                    )
                    gagal.append(pertanyaan)
                    continue

                nilai = jawaban.cari(pertanyaan) or ""

                if not nilai and jenis == "gaji":
                    nilai = str(config.expected_salary or "").strip()
                elif not nilai and jenis == "pengalaman":
                    nilai = f"{float(config.years_experience or 0):g}"
                elif not nilai:
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

    def _kelompok_checkbox(self) -> dict:
        """Kotak centang dikelompokkan per `name` atau per pertanyaannya."""
        grup = {}

        for element in self._find_all("input[type='checkbox']"):
            if not self._enabled(element):
                continue
            if not self._visible(element) and not self._label_terlihat(element):
                continue

            try:
                nama = (element.get_attribute("name") or "").strip()
            except Exception:
                nama = ""

            kunci = nama or self._kunci_grup_tanpa_nama(element)
            grup.setdefault(kunci, []).append(element)

        return grup

    def _dari_ingatan_banyak(self, pertanyaan: str, opsi) -> list:
        """Opsi yang pernah dipilih pengguna untuk kotak centang (bisa banyak)."""
        ingat = jawaban.cari(pertanyaan)
        if not ingat:
            return []

        diingat = {
            jawaban.kunci_pertanyaan(bagian)
            for bagian in str(ingat).split(";")
            if bagian.strip()
        }

        hasil = [item for item in opsi if jawaban.kunci_pertanyaan(item) in diingat]

        if hasil:
            return hasil

        # Toleransi ejaan/spasi seperti pada _dari_ingatan.
        for item in opsi:
            kunci_opsi = jawaban.kunci_pertanyaan(item)
            if any(
                kunci and kunci_opsi and (kunci in kunci_opsi or kunci_opsi in kunci)
                for kunci in diingat
            ):
                hasil.append(item)

        return hasil

    def _jawab_checkbox(self) -> list:
        """Jawab pertanyaan centang (multi-pilih) yang aman dijawab.

        Kebijakan (tidak mengklaim hal yang tidak benar):
        0. pakai jawaban yang pernah diberikan (ingatan) lebih dulu;
        1. centang opsi yang cocok dengan keterampilan pengguna
           (SKILL_KEYWORDS / TITLE_KEYWORDS);
        2. bila tidak ada yang cocok, centang opsi "tidak ada / none /
           other" sebagai jawaban jujur;
        3. selain itu biarkan untuk pengguna (masuk daftar manual).
        """
        grup = self._kelompok_checkbox()

        gagal = []
        kata_kunci = [
            _norm(kata) for kata in (
                list(getattr(config, "skill_keywords", ()) or ())
                + list(getattr(config, "title_keywords", ()) or ())
            )
            if _norm(kata)
        ]
        kata_nol = (
            "none", "no experience", "tidak ada", "tidak punya", "belum ada",
            "other", "lainnya", "lain-lain", "tidak relevan", "not applicable",
        )

        for element_grup in grup.values():
            if len(element_grup) < 2:
                continue

            if any(self._selected(item) for item in element_grup):
                continue

            # Pasangan (elemen, label) dijaga agar indeks tidak bergeser bila
            # ada opsi tanpa label.
            pasangan = []
            for item in element_grup:
                label = self._label_untuk(item)
                if label:
                    pasangan.append((item, label))

            opsi = [label for _, label in pasangan]

            pertanyaan = self._pertanyaan_grup(element_grup[0], opsi)

            if jawaban.perlu_konfirmasi(pertanyaan):
                gagal.append(pertanyaan or "pertanyaan persetujuan")
                continue

            dari_ingatan = self._dari_ingatan_banyak(pertanyaan, opsi)

            if dari_ingatan:
                for item, label in pasangan:
                    if label not in dari_ingatan:
                        continue
                    if self._centang(item):
                        console.print(
                            f'[dim]   centang "{label}" (ingatan) untuk: '
                            f"{pertanyaan[:70]}[/]"
                        )
                continue

            pilihan = [
                label for label in opsi
                if any(kata in _norm(label) for kata in kata_kunci)
            ]

            if not pilihan:
                pilihan = [
                    label for label in opsi
                    if any(kata in _norm(label) for kata in kata_nol)
                ]

            if not pilihan:
                gagal.append(pertanyaan or "pertanyaan centang")
                continue

            for item, label in pasangan:
                if label not in pilihan:
                    continue
                if self._centang(item):
                    console.print(
                        f'[dim]   centang "{label}" untuk: {pertanyaan[:70]}[/]'
                    )

        return gagal

    def _centang(self, element) -> bool:
        """Centang satu kotak dan pastikan statusnya berubah."""
        if self._selected(element):
            return True

        if self._click(element) and self._selected(element):
            self._picu_perubahan(element)
            return True

        with contextlib.suppress(Exception):
            id_el = (element.get_attribute("id") or "").strip()
            if id_el:
                for label in self._find_all(f"label[for='{id_el}']"):
                    if self._click(label) and self._selected(element):
                        self._picu_perubahan(element)
                        return True

        with contextlib.suppress(Exception):
            induk = element.find_element(By.XPATH, "..")
            if induk is not None and self._click(induk) and self._selected(element):
                self._picu_perubahan(element)
                return True

        return self._selected(element)

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
        gagal.extend(self._jawab_checkbox())
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
            f"{batas} detik. Isian Anda akan diingat dan dipakai otomatis "
            "di lamaran berikutnya."
        )

        sebelum = self._potret_jawaban()

        for sisa in range(batas, 0, -1):
            time.sleep(1)

            if self._is_success():
                self._rekam_jawaban_pengguna(sebelum)
                return "applied"

            # Lanjut hanya bila tidak ada pertanyaan tersisa DAN tidak ada
            # peringatan validasi — supaya tidak mengklik Kirim berulang kali.
            if not self.jawab_pertanyaan() and not self._validation_error():
                self._rekam_jawaban_pengguna(sebelum)
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
                self.driver.switch_to.window(next(iter(handles_before)))
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
        """Lamar satu lowongan; semua isian pengguna direkam di akhir.

        Pembungkus ini memastikan perubahan jawaban tetap diingat walau alur
        berakhir dengan `manual_required`, galat, atau waktu tunggu habis —
        bukan hanya saat lamaran berhasil.
        """
        try:
            potret_awal = self._potret_jawaban()
        except Exception:
            potret_awal = {}

        try:
            return self._apply_alur(job)
        finally:
            # Jangan pernah menggagalkan lamaran hanya karena pencatatan.
            with contextlib.suppress(Exception):
                self._rekam_jawaban_pengguna(potret_awal)

    def _apply_alur(self, job: dict) -> ApplyResult:
        url = (job.get("url") or "").strip()

        if not url:
            return ApplyResult(False, "error", "URL lowongan kosong")

        # Lowongan sebelumnya bisa saja meninggalkan browser di dalam iframe.
        self._keluar_kerangka()

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
                # (mis. Glints "Lamar 1x tap di aplikasi"), atau situs meminta
                # login/verifikasi lebih dulu. Simpan bukti halaman supaya
                # penyebabnya terbaca, bukan ditebak.
                alasan = self._blocker()
                self._dump_debug(job, paksa=True)

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

            # Indeed Apply menampilkan formulirnya di iframe; masuk dulu agar
            # isian dan tombol Kirim bisa ditemukan.
            galat_kerangka = self._masuk_kerangka_lamaran()
            if galat_kerangka:
                self._dump_debug(job)
                return ApplyResult(False, "manual_required", galat_kerangka)

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

            if self._is_success() or (
                sudah_klik_kirim and self.is_already_applied()
            ):
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
