"""Pencarian dan pelamaran otomatis di Indeed (id.indeed.com).

Aturan Indeed **sama persis dengan JobStreet**:

* riset semua kata kunci × semua lokasi `LOCATIONS`, maksimal 5 halaman per
  kombinasi (halaman 6 dan seterusnya tidak pernah dibuka),
* urut tanggal terbaru (`sort=date`), dedupe lintas kombinasi,
* saring dengan `JobFilter` yang sama (judul, lokasi, gaji `MIN_SALARY`,
  kualifikasi) + wajib logo perusahaan bila `REQUIRE_COMPANY_LOGO=true`,
* skor 8 dimensi lalu ranking global, ambil yang terbaik sebanyak sisa kuota,
* kuota harian dari `kuota.py` — **dipakai bersama** JobStreet dan Glints,
* `AUTO_APPLY_MAX_PER_SESSION`, `DELAY_BETWEEN_APPLY`,
* lewati lowongan yang sudah pernah dilamar (tanda situs **dan** database),
* mode manual `AUTO_APPLY=false`, login habis menghentikan sesi,
* notifikasi Telegram per lamaran + laporan harian,
* ingatan jawaban formulir (`jawaban.py`) — sekali diisi, terisi otomatis.
"""

import contextlib
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from rich.console import Console
from rich.table import Table
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

import antrean
import kendali
import kuota
import log_aktivitas
from auto_apply import ApplyResult, AutoApplier
from browser import buka_chrome, tutup_chrome
from config import MAKS_HALAMAN_RISET, batas_halaman_riset, config
from database import db
from glints import (
    folder_debug,
    label_umur,
    pilih_teratas,
    tampilkan_perbandingan,
    tampilkan_rincian_skor,
    umur_dari_teks,
)
from job_filter import (
    JobFilter,
    dedupe_jobs,
)
from job_filter import (
    alasan_tidak_layak as alasan_standar,
)
from notifier import notifier

console = Console()

DOMAIN = "indeed.com"
BASE = "https://id.indeed.com"
LOGIN_URL = f"{BASE}/account/login"

# Halaman pencarian: `sort=date` = urut tanggal terbaru (setara "Baru
# Ditambahkan" di Glints dan "tanggal terbaru" di JobStreet).
SEARCH_URL = BASE + "/jobs?q={keyword}&l={location}&sort=date"

# Kunci lowongan Indeed ada di parameter `jk` (mis. ?jk=1a2b3c4d5e6f7890).
TAUTAN_LOWONGAN = re.compile(r"[?&]jk=([0-9a-zA-Z]+)")

# Tautan yang bukan halaman lowongan.
TAUTAN_BUKAN_LOWONGAN = (
    "/career/",
    "/companies/",
    "/salaries/",
    "/q-",
    "advice",
)

# Tombol/tautan yang berarti lamaran dialihkan ke situs perusahaan.
TEKS_SITUS_LAIN = (
    "apply on company site",
    "apply on employer site",
    "lamar di situs perusahaan",
    "lamar di situs perusahaan",
    "melamar di situs perusahaan",
)

# Teks khas Indeed saat lamaran sudah terkirim.
SUKSES_INDEED = (
    "lamaran anda telah dikirim",
    "lamaran anda sudah dikirim",
    "lamaran berhasil dikirim",
    "your application has been submitted",
    "application submitted",
    "anda telah melamar",
)

# Teks khas Indeed saat lowongan sudah pernah dilamar.
SUDAH_DILAMAR_TEXTS = (
    "anda sudah melamar",
    "sudah pernah melamar",
    "you have already applied",
    "sudah dilamar",
    "applied",
)

# Skrip pembaca kartu: dibaca dari tautan `jk=` agar tahan perubahan kelas CSS.
SKRIP_KARTU = r"""
const hasil = [];
const dilihat = new Set();

function teks(el) {
    return el ? (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim() : "";
}

for (const tautan of document.querySelectorAll("a[href*='jk=']")) {
    const href = tautan.getAttribute("href") || "";
    if (!href || href.includes("/career/") || href.includes("/companies/")) continue;

    const wadah = tautan.closest(
        "li, td.resultContent, div.job_seekers_intention, div.jobsearch-SerpJobCard, " +
        "div.css-1m4cuuf, article, div.slider_container"
    ) || tautan.parentElement;
    if (!wadah) continue;

    const isi = teks(wadah);
    if (isi.length < 10) continue;

    const judulEl = wadah.querySelector("h2, .jobTitle, a[data-testid='jobTitle']");
    const judul = teks(judulEl) || teks(tautan);
    const kunci = (href.match(/[?&]jk=([0-9a-zA-Z]+)/) || [])[1] || "";
    if (!kunci || dilihat.has(kunci)) continue;
    dilihat.add(kunci);

    const ambil = (pemilih) => {
        for (const p of pemilih) {
            const el = wadah.querySelector(p);
            const t = teks(el);
            if (t) return t;
        }
        return "";
    };

    const logo = [];
    for (const img of wadah.querySelectorAll("img")) {
        logo.push({
            src: img.getAttribute("src") || img.getAttribute("data-src") || "",
            alt: img.getAttribute("alt") || "",
            penanda: (img.getAttribute("data-testid") || "") + " " +
                      (img.getAttribute("class") || "")
        });
    }

    hasil.push({
        url: href,
        kunci: kunci,
        title: judul,
        company: ambil([
            "[data-testid='company-name']", "span.companyName",
            "div.company_location a", ".css-1saizt3"
        ]),
        location: ambil([
            "[data-testid='text-location']", "div.companyLocation",
            "div.company_location div", ".css-1p0sjhy"
        ]),
        salary: ambil([
            "[data-testid='attribute_snippet_testid']", "span.salary-snippet",
            "div.metadata.salary-snippet-container", ".css-1cvvo1b"
        ]),
        text: isi,
        logo: logo
    });
}

return hasil;
"""


