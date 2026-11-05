import argparse
import contextlib
import subprocess

from rich.console import Console
from rich.table import Table

from config import MAKS_HALAMAN_RISET, batas_halaman_riset, config
from database import db

console = Console()


def versi_kode() -> str:
    """Commit yang sedang dijalankan — untuk memastikan kode sudah terbaru."""
    try:
        hasil = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if hasil.returncode == 0:
            return hasil.stdout.strip() or "-"
    except Exception:
        pass
    return "-"


def show_stats():
    stats = db.get_stats()
    table = Table(title="Statistik")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    for key, value in stats.items():
        table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)


def uji_lamar(url: str):
    """Uji alur lamaran untuk satu lowongan, tanpa pencarian/filter."""
    from auto_apply import AutoApplier
    from scraper import JobStreetBot

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print(f"[cyan]Lowongan uji:[/] {url}")

    bot = JobStreetBot()
    try:
        bot.init_browser()
        if not bot.login():
            console.print("[bold red]Login belum selesai. Uji dibatalkan.[/]")
            return

        hasil = AutoApplier(bot.driver, bot.wait).apply(
            {"url": url, "title": "lowongan uji"}
        )
    finally:
        with contextlib.suppress(Exception):
            bot.close()

    warna = "green" if hasil.applied else "yellow"
    console.print(
        f"\n[bold {warna}]Status:[/] {hasil.status} — {hasil.reason}"
    )
    if hasil.applied:
        console.print("[bold green]Lamaran terkirim otomatis.[/]")
    else:
        console.print(
            "[dim]Bila perlu, kirim file di folder debug/ (png + txt) untuk "
            "perbaikan selector.[/]"
        )


def cek_logo(limit: int = 10, max_pages: int = 1, keywords: str = ""):
    """Periksa deteksi logo perusahaan pada kartu lowongan JobStreet.

    Menampilkan kartu yang terbaca beserta hasil deteksi dan keterangannya,
    supaya aturan deteksi bisa dicocokkan dengan tampilan situs yang nyata.
    """
    from scraper import JobStreetBot

    daftar_keyword = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    if not daftar_keyword:
        daftar_keyword = list(config.keywords)[:1] or ["inventory"]

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print("[cyan]Situs:[/] JobStreet — pemeriksaan deteksi logo")
    console.print(
        f"[dim]Kata kunci: {', '.join(daftar_keyword)} | halaman: {max_pages} "
        f"| batas tampil: {limit}[/]"
    )

    bot = JobStreetBot()
    terbaca: list[dict] = []

    try:
        bot.init_browser()
        if not bot.login():
            console.print(
                "[bold red]Login belum selesai. Pemeriksaan dibatalkan.[/]"
            )
            return

        for keyword in daftar_keyword:
            for page in range(1, max(1, max_pages) + 1):
                for job in bot.search_jobs(
                    keyword, page, location=config.location
                ):
                    terbaca.append(job)
                    if len(terbaca) >= limit:
                        break
                if len(terbaca) >= limit:
                    break
            if len(terbaca) >= limit:
                break
    finally:
        with contextlib.suppress(Exception):
            bot.close()

    if not terbaca:
        console.print("[yellow]Tidak ada kartu lowongan yang terbaca.[/]")
        return

    table = Table(title="Deteksi logo perusahaan")
    table.add_column("Judul", style="cyan", max_width=38)
    table.add_column("Perusahaan", max_width=24)
    table.add_column("Logo", justify="center")
    table.add_column("Keterangan", style="dim", max_width=34)

    for job in terbaca:
        table.add_row(
            (job.get("title") or "-")[:38],
            (job.get("company") or "-")[:24],
            "[green]ya[/]" if job.get("has_logo") else "[red]tidak[/]",
            (job.get("logo_src") or "-")[:34],
        )

    console.print(table)

    berlogo = sum(1 for job in terbaca if job.get("has_logo"))
    console.print(
        f"[bold]{berlogo}[/] dari [bold]{len(terbaca)}[/] kartu terdeteksi "
        "berlogo perusahaan."
    )

    if berlogo == 0:
        console.print(
            "[yellow]Tidak ada logo terdeteksi sama sekali. Bila di situs "
            "logo memang terlihat, kirimkan tabel di atas agar aturan deteksi "
            "disesuaikan.[/]"
        )

    if config.require_company_logo:
        console.print(
            "[green]REQUIRE_COMPANY_LOGO=true[/] — lowongan tanpa logo "
            "otomatis dilewati saat melamar."
        )
    else:
        console.print(
            "[yellow]REQUIRE_COMPANY_LOGO=false[/] — filter logo belum aktif. "
            "Aktifkan dengan: python cli.py set-env REQUIRE_COMPANY_LOGO=true"
        )


