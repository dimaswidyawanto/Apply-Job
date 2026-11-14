"""Pembungkus Selenium untuk membuka JobStreet dan membaca kartu lowongan.

Program ini tidak mengirim lamaran otomatis: halaman lowongan hanya dibuka
agar pengguna meninjau dan mengirim lamaran sendiri di browser.
"""

import contextlib
import hashlib
import re
import time
from urllib.parse import urldefrag, urlencode, urljoin

from rich.console import Console
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import teks as teks_modul
from auto_apply import ApplyResult, AutoApplier
from browser import buka_chrome, tutup_chrome
from config import config
from database import db

console = Console()

CARD_SELECTORS = (
    "article",
    "[data-automation='normalJob']",
    "[data-testid='job-card']",
)

# Badge "Applied/Anda sudah melamar" pada kartu hasil pencarian.
APPLIED_CARD_SELECTORS = (
    "[data-automation='jobCardAppliedBadge']",
    "[data-automation*='applied']",
    "[data-testid*='applied']",
)

# Penanda logo perusahaan pada kartu lowongan JobStreet.
LOGO_SELECTORS = (
    "[data-automation*='logo']",
    "[data-testid*='logo']",
    "img[alt*='logo' i]",
)

# Kata yang menunjukkan gambar itu ikon/placeholder, bukan logo perusahaan.
KATA_BUKAN_LOGO = (
    "icon",
    "ikon",
    "sprite",
    "pixel",
    "placeholder",
    "spacer",
    "flag",
    "bendera",
    "avatar-default",
)

APPLIED_CARD_TEXTS = {
    "applied",
    "anda sudah melamar",
    "you applied",
    "telah melamar",
    "sudah dilamar",
    "sudah pernah melamar",
}

ALREADY_APPLIED_MARKERS = (
    "[data-automation='job-detail-applied-badge']",
    "[data-automation='appliedBadge']",
    "[data-testid='applied-badge']",
)


def _norm_teks(teks: str) -> str:
    """Huruf kecil tanpa tanda baca, untuk membandingkan nama perusahaan.

    Isinya kini satu tempat dengan `jawaban` lewat `teks.kunci_nama()`
    (audit E-12); nama lama dipertahankan supaya pemanggil lama tetap jalan.
    """
    return teks_modul.kunci_nama(teks)


def logo_perusahaan(
    alt: str = "", src: str = "", penanda: str = "", perusahaan: str = ""
) -> bool:
    """Menilai apakah satu gambar pada kartu lowongan adalah logo perusahaan.

    Dipisah dari Selenium supaya bisa diuji tanpa membuka browser. Aturannya
    berlapis karena JobStreet dapat mengubah penanda HTML-nya:

    1. penanda/atribut memuat "logo" (data-automation, data-testid, alt);
    2. gambar yang jelas ikon/placeholder ditolak;
    3. URL gambar memuat "logo"/"brand";
    4. teks alternatif gambar memuat nama perusahaan.
    """
    alt = (alt or "").strip()
    src = (src or "").strip()
    penanda = (penanda or "").strip()

    if not alt and not src and not penanda:
        return False

    gabungan = f"{alt} {src} {penanda}".lower()

    if "logo" in penanda.lower() or "logo" in alt.lower():
        return True

    if any(kata in gabungan for kata in KATA_BUKAN_LOGO):
        return False

    if "logo" in src.lower() or "brand" in src.lower():
        return True

    nama_perusahaan = _norm_teks(perusahaan)
    nama_alt = _norm_teks(alt)

    return bool(
        nama_perusahaan
        and len(nama_alt) >= 3
        and (nama_perusahaan in nama_alt or nama_alt in nama_perusahaan)
    )


