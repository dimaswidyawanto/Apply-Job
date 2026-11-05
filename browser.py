"""Membuka Chrome dengan beberapa percobaan agar tahan gagal.

Galat seperti ``session not created: DevToolsActivePort file doesn't exist``
biasanya berarti Chrome tidak bisa memakai profilnya: profilnya masih dipakai
Chrome lain, ada sisa proses Chrome yang macet, atau profilnya rusak. Urutan
percobaan di modul ini:

1. profil tersimpan (sesi login ikut),
2. profil tersimpan setelah berkas kunci sisa Chrome dibersihkan,
3. profil sementara (membuktikan profilnya yang bermasalah),
4. tanpa mode headless (bila HEADLESS_MODE=true).

Semua percobaan dicatat supaya penyebabnya jelas, dan bila semuanya gagal
pesan galatnya berisi langkah perbaikan yang bisa langsung dijalankan.
"""

import contextlib
import shutil
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from config import config

console = Console()

# Berkas kunci yang ditinggalkan Chrome saat prosesnya tidak berhenti rapi.
BERKAS_KUNCI = (
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
    "lockfile",
    "DevToolsActivePort",
)

# Galat yang memang perlu bantuan webdriver-manager (driver tidak cocok).
TANDA_DRIVER_MANUAL = (
    "executable needs to be in path",
    "cannot find chrome binary",
    "this version of chromedriver only supports",
    "only supports chrome version",
    "chromedriver version",
)


def bersihkan_kunci_profil(profile: Path) -> List[str]:
    """Hapus berkas kunci sisa Chrome yang mati.

    Kembalikan daftar nama berkas yang dihapus (kosong bila tidak ada).
    """
    dihapus: List[str] = []

    if not profile.exists():
        return dihapus

    for nama in BERKAS_KUNCI:
        berkas = profile / nama
        if not berkas.exists() and not berkas.is_symlink():
            continue

        with contextlib.suppress(Exception):
            if berkas.is_dir() and not berkas.is_symlink():
                shutil.rmtree(berkas)
            else:
                berkas.unlink()
            dihapus.append(nama)

    return dihapus


def sembunyikan_otomasi(driver):
    """Kurangi jejak otomatisasi (membantu situs di balik Cloudflare)."""
    skrip = (
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        "Object.defineProperty(navigator, 'languages', "
        "{get: () => ['id-ID', 'en-US', 'en']});"
        "window.chrome = window.chrome || {runtime: {}};"
    )

    with contextlib.suppress(Exception):
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument", {"source": skrip}
        )

    versi = ""
    with contextlib.suppress(Exception):
        versi = str(driver.capabilities.get("browserVersion") or "").strip()

    with contextlib.suppress(Exception):
        driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"Chrome/{versi or '131.0.0.0'} Safari/537.36"
                ),
                "acceptLanguage": "id-ID,id;q=0.9,en;q=0.8",
            },
        )

    return driver


def tempel_chrome(port: int):
    """Menempel ke Chrome yang sudah berjalan dengan port debug."""
    options = Options()
    options.debugger_address = f"127.0.0.1:{int(port)}"
    return webdriver.Chrome(options=options)


def _opsi(headless: bool, profile: Optional[Path]) -> Options:
    """Opsi Chrome yang dipakai semua percobaan."""
    options = Options()
    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-dev-shm-usage")
    # Port acak: menghindari bentrok bila ada Chrome lain di port debug.
    options.add_argument("--remote-debugging-port=0")
    with contextlib.suppress(Exception):
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        options.add_experimental_option("useAutomationExtension", False)

    if getattr(config, "chrome_binary", ""):
        with contextlib.suppress(Exception):
            options.binary_location = config.chrome_binary

    if profile is not None:
        with contextlib.suppress(Exception):
            profile.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--profile-directory=Default")

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    else:
        options.add_argument("--start-maximized")

    return options


def _perlu_driver_manual(pesan: str) -> bool:
    teks = str(pesan or "").lower()
    return any(tanda in teks for tanda in TANDA_DRIVER_MANUAL)


def _buka(options: Options):
    """Buka Chrome; pakai webdriver-manager hanya bila perlu."""
    try:
        return webdriver.Chrome(options=options)
    except Exception as pertama:
        ringkas = str(pertama).splitlines()[0][:200]
        console.print(f"[dim]Percobaan driver bawaan gagal: {ringkas}[/]")

        if not _perlu_driver_manual(str(pertama)):
            raise

        from webdriver_manager.chrome import ChromeDriverManager

        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)