def jalankan_glints(max_pages: int = 0, keywords: str = "", batas: int = 0):
    """Cari, saring, lalu lamar lowongan di Glints."""
    from glints import jalankan_glints as _jalankan

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print("[cyan]Situs:[/] Glints (glints.com)")

    daftar = [k.strip() for k in keywords.split(",") if k.strip()] or None
    try:
        laporan = _jalankan(
            max_pages=max(0, max_pages), keywords=daftar, batas=max(0, batas)
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dihentikan oleh pengguna.[/]")
        return
    except Exception as exc:
        console.print(f"[bold red]Gagal menjalankan Glints:[/] {exc}")
        return

    console.print()
    console.print(
        "[bold]Ringkasan Glints:[/] "
        f"{laporan['dibaca']} terbaca · {laporan['baru']} baru · "
        f"{laporan['dilamar']} terkirim · {laporan['sudah']} sudah dilamar · "
        f"{laporan['perlu_manual']} perlu manual · "
        f"{laporan['dilewati']} dilewati · {laporan['gagal']} gagal · "
        f"{laporan['khusus_aplikasi']} hanya via aplikasi"
    )


def diagnosa_glints_cli(keyword: str = ""):
    """Cetak diagnosa pembacaan kartu Glints."""
    from glints import diagnosa_glints

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    diagnosa_glints(keyword)


def cari_glints(keywords: str = "", max_pages: int = 1, batas: int = 10,
                semuanya: bool = False):
    """Tampilkan lowongan Glints yang layak dilamar beserta URL-nya."""
    from rich.table import Table

    from glints import daftar_kandidat

    kata_kunci = [k.strip() for k in keywords.split(",") if k.strip()] or None
    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")

    try:
        lowongan = daftar_kandidat(
            keywords=kata_kunci,
            max_pages=max(1, max_pages),
            batas=max(1, batas),
            semuanya=semuanya,
        )
    except Exception as exc:
        console.print(f"[bold red]Gagal mencari lowongan Glints:[/] {exc}")
        return

    if not lowongan:
        console.print("[yellow]Tidak ada lowongan yang layak.[/]")
        return

    table = Table(title=f"{len(lowongan)} lowongan layak dilamar")
    table.add_column("#", justify="right")
    table.add_column("Posisi", style="cyan")
    table.add_column("Perusahaan", overflow="fold")
    table.add_column("Gaji")
    table.add_column("Lokasi", overflow="fold")
    table.add_column("Logo", justify="center")
    table.add_column("URL", overflow="fold", style="dim")

    for nomor, job in enumerate(lowongan, start=1):
        table.add_row(
            str(nomor),
            job.get("title", "")[:40],
            (job.get("company") or "-")[:28],
            job.get("salary") or "-",
            (job.get("location") or "-")[:26],
            "[green]ya[/]" if job.get("has_logo") else "[red]tidak[/]",
            job.get("url", ""),
        )

    console.print(table)
    console.print(
        "[dim]Salin salah satu URL untuk: "
        "jalankan.bat glints uji --url \"URL\"[/]"
    )

    berlogo = sum(1 for job in lowongan if job.get("has_logo"))
    console.print(
        f"[bold]{berlogo}[/] dari [bold]{len(lowongan)}[/] kartu terdeteksi "
        "berlogo perusahaan."
    )

    if config.require_company_logo:
        console.print(
            "[green]REQUIRE_COMPANY_LOGO=true[/] — kartu tanpa logo dilewati "
            "saat melamar. Tambahkan --semua untuk melihat kartu yang tersaring."
        )
    else:
        console.print(
            "[yellow]REQUIRE_COMPANY_LOGO=false[/] — filter logo belum aktif "
            "(sama seperti JobStreet)."
        )


def uji_glints_otomatis(keywords: str = "", max_pages: int = 1):
    """Pilih sendiri satu lowongan layak, lalu uji alur lamarannya."""
    from glints import uji_otomatis

    kata_kunci = [k.strip() for k in keywords.split(",") if k.strip()] or None
    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print("[cyan]Mode:[/] uji otomatis (lowongan dipilih sendiri)")

    try:
        job, hasil = uji_otomatis(keywords=kata_kunci, max_pages=max_pages)
    except Exception as exc:
        console.print(f"[bold red]Gagal menguji lowongan:[/] {exc}")
        return

    if job:
        console.print("[cyan]URL[/]", end=" ")
        console.print(str(job.get("url") or ""), soft_wrap=True)

    warna = "green" if hasil.applied else "yellow"
    console.print(f"\n[bold {warna}]Status:[/] {hasil.status} — {hasil.reason}")

    if hasil.applied:
        console.print("[bold green]Lamaran Glints terkirim otomatis.[/]")
    else:
        console.print(
            "[dim]Bila perlu, kirim file di folder debug/ (txt + png) untuk "
            "perbaikan selector.[/]"
        )


def simulasi_glints():
    """Simulasi alur lamaran Glints tanpa Chrome."""
    from simulasi_glints import jalankan

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    jalankan()

def uji_glints(url: str):
    """Uji alur lamaran pada satu lowongan Glints."""
    from glints import uji_glints as _uji

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print(f"[cyan]Lowongan uji:[/] {url}")

    try:
        hasil = _uji(url)
    except Exception as exc:
        console.print(f"[bold red]Gagal menguji lowongan:[/] {exc}")
        return

    warna = "green" if hasil.applied else "yellow"
    console.print(f"\n[bold {warna}]Status:[/] {hasil.status} — {hasil.reason}")
    if hasil.applied:
        console.print("[bold green]Lamaran Glints terkirim otomatis.[/]")
    else:
        console.print(
            "[dim]Bila perlu, kirim file di folder debug/ (png + txt) untuk "
            "perbaikan selector.[/]"
        )


def perbarui_env():
    """Samakan KEYWORDS/TITLE_KEYWORDS di .env dengan daftar terbaru."""
    from pathlib import Path

    from env_tools import perbarui_env as jalan

    hasil = jalan(Path(".env"), Path(".env.example"))

    if hasil["status"] == "contoh_tidak_ada":
        console.print("[bold red].env.example tidak ditemukan.[/]")
        return

    if hasil["status"] == "tidak_ada_kunci":
        console.print("[bold red].env.example tidak memuat KEYWORDS.[/]")
        return

    if hasil["status"] == "sudah_terbaru":
        console.print("[green].env sudah memakai daftar kata kunci terbaru.[/]")
        return

    console.print(
        "[bold green]Kata kunci di .env diperbarui:[/] "
        + ", ".join(hasil["perubahan"])
    )
    if hasil["backup"]:
        console.print(f"[dim]Cadangan file lama: {hasil['backup']}[/]")
    console.print(
        "[dim]Jalankan ulang program agar nilai baru terpakai.[/]"
    )


def simulasi():
    """Uji alur lamaran dengan halaman palsu (tanpa Chrome/internet)."""
    from simulasi import jalankan

    if not jalankan():
        raise SystemExit(1)


def atur_env(pasangan_teks):
    """Ubah nilai tertentu di .env, mis. MAX_APPLY_PER_DAY=500."""
    from pathlib import Path

    from env_tools import atur_nilai, parse_pasangan

    try:
        pasangan = parse_pasangan(pasangan_teks)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/]")
        raise SystemExit(2) from None

    hasil = atur_nilai(Path(".env"), pasangan)

    if hasil["status"] == "sudah_terbaru":
        console.print("[green].env sudah memakai nilai tersebut.[/]")
        return

    console.print(
        "[bold green]Nilai di .env diperbarui:[/] "
        + ", ".join(hasil["perubahan"])
    )
    if hasil["backup"]:
        console.print(f"[dim]Cadangan file lama: {hasil['backup']}[/]")
    console.print("[dim]Jalankan ulang program agar nilai baru terpakai.[/]")


