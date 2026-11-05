"""Pencarian dan pelamaran otomatis di Glints (glints.com).

Modul ini memakai mesin yang sama dengan versi JobStreet (``auto_apply``),
tetapi dengan peta situs Glints sendiri:

* pencarian  : ``/id/opportunities/jobs/explore?keyword=...&countryCode=ID``
* lowongan   : ``/id/opportunities/jobs/<slug>/<uuid>``
* tombol     : "Lamar" lalu "Lamar Sekarang" di formulir lamaran
* tombol urut: "Baru Ditambahkan" (setara *newest first*)

Pengambilan kartu lowongan memakai satu skrip JavaScript yang membaca tautan
lowongan, bukan nama kelas CSS (kelas Glints berubah-ubah). Dengan begitu
perubahan tampilan tidak langsung mematahkan pembacaan.
"""

import contextlib
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from rich.console import Console
from rich.table import Table
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from auto_apply import ApplyResult, AutoApplier
from config import config
from database import db
from job_filter import JobFilter, rentang_gaji
from job_filter import job_filter as penyaring
from notifier import notifier

console = Console()


class ChromeTertutup(RuntimeError):
    """Chrome/jendela ditutup saat program berjalan."""


TANDA_CHROME_MATI = (
    "invalid session",
    "not connected to devtools",
    "browser has closed",
    "chrome not reachable",
    "disconnected",
)


def chrome_mati(pesan: str) -> bool:
    """True bila pesan galat berarti jendela Chrome sudah tidak ada."""
    teks = str(pesan or "").lower()
    return any(tanda in teks for tanda in TANDA_CHROME_MATI)

DOMAIN = "glints.com"
BASE = "https://glints.com"
SEARCH_URL = BASE + "/id/opportunities/jobs/explore?keyword={keyword}&countryCode=ID"
LOGIN_URL = BASE + "/id/login"