def url_pencarian(keyword: str, location: str = "") -> str:
    """URL pencarian Indeed, urut tanggal terbaru."""
    return SEARCH_URL.format(
        keyword=quote_plus(str(keyword or "").strip()),
        location=quote_plus(str(location or "").strip()),
    )


def id_dari_url(url: str) -> str:
    """Kunci lowongan (`jk`) dari sebuah URL Indeed."""
    cocok = TAUTAN_LOWONGAN.search(url or "")
    return cocok.group(1) if cocok else ""


# Gambar pengganti di kartu Indeed (bukan logo perusahaan).
_BUKAN_LOGO_INDEED = (
    "placeholder",
    "no-logo",
    "nologo",
    "no-logo",
    "noimage",
    "no-image",
    "default-company",
    "company-logo-default",
    "spacer",
    "pixel",
    "1x1",
    "blank",
    "transparent",
)


def logo_kartu_indeed(kandidat, perusahaan: str = "") -> tuple:
    """Apakah kartu Indeed menampilkan logo perusahaan.

    Indeed hanya menampilkan gambar perusahaan bila logonya benar-benar ada;
    selain itu ia memakai gambar pengganti (placeholder). Karena itu aturan
    JobStreet yang menuntut kata "logo"/"brand" pada URL terlalu ketat di sini:
    logo Indeed sering berasal dari CDN perusahaan tanpa kata "logo".
    """
    if not isinstance(kandidat, (list, tuple)) or not kandidat:
        return False, "tidak ada gambar"

    for item in kandidat:
        if not isinstance(item, dict):
            continue

        src = str(item.get("src") or "").strip()
        alt = str(item.get("alt") or "").strip()
        penanda = str(item.get("penanda") or "").strip().lower()

        if not src and not alt:
            continue

        gabungan = f"{src} {penanda}".lower()

        # Data URI kecil = garis/pengisi, bukan logo.
        if src.startswith("data:") and len(src) < 200:
            continue

        if any(tanda in gabungan for tanda in _BUKAN_LOGO_INDEED):
            continue

        if src.startswith("http") or alt:
            return True, f"<img alt='{alt[:30]}'>"

    return False, "gambar pengganti"


def rapikan_kartu(data: Dict) -> Optional[Dict]:
    """Ubah hasil pembaca kartu menjadi dict lowongan; None bila tidak layak."""
    if not isinstance(data, dict):
        return None

    kunci = str(data.get("kunci") or "").strip() or id_dari_url(data.get("url", ""))
    judul = " ".join(str(data.get("title") or "").split())

    if not kunci or not judul:
        return None

    teks = " ".join(str(data.get("text") or "").split())
    perusahaan = " ".join(str(data.get("company") or "").split())
    punya_logo, info_logo = logo_kartu_indeed(data.get("logo"), perusahaan)
    umur = umur_dari_teks(teks.lower())

    return {
        "has_logo": punya_logo,
        # Kartu Indeed tidak memuat logo perusahaan, jadi aturan "wajib logo"
        # (JobStreet & Glints) tidak dipakai di sini.
        "logo_diabaikan": True,
        "logo_src": info_logo,
        "job_id": f"indeed:{kunci}",
        "title": judul,
        "company": perusahaan,
        "location": " ".join(str(data.get("location") or "").split()),
        "salary": " ".join(str(data.get("salary") or "").split()),
        "description": teks[:800],
        "url": f"{BASE}/viewjob?jk={kunci}",
        "date_posted": label_umur(umur),
        "age_days": umur,
        "source": "indeed",
        "sudah_dilamar": any(tanda in teks.lower() for tanda in SUDAH_DILAMAR_TEXTS),
        "khusus_aplikasi": False,
    }


def alasan_tidak_layak(job: Dict, saringan: Optional[JobFilter] = None) -> str:
    """Alasan lowongan tidak dicoba dilamar ('' bila layak).

    Memakai aturan tunggal JobStreet (`job_filter.alasan_tidak_layak`), tanpa
    syarat tambahan khusus Indeed.
    """
    return alasan_standar(job, saringan)