class JobStreetBot:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.login_expired = False

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------
    def init_browser(self):
        """Membuka Chrome. Mode headless mengikuti HEADLESS_MODE di .env."""
        console.print("[bold blue]Membuka Chrome...[/]")

        self.driver = buka_chrome(label="JobStreet")

        detik = max(3, int(getattr(config, "search_wait", 20) or 20))
        self.wait = WebDriverWait(self.driver, detik)
        console.print("[bold green]Chrome siap.[/]")

    def _has_session_cookie(self) -> bool:
        """Ada cookie sesi JobStreet? Dipakai sebagai bukti sudah login."""
        try:
            cookies = self.driver.get_cookies() or []
        except Exception:
            return False

        penanda = ("session", "seeker", "auth", "token", "logged")

        for cookie in cookies:
            name = str(cookie.get("name", "")).lower()
            domain = str(cookie.get("domain", "")).lower()

            if "jobstreet" not in domain:
                continue

            if any(kata in name for kata in penanda):
                return True

        return False

    def _login_status(self) -> bool | None:
        """True = sudah login, False = belum, None = tidak pasti."""
        for selector in (
            "a[data-automation='signIn']",
            "button[data-automation='signIn']",
            "a[href*='/signin']",
            "a[href*='/login']",
        ):
            if any(
                self._visible(element)
                for element in self._find_elements(selector)
            ):
                return False

        for selector in (
            "[data-automation='accountMenu']",
            "[data-automation='userMenu']",
            "[data-automation*='account']",
            "a[href*='/profile']",
        ):
            if any(
                self._visible(element)
                for element in self._find_elements(selector)
            ):
                return True

        # Beberapa halaman tidak menampilkan menu akun secara eksplisit;
        # cookie sesi yang masih ada cukup jadi bukti.
        if self._has_session_cookie():
            return True

        return None

    def _find_elements(self, selector: str) -> list:
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            return []

    @staticmethod
    def _visible(element) -> bool:
        try:
            return element.is_displayed()
        except Exception:
            return False

    def login(self) -> bool:
        """Memakai sesi tersimpan; bila belum ada, menunggu login di Chrome.

        Tidak ada tombol Enter: program memeriksa sendiri sampai login
        terdeteksi (cookie sesi / menu akun muncul).
        """
        if not self.driver:
            console.print("[bold red]Browser belum dibuka.[/]")
            return False

        try:
            self.driver.get(config.base_url)
            time.sleep(2)

            if self._login_status() is True:
                console.print(
                    "[bold green]Sudah login (sesi tersimpan di profil "
                    "Chrome).[/]"
                )
                return True

            if not config.login_wait:
                console.print(
                    "[bold red]Belum login dan LOGIN_WAIT mati. "
                    "Jalankan sekali dengan LOGIN_WAIT=true untuk login.[/]"
                )
                return False

            console.print(
                "\n[bold cyan]Silakan login di jendela Chrome. Program "
                "menunggu otomatis — tidak perlu menekan apa pun di "
                "terminal.[/]"
            )

            if config.headless:
                console.print(
                    "[yellow]HEADLESS_MODE aktif sehingga jendela Chrome "
                    "tidak terlihat. Set HEADLESS_MODE=false untuk login.[/]"
                )

            batas = time.time() + config.login_timeout
            putaran = 0

            while time.time() < batas:
                time.sleep(3)
                putaran += 1

                if self._login_status() is True:
                    console.print(
                        "[bold green]Login terdeteksi. Melanjutkan...[/]"
                    )
                    time.sleep(1)
                    return True

                if putaran % 5 == 0:
                    sisa = max(0, int(batas - time.time()))
                    console.print(
                        f"[dim]Masih menunggu login di Chrome "
                        f"({sisa} detik lagi)...[/]"
                    )

            console.print(
                "[bold red]Batas waktu login habis. Jalankan ulang program, "
                "atau naikkan LOGIN_TIMEOUT di .env.[/]"
            )
            return False

        except KeyboardInterrupt:
            console.print("\n[yellow]Login dibatalkan.[/]")
            return False

        except Exception as exc:
            console.print(f"[bold red]Gagal membuka JobStreet: {exc}[/]")
            return False

    # ------------------------------------------------------------------
    # Pencarian
    # ------------------------------------------------------------------
    def search_jobs(
        self, keyword: str, page: int = 1, location: str | None = None
    ) -> list[dict]:
        """Membuka hasil pencarian dan membaca lowongan yang dapat dikenali."""
        jobs: list[dict] = []
        seen_urls = set()
        seen_ids = set()

        if not self.driver:
            console.print("[bold red]Browser belum dibuka.[/]")
            return jobs

        try:
            # Lokasi bisa berbeda per pencarian (mendukung banyak kota).
            lokasi = (location or config.location or "").strip()
            params = {"keywords": keyword}

            if lokasi:
                params["where"] = lokasi

            # ListedDate = urutkan dari lowongan yang paling baru diposting.
            if config.sort_mode:
                params["sortmode"] = config.sort_mode

            if config.max_age_days > 0:
                params["daterange"] = str(config.max_age_days)

            if page > 1:
                params["page"] = str(page)

            url = f"{config.search_url}?{urlencode(params)}"

            console.print(
                f"[bold cyan]Mencari: {keyword} — {lokasi or 'semua lokasi'} "
                f"— halaman {page}[/]"
            )
            detik_tunggu = max(
                3, int(getattr(config, "search_wait", 20) or 20)
            )
            self.driver.get(url)

            try:
                self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ", ".join(CARD_SELECTORS))
                    )
                )
            except TimeoutException:
                console.print(
                    f"[yellow]Kartu lowongan tidak muncul dalam {detik_tunggu} detik. "
                    "Mungkin halaman masih memuat atau struktur website "
                    "berubah.[/]"
                )

            time.sleep(1)

            cards = []
            for selector in CARD_SELECTORS:
                found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    cards.extend(found)

            for card in cards:
                try:
                    job = self._parse_job_card(card)
                    if not job:
                        continue

                    if job["url"] in seen_urls or job["job_id"] in seen_ids:
                        continue

                    seen_urls.add(job["url"])
                    seen_ids.add(job["job_id"])
                    jobs.append(job)

                except Exception:
                    continue

            if jobs:
                console.print(f"   Terbaca {len(jobs)} lowongan.")
            else:
                console.print(
                    "[yellow]Tidak ada lowongan yang berhasil dibaca. "
                    "Periksa halaman Chrome; struktur website mungkin berubah.[/]"
                )
                console.print(f"[dim]Halaman pencarian: {url}[/]")

        except Exception as exc:
            console.print(f"[bold red]Gagal membaca hasil pencarian: {exc}[/]")

        return jobs

    def _logo_card(self, card, company: str = "") -> tuple[bool, str]:
        """Cari logo perusahaan pada satu kartu lowongan.

        Kembalikan (ada_logo, keterangan) — keterangan dipakai perintah
        `cek-logo` agar deteksi bisa diperiksa dengan data nyata.
        """
        for selector in LOGO_SELECTORS:
            try:
                elemen = card.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue

            for el in elemen:
                if not self._visible(el):
                    continue

                alt = el.get_attribute("alt") or (el.text or "")
                src = el.get_attribute("src") or ""
                penanda = " ".join(
                    bagian
                    for bagian in (
                        el.get_attribute("data-automation"),
                        el.get_attribute("data-testid"),
                        el.get_attribute("class"),
                    )
                    if bagian
                )

                if logo_perusahaan(alt, src, penanda, company):
                    return True, f"penanda '{penanda.strip()[:40]}'"

        try:
            gambar = card.find_elements(By.TAG_NAME, "img")
        except Exception:
            gambar = []

        for img in gambar:
            if not self._visible(img):
                continue

            alt = img.get_attribute("alt") or ""
            src = img.get_attribute("src") or ""

            if logo_perusahaan(alt, src, "", company):
                return True, f"<img alt='{alt.strip()[:30]}'>"

        return False, f"{len(gambar)} gambar tanpa logo"

    def _parse_job_card(self, card) -> dict | None:
        """Membaca satu kartu lowongan. Kartu tanpa judul/URL dilewati."""
        links = self._collect_job_links(card)

        title = ""
        job_url = ""

        for link in links:
            href = link.get_attribute("href")
            if not href:
                continue

            candidate_title = self._read_link_title(link)
            if not candidate_title:
                continue

            title = candidate_title
            job_url = urldefrag(
                urljoin(self.driver.current_url, href)
            )[0]
            break

        # Jangan membuat atau memproses lowongan dengan judul kosong.
        if not title or not job_url:
            return None

        company = self._read_card_value(
            card,
            [
                "[data-automation='jobCompany']",
                "[data-automation*='jobCompany']",
            ],
        )

        location = self._read_card_value(
            card,
            [
                "[data-automation='jobLocation']",
                "[data-automation*='jobLocation']",
            ],
        )

        salary = self._read_card_value(
            card,
            [
                "[data-automation='jobSalary']",
                "[data-automation*='jobSalary']",
            ],
        )

        date_posted = self._read_card_value(
            card,
            [
                "[data-automation='jobListingDate']",
                "time",
            ],
        )

        try:
            description = (card.text or "").strip()
        except Exception:
            description = ""

        has_logo, info_logo = self._logo_card(card, company)

        return {
            "has_logo": has_logo,
            "logo_src": info_logo,
            "job_id": self._extract_job_id(job_url),
            "title": title,
            "company": company or "Tidak diketahui",
            "location": location,
            "salary": salary or "Tidak disebutkan",
            "description": description,
            "url": job_url,
            "date_posted": date_posted,
            "age_days": self._parse_listing_age(date_posted),
            "applied": self._card_is_applied(card),
        }

    @staticmethod
    def _card_is_applied(card) -> bool:
        """Apakah kartu lowongan sudah berlabel Applied / Anda sudah melamar."""
        for selector in APPLIED_CARD_SELECTORS:
            try:
                elements = card.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue

            for element in elements:
                try:
                    if element.is_displayed():
                        return True
                except Exception:
                    continue

        try:
            text = card.text or ""
        except Exception:
            text = ""

        baris = {
            " ".join(line.split()).strip().lower()
            for line in text.splitlines()
            if line.strip()
        }

        return bool(baris & APPLIED_CARD_TEXTS)

    @staticmethod
    def _parse_listing_age(text: str) -> int | None:
        """Mengubah label tanggal ("Hari ini", "3 hari yang lalu") jadi umur hari."""
        value = " ".join(str(text or "").split()).lower()

        if not value:
            return None

        if any(word in value for word in ("hari ini", "today", "baru", "just now")):
            return 0

        if any(word in value for word in ("kemarin", "yesterday")):
            return 1

        if "+" in value and any(word in value for word in ("hari", "day")):
            return 30

        match = re.search(r"(\d+)\s*(?:jam|hour|h)\b", value)
        if match:
            return 0

        match = re.search(r"(\d+)\s*(?:hari|day|d)\b", value)
        if match:
            return int(match.group(1))

        match = re.search(r"(\d+)\s*(?:minggu|week|w)\b", value)
        if match:
            return int(match.group(1)) * 7

        match = re.search(r"(\d+)\s*(?:bulan|month|mo)\b", value)
        if match:
            return int(match.group(1)) * 30

        return None

    @staticmethod
    def _collect_job_links(card) -> list:
        selectors = (
            "a[data-automation='jobTitle']",
            "a[data-automation*='jobTitle']",
            "h3 a",
            "a[href*='/job/']",
            "a[href*='/job-']",
        )

        links = []
        seen = set()

        for selector in selectors:
            try:
                elements = card.find_elements(By.CSS_SELECTOR, selector)
            except Exception:
                continue

            for element in elements:
                if element.id in seen:
                    continue
                seen.add(element.id)
                links.append(element)

        return links

    @staticmethod
    def _read_link_title(link) -> str:
        candidates = [
            link.text,
            link.get_attribute("aria-label"),
            link.get_attribute("title"),
            link.get_attribute("textContent"),
        ]

        return next(
            (
                value.strip()
                for value in candidates
                if value and value.strip()
            ),
            "",
        )

    @staticmethod
    def _read_card_value(card, selectors: list[str]) -> str:
        for selector in selectors:
            try:
                element = card.find_element(By.CSS_SELECTOR, selector)
                value = (
                    element.text
                    or element.get_attribute("textContent")
                    or ""
                )
                value = value.strip()
                if value:
                    return value
            except NoSuchElementException:
                continue
            except Exception:
                continue

        return ""

    @staticmethod
    def _extract_job_id(url: str) -> str:
        """Membuat ID stabil agar lowongan yang sama tidak berubah ID."""
        match = re.search(r"/job(?:/|-)(\d+)", url, re.IGNORECASE)

        if match:
            return match.group(1)

        query_id = re.search(r"[?&]id=(\d+)", url)
        if query_id:
            return query_id.group(1)

        clean_url = url.split("?", 1)[0].rstrip("/")
        return hashlib.sha256(clean_url.encode("utf-8")).hexdigest()[:24]

    # ------------------------------------------------------------------
    # Meninjau / mencatat lamaran
    # ------------------------------------------------------------------
    def _is_already_applied_page(self) -> bool:
        for selector in ALREADY_APPLIED_MARKERS:
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
            except Exception:
                continue

        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            page_text = (body.text or "").lower()
        except Exception:
            return False

        markers = (
            "anda sudah melamar",
            "sudah pernah melamar",
            "you have already applied",
            "application submitted",
        )
        return any(marker in page_text for marker in markers)

    def apply_job(self, job: dict) -> ApplyResult:
        """Melamar satu lowongan: otomatis bila AUTO_APPLY aktif, atau manual."""
        title = (job.get("title") or "").strip()
        job_url = (job.get("url") or "").strip()
        job_id = str(job.get("job_id") or "").strip()

        if not title or not job_url:
            console.print(
                "[yellow]Lowongan dilewati karena judul atau URL tidak terbaca.[/]"
            )
            return ApplyResult(False, "error", "Judul atau URL tidak terbaca")

        if not job_id:
            job_id = self._extract_job_id(job_url)
            job["job_id"] = job_id

        if db.is_already_applied(job_id):
            return ApplyResult(False, "already_applied", "Sudah tercatat dilamar")

        if config.auto_apply:
            return self._apply_automatically(job, job_id)

        return self._apply_manually(job, job_id)

    @staticmethod
    def _record(job_id: str, status: str, notes: str):
        try:
            db.record_application(job_id, status, notes)
        except Exception as exc:
            console.print(f"[yellow]Gagal mencatat lamaran: {exc}[/]")

    def _apply_automatically(self, job: dict, job_id: str) -> ApplyResult:
        title = (job.get("title") or "").strip()
        console.print(f"\n[bold magenta]{title}[/] [cyan](otomatis)[/]")

        result = AutoApplier(self.driver, self.wait).apply(job)

        if result.status == "applied":
            self._record(job_id, "applied", result.reason or "Dikirim otomatis")
            console.print("[bold green]Lamaran terkirim otomatis.[/]")

        elif result.status == "already_applied":
            self._record(job_id, "already_applied", result.reason)

        elif result.status == "login_required":
            self._record(job_id, "error", result.reason)
            self.login_expired = True
            console.print(
                "[bold red]Sesi login JobStreet sudah habis. Berhenti; "
                "jalankan sekali lagi tanpa --no-login-wait untuk login.[/]"
            )

        elif result.status == "manual_required":
            self._record(job_id, "manual_required", result.reason)
            console.print(f"[yellow]Dilewati: {result.reason}[/]")

        else:
            self._record(job_id, "error", result.reason)
            console.print(
                f"[bold red]Gagal melamar otomatis: {result.reason}[/]"
            )

        return result

    def _apply_manually(self, job: dict, job_id: str) -> ApplyResult:
        """Membuka halaman lowongan agar pengguna melamar sendiri."""
        title = (job.get("title") or "").strip()
        job_url = (job.get("url") or "").strip()

        try:
            self.driver.get(job_url)
            self.wait.until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)

            if self._is_already_applied_page():
                self._record(
                    job_id,
                    "already_applied",
                    "Halaman menandai lowongan ini sudah pernah dilamar",
                )
                console.print(
                    f"[yellow]JobStreet menandai '{title}' sudah pernah "
                    "dilamar. Dicatat dan dilewati.[/]"
                )
                return ApplyResult(False, "already_applied", "Sudah pernah dilamar")

            # Mode manual: isian yang pengguna lakukan di halaman ini juga
            # diingat, supaya lamaran berikutnya terisi otomatis.
            pencatat = AutoApplier(self.driver, self.wait)
            try:
                potret_awal = pencatat._potret_jawaban()
            except Exception:
                potret_awal = {}

            console.print(f"\n[bold magenta]{title}[/]")
            console.print(f"Perusahaan: {job.get('company', 'Tidak diketahui')}")
            console.print(f"URL: {job_url}")
            console.print(
                "[cyan]Tinjau persyaratan di Chrome. "
                "Jika cocok, lakukan Apply dan Submit sendiri.[/]"
            )

            answer = input(
                "Setelah selesai meninjau, tekan Enter "
                "(ketik y bila lamaran sudah terkirim): "
            ).strip().lower()

            with contextlib.suppress(Exception):
                pencatat._rekam_jawaban_pengguna(potret_awal)

            if answer in ("y", "ya", "yes"):
                self._record(
                    job_id,
                    "applied",
                    "Dikirim manual dan dikonfirmasi pengguna",
                )
                console.print("[bold green]Lamaran dicatat sebagai terkirim.[/]")
                return ApplyResult(True, "applied", "Dikonfirmasi manual")

            self._record(
                job_id,
                "skipped",
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
            self._record(job_id, "error", str(exc))
            return ApplyResult(False, "error", str(exc))

    def close(self):
        if self.driver:
            # Pesan hanya dicetak bila Chrome benar-benar ditutup; dulu selalu
            # "Chrome ditutup." walau Chrome dibiarkan hidup, sehingga sesi
            # berikutnya gagal membuka profil yang masih terkunci.
            benar_tertutup = tutup_chrome(self.driver)
            self.driver = None
            self.wait = None

            if benar_tertutup:
                console.print("[blue]Chrome ditutup.[/]")