# Pola tautan lowongan Glints: /id/opportunities/jobs/<slug>/<uuid>
TAUTAN_LOWONGAN = re.compile(
    r"/opportunities/jobs/[^/?#]+/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)

# Teks tombol yang berarti "sudah pernah dilamar" pada kartu Glints.
SUDAH_DILAMAR_TEXTS = (
    "sudah dilamar",
    "sudah melamar",
    "lamaran terkirim",
    "you applied",
)

# Glints punya lowongan yang hanya bisa dilamar lewat aplikasi mobile.
KHUSUS_APLIKASI_TEXTS = (
    "lamar 1x tap di aplikasi",
    "1x tap di aplikasi",
    "tap di aplikasi",
    "lamar di aplikasi",
    "hanya bisa dilamar di aplikasi",
)

# Badge ini juga muncul pada lowongan yang tetap bisa dilamar di web, jadi
# TIDAK dipakai untuk melewati lowongan.
BADGE_APLIKASI = (
    "lamar & chat di aplikasi",
    "lamar dan chat di aplikasi",
    "chat di aplikasi",
)

# Teks yang menandakan lamaran benar-benar terkirim di Glints.
SUKSES_GLINTS = (
    "lamaran berhasil dikirim",
    "lamaran kamu berhasil dikirim",
    "lamaran anda berhasil dikirim",
    "lamaran berhasil",
    "berhasil melamar",
    "lamaran terkirim",
    "lamaran kamu sudah terkirim",
    "lamaran anda sudah terkirim",
    "application submitted",
    "application sent",
    "you have successfully applied",
)

# Penghalang khas Glints: profil belum lengkap, CV belum dipilih, dsb.
PENGHALANG_GLINTS = (
    (
        "lengkapi profil",
        "Profil Glints belum lengkap — lengkapi di glints.com lalu jalankan lagi",
    ),
    ("profilmu belum lengkap", "Profil Glints belum lengkap — lengkapi dulu"),
    ("unggah cv", "Glints meminta unggah CV — isi RESUME_PATH di .env"),
    ("unggah resume", "Glints meminta unggah CV — isi RESUME_PATH di .env"),
    ("upload cv", "Glints meminta unggah CV — isi RESUME_PATH di .env"),
    ("pilih cv", "Glints meminta memilih CV — unggah CV di profil Glints"),
    ("masuk untuk melanjutkan", "Sesi Glints berakhir — login ulang"),
    ("login untuk melanjutkan", "Sesi Glints berakhir — login ulang"),
)

SIBUK_TEXTS = (
    "sudah pernah melamar",
    "kamu sudah melamar",
    "anda sudah melamar",
    "you have already applied",
)

# Skrip pembaca kartu. Dijalankan di halaman hasil pencarian Glints.
SKRIP_KARTU = r"""
const hasil = [];
const terlihat = new Set();
const tautan = document.querySelectorAll("a[href*='/opportunities/jobs/']");
tautan.forEach(function (a) {
    const cocok = (a.href || "").match(
        /\/opportunities\/jobs\/[^\/?#]+\/[0-9a-fA-F-]{36}/
    );
    if (!cocok) { return; }
    const url = (a.href || "").split("?")[0];
    const id = cocok[0].split("/").pop();
    if (terlihat.has(id)) { return; }
    const judul = (a.textContent || "").replace(/\s+/g, " ").trim();
    if (judul.length < 3) { return; }

    // Naik ke wadah yang memuat tautan perusahaan: struktur kartu Glints.
    let wadah = a;
    for (let i = 0; i < 8 && wadah; i += 1) {
        wadah = wadah.parentElement;
        if (!wadah) { break; }
        if (wadah.querySelector("a[href*='/companies/']")) { break; }
    }

    const teks = wadah
        ? (wadah.innerText || wadah.textContent || "")
        : "";
    const perusahaan = wadah
        ? wadah.querySelector("a[href*='/companies/']")
        : null;
    const lokasi = wadah
        ? Array.from(wadah.querySelectorAll("a[href*='/job-location/']"))
        : [];
    const gambar = wadah
        ? Array.from(wadah.querySelectorAll("img")).slice(0, 4)
        : [];
    const polaGaji =
        /Rp\s?[\d.,]+(?:\s?(-|–)\s?[\d.,]+)?\s?(jt|juta|rb|ribu)?/i;
    const gaji = (teks.match(polaGaji) || [""])[0];

    terlihat.add(id);
    hasil.push({
        url: url,
        title: judul,
        company: perusahaan
            ? (perusahaan.textContent || "").replace(/\s+/g, " ").trim()
            : "",
        location: lokasi
            .map(function (x) { return (x.textContent || "").trim(); })
            .join(", "),
        salary: gaji,
        text: teks.slice(0, 600),
        logo: gambar.map(function (img) {
            return {
                alt: (img.getAttribute("alt") || "").trim(),
                src: (img.getAttribute("src") || "").trim(),
                penanda: [
                    img.getAttribute("data-testid") || "",
                    img.getAttribute("class") || ""
                ].join(" ").trim()
            };
        })
    });
});
return hasil;
"""


# ----------------------------------------------------------------------
# Fungsi bantu (murni, mudah diuji)
# ----------------------------------------------------------------------
def id_dari_url(url: str) -> str:
    """UUID lowongan Glints dari URL; "" bila bukan URL lowongan."""
    cocok = TAUTAN_LOWONGAN.search(url or "")
    return cocok.group(1) if cocok else ""


def logo_kartu(kandidat, perusahaan: str = "") -> tuple:
    """Apakah kartu Glints menampilkan logo perusahaan.

    Memakai aturan yang sama dengan kartu JobStreet (`logo_perusahaan`),
    supaya `REQUIRE_COMPANY_LOGO` berlaku di kedua situs.
    """
    from scraper import logo_perusahaan

    if not isinstance(kandidat, (list, tuple)):
        return False, "tidak ada gambar"

    for item in kandidat:
        if not isinstance(item, dict):
            continue

        alt = str(item.get("alt") or "")
        src = str(item.get("src") or "")
        penanda = str(item.get("penanda") or "")

        if logo_perusahaan(alt, src, penanda, perusahaan):
            return True, f"<img alt='{alt[:30]}'>"

    return False, f"{len(kandidat)} gambar tanpa logo"


def pilih_teratas(lowongan: List[Dict], batas: int = 0) -> List[Dict]:
    """Urutkan kandidat seperti di JobStreet, lalu batasi sesuai sisa kuota.

    `RANK_BY=relevance` (bawaan) = kecocokan tertinggi dulu, `newest` =
    posting terbaru dulu. `batas` 0 berarti tanpa pemotongan.
    """
    if not lowongan:
        return []

    urut_terbaru = getattr(config, "rank_by", "relevance") == "newest"
    terurut = penyaring.rank_jobs(lowongan, prefer_newest=urut_terbaru)

    if batas and batas > 0:
        return terurut[:batas]

    return terurut


def tampilkan_perbandingan(kandidat: List[Dict], maksimal: int = 10):
    """Tabel kandidat teratas beserta skor kecocokannya (Glints)."""
    if not kandidat:
        return

    table = Table(
        title=f"Kandidat Glints yang akan dilamar (dibandingkan dari "
        f"{len(kandidat)})",
        show_lines=False,
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Skor", justify="right", style="green")
    table.add_column("Judul", style="cyan", max_width=44)
    table.add_column("Perusahaan", max_width=26)
    table.add_column("Lokasi", style="dim", max_width=20)

    for nomor, job in enumerate(kandidat[:maksimal], start=1):
        table.add_row(
            str(nomor),
            str(job.get("_score", 0)),
            (job.get("title") or "-")[:44],
            (job.get("company") or "-")[:26],
            (job.get("location") or "-")[:20],
        )

    console.print(table)

    if len(kandidat) > maksimal:
        console.print(
            f"[dim]… dan {len(kandidat) - maksimal} lowongan lain di bawahnya "
            "(tidak dilamar pada sesi ini).[/]"
        )


def rapikan_kartu(data: dict) -> Optional[Dict]:
    """Ubah hasil skrip kartu menjadi dict lowongan; None bila tidak layak."""
    if not isinstance(data, dict):
        return None

    url = str(data.get("url") or "").strip()
    job_id = id_dari_url(url)
    judul = " ".join(str(data.get("title") or "").split())

    if not job_id or not judul:
        return None

    teks = " ".join(str(data.get("text") or "").split()).lower()
    perusahaan = " ".join(str(data.get("company") or "").split())
    punya_logo, info_logo = logo_kartu(data.get("logo"), perusahaan)

    return {
        "has_logo": punya_logo,
        "logo_src": info_logo,
        "job_id": f"glints:{job_id}",
        "title": judul,
        "company": perusahaan,
        "location": " ".join(str(data.get("location") or "").split()),
        "salary": " ".join(str(data.get("salary") or "").split()),
        "description": " ".join(str(data.get("text") or "").split())[:800],
        "url": url,
        "date_posted": "",
        "age_days": None,
        "source": "glints",
        "sudah_dilamar": any(tanda in teks for tanda in SUDAH_DILAMAR_TEXTS),
        "khusus_aplikasi": bool(khusus_aplikasi(teks)),
    }


def khusus_aplikasi(teks: str) -> str:
    """Penanda Glints yang ditemukan ('' bila lowongan bisa dilamar di web)."""
    isi = " ".join(str(teks or "").lower().split())

    for tanda in KHUSUS_APLIKASI_TEXTS:
        if tanda in isi:
            return tanda

    return ""

def lokasi_cocok(lokasi: str, daftar: List[str]) -> bool:
    """True bila teks lokasi kartu cocok dengan salah satu lokasi dicari."""
    if not daftar:
        return True

    teks = " ".join((lokasi or "").lower().split())
    if not teks:
        # Tanpa info lokasi, jangan langsung dibuang: biarkan filter lain.
        return True

    return any(item.lower().strip() in teks for item in daftar if item.strip())


def lolos_gaji(job: Dict, minimal: Optional[int] = None) -> bool:
    """True bila gaji lowongan memenuhi batas minimal Glints.

    Aturan pemakai: gaji di bawah batas tidak dilamar, tetapi lowongan yang
    tidak mencantumkan gaji tetap dilamar. Untuk rentang (mis. "Rp 4-4,5jt")
    dipakai angka tertinggi, karena gaji yang ditawarkan bisa mencapai itu.
    """
    batas = config.glints_min_salary if minimal is None else minimal
    if not batas or batas <= 0:
        return True

    _, tertinggi = rentang_gaji(str(job.get("salary") or ""))
    if tertinggi <= 0:
        # Tidak ada angka gaji: tetap dilamar sesuai permintaan.
        return True

    return tertinggi >= batas


def alasan_gaji(job: Dict, minimal: Optional[int] = None) -> str:
    """Alasan penolakan karena gaji ('' bila lolos)."""
    if lolos_gaji(job, minimal):
        return ""

    batas = config.glints_min_salary if minimal is None else minimal
    gaji = " ".join(str(job.get("salary") or "").split())
    return (
        f"Gaji di bawah Rp{batas:,}".replace(",", ".")
        + f" ({gaji})"
    )


def alasan_tidak_layak(job: Dict, saringan: Optional[JobFilter] = None) -> str:
    """Alasan lowongan tidak dicoba dilamar ('' bila layak).

    Dipakai `glints cari` dan `glints uji` otomatis, supaya keduanya memilih
    lowongan dengan aturan yang sama seperti sesi penuh.
    """
    if job.get("khusus_aplikasi"):
        return "hanya bisa dilamar lewat aplikasi Glints"

    if job.get("sudah_dilamar"):
        return "sudah pernah dilamar"

    alasan = alasan_gaji(job)
    if alasan:
        return alasan

    if not lokasi_cocok(str(job.get("location") or ""), config.locations):
        return f"lokasi di luar daftar ({job.get('location') or '-'})"

    saringan = saringan or JobFilter()
    lolos, kenapa = saringan.should_apply(job)
    if not lolos:
        return kenapa

    return ""


# ----------------------------------------------------------------------
# Pelamar: mesin auto_apply dengan peta Glints
# ----------------------------------------------------------------------
class GlintsApplier(AutoApplier):
    """AutoApplier yang mengenali tombol serta teks khas Glints."""

    situs_host = DOMAIN
    nama_situs = "Glints"

    apply_selectors = (
        "button[data-testid='apply-button']",
        "a[data-testid='apply-button']",
        "button[aria-label*='Lamar']",
    )
    apply_texts = ("lamar", "apply now", "apply")

    submit_selectors = (
        "button[data-testid='submit-application']",
        "button[type='submit']",
    )
    submit_texts = (
        "lamar sekarang",
        "kirim lamaran",
        "kirim aplikasi",
        "submit application",
        "apply now",
    )

    continue_selectors = ("button[data-testid='continue-application']",)
    continue_texts = (
        "lanjutkan",
        "lanjut",
        "continue",
        "berikutnya",
        "selanjutnya",
        "next",
    )

    submit_texts = (
        "lamar sekarang",
        "kirim lamaran",
        "kirim aplikasi",
        "submit application",
        "kirim",
        "apply now",
        "selanjutnya",
        "lanjutkan",
    )

    success_texts = SUKSES_GLINTS
    already_texts = SIBUK_TEXTS

    def __init__(self, driver, wait=None):
        super().__init__(driver, wait)

        # Formulir Glints berupa modal yang butuh waktu memuat; 3 detik
        # terlalu singkat sehingga alur sehat pun dianggap tidak dikenali.
        self.step_timeout = max(self.step_timeout, 12)
        self.submit_timeout = max(self.submit_timeout, 30)

    # Label yang berarti CTA "buka aplikasi", bukan lamar di web.
    _label_aplikasi = ("aplikasi", "app", "unduh", "download")

    def _cari_tombol_lamar(self):
        """Utamakan tombol berlabel tepat "Lamar", bukan "Lamar di aplikasi"."""
        for selector in self.apply_selectors:
            for element in self._find_all(selector):
                if self._visible(element) and self._enabled(element):
                    return element

        for selector in ("button", "a", "[role='button']"):
            for element in self._find_all(selector):
                if not self._visible(element) or not self._enabled(element):
                    continue

                label = self._text(element)
                if label not in ("lamar", "apply", "apply now", "lamar sekarang"):
                    continue

                if any(kata in label for kata in self._label_aplikasi):
                    continue

                return element

        return None

    # Label tombol yang bukan pengiriman lamaran (mis. kirim pesan/chat).
    _label_bukan_kirim = ("pesan", "chat", "obrolan", "tanya", "follow")

    def _find_submit_button(self, review_page: bool = False):
        """Jangan pernah menganggap "Kirim pesan" sebagai kirim lamaran."""
        tombol = super()._find_submit_button(review_page)
        if tombol is None:
            return None

        label = self._text(tombol)
        if any(kata in label for kata in self._label_bukan_kirim):
            # Cari kandidat lain yang bukan tombol chat.
            kandidat = self._find_clickable(self.submit_selectors, ())

            if kandidat is not None:
                label_kandidat = self._text(kandidat)
                if not any(
                    kata in label_kandidat for kata in self._label_bukan_kirim
                ):
                    return kandidat

            return None

        return tombol

    def _blocker(self) -> str:
        """Penghalang khas Glints (profil/CV/login) sebelum menyerah."""
        alasan = super()._blocker()
        if alasan:
            return alasan

        body = self._body_text()
        for tanda, pesan in PENGHALANG_GLINTS:
            if tanda in body:
                return pesan

        # Tombol Lamar di Glints kadang hanya mengarahkan ke aplikasi mobile.
        tanda = khusus_aplikasi(f"{body} {self._teks_modal()}")
        if tanda:
            return (
                "Lowongan Glints hanya bisa dilamar lewat aplikasi mobile "
                f'(tertulis "{tanda}") — dilewati'
            )

        return ""

    def _pesan_alur_tidak_dikenali(self) -> str:
        """Sertakan tombol yang terlihat supaya mudah dilaporkan."""
        label = []
        for selector in ("button", "a[role='button']", "[role='dialog']"):
            for element in self._find_all(selector):
                if not self._visible(element):
                    continue
                teks = self._text(element)
                if teks and teks not in label:
                    label.append(teks[:30])

        dasar = super()._pesan_alur_tidak_dikenali()
        if not label:
            return dasar

        return f"{dasar}. Tombol terlihat: {', '.join(label[:10])}"

    def _alasan_lewati(self) -> str:
        """Lowongan Glints yang hanya bisa dilamar dari aplikasi mobile."""
        body = self._body_text()

        if "halaman ini tidak tersedia" in body or "job not found" in body:
            return "Lowongan Glints tidak lagi tersedia — dilewati"

        return ""


# ----------------------------------------------------------------------
# Peramban Glints
# ----------------------------------------------------------------------
class GlintsBot:
    def __init__(self):
        self.driver = None
        self.filters = JobFilter()

    # ------------------------------ browser ---------------------------
    def init_browser(self):
        console.print("[bold blue]Membuka Chrome untuk Glints...[/]")

        options = Options()
        options.add_argument("--window-size=1400,900")
        options.add_argument("--disable-blink-features=AutomationControlled")

        if config.use_profile:
            profile_path = Path(config.profile_dir).expanduser()
            with contextlib.suppress(Exception):
                profile_path.mkdir(parents=True, exist_ok=True)
                options.add_argument(f"--user-data-dir={profile_path}")
                options.add_argument("--profile-directory=Default")

        if config.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
        else:
            options.add_argument("--start-maximized")

        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception as pertama:
            console.print(
                f"[yellow]ChromeDriver otomatis gagal ({pertama}). "
                "Mencoba webdriver-manager...[/]"
            )
            try:
                from webdriver_manager.chrome import ChromeDriverManager

                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            except Exception as kedua:
                raise RuntimeError(
                    "Chrome tidak bisa dibuka. Pastikan Google Chrome "
                    "terpasang dan komputer tersambung internet, lalu jalankan "
                    f"ulang. Detail: {kedua}"
                ) from pertama

    def _teks_halaman(self) -> str:
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            return " ".join((body.text or "").split()).lower()
        except Exception:
            return ""

    def _url(self) -> str:
        try:
            return str(self.driver.current_url or "")
        except Exception:
            return ""

    # ------------------------------- login ----------------------------
    def sudah_login(self) -> bool:
        """Tebakan login: halaman bukan /login dan tidak ada tombol Masuk."""
        url = self._url().lower()
        if "/login" in url or "/signup" in url:
            return False

        teks = self._teks_halaman()
        if not teks:
            return False

        # Tombol "Masuk" di header hanya ada saat belum login.
        return not (
            "masuk untuk" in teks
            or "login untuk" in teks
            or "masuk ke glints" in teks
        )

    def login(self) -> bool:
        """Buka halaman login dan tunggu pengguna menyelesaikannya sendiri."""
        self.driver.get(LOGIN_URL)
        time.sleep(2)

        if self.sudah_login():
            console.print("[green]Sesi Glints sudah aktif.[/]")
            return True

        console.print(
            "[yellow]Silakan login di Chrome (jendela yang terbuka). "
            "Program menunggu otomatis — tidak perlu menekan apa pun.[/]"
        )

        batas = time.time() + (600 if config.login_wait else 30)
        while time.time() < batas:
            time.sleep(2)
            if "/login" not in self._url().lower() and self.sudah_login():
                console.print("[green]Login Glints terdeteksi.[/]")
                return True

        return False

    # ----------------------------- pencarian --------------------------
    def buka_pencarian(self, keyword: str) -> bool:
        url = SEARCH_URL.format(keyword=quote_plus(keyword))
        self.driver.get(url)
        time.sleep(2.5)

        teks = self._teks_halaman()
        if "masuk" in teks and "lowongan" not in teks:
            console.print("[yellow]Halaman Glints meminta login.[/]")
            return False

        return True

    def urutkan_terbaru(self) -> bool:
        """Klik tombol urut "Baru Ditambahkan" bila ada."""
        kandidat = "button, a, div[role='button']"
        for element in self.driver.find_elements(By.CSS_SELECTOR, kandidat):
            with contextlib.suppress(Exception):
                label = " ".join((element.text or "").split()).lower()
                if label in ("baru ditambahkan", "terbaru", "newest"):
                    element.click()
                    time.sleep(2)
                    return True
        return False

    def muat_lebih(self) -> bool:
        """Klik "Muat lebih banyak" / "Lihat lebih banyak" bila tersedia."""
        for element in self.driver.find_elements(By.CSS_SELECTOR, "button, a"):
            with contextlib.suppress(Exception):
                label = " ".join((element.text or "").split()).lower()
                if label in (
                    "muat lebih banyak",
                    "lihat lebih banyak",
                    "tampilkan lebih banyak",
                    "load more",
                    "show more",
                ):
                    element.click()
                    time.sleep(2)
                    return True
        return False

    def _kartu_mentah(self) -> list:
        try:
            hasil = self.driver.execute_script(SKRIP_KARTU)
        except Exception:
            return []

        return hasil if isinstance(hasil, list) else []

    def cari(self, keyword: str, halaman: int = 0) -> List[Dict]:
        """Kembalikan daftar lowongan Glints untuk satu kata kunci."""
        if not self.buka_pencarian(keyword):
            return []

        if halaman == 0 and config.prefer_newest:
            self.urutkan_terbaru()

        for _ in range(halaman):
            if not self.muat_lebih():
                # Tidak ada tombol: gulir untuk memicu pemuatan malas.
                with contextlib.suppress(Exception):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(2)
                break

        lowongan = []
        sudah_ada = set()

        for mentah in self._kartu_mentah():
            job = rapikan_kartu(mentah)
            if not job or job["job_id"] in sudah_ada:
                continue
            sudah_ada.add(job["job_id"])
            lowongan.append(job)

        return lowongan

    # ------------------------------ lamar -----------------------------
    def lamar(self, job: dict) -> ApplyResult:
        try:
            hasil = GlintsApplier(self.driver).apply(job)
        except WebDriverException as exc:
            if chrome_mati(str(exc)):
                raise ChromeTertutup(
                    "Jendela Chrome tertutup saat program berjalan"
                ) from exc
            return ApplyResult(False, "error", f"Galat browser: {exc}")
        except Exception as exc:  # jaring pengaman: jangan hentikan sesi
            return ApplyResult(
                False, "error", f"Galat tak terduga: {exc}"
            )

        # apply() menelan galat browser menjadi ApplyResult; ubah lagi menjadi
        # ChromeTertutup supaya sesi berhenti rapi, bukan mencetak traceback.
        if hasil.status == "error" and chrome_mati(hasil.reason):
            raise ChromeTertutup(
                "Jendela Chrome tertutup saat program berjalan"
            )

        return hasil

    def tutup(self):
        with contextlib.suppress(Exception):
            self.driver.quit()


# ----------------------------------------------------------------------
# Alur utama
# ----------------------------------------------------------------------
def _batas_harian_tercapai() -> bool:
    batas = int(getattr(config, "max_apply_per_day", 0) or 0)
    if batas <= 0:
        return False
    return db.get_today_apply_count() >= batas


def jalankan_glints(max_pages: int = 0, keywords: Optional[List[str]] = None,
                    batas: int = 0) -> dict:
    """Cari, saring, lalu lamar lowongan Glints secara otomatis."""
    kata_kunci = list(keywords or config.keywords)
    halaman = max_pages or config.max_pages

    bot = GlintsBot()
    laporan = {
        "dibaca": 0, "baru": 0, "dilamar": 0, "sudah": 0,
        "dilewati": 0, "gagal": 0, "perlu_manual": 0,
        "khusus_aplikasi": 0,
    }

    try:
        bot.init_browser()

        if not bot.login():
            console.print("[red]Login Glints belum selesai — dihentikan.[/]")
            return laporan

        lowongan: List[Dict] = []
        terlihat = set()

        for keyword in kata_kunci:
            for nomor in range(halaman):
                console.print(
                    f"[cyan]Glints: '{keyword}' halaman {nomor + 1}[/]"
                )
                for job in bot.cari(keyword, nomor):
                    if job["job_id"] in terlihat:
                        continue
                    terlihat.add(job["job_id"])
                    lowongan.append(job)

        # Mulai dari lowongan yang tampil paling atas (urut "Baru Ditambahkan").
        laporan["dibaca"] = len(lowongan)
        console.print(f"[bold]Terbaca {len(lowongan)} lowongan Glints.[/]")

        # --- Saring dulu semuanya, baru bandingkan dan pilih yang terbaik ---
        layak: List[Dict] = []

        for job in lowongan:
            if job.get("khusus_aplikasi"):
                # Glints menandai lowongan "Lamar 1x tap di aplikasi"; tidak
                # ada formulir web, jadi jangan buka halamannya sama sekali.
                laporan["khusus_aplikasi"] += 1
                laporan["dilewati"] += 1
                console.print(
                    f"[dim]Lewati: {job['title']} — hanya bisa dilamar lewat "
                    "aplikasi Glints[/]"
                )
                continue

            if job.get("sudah_dilamar"):
                laporan["sudah"] += 1
                console.print(f"[dim]Lewati: {job['title']} — sudah dilamar[/]")
                continue

            alasan = alasan_gaji(job)
            if alasan:
                laporan["dilewati"] += 1
                console.print(f"[dim]Lewati: {job['title']} — {alasan}[/]")
                continue

            if not lokasi_cocok(job.get("location", ""), config.locations):
                laporan["dilewati"] += 1
                console.print(
                    f"[dim]Lewati: {job['title']} — lokasi {job['location']}[/]"
                )
                continue

            lolos, alasan = bot.filters.should_apply(job)
            if not lolos:
                laporan["dilewati"] += 1
                console.print(f"[dim]Lewati: {job['title']} — {alasan}[/]")
                continue

            layak.append(job)

        if not layak:
            console.print("[yellow]Tidak ada lowongan Glints yang lolos filter.[/]")
            return laporan

        # Sisa kuota harian, sama seperti di JobStreet.
        sisa = 0
        if config.max_apply_per_day > 0:
            sudah = db.get_today_apply_count()
            sisa = max(0, config.max_apply_per_day - sudah)
            console.print(
                f"[cyan]Kuota harian:[/] {sudah} sudah dilamar hari ini, "
                f"sisa {sisa} dari {config.max_apply_per_day}."
            )

            if sisa == 0:
                console.print(
                    "[bold yellow]Kuota lamaran hari ini sudah habis. "
                    "Tidak ada lamaran dikirim.[/]"
                )
                return laporan

        dipilih = pilih_teratas(layak, sisa)

        if sisa and len(layak) > sisa:
            console.print(
                f"[bold]{len(layak)} kandidat[/] bersaing untuk "
                f"[bold]{sisa} slot[/] — diambil {sisa} yang paling cocok."
            )

        tampilkan_perbandingan(dipilih)

        for job in dipilih:
            if batas and laporan["dilamar"] >= batas:
                console.print("[yellow]Batas lamaran sesi ini tercapai.[/]")
                break
            if _batas_harian_tercapai():
                console.print("[yellow]Batas lamaran harian tercapai.[/]")
                break

            if db.add_job(job):
                laporan["baru"] += 1

            try:
                hasil = bot.lamar(job)
            except ChromeTertutup as exc:
                console.print(f"[bold red]{exc}.[/] Sesi dihentikan.")
                laporan["gagal"] += 1
                break

            if hasil.applied:
                laporan["dilamar"] += 1
                db.record_application(
                    job["job_id"], "applied", hasil.reason
                )
                notifier.send_apply_success(job)
                console.print(f"[green]Terkirim: {job['title']}[/]")
            elif hasil.status == "already_applied":
                laporan["sudah"] += 1
                db.record_application(
                    job["job_id"], "already_applied", hasil.reason
                )
            elif hasil.status == "manual_required":
                laporan["perlu_manual"] += 1
                db.record_application(
                    job["job_id"], "manual_required", hasil.reason
                )
                console.print(
                    f"[yellow]Perlu manual: {job['title']} — {hasil.reason}[/]"
                )
            else:
                laporan["gagal"] += 1
                db.record_application(job["job_id"], hasil.status, hasil.reason)
                console.print(f"[red]Gagal: {job['title']} — {hasil.reason}[/]")

            time.sleep(max(0.0, float(config.delay_between_apply or 0)))
    finally:
        bot.tutup()

    return laporan


def kumpulkan_lowongan(bot, kata_kunci, halaman: int) -> List[Dict]:
    """Baca semua kartu dari daftar kata kunci, tanpa duplikat."""
    lowongan: List[Dict] = []
    terlihat = set()

    for keyword in kata_kunci:
        for nomor in range(max(1, halaman)):
            console.print(f"[cyan]Glints: '{keyword}' halaman {nomor + 1}[/]")
            for job in bot.cari(keyword, nomor):
                if job["job_id"] in terlihat:
                    continue
                terlihat.add(job["job_id"])
                lowongan.append(job)

    return lowongan


def pilih_kandidat(lowongan: List[Dict], batas: int = 0,
                   semuanya: bool = False) -> List[Dict]:
    """Saring lowongan yang layak dicoba (urutan tetap seperti di situs)."""
    saringan = JobFilter()
    hasil = []

    for job in lowongan:
        if not semuanya and alasan_tidak_layak(job, saringan):
            continue
        hasil.append(job)
        if batas and len(hasil) >= batas:
            break

    return hasil

def pesan_url_salah(url: str) -> str:
    """Pesan bantuan saat URL uji tidak bisa dipakai."""
    contoh = (
        "https://glints.com/id/opportunities/jobs/admin-warehouse/"
        "b5f8d754-afd9-4f0c-a618-360afe12248c"
    )

    if not url or url.startswith("<") or "contoh" in url.lower():
        return (
            "URL belum diisi (masih teks contoh). Tempel URL asli hasil copy "
            f"dari halaman lowongan Glints, mis. {contoh}"
        )

    if "glints.com" not in url.lower():
        return (
            "URL itu bukan alamat Glints. Buka lowongan di glints.com lalu "
            "salin dari kolom alamat Chrome."
        )

    return (
        "URL Glints belum berisi kode lowongan (bagian .../<kode-panjang>). "
        "Buka halaman detail lowongan, bukan halaman pencarian. Contoh: "
        f"{contoh}"
    )


def daftar_kandidat(keywords: Optional[List[str]] = None,
                    max_pages: int = 1, batas: int = 10,
                    semuanya: bool = False) -> List[Dict]:
    """Cari lowongan Glints lalu kembalikan yang layak dilamar (tanpa melamar)."""
    kata_kunci = list(keywords or config.keywords)
    bot = GlintsBot()

    try:
        bot.init_browser()
        lowongan = kumpulkan_lowongan(bot, kata_kunci, max_pages)
    finally:
        bot.tutup()

    console.print(f"[bold]Terbaca {len(lowongan)} lowongan Glints.[/]")
    return pilih_kandidat(lowongan, batas=batas, semuanya=semuanya)


def uji_otomatis(keywords: Optional[List[str]] = None,
                 max_pages: int = 1) -> tuple:
    """Pilih sendiri satu lowongan yang layak, lalu uji lamar di sana.

    Dipakai `glints uji` tanpa --url, supaya tidak perlu mencari URL manual.
    """
    kata_kunci = list(keywords or config.keywords)
    bot = GlintsBot()

    try:
        bot.init_browser()
        lowongan = kumpulkan_lowongan(bot, kata_kunci, max_pages)

        if not lowongan:
            return None, ApplyResult(
                False, "error", "Tidak ada lowongan terbaca dari pencarian"
            )

        kandidat = pilih_kandidat(lowongan, batas=1)

        if not kandidat:
            contoh = next(
                (job for job in lowongan if not job.get("khusus_aplikasi")),
                lowongan[0],
            )
            return contoh, ApplyResult(
                False,
                "manual_required",
                "Semua lowongan terbaca sudah tersaring (gaji/lokasi/judul/"
                "aplikasi). Coba --keywords lain.",
            )

        if not bot.login():
            return kandidat[0], ApplyResult(
                False, "login_required", "Login Glints belum selesai"
            )

        job = kandidat[0]
        console.print(
            f"[cyan]Lowongan uji terpilih:[/] {job['title']} — "
            f"{job.get('company') or '-'} ({job.get('location') or '-'})"
        )
        return job, bot.lamar(job)
    finally:
        bot.tutup()

def uji_glints(url: str) -> ApplyResult:
    """Uji alur lamaran pada satu lowongan Glints (tanpa pencarian)."""
    url = (url or "").strip()

    if not id_dari_url(url):
        return ApplyResult(False, "error", pesan_url_salah(url))

    bot = GlintsBot()
    try:
        bot.init_browser()
        if not bot.login():
            return ApplyResult(False, "login_required", "Login Glints belum selesai")

        job = {
            "job_id": f"glints:{id_dari_url(url)}",
            "title": "uji-lamar",
            "url": url,
        }
        return bot.lamar(job)
    finally:
        bot.tutup()