class IndeedApplier(AutoApplier):
    """AutoApplier dengan peta tombol Indeed."""

    situs_host = DOMAIN
    nama_situs = "Indeed"

    apply_selectors = (
        "button#indeedApplyButton",
        "button[id='indeedApplyButton']",
        "button[data-testid='apply-button']",
        "a[data-testid='apply-button']",
        "button[id='applyButton']",
    )
    apply_texts = (
        "lamar sekarang",
        "apply now",
        "lamar dengan indeed",
        "apply with indeed",
        "lamar",
    )

    submit_selectors = (
        "button[data-testid='submit-application-button']",
        "button[id='form-action-submit']",
        "button[type='submit']",
    )
    submit_texts = (
        "kirim lamaran",
        "submit application",
        "kirim lamaran anda",
        "submit your application",
        "kirim",
        "submit",
    )

    continue_selectors = (
        "button[data-testid='continue-button']",
        "button[id='form-action-continue']",
    )
    continue_texts = (
        "lanjutkan",
        "lanjut",
        "continue",
        "berikutnya",
        "selanjutnya",
        "next",
    )

    success_texts = SUKSES_INDEED
    already_texts = SUDAH_DILAMAR_TEXTS

    def __init__(self, driver, wait=None):
        super().__init__(driver, wait)

        # Formulir Indeed (termasuk Indeed Apply) dimuat bertahap.
        self.step_timeout = max(self.step_timeout, 12)
        self.submit_timeout = max(self.submit_timeout, 30)