def show_config():
    table = Table(title="Konfigurasi")
    table.add_column("Pengaturan", style="cyan")
    table.add_column("Nilai", style="green")

    table.add_row("Kata kunci", ", ".join(config.keywords))
    table.add_row(
        "Lokasi pencarian",
        ", ".join(config.locations) if config.locations else "(semua)",
    )
    table.add_row(
        "Filter judul minat",
        (
            f"Aktif ({len(config.title_keywords)} kata kunci)"
            if config.require_keyword_match
            else "Tidak aktif"
        ),
    )
    table.add_row(
        "Filter lokasi ketat",
        "Aktif" if config.strict_location else "Tidak aktif",
    )
    table.add_row(
        "Wajib ada logo perusahaan",
        "Aktif (JobStreet & Glints)" if config.require_company_logo
        else "Tidak aktif",
    )
    table.add_row(
        "Pertanyaan pilihan otomatis",
        (
            "Aktif "
            f"(S1, {config.years_experience:g} th, gaji "
            f"{config.expected_salary or 'tidak dijawab'})"
            if config.auto_answer_questions
            else "Tidak aktif"
        ),
    )
    table.add_row("Gaji minimum", f"Rp {config.min_salary:,}")
    table.add_row("Batas pengalaman", f"{config.max_experience} tahun")
    table.add_row(
        "Urutan hasil",
        f"Dari yang terbaru ({config.sort_mode})"
        if config.sort_mode else "Relevansi JobStreet",
    )
    table.add_row(
        "Hanya lowongan baru",
        f"Maksimal {config.max_age_days} hari"
        if config.max_age_days > 0 else "Tanpa batas umur",
    )
    table.add_row("Halaman per kata kunci", str(config.max_pages))
    table.add_row(
        "Riset lowongan",
        f"Maksimal {config.research_max_pages} halaman per kombinasi "
        f"kata kunci & lokasi (batas tetap {MAKS_HALAMAN_RISET}) "
        "— tidak dibatasi 50",
    )
    table.add_row(
        "Kata kunci riset",
        f"{len(config.keywords_riset)} kategori"
        + (
            " (dari RESEARCH_KEYWORDS)"
            if config.research_keywords
            else " (ikut KEYWORDS)"
        ),
    )
    table.add_row(
        "Batas hasil riset",
        str(config.research_max_jobs)
        if config.research_max_jobs > 0
        else "Tanpa batas",
    )
    table.add_row(
        "Urutan pelamaran",
        (
            "Kumpulkan dulu lalu bandingkan — "
            + (
                "posting terbaru dulu"
                if config.rank_by == "newest"
                else "kecocokan tertinggi dulu"
            )
            if config.auto_apply and config.collect_before_apply
            else "Lamar sambil mencari (halaman terbaru dulu)"
        ),
    )
    table.add_row(
        "Batas lamaran per hari",
        (
            str(config.max_apply_per_day)
            if config.max_apply_per_day > 0
            else "Tanpa batas"
        ),
    )
    table.add_row("Jeda antar-lowongan", f"{config.delay_between_apply} detik")
    table.add_row(
        "Waktu tunggu kuesioner",
        f"{config.auto_answer_wait} detik"
        if config.auto_answer_wait > 0
        else "Tidak menunggu (langsung dilewati)",
    )
    table.add_row("Mode browser", "Headless" if config.headless else "Terlihat")
    table.add_row(
        "Mode lamaran",
        "Otomatis" if config.auto_apply else "Tinjau dan kirim manual",
    )
    if config.auto_apply:
        table.add_row(
            "Batas lamaran otomatis/sesi",
            (
                str(config.auto_apply_max_per_session)
                if config.auto_apply_max_per_session > 0
                else "Tanpa batas"
            ),
        )
        table.add_row(
            "Waktu kirim di halaman review",
            f"{config.auto_apply_submit_timeout} detik",
        )
    table.add_row("Versi kode (commit)", versi_kode())
    table.add_row("File database", config.db_path)
    table.add_row(
        "Notifikasi Telegram",
        "Aktif" if config.telegram_token and config.telegram_chat_id
        else "Tidak aktif",
    )

    console.print(table)


