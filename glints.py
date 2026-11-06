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
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

import kuota
from auto_apply import ApplyResult, AutoApplier
from browser import buka_chrome, tutup_chrome
from config import MAKS_HALAMAN_RISET, batas_halaman_riset, config
from database import db
from job_filter import (
    JobFilter,
    dedupe_jobs,
)
from job_filter import (
    alasan_tidak_layak as alasan_standar,
)
from job_filter import job_filter as penyaring
from notifier import notifier

console = Console()

# Sama seperti JobStreet: riset Glints berhenti setelah 5 kali muat
# ("Muat lebih banyak") untuk setiap kata kunci.
BATAS_MUAT_GLINTS = MAKS_HALAMAN_RISET


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
# Glints kadang memindahkan halaman pencarian. Semua bentuk ini dicoba
# berurutan sampai ada kartu lowongan; yang berhasil diingat untuk kata
# kunci berikutnya.
SEARCH_URL_CANDIDATES = (
    BASE + "/id/opportunities/jobs/explore?keyword={keyword}&countryCode=ID",
    BASE + "/id/opportunities/jobs?keyword={keyword}",
    BASE + "/id/opportunities/jobs/explore?keyword={keyword}",
    BASE + "/id/search?keyword={keyword}",
    BASE + "/id/opportunities/jobs/explore?keyword={keyword}&sortBy=LATEST",
)
SEARCH_URL = SEARCH_URL_CANDIDATES[0]
LOGIN_URL = BASE + "/id/login"

# Pola tautan lowongan Glints. UUID boleh berada setelah slug
# (/opportunities/jobs/<slug>/<uuid>) atau langsung
# (/opportunities/jobs/<uuid>), karena dua bentuk itu pernah dipakai.
TAUTAN_LOWONGAN = re.compile(
    r"/opportunities/jobs/(?:[^/?#]+/)?"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12})"
)

# Tautan yang bukan lowongan (halaman pencarian/kategori).
TAUTAN_BUKAN_LOWONGAN = ("/explore", "/search", "/job-location/", "/companies/")

# Halaman verifikasi Cloudflare: "Just a moment..." / "Checking your browser".
TANDA_CLOUDFLARE = (
    "just a moment",
    "checking your browser",
    "verifikasi browser",
    "verifying you are human",
    "cf-challenge",
    "cf_chl_opt",
    "cloudflare",
    "enable javascript and cookies to continue",
)

# Berapa detik menunggu verifikasi Cloudflare selesai sendiri.
CLOUDFLARE_WAIT = 45

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

def folder_debug() -> Path:
    """Folder penyimpanan HTML/screenshot saat pembacaan gagal."""
    return Path(__file__).resolve().parent / "debug"


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


def halaman_per_kata_kunci(max_pages: int = 0) -> int:
    """Berapa kali daftar dimuat per kata kunci.

    Maksimal 5 (BATAS_MUAT_GLINTS), sama seperti batas halaman riset
    JobStreet. Nilai 0 atau lebih dari 5 tetap dipakai sebagai 5; nilai
    lebih kecil dihormati.
    """
    if max_pages and max_pages > 0:
        return batas_halaman_riset(max_pages)

    return batas_halaman_riset(
        getattr(config, "research_max_pages", MAKS_HALAMAN_RISET)
    )


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


def tampilkan_rincian_skor(kandidat: List[Dict], maksimal: int = 3,
                           situs: str = "Glints"):
    """Rincian skor per dimensi (sama seperti tabel JobStreet)."""
    if not kandidat:
        return

    table = Table(
        title=f"Rincian skor kandidat teratas ({situs})", show_lines=False
    )
    table.add_column("Judul", style="cyan", max_width=30)
    for nama in ("Posisi", "Lokasi", "Kualifikasi", "Pengalaman", "Pendidikan",
                 "Keterampilan", "Tanggal", "Gaji", "Total"):
        table.add_column(nama, justify="right", style="dim")

    for job in kandidat[:maksimal]:
        rincian = job.get("_skor_rincian") or {}
        table.add_row(
            str(job.get("title") or "-")[:30],
            *[
                str(rincian.get(kunci, 0))
                for kunci in ("posisi", "lokasi", "kualifikasi", "pengalaman",
                              "pendidikan", "keterampilan", "tanggal", "gaji")
            ],
            f"[green]{job.get('_score', 0)}[/]",
        )

    console.print(table)