class IndeedBot:
    """Mesin Indeed: buka pencarian, baca kartu, lalu melamar."""

    def __init__(self):
        self.driver = None
        self.filters = JobFilter()
        self.login_expired = False
        self.diagnosa_terakhir: Dict = {}

    # ------------------------------ browser ---------------------------
    def init_browser(self):
        console.print("[bold blue]Membuka Chrome untuk Indeed...[/]")
        self.driver = buka_chrome(label="Indeed")
        console.print("[bold green]Chrome siap.[/]")

    def tutup(self):
        tutup_chrome(self.driver)

    def _url(self) -> str:
        with contextlib.suppress(Exception):
            return str(self.driver.current_url or "")
        return ""

    def _teks_halaman(self) -> str:
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            return " ".join((body.text or "").split()).lower()
        except Exception:
            return ""

    def sudah_login(self) -> bool:
        """Tebakan login: bukan halaman masuk dan tidak ada ajakan masuk."""
        url = self._url().lower()
        if "/account/login" in url or "/login" in url:
            return False

        teks = self._teks_halaman()
        if not teks:
            return False

        return not (
            "masuk ke indeed" in teks
            or "sign in to indeed" in teks
            or "masuk atau daftar" in teks
        )

    def login(self) -> bool:
        """Buka halaman login dan tunggu pengguna menyelesaikannya sendiri."""
        self.driver.get(LOGIN_URL)
        time.sleep(2)

        if self.sudah_login():
            console.print("[green]Sesi Indeed sudah aktif.[/]")
            return True

        console.print(
            "[yellow]Silakan login di Chrome (jendela yang terbuka). "
            "Program menunggu otomatis — tidak perlu menekan apa pun.[/]"
        )

        batas = time.time() + (600 if config.login_wait else 30)
        while time.time() < batas:
            time.sleep(2)
            if self.sudah_login():
                console.print("[green]Login Indeed terdeteksi.[/]")
                return True

        return False

    # --------------------------- pencarian ----------------------------
    def _tautan_kartu(self) -> List[str]:
        try:
            elemen = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='jk=']")
        except Exception:
            return []

        hasil = []
        for satu in elemen:
            with contextlib.suppress(Exception):
                href = satu.get_attribute("href") or ""
                if not href or any(bukan in href for bukan in TAUTAN_BUKAN_LOWONGAN):
                    continue
                if TAUTAN_LOWONGAN.search(href):
                    hasil.append(href)

        return hasil

    def _tunggu_kartu(self, detik: Optional[int] = None) -> int:
        """Tunggu sampai tautan lowongan muncul (SEARCH_WAIT detik)."""
        batas = time.time() + max(
            3, int(detik if detik is not None else config.search_wait)
        )
        jumlah = len(self._tautan_kartu())
        digulir = False
        mulai = time.time()

        while jumlah == 0 and time.time() < batas:
            if not digulir and time.time() - mulai >= 3:
                with contextlib.suppress(Exception):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                digulir = True

            time.sleep(0.5)
            jumlah = len(self._tautan_kartu())

        return jumlah

    def buka_pencarian(self, keyword: str, location: str = "") -> bool:
        """Buka halaman pencarian Indeed untuk satu kata kunci & lokasi."""
        url = url_pencarian(keyword, location)
        self.driver.get(url)
        time.sleep(1)

        if self.kena_captcha():
            console.print(
                "[bold yellow]Indeed menampilkan verifikasi/captcha. "
                "Selesaikan di jendela Chrome, lalu jalankan lagi.[/]"
            )
            batas = time.time() + 60
            while time.time() < batas and self.kena_captcha():
                time.sleep(2)

        jumlah = self._tunggu_kartu()
        if jumlah:
            console.print(f"[dim]Halaman pencarian Indeed: {url}[/]")
            return True

        console.print(
            f"[yellow]Tidak ada kartu lowongan di halaman Indeed: {url}[/]"
        )
        return False

    def kena_captcha(self) -> bool:
        teks = self._teks_halaman()
        return any(
            tanda in teks
            for tanda in ("unusual traffic", "captcha", "verifikasi")
        )

    def _halaman_berikutnya(self) -> bool:
        """Klik tombol halaman berikutnya; False bila tidak ada."""
        selectors = (
            "a[data-testid='pagination-page-next']",
            "a[aria-label='Next Page']",
            "a[aria-label='Berikutnya']",
            "a.np",
            "a[rel='next']",
        )

        for selector in selectors:
            for elemen in self.driver.find_elements(By.CSS_SELECTOR, selector):
                with contextlib.suppress(Exception):
                    if elemen.is_displayed() and elemen.is_enabled():
                        self.driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});",
                            elemen,
                        )
                        elemen.click()
                        time.sleep(1.5)
                        self._tunggu_kartu()
                        return True

        return False

    def _kartu_mentah(self) -> list:
        try:
            hasil = self.driver.execute_script(SKRIP_KARTU)
        except Exception:
            return []

        return hasil if isinstance(hasil, list) else []

    def _kartu_fallback(self) -> list:
        """Baca langsung dari elemen <a> bila skrip kartu gagal."""
        hasil = []

        for elemen in self.driver.find_elements(By.CSS_SELECTOR, "a[href*='jk=']"):
            with contextlib.suppress(Exception):
                href = elemen.get_attribute("href") or ""
                if not href or any(bukan in href for bukan in TAUTAN_BUKAN_LOWONGAN):
                    continue
                kunci = id_dari_url(href)
                if not kunci:
                    continue

                wadah = elemen
                with contextlib.suppress(Exception):
                    wadah = elemen.find_element(By.XPATH, "./ancestor::li[1]")

                teks = " ".join(((wadah.text if wadah else "") or "").split())
                hasil.append({
                    "url": href,
                    "kunci": kunci,
                    "title": " ".join((elemen.text or "").split()),
                    "text": teks,
                    "logo": [],
                })

        return hasil

    def cari(self, keyword: str, halaman: int = 0,
             location: str = "") -> List[Dict]:
        """Kumpulkan lowongan Indeed: satu kata kunci, maksimal `halaman` muat."""
        if not self.buka_pencarian(keyword, location):
            return []

        lowongan: List[Dict] = []
        sudah_ada = set()

        def serap() -> int:
            baru = 0
            mentah = self._kartu_mentah() or self._kartu_fallback()

            for data in mentah:
                job = rapikan_kartu(data)
                if not job or job["job_id"] in sudah_ada:
                    continue
                sudah_ada.add(job["job_id"])
                lowongan.append(job)
                baru += 1

            return baru

        serap()

        for _ in range(max(0, halaman)):
            if not self._halaman_berikutnya():
                break

            if serap() == 0:
                break

        return lowongan

    # ----------------------------- melamar ----------------------------
    def lamar(self, job: dict) -> ApplyResult:
        """Lamar satu lowongan Indeed dengan aturan yang sama seperti JobStreet."""
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()
        job_id = str(job.get("job_id") or "").strip()

        if not title or not url:
            console.print(
                "[yellow]Lowongan dilewati karena judul atau URL tidak terbaca.[/]"
            )
            return ApplyResult(False, "error", "Judul atau URL tidak terbaca")

        if not job_id:
            job_id = f"indeed:{id_dari_url(url)}"
            job["job_id"] = job_id

        if db.is_already_applied(job_id):
            return ApplyResult(False, "already_applied", "Sudah tercatat dilamar")

        if not config.auto_apply:
            return self._lamar_manual(job, job_id)

        console.print(
            f"\n[bold magenta]{title}[/] [cyan](otomatis)[/]"
        )

        ulang = 0

        while True:
            try:
                hasil = IndeedApplier(self.driver).apply(job)
            except WebDriverException as exc:
                if "chrome" in str(exc).lower() and "closed" in str(exc).lower():
                    raise
                self._catat(job_id, "error", f"Galat browser: {exc}")
                return ApplyResult(False, "error", f"Galat browser: {exc}")
            except Exception as exc:
                self._catat(job_id, "error", f"Galat tak terduga: {exc}")
                return ApplyResult(False, "error", f"Galat tak terduga: {exc}")

            # Auto recovery yang sama dengan JobStreet & Glints.
            if (
                hasil.status == "error"
                and antrean.sementara(hasil.reason)
                and ulang < antrean.maks_ulang()
            ):
                ulang += 1
                log_aktivitas.catat(
                    f"Ulang {ulang}/{antrean.maks_ulang()} (Indeed): "
                    f"{title} — {(hasil.reason or '')[:140]}",
                    "warning",
                )
                if antrean.jeda_ulang():
                    time.sleep(antrean.jeda_ulang())
                continue
            break

        if hasil.status == "applied":
            self._catat(job_id, "applied", hasil.reason or "Dikirim otomatis")
            console.print("[bold green]Lamaran terkirim otomatis.[/]")
        elif hasil.status == "already_applied":
            self._catat(job_id, "already_applied", hasil.reason)
        elif hasil.status == "login_required":
            self._catat(job_id, "error", hasil.reason)
            self.login_expired = True
            console.print(
                "[bold red]Sesi login Indeed sudah habis. Sesi dihentikan.[/]"
            )
        elif hasil.status == "manual_required":
            self._catat(job_id, "manual_required", hasil.reason)
            console.print(f"[yellow]Dilewati: {hasil.reason}[/]")
        else:
            self._catat(job_id, "error", hasil.reason)
            console.print(f"[bold red]Gagal melamar otomatis: {hasil.reason}[/]")

        return hasil

    @staticmethod
    def _catat(job_id: str, status: str, catatan: str) -> None:
        try:
            db.record_application(job_id, status, catatan)
        except Exception as exc:
            console.print(f"[yellow]Gagal mencatat lamaran: {exc}[/]")

    def _lamar_manual(self, job: dict, job_id: str) -> ApplyResult:
        """Mode manual: buka lowongan, pengguna melamar sendiri."""
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()

        try:
            self.driver.get(url)
            time.sleep(2)

            teks = self._teks_halaman()
            if any(tanda in teks for tanda in SUDAH_DILAMAR_TEXTS):
                self._catat(
                    job_id, "already_applied",
                    "Halaman menandai lowongan ini sudah pernah dilamar",
                )
                return ApplyResult(False, "already_applied", "Sudah pernah dilamar")

            pencatat = IndeedApplier(self.driver)
            with contextlib.suppress(Exception):
                potret_awal = pencatat._potret_jawaban()

            console.print(f"\n[bold magenta]{title}[/]")
            console.print(f"Perusahaan: {job.get('company', 'Tidak diketahui')}")
            console.print(f"URL: {url}")
            console.print(
                "[cyan]Tinjau lowongan di Chrome. Jika cocok, kirim lamaran "
                "sendiri.[/]"
            )

            jawab = input(
                "Setelah selesai meninjau, tekan Enter "
                "(ketik y bila lamaran sudah terkirim): "
            ).strip().lower()

            with contextlib.suppress(Exception):
                pencatat._rekam_jawaban_pengguna(potret_awal)

            if jawab in ("y", "ya", "yes"):
                self._catat(
                    job_id, "applied", "Dikirim manual dan dikonfirmasi pengguna"
                )
                return ApplyResult(True, "applied", "Dikonfirmasi manual")

            self._catat(
                job_id, "skipped",
                "Tidak dikonfirmasi sebagai lamaran terkirim",
            )
            return ApplyResult(False, "skipped", "Tidak dikonfirmasi")

        except (EOFError, KeyboardInterrupt):
            console.print(
                "\n[yellow]Tinjauan dibatalkan; lamaran tidak dicatat.[/]"
            )
            return ApplyResult(False, "skipped", "Dibatalkan")
        except Exception as exc:
            console.print(f"[bold red]Gagal membuka lowongan: {exc}[/]")
            self._catat(job_id, "error", str(exc))
            return ApplyResult(False, "error", str(exc))

    # ---------------------------- diagnosa ----------------------------
    def _judul_halaman(self) -> str:
        with contextlib.suppress(Exception):
            return " ".join(str(self.driver.title or "").split())
        return ""

    def simpan_diagnosa(self, awalan: str = "indeed", keyword: str = "") -> Dict:
        """Simpan HTML + screenshot dan laporkan penyebab kartu tidak terbaca."""
        folder = folder_debug()
        cap = f"{awalan}-{time.strftime('%Y%m%d-%H%M%S')}"

        if keyword:
            bersih = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
            if bersih:
                cap += f"-{bersih}"

        html = folder / f"{cap}.html"
        png = folder / f"{cap}.png"

        kartu = [
            job for job in (
                rapikan_kartu(mentah) for mentah in self._kartu_mentah()
            ) if job
        ]

        info = {
            "url": self._url(),
            "judul": self._judul_halaman(),
            "jumlah_tautan": len(self._tautan_kartu()),
            "jumlah_kartu": len(kartu),
            "captcha": self.kena_captcha(),
            "berkas_html": "",
            "berkas_png": "",
        }

        with contextlib.suppress(Exception):
            folder.mkdir(parents=True, exist_ok=True)
            html.write_text(self.driver.page_source or "", encoding="utf-8")
            info["berkas_html"] = str(html)

        with contextlib.suppress(Exception):
            self.driver.save_screenshot(str(png))
            info["berkas_png"] = str(png)

        console.print(f"[cyan]URL akhir:[/] {info['url']}")
        console.print(f"[cyan]Judul:[/] {info['judul']}")
        console.print(
            f"[cyan]Tautan lowongan:[/] {info['jumlah_tautan']} · "
            f"[cyan]kartu terbaca:[/] {info['jumlah_kartu']}"
        )
        if info["captcha"]:
            console.print(
                "[yellow]Halaman meminta verifikasi/captcha. Selesaikan di "
                "jendela Chrome, lalu jalankan lagi.[/]"
            )
        if info["berkas_html"]:
            console.print(f"[dim]HTML: {info['berkas_html']}[/]")
        if info["berkas_png"]:
            console.print(f"[dim]Screenshot: {info['berkas_png']}[/]")

        self.diagnosa_terakhir = info
        return info