def _pesan_gagal(detail: str) -> str:
    return (
        "Chrome tidak bisa dibuka setelah beberapa percobaan.\n"
        "Coba berurutan:\n"
        "  1. Tutup SEMUA jendela Chrome. Buka Task Manager (Ctrl+Shift+Esc), "
        "cari chrome.exe yang tersisa, lalu End task.\n"
        "  2. Jalankan: python cli.py perbaiki-chrome  "
        "(memakai profil Chrome baru; Anda perlu login sekali lagi).\n"
        "  3. Bila Chrome baru saja diperbarui: tutup Chrome, lalu jalankan "
        "lagi — Selenium mengunduh driver yang cocok.\n"
        "  4. Pastikan antivirus/firewall tidak memblokir Chrome yang "
        "dijalankan program.\n"
        "  5. Bila situs menampilkan 'Just a moment...' (Cloudflare): "
        "jalankan chrome-debug.bat, selesaikan verifikasi di jendela itu, "
        "lalu jalankan: python cli.py set-env CHROME_DEBUG_PORT=9222\n"
        f"Detail terakhir: {detail}"
    )


def buka_chrome(
    profile_dir: str = "",
    use_profile: bool = True,
    headless: Optional[bool] = None,
    label: str = "Chrome",
):
    """Buka Chrome dan kembalikan driver-nya.

    Melempar RuntimeError berisi langkah perbaikan bila semua percobaan gagal.
    """
    mode_headless = config.headless if headless is None else headless
    profil: Optional[Path] = None

    if use_profile:
        teks_profil = str(profile_dir or config.profile_dir or "").strip()
        if teks_profil:
            profil = Path(teks_profil).expanduser()

    percobaan = []

    if profil is not None:
        percobaan.append(("profil tersimpan", profil, mode_headless, False))
        percobaan.append(
            ("profil tersimpan (kunci dibersihkan)", profil, mode_headless, True)
        )
        percobaan.append(
            (
                "profil cadangan (baru, sesi login perlu diulang)",
                Path(str(profil) + "-baru"),
                mode_headless,
                False,
            )
        )
        percobaan.append(("profil sementara", None, mode_headless, False))
    else:
        percobaan.append(("profil sementara", None, mode_headless, False))

    if mode_headless:
        percobaan.append(("tanpa mode headless", profil, False, True))

    galat_terakhir = "tidak diketahui"

    # 0. Menempel ke Chrome yang sudah dibuka pengguna (paling ampuh untuk
    #    situs di balik Cloudflare).
    port = int(getattr(config, "chrome_debug_port", 0) or 0)
    if port:
        console.print(
            f"[cyan]Menempel ke Chrome yang berjalan di port {port}...[/]"
        )
        try:
            return sembunyikan_otomasi(tempel_chrome(port))
        except Exception as exc:
            console.print(
                f"[yellow]Gagal menempel ke port {port}: "
                f"{str(exc).splitlines()[0][:160]}[/]"
            )
            console.print(
                "[yellow]Jalankan chrome-debug.bat lebih dulu (Chrome harus "
                "sudah terbuka), atau set CHROME_DEBUG_PORT=0 untuk memakai "
                "Chrome biasa.[/]"
            )

    for nomor, (nama, path_profil, headless_ke, bersihkan) in enumerate(
        percobaan, start=1
    ):
        console.print(
            f"[dim]Percobaan {nomor}/{len(percobaan)}: {label} — {nama}[/]"
        )

        if bersihkan and path_profil is not None:
            dihapus = bersihkan_kunci_profil(path_profil)
            if dihapus:
                console.print(
                    "[yellow]Berkas kunci sisa Chrome dihapus: "
                    f"{', '.join(dihapus)}[/]"
                )

        if path_profil is not None:
            console.print(f"[dim]Profil Chrome: {path_profil}[/]")

        try:
            driver = _buka(_opsi(headless_ke, path_profil))
        except Exception as exc:
            galat_terakhir = str(exc).splitlines()[0][:300]
            console.print(f"[yellow]Gagal: {galat_terakhir}[/]")
            continue

        driver = sembunyikan_otomasi(driver)

        if nama == "profil sementara":
            console.print(
                "[yellow]Chrome terbuka TANPA profil tersimpan, jadi sesi "
                "login tidak terbawa. Login sekali di jendela itu, lalu pada "
                "sesi berikutnya tutup semua Chrome lebih dulu agar profil "
                "tersimpan bisa dipakai.[/]"
            )
        elif nama.startswith("profil cadangan"):
            console.print(
                f"[yellow]Profil Chrome lama tidak bisa dipakai; sekarang "
                f"memakai profil baru di {path_profil}. Login sekali di "
                "jendela ini, sesi berikutnya akan tersimpan di profil itu.[/]"
            )
        else:
            console.print(f"[dim]Chrome siap memakai {nama}.[/]")

        return driver

    raise RuntimeError(_pesan_gagal(galat_terakhir))