def tampilkan_perbandingan(kandidat: List[Dict], maksimal: int = 10,
                           situs: str = "Glints"):
    """Tabel kandidat teratas beserta skor kecocokannya."""
    if not kandidat:
        return

    table = Table(
        title=f"Kandidat {situs} yang akan dilamar (dibandingkan dari "
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


# Teks umur lowongan yang biasa muncul di kartu Glints.
_POLA_UMUR = (
    (r"baru saja|hari ini|just posted|today", 0),
    (r"(\d+)\s*menit|(\d+)\s*minute", 0),
    (r"(\d+)\s*jam|(\d+)\s*hour", 0),
    (r"(\d+)\s*hari|(\d+)\s*day", 1),
    (r"(\d+)\s*minggu|(\d+)\s*week", 7),
    (r"(\d+)\s*bulan|(\d+)\s*month", 30),
)


def umur_dari_teks(teks: str) -> Optional[int]:
    """Umur lowongan (hari) dari teks kartu Glints; None bila tak terbaca.

    Kartu Glints menulis hal seperti "3 hari lalu", "2 minggu lalu",
    "Baru saja", atau "5 jam lalu".
    """
    isi = " ".join(str(teks or "").lower().split())
    if not isi:
        return None

    for pola, faktor in _POLA_UMUR:
        cocok = re.search(pola, isi)
        if not cocok:
            continue

        if faktor == 0:
            return 0

        angka = next((g for g in cocok.groups() if g), None)
        if angka is None:
            return 0

        return int(angka) * faktor

    return None


def label_umur(umur: Optional[int]) -> str:
    """Teks tanggal publikasi untuk laporan & penyortiran."""
    if umur is None:
        return ""
    if umur <= 0:
        return "Hari ini"
    return f"{umur} hari lalu"


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
    umur = umur_dari_teks(teks)

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
        "date_posted": label_umur(umur),
        "age_days": umur,
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


def alasan_tidak_layak(job: Dict, saringan: Optional[JobFilter] = None) -> str:
    """Alasan lowongan tidak dicoba dilamar ('' bila layak).

    Memakai aturan tunggal JobStreet (`job_filter.alasan_tidak_layak`): tidak
    ada syarat tambahan khusus Glints seperti batas gaji Glints atau lokasi
    wajib, dan logo perusahaan tidak dipakai menyaring.
    """
    return alasan_standar(job, saringan)


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
        # Sama seperti JobStreet: bila Glints meminta login di tengah sesi,
        # sesi dihentikan agar tidak menumpuk galat.
        self.login_expired = False
        # Pola URL pencarian yang terbukti menghasilkan kartu.
        self.search_url = ""
        # Ringkasan diagnosa terakhir (dipakai tes & laporan).
        self.diagnosa_terakhir: Dict = {}

    # ------------------------------ browser ---------------------------
    def init_browser(self):
        console.print("[bold blue]Membuka Chrome untuk Glints...[/]")
        self.driver = buka_chrome(label="Glints")
        console.print("[bold green]Chrome siap.[/]")

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

        # Halaman verifikasi Cloudflare tidak memuat menu login sama sekali;
        # tanpa cek ini bot keliru menyimpulkan "sudah login".
        if self.kena_cloudflare():
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

    # --------------------------- diagnosa -----------------------------
    def _judul_halaman(self) -> str:
        with contextlib.suppress(Exception):
            return " ".join(str(self.driver.title or "").split())
        return ""

    def _tautan_kartu(self) -> List[str]:
        """Semua href yang mengarah ke halaman lowongan di halaman ini."""
        try:
            elemen = self.driver.find_elements(
                By.CSS_SELECTOR, "a[href*='/opportunities/jobs/']"
            )
        except Exception:
            return []

        hasil = []
        for elemen_satu in elemen:
            with contextlib.suppress(Exception):
                href = elemen_satu.get_attribute("href") or ""
                if not href or any(bukan in href for bukan in TAUTAN_BUKAN_LOWONGAN):
                    continue
                if TAUTAN_LOWONGAN.search(href):
                    hasil.append(href)

        return hasil

    def kena_cloudflare(self) -> bool:
        """True bila halaman yang terbuka adalah verifikasi Cloudflare."""
        judul = self._judul_halaman().lower()
        teks = self._teks_halaman()

        return any(
            tanda in judul or tanda in teks for tanda in TANDA_CLOUDFLARE
        )

    def _tunggu_cloudflare(self, detik: int = CLOUDFLARE_WAIT) -> bool:
        """Tunggu verifikasi Cloudflare lewat; True bila halaman sudah lolos."""
        if not self.kena_cloudflare():
            return True

        console.print(
            "[yellow]Halaman Glints sedang menampilkan verifikasi Cloudflare "
            '("Just a moment...").[/]'
        )

        batas = time.time() + max(5, detik)
        while time.time() < batas:
            time.sleep(2)
            if not self.kena_cloudflare() or self._tautan_kartu():
                console.print("[green]Verifikasi selesai.[/]")
                return True

        console.print(
            "[bold yellow]Verifikasi Cloudflare belum selesai. Pilihan:[/]\n"
            "  1. Selesaikan centang/verifikasi di jendela Chrome yang "
            "terbuka, lalu jalankan lagi.\n"
            "  2. Pakai Chrome Anda sendiri (paling stabil): jalankan "
            "chrome-debug.bat, selesaikan verifikasinya, lalu\n"
            "     python cli.py set-env CHROME_DEBUG_PORT=9222 dan jalankan "
            "lagi."
        )
        return False

    def _tunggu_kartu(self, detik: Optional[int] = None) -> int:
        """Tunggu sampai tautan lowongan muncul (SEARCH_WAIT detik)."""
        batas = time.time() + max(
            3, int(detik if detik is not None else config.search_wait)
        )
        mulai = time.time()
        digulir = False
        jumlah = len(self._tautan_kartu())

        while jumlah == 0 and time.time() < batas:
            # Sebagian halaman memuat kartu saat digulir, bukan saat dibuka.
            if not digulir and time.time() - mulai >= 3:
                with contextlib.suppress(Exception):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                digulir = True

            time.sleep(0.5)
            jumlah = len(self._tautan_kartu())

        return jumlah

    def simpan_diagnosa(self, awalan: str = "glints", keyword: str = "") -> Dict:
        """Simpan HTML + screenshot dan cetak ringkasan penyebab 0 kartu."""
        folder = folder_debug()
        cap = f"{awalan}-{time.strftime('%Y%m%d-%H%M%S')}"

        if keyword:
            bersih = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
            if bersih:
                cap += f"-{bersih}"

        html = folder / f"{cap}.html"
        png = folder / f"{cap}.png"

        teks = self._teks_halaman()
        tautan = self._tautan_kartu()
        kartu = []
        with contextlib.suppress(Exception):
            kartu = [
                rapikan_kartu(mentah) for mentah in self._kartu_mentah()
            ]

        info = {
            "url": self._url(),
            "judul": self._judul_halaman(),
            "jumlah_tautan": len(tautan),
            "contoh_tautan": tautan[:8],
            "jumlah_kartu": len([k for k in kartu if k]),
            "meminta_login": "masuk" in teks and "lowongan" not in teks,
            "cloudflare": self.kena_cloudflare(),
            "captcha": any(
                tanda in teks
                for tanda in ("captcha", "unusual traffic")
            ),
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

        self.diagnosa_terakhir = info

        console.print("[bold yellow]Diagnosa halaman Glints:[/]")
        console.print(f"  URL          : {info['url'] or '-'}")
        console.print(f"  Judul halaman: {info['judul'] or '-'}")
        console.print(
            f"  Tautan lowongan ditemukan: {info['jumlah_tautan']}, "
            f"kartu terbaca: {info['jumlah_kartu']}"
        )

        for contoh in info["contoh_tautan"]:
            console.print(f"    - {contoh}")

        if info["meminta_login"]:
            console.print(
                "[yellow]  Halaman meminta login: masuk dulu ke Glints di "
                "jendela Chrome, lalu jalankan lagi.[/]"
            )
        if info["cloudflare"]:
            console.print(
                "[yellow]  Halaman ini adalah verifikasi Cloudflare "
                '("Just a moment..."). Selesaikan verifikasinya di jendela '
                "Chrome, atau pakai Chrome Anda sendiri: jalankan "
                "chrome-debug.bat lalu set CHROME_DEBUG_PORT=9222.[/]"
            )
        if info["captcha"]:
            console.print(
                "[yellow]  Halaman menampilkan captcha: selesaikan di "
                "jendela Chrome, lalu jalankan lagi.[/]"
            )
        if info["berkas_html"]:
            console.print(f"  HTML        : {info['berkas_html']}")
        if info["berkas_png"]:
            console.print(f"  Screenshot  : {info['berkas_png']}")

        return info

    # ----------------------------- pencarian --------------------------
    def buka_pencarian(self, keyword: str) -> bool:
        """Buka halaman hasil pencarian Glints; coba beberapa bentuk URL."""
        kandidat = ([self.search_url] if self.search_url else [])
        kandidat += [u for u in SEARCH_URL_CANDIDATES if u not in kandidat]

        for pola in kandidat:
            url = pola.format(keyword=quote_plus(keyword))
            self.driver.get(url)

            if self.kena_cloudflare():
                self._tunggu_cloudflare()

            jumlah = self._tunggu_kartu()

            if jumlah:
                if pola != self.search_url:
                    console.print(
                        f"[dim]Halaman pencarian Glints yang dipakai: {url}[/]"
                    )
                self.search_url = pola
                return True

            if "/login" in self._url().lower():
                console.print("[yellow]Halaman Glints meminta login.[/]")
                return False

            teks = self._teks_halaman()
            if "masuk" in teks and "lowongan" not in teks:
                console.print("[yellow]Halaman Glints meminta login.[/]")
                return False

        console.print(
            "[bold yellow]Tidak ada kartu lowongan yang muncul di halaman "
            f"pencarian Glints untuk \"{keyword}\".[/]"
        )
        self.simpan_diagnosa("pencarian", keyword)
        return False

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

        # Urutkan dari yang paling baru setiap kali mencari, berapa pun
        # jumlah "Muat lebih banyak"-nya (dulu hanya saat halaman == 0,
        # sehingga riset 5 muat kehilangan urutan terbaru).
        if config.prefer_newest:
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

        if not lowongan:
            # Skrip kartu tidak menemukan apa pun: coba baca langsung dari
            # elemen <a> (struktur situs bisa berubah sewaktu-waktu).
            for mentah in self._kartu_fallback():
                job = rapikan_kartu(mentah)
                if not job or job["job_id"] in sudah_ada:
                    continue
                sudah_ada.add(job["job_id"])
                lowongan.append(job)

            if lowongan:
                console.print(
                    f"[yellow]Pembaca kartu utama tidak mengenali halaman; "
                    f"dipakai cara cadangan ({len(lowongan)} lowongan).[/]"
                )
            else:
                self.simpan_diagnosa("kartu-kosong", keyword)

        return lowongan

    def _kartu_fallback(self) -> list:
        """Baca kartu langsung dari elemen <a>, tanpa skrip JavaScript."""
        try:
            elemen_semua = self.driver.find_elements(
                By.CSS_SELECTOR, "a[href*='/opportunities/jobs/']"
            )
        except Exception:
            return []

        hasil = []

        for elemen in elemen_semua:
            with contextlib.suppress(Exception):
                href = elemen.get_attribute("href") or ""
                if not href or not TAUTAN_LOWONGAN.search(href):
                    continue
                if any(bukan in href for bukan in TAUTAN_BUKAN_LOWONGAN):
                    continue

                teks = " ".join((elemen.text or "").split())
                hasil.append({
                    "url": href.split("?")[0],
                    "title": teks,
                    "company": "",
                    "location": "",
                    "salary": "",
                    "text": teks,
                    "logo": [],
                })

        return hasil

    # ------------------------------ lamar -----------------------------
    def lamar(self, job: dict) -> ApplyResult:
        """Lamar satu lowongan Glints dengan aturan yang sama seperti JobStreet.

        Urutannya: periksa judul/URL → periksa catatan database → mode otomatis
        (`AUTO_APPLY=true`) atau tinjau manual. Status selalu dicatat ke
        database, termasuk `already_applied` dan `login_required`.
        """
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()
        job_id = str(job.get("job_id") or "").strip()

        if not title or not url:
            console.print(
                "[yellow]Lowongan dilewati karena judul atau URL tidak terbaca.[/]"
            )
            return ApplyResult(False, "error", "Judul atau URL tidak terbaca")

        if not job_id:
            job_id = f"glints:{id_dari_url(url)}"
            job["job_id"] = job_id

        # Sama seperti JobStreet: jangan pernah melamar dua kali.
        if db.is_already_applied(job_id):
            return ApplyResult(False, "already_applied", "Sudah tercatat dilamar")

        if config.auto_apply:
            return self._lamar_otomatis(job, job_id)

        return self._lamar_manual(job, job_id)

    @staticmethod
    def _catat(job_id: str, status: str, catatan: str) -> None:
        try:
            db.record_application(job_id, status, catatan)
        except Exception as exc:
            console.print(f"[yellow]Gagal mencatat lamaran: {exc}[/]")

    def _lamar_otomatis(self, job: dict, job_id: str) -> ApplyResult:
        title = (job.get("title") or "").strip()
        console.print(f"\n[bold magenta]{title}[/] [cyan](otomatis)[/]")

        try:
            hasil = GlintsApplier(self.driver).apply(job)
        except WebDriverException as exc:
            if chrome_mati(str(exc)):
                raise ChromeTertutup(
                    "Jendela Chrome tertutup saat program berjalan"
                ) from exc
            self._catat(job_id, "error", f"Galat browser: {exc}")
            return ApplyResult(False, "error", f"Galat browser: {exc}")
        except Exception as exc:  # jaring pengaman: jangan hentikan sesi
            self._catat(job_id, "error", f"Galat tak terduga: {exc}")
            return ApplyResult(False, "error", f"Galat tak terduga: {exc}")

        # apply() menelan galat browser menjadi ApplyResult; ubah lagi menjadi
        # ChromeTertutup supaya sesi berhenti rapi, bukan mencetak traceback.
        if hasil.status == "error" and chrome_mati(hasil.reason):
            raise ChromeTertutup(
                "Jendela Chrome tertutup saat program berjalan"
            )

        if hasil.status == "applied":
            self._catat(job_id, "applied", hasil.reason or "Dikirim otomatis")
            console.print("[bold green]Lamaran terkirim otomatis.[/]")
        elif hasil.status == "already_applied":
            self._catat(job_id, "already_applied", hasil.reason)
        elif hasil.status == "login_required":
            self._catat(job_id, "error", hasil.reason)
            self.login_expired = True
            console.print(
                "[bold red]Sesi login Glints sudah habis. Sesi dihentikan.[/]"
            )
        elif hasil.status == "manual_required":
            self._catat(job_id, "manual_required", hasil.reason)
            console.print(f"[yellow]Dilewati: {hasil.reason}[/]")
        else:
            self._catat(job_id, "error", hasil.reason)
            console.print(f"[bold red]Gagal melamar otomatis: {hasil.reason}[/]")

        return hasil

    def _lamar_manual(self, job: dict, job_id: str) -> ApplyResult:
        """Buka halaman lowongan supaya pengguna melamar sendiri (JobStreet)."""
        title = (job.get("title") or "").strip()
        url = (job.get("url") or "").strip()

        try:
            self.driver.get(url)
            time.sleep(2)

            if self._halaman_sudah_dilamar():
                self._catat(
                    job_id, "already_applied",
                    "Halaman menandai lowongan ini sudah pernah dilamar",
                )
                console.print(
                    f"[yellow]Glints menandai '{title}' sudah pernah dilamar. "
                    "Dicatat dan dilewati.[/]"
                )
                return ApplyResult(False, "already_applied", "Sudah pernah dilamar")

            # Mode manual: isian pengguna di halaman ini ikut diingat.
            pencatat = GlintsApplier(self.driver)
            try:
                potret_awal = pencatat._potret_jawaban()
            except Exception:
                potret_awal = {}

            console.print(f"\n[bold magenta]{title}[/]")
            console.print(f"Perusahaan: {job.get('company', 'Tidak diketahui')}")
            console.print(f"URL: {url}")
            console.print(
                "[cyan]Tinjau persyaratan di Chrome. Jika cocok, lakukan Lamar "
                "dan Kirim sendiri.[/]"
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
                console.print("[bold green]Lamaran dicatat sebagai terkirim.[/]")
                return ApplyResult(True, "applied", "Dikonfirmasi manual")

            self._catat(
                job_id, "skipped",
                "Tidak dikonfirmasi sebagai lamaran terkirim",
            )
            console.print("[yellow]Tidak dicatat sebagai lamaran terkirim.[/]")
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

    def _halaman_sudah_dilamar(self) -> bool:
        teks = self._teks_halaman()
        return any(tanda in teks for tanda in SUDAH_DILAMAR_TEXTS)

    def tutup(self):
        tutup_chrome(self.driver)


# ----------------------------------------------------------------------
# Alur utama
# ----------------------------------------------------------------------
def _batas_harian_tercapai() -> bool:
    """Sama seperti JobStreet: satu aturan di modul `kuota`."""
    if not kuota.habis(db):
        return False

    console.print("[bold yellow]Batas lamaran harian tercapai.[/]")
    return True


def tampilkan_konfigurasi_glints() -> None:
    """Ringkasan pengaturan aktif, isinya sama dengan banner JobStreet."""
    mode = "otomatis" if config.auto_apply else "manual (tinjau sendiri)"
    batas_harian = kuota.batas()
    teks_kuota = f"{batas_harian} per hari" if batas_harian else "tanpa batas"
    batas_sesi = int(getattr(config, "auto_apply_max_per_session", 0) or 0)
    port = int(getattr(config, "chrome_debug_port", 0) or 0)

    tabel = Table(title="Pengaturan sesi Glints", show_header=False)
    tabel.add_column("Pengaturan", style="cyan")
    tabel.add_column("Nilai")

    kata_kunci = list(config.keywords_riset or [])
    tabel.add_row("Mode lamar", mode)
    tabel.add_row("Kuota lamaran", teks_kuota)
    tabel.add_row(
        "Batas per sesi", f"{batas_sesi} lamaran" if batas_sesi else "tanpa batas"
    )
    tabel.add_row(
        "Kata kunci riset",
        f"{len(kata_kunci)} — {', '.join(kata_kunci[:3])}"
        + (" ..." if len(kata_kunci) > 3 else ""),
    )
    tabel.add_row(
        "Lokasi disaring",
        f"{len(config.locations)} — {', '.join(config.locations[:3])}"
        if config.locations
        else "semua lokasi",
    )
    tabel.add_row("Wajib logo perusahaan", "tidak (sama di semua situs)")
    tabel.add_row("Urutan kandidat", getattr(config, "rank_by", "relevance"))
    tabel.add_row("Jeda antar lamaran", f"{config.delay_between_apply} detik")
    tabel.add_row(
        "Gaji minimal",
        f"Rp{config.min_salary:,}".replace(",", ".")
        if config.min_salary
        else "tanpa batas",
    )
    tabel.add_row(
        "Chrome",
        f"menempel ke port {port}" if port else "dibuka oleh bot",
    )

    console.print(tabel)


def jalankan_glints(max_pages: int = 0, keywords: Optional[List[str]] = None,
                    batas: int = 0, laporan_harian: bool = True) -> dict:
    """Cari, saring, lalu lamar lowongan Glints secara otomatis."""
    kata_kunci = list(keywords) if keywords else config.keywords_riset
    halaman = halaman_per_kata_kunci(max_pages)
    batas_riset = int(getattr(config, "research_max_jobs", 0) or 0)

    bot = GlintsBot()
    laporan = {
        "dibaca": 0, "baru": 0, "dilamar": 0, "sudah": 0,
        "dilewati": 0, "gagal": 0, "perlu_manual": 0,
        "khusus_aplikasi": 0,
    }

    tampilkan_konfigurasi_glints()

    if not config.auto_apply:
        console.print(
            "[bold yellow]Mode manual aktif: setiap lowongan dibuka untuk Anda "
            "tinjau dan kirim sendiri. Pakai AUTO_APPLY=true untuk mengirim "
            "otomatis.[/]\n"
        )

    try:
        bot.init_browser()

        if not bot.login():
            console.print("[red]Login Glints belum selesai — dihentikan.[/]")
            return laporan

        lowongan: List[Dict] = []
        terlihat = set()
        duplikat = 0

        console.print(
            f"[bold blue]RISET GLINTS[/] — {len(kata_kunci)} kata kunci, "
            f"maksimal {halaman} muat per kata kunci "
            f"(batas tetap {MAKS_HALAMAN_RISET}), urut 'Baru Ditambahkan'."
        )

        mulai_riset = time.monotonic()
        total_kata_kunci = len(kata_kunci)
        selesai_kata_kunci = 0

        for keyword in kata_kunci:
            console.print(
                f"[cyan]Glints: '{keyword}' — muat sampai {halaman} kali[/]"
            )
            # Sekali buka per kata kunci: `cari` sendiri yang mengklik "Muat
            # lebih banyak" sampai tombolnya habis, lalu mengembalikan semua
            # kartu yang sudah termuat. Jauh lebih cepat daripada membuka
            # ulang halaman untuk setiap nomor halaman.
            kartu = bot.cari(keyword, max(0, halaman - 1))

            baru = 0
            for job in kartu:
                if job["job_id"] in terlihat:
                    duplikat += 1
                    continue
                terlihat.add(job["job_id"])
                lowongan.append(job)
                baru += 1

            if baru == 0:
                console.print(
                    "[dim]Tidak ada lowongan baru untuk kata kunci ini.[/]"
                )

            selesai_kata_kunci += 1
            lama_riset = time.monotonic() - mulai_riset
            per_kata_kunci = lama_riset / max(1, selesai_kata_kunci)
            sisa = per_kata_kunci * (
                total_kata_kunci - selesai_kata_kunci
            )
            console.print(
                f"[dim]Kemajuan riset Glints: {selesai_kata_kunci}/"
                f"{total_kata_kunci} kata kunci, {len(lowongan)} lowongan, "
                f"{lama_riset:.0f} detik berlalu — perkiraan sisa "
                f"{sisa:.0f} detik.[/]"
            )

            if batas_riset and len(lowongan) >= batas_riset:
                console.print(
                    f"[cyan]Batas riset RESEARCH_MAX_JOBS={batas_riset} "
                    "tercapai — riset Glints dihentikan.[/]"
                )
                break

        sebelum_dedup = len(lowongan)
        lowongan = dedupe_jobs(lowongan)
        dibuang = (sebelum_dedup - len(lowongan)) + duplikat

        laporan["dibaca"] = len(lowongan)
        console.print(
            f"[bold green]Riset Glints selesai:[/] "
            f"{sebelum_dedup + duplikat} terbaca → {len(lowongan)} unik "
            f"({dibuang} duplikat dibuang) dalam "
            f"{time.monotonic() - mulai_riset:.0f} detik."
        )

        # --- Saring dulu semuanya, baru bandingkan dan pilih yang terbaik ---
        layak: List[Dict] = []

        for job in lowongan:
            if job.get("khusus_aplikasi"):
                # Perbedaan teknis Glints: lowongan ini tidak punya formulir
                # web. Diperlakukan seperti "apply di situs perusahaan" pada
                # JobStreet, yaitu PERLU MANUAL — bukan dilewati.
                laporan["khusus_aplikasi"] += 1
                laporan["perlu_manual"] += 1
                console.print(
                    f"[yellow]Perlu manual: {job['title']} — hanya bisa "
                    f"dilamar lewat aplikasi Glints[/]\n[dim]   {job.get('url', '')}[/]"
                )
                continue

            if job.get("sudah_dilamar"):
                laporan["sudah"] += 1
                db.add_job(job)
                db.record_application(
                    job["job_id"], "already_applied",
                    "Ditandai sudah dilamar di Glints",
                )
                console.print(f"[dim]Lewati: {job['title']} — sudah dilamar[/]")
                continue

            # Sama seperti JobStreet: lowongan yang pernah dilamar bot (atau
            # tercatat di database) dilewati diam-diam, tidak memakai kuota.
            if db.is_already_applied(job["job_id"]):
                laporan["sudah"] += 1
                continue

            # Catat lowongan baru seperti JobStreet menghitung "baru".
            if db.add_job(job):
                laporan["baru"] += 1

            # Aturan kelayakan tunggal — sama persis dengan JobStreet & Indeed.
            alasan = alasan_tidak_layak(job, bot.filters)
            if alasan:
                laporan["dilewati"] += 1
                console.print(f"[dim]Lewati: {job['title']} — {alasan}[/]")
                continue

            layak.append(job)

        if not layak:
            console.print("[yellow]Tidak ada lowongan Glints yang lolos filter.[/]")
            if not lowongan:
                console.print(
                    "[dim]Jalankan `python cli.py glints diagnosa` untuk "
                    "memeriksa apakah kartu lowongan terbaca.[/]"
                )
            return laporan

        # Sisa kuota harian — modul `kuota` yang sama dengan JobStreet.
        console.print(f"[cyan]{kuota.ringkasan(db)}[/]")

        if kuota.habis(db):
            console.print(f"[bold yellow]{kuota.pesan_habis()}[/]")
            return laporan

        dipilih = pilih_teratas(layak, kuota.sisa(db) or 0)

        sisa = kuota.sisa(db)
        if sisa is not None and len(layak) > sisa:
            console.print(
                f"[bold]{len(layak)} kandidat[/] bersaing untuk "
                f"[bold]{sisa} slot[/] — diambil {sisa} yang paling cocok."
            )

        tampilkan_perbandingan(dipilih)
        tampilkan_rincian_skor(dipilih)

        batas_sesi = int(getattr(config, "auto_apply_max_per_session", 0) or 0)

        for job in dipilih:
            if batas and laporan["dilamar"] >= batas:
                console.print("[yellow]Batas lamaran sesi ini tercapai.[/]")
                break
            if _batas_harian_tercapai():
                console.print("[yellow]Batas lamaran harian tercapai.[/]")
                break
            if batas_sesi and laporan["dilamar"] >= batas_sesi:
                console.print(
                    "[bold yellow]Batas lamaran otomatis per sesi "
                    f"({batas_sesi}) tercapai. Sisa lowongan dilewati.[/]"
                )
                break

            try:
                hasil = bot.lamar(job)
            except ChromeTertutup as exc:
                console.print(f"[bold red]{exc}.[/] Sesi dihentikan.")
                laporan["gagal"] += 1
                break

            if hasil.status == "login_required":
                laporan["gagal"] += 1
                console.print(
                    "[bold red]Sesi login Glints sudah habis. Sesi dihentikan "
                    "agar tidak menumpuk galat.[/]"
                )
                notifier.send_error("Sesi login Glints habis")
                break

            if hasil.applied:
                laporan["dilamar"] += 1
                notifier.send_apply_success(job)
                console.print(f"[green]Terkirim: {job['title']}[/]")
            elif hasil.status == "already_applied":
                laporan["sudah"] += 1
            elif hasil.status == "manual_required":
                laporan["perlu_manual"] += 1
                console.print(
                    f"[yellow]Perlu manual: {job['title']} — {hasil.reason}[/]"
                )
            elif hasil.status == "skipped":
                laporan["dilewati"] += 1
            else:
                laporan["gagal"] += 1
                console.print(f"[red]Gagal: {job['title']} — {hasil.reason}[/]")

            # Jeda hanya setelah lamaran benar-benar diproses, sama seperti
            # JobStreet; lowongan yang dilewati langsung lanjut.
            if hasil.applied or hasil.status == "error":
                jeda = max(0.0, float(config.delay_between_apply or 0))
                if jeda:
                    console.print(
                        f"[dim]Jeda {jeda:.0f} detik sebelum lowongan "
                        "berikutnya...[/]"
                    )
                    time.sleep(jeda)
    except Exception as exc:
        # Sama seperti JobStreet: galat tak terduga dilaporkan ke Telegram.
        notifier.send_error(str(exc))
        raise

    finally:
        bot.tutup()

        # Ringkasan harian ke Telegram, sama seperti sesi JobStreet.
        # Peluncur satu klik mematikan ini agar laporannya cukup satu.
        if laporan_harian:
            try:
                notifier.send_daily_report(db.get_stats())
            except Exception as exc:
                console.print(f"[yellow]Laporan harian gagal dikirim: {exc}[/]")

    return laporan


def kumpulkan_lowongan(bot, kata_kunci, halaman: int) -> List[Dict]:
    """Baca semua kartu dari daftar kata kunci, tanpa duplikat."""
    lowongan: List[Dict] = []
    terlihat = set()

    for keyword in kata_kunci:
        console.print(
            f"[cyan]Glints: '{keyword}' — muat sampai {max(1, halaman)} kali[/]"
        )
        for job in bot.cari(keyword, max(0, halaman - 1)):
            if job["job_id"] in terlihat:
                continue
            terlihat.add(job["job_id"])
            lowongan.append(job)

    return dedupe_jobs(lowongan)


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

def diagnosa_glints(keyword: str = "") -> Dict:
    """Periksa mengapa kartu lowongan Glints tidak terbaca.

    Membuka satu kata kunci di Chrome, mencoba semua bentuk URL pencarian,
    lalu melaporkan URL akhir, judul halaman, jumlah tautan lowongan, contoh
    tautannya, serta menyimpan HTML + screenshot ke folder debug/.
    """
    kata = (keyword or "").strip()
    if not kata:
        kata = config.keywords[0] if config.keywords else "inventory"

    bot = GlintsBot()
    info: Dict = {}

    try:
        bot.init_browser()
        console.print(f"[cyan]Diagnosa Glints — kata kunci: '{kata}'[/]")

        berhasil = bot.buka_pencarian(kata)
        # buka_pencarian sudah menyimpan diagnosa saat gagal; jangan ulangi.
        info = bot.diagnosa_terakhir or bot.simpan_diagnosa("diagnosa", kata)

        console.print(
            f"[cyan]Login Glints terdeteksi:[/] "
            f"{'ya' if bot.sudah_login() else 'belum'}"
        )

        if berhasil:
            kartu = [rapikan_kartu(mentah) for mentah in bot._kartu_mentah()]
            kartu = [job for job in kartu if job]
            console.print(
                f"[green]Pembaca kartu utama berhasil: {len(kartu)} "
                "lowongan terbaca.[/]"
            )

            for job in kartu[:5]:
                console.print(
                    f"  - {job['title'][:45]} | {job['company'] or '-'} | "
                    f"{job['location'] or '-'} | {job['salary'] or '-'} | "
                    f"logo: {'ada' if job.get('has_logo') else 'tidak'}"
                )

            if not kartu:
                cadangan = bot._kartu_fallback()
                console.print(
                    f"[yellow]Cara cadangan (tanpa JS) menemukan "
                    f"{len(cadangan)} tautan lowongan.[/]"
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


# ----------------------------------------------------------------------
# Periksa kesehatan Glints (satu perintah, berurutan)
# ----------------------------------------------------------------------
def _setuju_lamar(jumlah: int, kandidat: List[Dict]) -> bool:
    """Tanya sekali sebelum mengirim lamaran sungguhan saat `glints cek`."""
    console.print(
        f"[bold]Uji kirim {jumlah} lamaran SUNGGUHAN ke Glints.[/] "
        "Lamaran ini tercatat di akun Anda."
    )
    for job in kandidat[:jumlah]:
        console.print(
            f"  - {str(job.get('title') or '')[:45]} | "
            f"{job.get('company') or '-'}"
        )
    try:
        jawab = input("Lanjutkan? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return jawab in {"y", "ya", "yes", "yup"}


def cek_glints(keyword: str = "", max_pages: int = 1, lamar: int = 0,
               ya: bool = False) -> bool:
    """Periksa Glints berurutan: baca kartu → saring → simulasi → (opsional) lamar.

    Mengembalikan True bila semua tahap yang dijalankan lulus. Pengiriman
    lamaran hanya terjadi bila `lamar` > 0 dan pengguna menyetujuinya.
    """
    kata = (keyword or "").strip()
    if not kata:
        kata = (config.keywords_riset or ["inventory"])[0]
    halaman = max(1, min(int(max_pages or 1), MAKS_HALAMAN_RISET))
    tahap: List[tuple] = []

    def catat(nama: str, lulus: bool, keterangan: str) -> None:
        tahap.append((nama, bool(lulus), keterangan))
        warna = "green" if lulus else "red"
        console.print(
            f"[{warna}]{'OK' if lulus else 'GAGAL'}[/] {nama} — {keterangan}"
        )

    kandidat: List[Dict] = []
    cloudflare = False

    console.print(
        f"[bold blue]PERIKSA GLINTS[/] — kata kunci '{kata}', "
        f"muat sampai {halaman} kali"
    )

    # ---------- Tahap 1 & 2: buka pencarian, baca kartu, saring ----------
    bot = GlintsBot()
    try:
        bot.init_browser()
    except Exception as exc:
        catat("1. Baca kartu", False, f"Chrome gagal dibuka: {exc}")
        catat("2. Saring kandidat", False, "dilewati (Chrome gagal dibuka)")
    else:
        try:
            bot.buka_pencarian(kata)
            judul = (bot.driver.title or "").strip()
            cloudflare = bot.kena_cloudflare()

            if cloudflare:
                catat(
                    "1. Baca kartu", False,
                    "halaman verifikasi Cloudflare — jalankan chrome-debug.bat "
                    "lalu set-env CHROME_DEBUG_PORT=9222",
                )
            else:
                mentah = bot._kartu_mentah()
                kartu = [j for j in (rapikan_kartu(m) for m in mentah) if j]
                cadangan = 0 if kartu else len(bot._kartu_fallback())
                berlogo = sum(1 for j in kartu if j.get("has_logo"))
                if len(kartu) >= 5:
                    catat(
                        "1. Baca kartu", True,
                        f"{len(kartu)} kartu ({berlogo} berlogo) · "
                        f"judul '{judul[:40]}'",
                    )
                elif cadangan >= 5:
                    catat(
                        "1. Baca kartu", True,
                        f"pembaca utama 0 kartu, cadangan {cadangan} tautan",
                    )
                else:
                    catat(
                        "1. Baca kartu", False,
                        f"hanya {len(kartu)} kartu / {cadangan} tautan cadangan",
                    )

                if not bot.sudah_login():
                    console.print(
                        "[yellow]Catatan: login Glints belum terdeteksi — "
                        "lamaran bisa gagal. Jalankan login dulu.[/]"
                    )
        except ChromeTertutup as exc:
            catat("1. Baca kartu", False, f"Chrome tertutup: {exc}")
        except Exception as exc:
            catat("1. Baca kartu", False, f"galat: {exc}")

        if cloudflare:
            catat("2. Saring kandidat", False, "dilewati (Cloudflare)")
        else:
            try:
                lowongan = kumpulkan_lowongan(bot, [kata], halaman)
                kandidat = pilih_kandidat(lowongan, batas=10)
                if not lowongan:
                    catat("2. Saring kandidat", False, "0 lowongan terkumpul")
                elif not kandidat:
                    catat(
                        "2. Saring kandidat", False,
                        f"{len(lowongan)} terbaca, 0 lolos saringan",
                    )
                else:
                    tanpa_logo = sum(
                        1 for j in kandidat if not j.get("has_logo")
                    )
                    url = [str(j.get("url") or "") for j in kandidat]
                    dobel = len(url) - len(set(url))
                    catatan = (
                        f"{len(kandidat)} kandidat · "
                        f"{len(kandidat) - tanpa_logo} berlogo · {dobel} duplikat"
                    )
                    if tanpa_logo:
                        catatan += f" · {tanpa_logo} tanpa logo (tidak disaring)"
                    catat(
                        "2. Saring kandidat",
                        dobel == 0,
                        catatan,
                    )
            except Exception as exc:
                catat("2. Saring kandidat", False, f"galat: {exc}")
    finally:
        bot.tutup()

    # ---------- Tahap 3: simulasi alur lamaran (tanpa Chrome) ----------
    try:
        import simulasi_glints

        catat(
            "3. Simulasi alur lamaran",
            bool(simulasi_glints.jalankan()),
            "semua skenario sesuai harapan",
        )
    except Exception as exc:
        catat("3. Simulasi alur lamaran", False, f"galat: {exc}")

    # ---------- Tahap 4 & 5: kirim lamaran uji (opsional) ----------
    tujuan = max(0, int(lamar or 0))
    if tujuan <= 0:
        console.print(
            "[dim]Tahap kirim lamaran dilewati. Tambahkan "
            "--lamar 3 untuk menguji pengiriman sungguhan.[/]"
        )
    elif ya or _setuju_lamar(tujuan, kandidat):
        try:
            laporan = jalankan_glints(
                max_pages=1, keywords=[kata], batas=tujuan
            )
            terkirim = int(laporan.get("dilamar", 0))
            sudah = int(laporan.get("sudah", 0))
            catat(
                "4. Kirim lamaran uji",
                terkirim > 0 or sudah > 0,
                f"{terkirim} terkirim · {sudah} sudah pernah · "
                f"{int(laporan.get('gagal', 0))} gagal · "
                f"{int(laporan.get('perlu_manual', 0))} perlu manual",
            )
        except Exception as exc:
            catat("4. Kirim lamaran uji", False, f"galat: {exc}")
    else:
        console.print("[yellow]Uji kirim lamaran dibatalkan.[/]")

    # ---------- Tahap 6: catatan database ----------
    try:
        statistik = db.get_stats()
        catat(
            "5. Catatan database", True,
            f"hari ini {db.get_today_apply_count()} lamaran · "
            f"total dilamar {statistik.get('total_applied', '?')}",
        )
    except Exception as exc:
        catat("5. Catatan database", False, f"galat: {exc}")

    gagal = [nama for nama, lulus, _ in tahap if not lulus]
    print()
    if gagal:
        console.print(
            f"[bold red]{len(gagal)} tahap gagal:[/] " + ", ".join(gagal)
        )
        if cloudflare:
            console.print(
                "[yellow]Langkah berikut:[/] jalankan chrome-debug.bat, "
                "selesaikan verifikasi, lalu set-env CHROME_DEBUG_PORT=9222 "
                "dan ulangi glints cek."
            )
        else:
            console.print(
                "[yellow]Langkah berikut:[/] jalankan glints diagnosa, lalu "
                "kirim berkas debug/ terbaru."
            )
        return False

    console.print("[bold green]Semua tahap yang dijalankan lulus.[/] Glints siap.")
    return True