# ----------------------------------------------------------------------
# Alur utama
# ----------------------------------------------------------------------
def kumpulkan_lowongan(bot: IndeedBot, kata_kunci: List[str],
                       halaman: int,
                       lokasi: Optional[List[str]] = None) -> List[Dict]:
    """Riset Indeed: semua lokasi × kata kunci, dedupe, maksimal 5 halaman."""
    daftar_lokasi = list(lokasi if lokasi is not None else config.locations) or [""]
    halaman = max(1, min(int(halaman or 1), MAKS_HALAMAN_RISET))
    lowongan: List[Dict] = []
    terlihat = set()
    duplikat = 0

    total = len(daftar_lokasi) * len(kata_kunci)
    selesai = 0
    mulai = time.monotonic()

    console.print(
        f"[bold blue]RISET INDEED[/] — {len(kata_kunci)} kata kunci × "
        f"{len(daftar_lokasi)} lokasi, maksimal {halaman} halaman per "
        f"kombinasi (batas tetap {MAKS_HALAMAN_RISET}), urut tanggal terbaru."
    )

    for location in daftar_lokasi:
        for keyword in kata_kunci:
            kata = str(keyword or "").strip()
            if not kata:
                continue

            console.print(
                f"[cyan]Indeed: '{kata}'"
                + (f" — lokasi {location}" if location else " — semua lokasi")
                + f" — muat sampai {halaman} halaman[/]"
            )

            kartu = bot.cari(kata, max(0, halaman - 1), location=location)

            baru = 0
            for job in kartu:
                if job["job_id"] in terlihat:
                    duplikat += 1
                    continue
                terlihat.add(job["job_id"])
                job.setdefault("kata_kunci", kata)
                lowongan.append(job)
                baru += 1

            if baru == 0:
                console.print("[dim]Tidak ada lowongan baru di kombinasi ini.[/]")

            selesai += 1
            lama = time.monotonic() - mulai
            sisa = (lama / max(1, selesai)) * (total - selesai)
            console.print(
                f"[dim]Kemajuan riset Indeed: {selesai}/{total} kombinasi, "
                f"{len(lowongan)} lowongan, {lama:.0f} detik berlalu — "
                f"perkiraan sisa {sisa:.0f} detik.[/]"
            )

    sebelum = len(lowongan)
    lowongan = dedupe_jobs(lowongan)
    console.print(
        f"[bold green]Riset Indeed selesai:[/] {sebelum + duplikat} terbaca → "
        f"{len(lowongan)} unik ({sebelum - len(lowongan) + duplikat} duplikat "
        f"dibuang)."
    )
    return lowongan