def blacklist_company(company: str, reason: str = ""):
    db.add_blacklist(company, reason)
    console.print(f"[green]{company} di-blacklist[/]")
    console.print(
        "[dim]Nama dicocokkan longgar: \"royal abadi\" juga menangkap "
        "\"PT Royal Abadi Sejahtera\", \"PT. ROYAL ABADI SEJAHTERA\", "
        "dst.[/]"
    )


def show_applications(limit: int = 50):
    rows = db.get_recent_applications(limit)

    table = Table(title=f"Riwayat Lamaran ({limit} terakhir)")
    table.add_column("Tanggal", style="cyan", no_wrap=True)
    table.add_column("Posisi", style="white")
    table.add_column("Perusahaan", style="yellow")
    table.add_column("Status", style="green", no_wrap=True)

    if not rows:
        console.print("[dim]Belum ada lamaran yang tercatat.[/]")
        return

    for row in rows:
        table.add_row(
            row["applied_at"][:19],
            row["title"][:40],
            row["company"][:25],
            row["status"],
        )

    console.print(table)


def repair_data():
    report = db.repair_data()

    table = Table(title="Perbaikan Data")
    table.add_column("Perbaikan", style="cyan")
    table.add_column("Jumlah", style="green", justify="right")

    table.add_row("Judul kosong diisi", str(report["empty_titles_fixed"]))
    table.add_row("Perusahaan kosong diisi", str(report["empty_companies_fixed"]))
    table.add_row("Status dinormalkan", str(report["statuses_normalized"]))
    table.add_row(
        "Lamaran ganda dihapus",
        str(report["duplicate_applications_removed"]),
    )

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JobStreet Auto-Apply CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Jalankan pencarian lowongan")
    run_mode = run_parser.add_mutually_exclusive_group()
    run_mode.add_argument(
        "--auto",
        action="store_true",
        help="Kirim lamaran otomatis (tanpa klik manual)",
    )
    run_mode.add_argument(
        "--manual",
        action="store_true",
        help="Buka lowongan untuk ditinjau dan dikirim manual (default)",
    )
    run_parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Hanya lowongan yang diposting dalam N hari terakhir",
    )
    run_parser.add_argument(
        "--locations",
        default=None,
        help="Daftar lokasi dipisah koma, mis. \"Bandung,Jakarta,Tangerang\"",
    )
    run_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Jumlah halaman per kata kunci untuk mode lamar-sambil-mencari "
            "(tidak membatasi riset)"
        ),
    )
    run_parser.add_argument(
        "--riset-pages",
        type=int,
        default=None,
        help=(
            "Halaman riset per kombinasi kata kunci & lokasi, "
            f"maksimal {MAKS_HALAMAN_RISET} (bawaan RESEARCH_MAX_PAGES)"
        ),
    )
    run_parser.add_argument(
        "--headless",
        action="store_true",
        help="Jalankan Chrome tanpa jendela",
    )
    run_parser.add_argument(
        "--profile-dir",
        default=None,
        help="Folder profil Chrome untuk menyimpan sesi login",
    )
    run_parser.add_argument(
        "--no-profile",
        action="store_true",
        help="Pakai profil sementara (harus login ulang setiap sesi)",
    )
    run_parser.add_argument(
        "--no-login-wait",
        action="store_true",
        help="Jangan menunggu Enter saat login; berhenti bila belum login",
    )
    subparsers.add_parser("stats", help="Tampilkan statistik")
    subparsers.add_parser("config", help="Tampilkan konfigurasi aktif")
    subparsers.add_parser("repair", help="Rapikan data lama di database")
    subparsers.add_parser(
        "simulasi",
        help="Uji alur lamaran dengan halaman palsu (tanpa Chrome)",
    )
    subparsers.add_parser(
        "perbarui-env",
        help="Perbarui KEYWORDS/TITLE_KEYWORDS di .env dari .env.example",
    )

    history_parser = subparsers.add_parser(
        "history", help="Tampilkan riwayat lamaran"
    )
    history_parser.add_argument(
        "--limit", type=int, default=50, help="Jumlah baris (default 50)"
    )

    uji_parser = subparsers.add_parser(
        "uji-lamar",
        help="Uji alur lamaran untuk satu URL lowongan (tanpa filter)",
    )
    uji_parser.add_argument("--url", required=True, help="URL lowongan JobStreet")

    logo_parser = subparsers.add_parser(
        "cek-logo",
        help="Periksa deteksi logo perusahaan pada kartu lowongan JobStreet",
    )
    logo_parser.add_argument(
        "--limit", type=int, default=10, help="Jumlah kartu yang ditampilkan"
    )
    logo_parser.add_argument(
        "--max-pages", type=int, default=1, help="Jumlah halaman (default 1)"
    )
    logo_parser.add_argument(
        "--keywords", default="", help="Kata kunci pencarian (pisah koma)"
    )

    env_parser = subparsers.add_parser(
        "set-env",
        help="Ubah nilai di .env, mis. set-env MAX_APPLY_PER_DAY=500",
    )
    env_parser.add_argument(
        "pasangan",
        nargs="+",
        help="Satu atau beberapa KUNCI=nilai",
    )

    glints_parser = subparsers.add_parser(
        "glints", help="Cari & lamar lowongan di Glints"
    )
    glints_sub = glints_parser.add_subparsers(dest="glints_command")

    glints_run = glints_sub.add_parser("run", help="Jalankan pencarian Glints")
    glints_run.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help=(
            "Muat per kata kunci, maksimal "
            f"{MAKS_HALAMAN_RISET} (ikut RESEARCH_MAX_PAGES)"
        ),
    )
    glints_run.add_argument(
        "--keywords", default="", help="Kata kunci dipisah koma (0=bawaan .env)"
    )
    glints_run.add_argument(
        "--limit", type=int, default=0, help="Batas lamaran sesi ini (0=tanpa batas)"
    )

    glints_uji = glints_sub.add_parser(
        "uji",
        help="Uji alur lamaran Glints (tanpa --url: lowongan dipilih sendiri)",
    )
    glints_uji.add_argument(
        "--url", default="", help="URL lowongan Glints (opsional)"
    )
    glints_uji.add_argument(
        "--keywords", default="", help="Kata kunci dipisah koma untuk uji otomatis"
    )
    glints_uji.add_argument(
        "--max-pages", type=int, default=1, help="Halaman per kata kunci (1)"
    )

    glints_cari = glints_sub.add_parser(
        "cari", help="Tampilkan lowongan Glints yang layak + URL-nya"
    )
    glints_cari.add_argument(
        "--keywords", default="", help="Kata kunci dipisah koma (bawaan .env)"
    )
    glints_cari.add_argument(
        "--max-pages", type=int, default=1, help="Halaman per kata kunci (1)"
    )
    glints_cari.add_argument(
        "--limit", type=int, default=10, help="Jumlah lowongan ditampilkan (10)"
    )
    glints_cari.add_argument(
        "--semua",
        action="store_true",
        help="Tampilkan semua hasil, tanpa saringan gaji/lokasi/judul",
    )

    glints_diag = glints_sub.add_parser(
        "diagnosa",
        help="Periksa mengapa kartu Glints tidak terbaca (simpan HTML + PNG)",
    )
    glints_diag.add_argument(
        "--keyword",
        default="",
        help="Kata kunci yang diuji (default: kata kunci pertama di .env)",
    )

    glints_sub.add_parser(
        "simulasi", help="Simulasi alur lamaran Glints (tanpa Chrome)"
    )

    bl_parser = subparsers.add_parser("blacklist", help="Blacklist company")
    bl_parser.add_argument("company", help="Nama company")
    bl_parser.add_argument("--reason", default="", help="Alasan")

    args = parser.parse_args()

    if args.command == "run":
        if args.auto:
            config.auto_apply = True
        elif args.manual:
            config.auto_apply = False

        if args.locations:
            lokasi = [
                item.strip() for item in args.locations.split(",") if item.strip()
            ]
            if lokasi:
                config.locations = lokasi
                config.location = lokasi[0]

        if args.max_age_days is not None:
            config.max_age_days = max(0, args.max_age_days)

        if args.max_pages is not None:
            config.max_pages = max(1, args.max_pages)

        if getattr(args, "riset_pages", None) is not None:
            config.research_max_pages = batas_halaman_riset(args.riset_pages)

        if args.headless:
            config.headless = True

        if args.profile_dir:
            config.profile_dir = args.profile_dir
            config.use_profile = True

        if args.no_profile:
            config.use_profile = False

        if args.no_login_wait:
            config.login_wait = False

        from main import main

        main()
    elif args.command == "stats":
        show_stats()
    elif args.command == "config":
        show_config()
    elif args.command == "repair":
        repair_data()
    elif args.command == "perbarui-env":
        perbarui_env()
    elif args.command == "simulasi":
        simulasi()
    elif args.command == "set-env":
        atur_env(args.pasangan)
    elif args.command == "history":
        show_applications(args.limit)
    elif args.command == "uji-lamar":
        uji_lamar(args.url)
    elif args.command == "cek-logo":
        cek_logo(args.limit, args.max_pages, args.keywords)
    elif args.command == "glints":
        if args.glints_command == "run":
            jalankan_glints(args.max_pages, args.keywords, args.limit)
        elif args.glints_command == "uji":
            if args.url.strip():
                uji_glints(args.url)
            else:
                uji_glints_otomatis(args.keywords, max(1, args.max_pages))
        elif args.glints_command == "cari":
            cari_glints(
                args.keywords, args.max_pages, args.limit, args.semua
            )
        elif args.glints_command == "diagnosa":
            diagnosa_glints_cli(args.keyword)
        elif args.glints_command == "simulasi":
            simulasi_glints()
        else:
            glints_parser.print_help()
    elif args.command == "blacklist":
        blacklist_company(args.company, args.reason)
    else:
        parser.print_help()