def tampilkan_konfigurasi() -> None:
    """Ringkasan pengaturan sesi, isinya sama dengan JobStreet/Glints."""
    mode = "otomatis" if config.auto_apply else "manual (tinjau sendiri)"
    batas_harian = kuota.batas()
    batas_sesi = int(getattr(config, "auto_apply_max_per_session", 0) or 0)
    port = int(getattr(config, "chrome_debug_port", 0) or 0)

    tabel = Table(title="Pengaturan sesi Indeed", show_header=False)
    tabel.add_column("Pengaturan", style="cyan")
    tabel.add_column("Nilai")
    tabel.add_row("Mode lamar", mode)
    tabel.add_row(
        "Kuota lamaran",
        f"{batas_harian} per hari" if batas_harian else "tanpa batas",
    )
    tabel.add_row(
        "Batas per sesi", f"{batas_sesi} lamaran" if batas_sesi else "tanpa batas"
    )
    tabel.add_row(
        "Lokasi disaring",
        f"{len(config.locations)} — {', '.join(config.locations[:3])}"
        if config.locations
        else "semua lokasi",
    )
    tabel.add_row(
        "Wajib logo perusahaan", "tidak (kartu Indeed tanpa logo)"
    )
    tabel.add_row("Urutan kandidat", getattr(config, "rank_by", "relevance"))
    tabel.add_row("Jeda antar lamaran", f"{config.delay_between_apply} detik")
    tabel.add_row(
        "Chrome",
        f"menempel ke port {port}" if port else "dibuka oleh bot",
    )
    console.print(tabel)


def jalankan_indeed(max_pages: int = 0, keywords: Optional[List[str]] = None,
                    batas: int = 0, laporan_harian: bool = True) -> dict:
    """Riset → saring → peringkat → lamar di Indeed, aturan sama JobStreet."""
    kata_kunci = list(keywords) if keywords else config.keywords_riset
    halaman = batas_halaman_riset(max_pages)
    batas_riset = int(getattr(config, "research_max_jobs", 0) or 0)

    bot = IndeedBot()
    laporan = {
        "dibaca": 0, "baru": 0, "dilamar": 0, "sudah": 0,
        "dilewati": 0, "gagal": 0, "perlu_manual": 0,
        "khusus_aplikasi": 0,
    }

    tampilkan_konfigurasi()

    if not config.auto_apply:
        console.print(
            "[bold yellow]Mode manual aktif: setiap lowongan dibuka untuk Anda "
            "tinjau dan kirim sendiri. Pakai AUTO_APPLY=true untuk mengirim "
            "otomatis.[/]\n"
        )

    try:
        bot.init_browser()

        if not bot.login():
            console.print("[red]Login Indeed belum selesai — dihentikan.[/]")
            return laporan

        lowongan = kumpulkan_lowongan(bot, kata_kunci, halaman)
        laporan["dibaca"] = len(lowongan)

        if batas_riset and len(lowongan) > batas_riset:
            lowongan = lowongan[:batas_riset]

        layak: List[Dict] = []
        sudah = JobFilter()

        for job in lowongan:
            if job.get("sudah_dilamar"):
                laporan["sudah"] += 1
                db.add_job(job)
                db.record_application(
                    job["job_id"], "already_applied",
                    "Ditandai sudah dilamar di Indeed",
                )
                console.print(f"[dim]Lewati: {job['title']} — sudah dilamar[/]")
                continue

            if db.is_already_applied(job["job_id"]):
                laporan["sudah"] += 1
                continue

            if db.add_job(job):
                laporan["baru"] += 1

            alasan = alasan_tidak_layak(job, sudah)
            if alasan:
                laporan["dilewati"] += 1
                antrean.tandai_hasil(job["job_id"], alasan)
                log_aktivitas.catat(f"Ditolak: {job['title']} — {alasan}")
                console.print(f"[dim]Lewati: {job['title']} — {alasan}[/]")
                continue

            antrean.tandai_hasil(job["job_id"])
            layak.append(job)

        if not layak:
            console.print("[yellow]Tidak ada lowongan Indeed yang lolos filter.[/]")
            return laporan

        console.print(f"[cyan]{kuota.ringkasan(db)}[/]")

        if kuota.habis(db):
            console.print(f"[bold yellow]{kuota.pesan_habis()}[/]")
            return laporan

        sisa = kuota.sisa(db)
        dipilih = pilih_teratas(layak, sisa or 0)

        if sisa is not None and len(layak) > sisa:
            console.print(
                f"[bold]{len(layak)} kandidat[/] bersaing untuk "
                f"[bold]{sisa} slot[/] — diambil {sisa} yang paling cocok."
            )

        tampilkan_perbandingan(dipilih, situs="Indeed")
        tampilkan_rincian_skor(dipilih, situs="Indeed")

        batas_sesi = int(getattr(config, "auto_apply_max_per_session", 0) or 0)

        for job in dipilih:
            kendali.periksa()

            if batas and laporan["dilamar"] >= batas:
                console.print("[yellow]Batas lamaran sesi ini tercapai.[/]")
                break
            if kuota.habis(db):
                console.print("[yellow]Batas lamaran harian tercapai.[/]")
                break
            if batas_sesi and laporan["dilamar"] >= batas_sesi:
                console.print(
                    "[bold yellow]Batas lamaran otomatis per sesi "
                    f"({batas_sesi}) tercapai. Sisa lowongan dilewati.[/]"
                )
                break

            if not antrean.klaim(job["job_id"]):
                laporan["sudah"] += 1
                continue

            try:
                hasil = bot.lamar(job)
            except Exception as exc:
                console.print(f"[bold red]Sesi Indeed dihentikan: {exc}[/]")
                laporan["gagal"] += 1
                antrean.selesai(job["job_id"], "failed", str(exc)[:200])
                break

            if hasil.status == "login_required":
                laporan["gagal"] += 1
                console.print(
                    "[bold red]Sesi login Indeed sudah habis. Sesi dihentikan "
                    "agar tidak menumpuk galat.[/]"
                )
                notifier.send_error("Sesi login Indeed habis")
                break

            if hasil.applied:
                laporan["dilamar"] += 1
                antrean.selesai(job["job_id"], "applied", hasil.reason or "")
                log_aktivitas.catat(f"Terkirim: {job['title']} ({job['company']})")
                notifier.send_apply_success(job)
                console.print(f"[green]Terkirim: {job['title']}[/]")
            elif hasil.status == "already_applied":
                laporan["sudah"] += 1
                antrean.selesai(job["job_id"], "applied", hasil.reason or "")
            elif hasil.status == "manual_required":
                laporan["perlu_manual"] += 1
                antrean.selesai(job["job_id"], "review_required", hasil.reason or "")
                console.print(
                    f"[yellow]Perlu manual: {job['title']} — {hasil.reason}[/]"
                )
            elif hasil.status == "skipped":
                laporan["dilewati"] += 1
                antrean.selesai(job["job_id"], "filtered", hasil.reason or "")
            else:
                laporan["gagal"] += 1
                antrean.selesai(
                    job["job_id"],
                    antrean.status_gagal(hasil.reason or ""),
                    hasil.reason or "",
                )
                log_aktivitas.catat(
                    f"Gagal: {job['title']} — {hasil.reason}", "error"
                )
                console.print(f"[red]Gagal: {job['title']} — {hasil.reason}[/]")

            if hasil.applied or hasil.status == "error":
                jeda = max(0.0, float(config.delay_between_apply or 0))
                if jeda:
                    console.print(
                        f"[dim]Jeda {jeda:.0f} detik sebelum lowongan "
                        "berikutnya...[/]"
                    )
                    time.sleep(jeda)

    except Exception as exc:
        notifier.send_error(str(exc))
        raise

    finally:
        bot.tutup()

        if laporan_harian:
            try:
                notifier.send_daily_report(db.get_stats())
            except Exception as exc:
                console.print(f"[yellow]Laporan harian gagal dikirim: {exc}[/]")

    return laporan


def daftar_kandidat(keywords: Optional[List[str]] = None,
                    max_pages: int = 1, batas: int = 10,
                    semuanya: bool = False) -> List[Dict]:
    """Lowongan Indeed yang layak dilamar (tanpa melamar)."""
    kata_kunci = list(keywords or config.keywords)
    bot = IndeedBot()

    try:
        bot.init_browser()
        lowongan = kumpulkan_lowongan(bot, kata_kunci, max_pages)
    finally:
        bot.tutup()

    console.print(f"[bold]Terbaca {len(lowongan)} lowongan Indeed.[/]")

    saringan = JobFilter()
    hasil = []

    for job in lowongan:
        alasan = alasan_tidak_layak(job, saringan) if not semuanya else ""
        if alasan:
            continue
        hasil.append(job)

    hasil = pilih_teratas(hasil, 0)
    return hasil[:batas] if batas and batas > 0 else hasil


def diagnosa_indeed(keyword: str = "", location: str = "") -> Dict:
    """Periksa mengapa kartu Indeed tidak terbaca (HTML + PNG disimpan)."""
    kata = (keyword or "").strip()
    if not kata:
        kata = (config.keywords or ["inventory"])[0]

    # Tanpa lokasi, Indeed menampilkan lowongan dari seluruh Indonesia dan
    # hasilnya sering tidak nyambung dengan kata kunci. Pakai lokasi pertama
    # di .env sebagai contoh yang wajar.
    lokasi = (location or "").strip()
    if not lokasi and config.locations:
        lokasi = config.locations[0]

    bot = IndeedBot()
    info: Dict = {}

    try:
        bot.init_browser()
        console.print(
            f"[cyan]Diagnosa Indeed — kata kunci: '{kata}'"
            + (f" · lokasi: {lokasi}[/]" if lokasi else "[/]")
        )
        berhasil = bot.buka_pencarian(kata, lokasi)
        info = bot.diagnosa_terakhir or bot.simpan_diagnosa("diagnosa", kata)

        console.print(
            f"[cyan]Login Indeed terdeteksi:[/] "
            f"{'ya' if bot.sudah_login() else 'belum'}"
        )

        if berhasil:
            kartu = [
                job for job in (
                    rapikan_kartu(mentah) for mentah in bot._kartu_mentah()
                ) if job
            ]
            console.print(
                f"[green]Pembaca kartu utama: {len(kartu)} lowongan "
                "terbaca.[/]"
            )
            for job in kartu[:5]:
                console.print(
                    f"  - {job['title'][:45]} | {job['company'] or '-'} | "
                    f"{job['location'] or '-'} | {job['salary'] or '-'} | "
                    f"logo: {'ada' if job.get('has_logo') else 'tidak'}"
                )

            saringan = JobFilter()
            cocok = sum(
                1 for job in kartu if saringan.should_apply(job)[0]
            )
            berlogo = sum(1 for job in kartu if job.get("has_logo"))
            console.print(
                f"[dim]{cocok} dari {len(kartu)} kartu cocok dengan filter "
                f"judul/gaji · {berlogo} kartu berlogo perusahaan.[/]"
            )
            if not kartu:
                console.print(
                    f"[yellow]Cara cadangan menemukan "
                    f"{len(bot._kartu_fallback())} tautan lowongan.[/]"
                )
        else:
            console.print(
                "[bold yellow]Tidak ada kartu yang bisa dibaca. Kirimkan "
                "berkas HTML + screenshot di atas untuk penyesuaian.[/]"
            )

    except Exception as exc:
        console.print(f"[bold red]Diagnosa gagal:[/] {exc}")
    finally:
        bot.tutup()

    return info


__all__ = [
    "IndeedApplier",
    "IndeedBot",
    "alasan_tidak_layak",
    "daftar_kandidat",
    "diagnosa_indeed",
    "jalankan_indeed",
    "rapikan_kartu",
    "url_pencarian",
]
