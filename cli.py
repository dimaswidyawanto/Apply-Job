import argparse
import contextlib
import subprocess
import time
from pathlib import Path

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
            check=False,
        )
        if hasil.returncode == 0:
            return hasil.stdout.strip() or "-"
    except Exception:
        pass
    return "-"


def jalankan_terkunci(fungsi, *argumen, **kata_kunci):
    """Jalankan sesi lamar di bawah kunci tunggal (pasal 4.3).

    Tanpa kunci, dua jendela peluncur bisa memproses lowongan yang sama dan
    mengirim lamaran ganda.
    """
    import kunci

    try:
        with kunci.sesi_tunggal("."):
            return fungsi(*argumen, **kata_kunci)
    except kunci.SesiBerjalan as exc:
        console.print(f"[bold red]{exc}[/]")
        return None


def lamar_semua_situs(situs: str = "", max_pages: int = 0, batas: int = 0,
                      perbarui: bool = True):
    """Satu perintah untuk JobStreet + Glints + Indeed (dipakai .bat)."""
    from lamar_semua import jalankan as _jalankan

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    try:
        jalankan_terkunci(
            _jalankan,
            situs=situs, max_pages=max(0, max_pages),
            batas=max(0, batas), perbarui=perbarui,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dihentikan oleh pengguna.[/]")


def jalankan_indeed(max_pages: int = 0, keywords: str = "", batas: int = 0):
    """Riset & lamar lowongan Indeed (aturan sama dengan JobStreet)."""
    from indeed import jalankan_indeed as _jalankan

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print("[cyan]Situs:[/] Indeed (id.indeed.com)")

    daftar = [k.strip() for k in keywords.split(",") if k.strip()] or None
    try:
        laporan = jalankan_terkunci(
            _jalankan,
            max_pages=max(0, max_pages), keywords=daftar, batas=max(0, batas),
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dihentikan oleh pengguna.[/]")
        return
    except Exception as exc:
        console.print(f"[bold red]Gagal menjalankan Indeed:[/] {exc}")
        return

    if not laporan:
        return

    console.print()
    console.print(
        "[bold]Ringkasan Indeed:[/] "
        f"{laporan['dibaca']} terbaca · {laporan['baru']} baru · "
        f"{laporan['dilamar']} terkirim · {laporan['sudah']} sudah dilamar · "
        f"{laporan['perlu_manual']} perlu manual · "
        f"{laporan['dilewati']} dilewati · {laporan['gagal']} gagal"
    )


def cari_indeed(keywords: str = "", max_pages: int = 1, batas: int = 10,
                semuanya: bool = False):
    """Tampilkan lowongan Indeed yang layak dilamar beserta URL-nya."""
    from rich.table import Table as _Table

    from indeed import daftar_kandidat

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
        console.print(f"[bold red]Gagal mencari lowongan Indeed:[/] {exc}")
        return

    if not lowongan:
        console.print("[yellow]Tidak ada lowongan yang layak.[/]")
        return

    table = _Table(title=f"{len(lowongan)} lowongan Indeed layak dilamar")
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
            str(job.get("title") or "")[:40],
            str(job.get("company") or "-")[:28],
            str(job.get("salary") or "-"),
            str(job.get("location") or "-")[:26],
            "[green]ya[/]" if job.get("has_logo") else "[red]tidak[/]",
            str(job.get("url") or ""),
        )

    console.print(table)

    berlogo = sum(1 for job in lowongan if job.get("has_logo"))
    console.print(
        f"[bold]{berlogo}[/] dari [bold]{len(lowongan)}[/] kartu terdeteksi "
        "berlogo perusahaan."
    )


def diagnosa_indeed_cli(keyword: str = "", location: str = ""):
    """Cetak diagnosa pembacaan kartu Indeed."""
    from indeed import diagnosa_indeed

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    diagnosa_indeed(keyword, location)


def tampilkan_cv(path: str = "", pasang: bool = False):
    """Baca CV, tampilkan profil, dan (opsional) simpan CV_PATH ke .env."""
    import cv as modul_cv

    if pasang and path.strip():
        from env_tools import simpan_env

        simpan_env({"CV_PATH": path.strip()})
        print(f"CV_PATH disimpan ke .env: {path.strip()}")

    target = path.strip()
    if not target:
        from config import config as _config

        target = _config.cv_path

    console.print(f"[cyan]Berkas CV:[/] {target or '(belum diisi)'}")

    try:
        profil = modul_cv.profil_cv(target)
    except modul_cv.CvTidakTerbaca as exc:
        console.print(f"[bold red]CV tidak terbaca:[/] {exc}")
        return

    console.print(f"[green]Terbaca:[/] {modul_cv.format_profil(profil)}")

    table = Table(title="Profil CV")
    table.add_column("Bagian", style="cyan")
    table.add_column("Isi", overflow="fold")
    table.add_row(
        "Pengalaman",
        f"{profil.get('pengalaman_tahun')} tahun"
        if profil.get("pengalaman_tahun") is not None
        else "tidak disebut",
    )
    table.add_row("Pendidikan", str(profil.get("pendidikan") or "tidak disebut"))
    table.add_row("Bidang", ", ".join(profil.get("bidang") or []) or "-")
    table.add_row(
        "Keterampilan", ", ".join(profil.get("keterampilan") or []) or "-"
    )
    table.add_row(
        "Alat / software", ", ".join(profil.get("alat") or []) or "-"
    )
    table.add_row(
        "Sertifikasi", ", ".join(profil.get("sertifikasi") or []) or "-"
    )
    console.print(table)
    console.print(
        "[dim]Skor 6 parameter otomatis aktif selama CV_PATH terisi.[/]"
    )


def diagnosa_form(berkas: str = "", semua: bool = False):
    """Tunjukkan pertanyaan formulir yang belum terisi dari berkas debug."""
    import diagnosa_form as df

    jalur = berkas or str(df.berkas_terakhir() or "")

    if not jalur:
        console.print(
            "[yellow]Belum ada berkas debug.[/] Berkas ini dibuat otomatis "
            "saat bot menemui formulir yang tidak dikenali "
            "(folder debug/)."
        )
        return

    try:
        hasil = df.baca(jalur)
    except FileNotFoundError as exc:
        console.print(f"[yellow]{exc}[/]")
        return

    console.print(df.teks_laporan(hasil, semua=semua))


def tampilkan_antrean(batas: int = 20):
    """Lihat isi antrean: sebaran status + lowongan yang perlu ditinjau."""
    from database import db as _db

    hitung = _db.hitung_status_antrean()

    ringkas = Table(title="Antrean lowongan")
    ringkas.add_column("Status", style="cyan")
    ringkas.add_column("Jumlah", justify="right")
    for nama, jumlah in hitung.items():
        if jumlah:
            ringkas.add_row(nama, str(jumlah))
    console.print(ringkas)

    perhatian = []
    with _db._get_conn() as conn:  # noqa: SLF001 (pembacaan langsung, aman)
        for status in ("review_required", "failed", "expired"):
            for baris in conn.execute(
                """
                SELECT title, company, url, alasan, status_antrean
                  FROM jobs
                 WHERE status_antrean = ?
                 ORDER BY diperbarui_at DESC, id DESC
                 LIMIT ?
                """,
                (status, max(1, batas)),
            ):
                perhatian.append(dict(baris))

    if not perhatian:
        console.print("[dim]Tidak ada lowongan yang perlu ditinjau.[/]")
        return

    table = Table(title=f"{len(perhatian)} lowongan perlu perhatian")
    table.add_column("Status", style="yellow")
    table.add_column("Posisi", style="cyan", overflow="fold")
    table.add_column("Perusahaan", overflow="fold")
    table.add_column("Alasan", overflow="fold")
    table.add_column("URL", style="dim", overflow="fold")

    for job in perhatian:
        table.add_row(
            job["status_antrean"],
            str(job["title"])[:40],
            str(job["company"] or "-")[:24],
            str(job["alasan"] or "-")[:46],
            str(job["url"] or ""),
        )

    console.print(table)


def tampilkan_backup(daftar: bool = False, pulihkan: str = ""):
    """Backup / pulihkan database lamaran (master prompt pasal 12)."""
    import backup

    if pulihkan:
        try:
            sasaran = backup.pulihkan(pulihkan)
        except (FileNotFoundError, ValueError) as salah:
            console.print(f"[red]Gagal memulihkan:[/] {salah}")
            return
        console.print(f"[green]Database dipulihkan ke:[/] {sasaran}")
        console.print("[dim]Database sebelumnya disimpan sebagai .db.bak[/]")
        return

    if daftar:
        isi = backup.daftar()
        if not isi:
            console.print("[dim]Belum ada backup.[/]")
            return
        table = Table(title=f"Backup tersedia ({len(isi)})")
        table.add_column("Nama", style="cyan")
        table.add_column("Waktu")
        table.add_column("Ukuran", justify="right")
        for baris in isi:
            table.add_row(
                baris["nama"], baris["waktu"], f"{baris['ukuran'] / 1024:.0f} KB"
            )
        console.print(table)
        return

    try:
        berkas = backup.buat()
    except FileNotFoundError as salah:
        console.print(f"[red]Gagal backup:[/] {salah}")
        return

    ukuran = Path(berkas).stat().st_size / 1024
    console.print(f"[green]Backup dibuat:[/] {berkas} ({ukuran:.0f} KB)")


def tampilkan_laporan(simpan: bool = False):
    """Laporan kinerja + saran (master prompt pasal 12.4)."""
    import laporan

    data = laporan.ringkasan()

    table = Table(title="Laporan kinerja")
    table.add_column("Ukuran", style="cyan")
    table.add_column("Nilai", justify="right")
    table.add_row("Lowongan tersimpan", str(data["lowongan_tersimpan"]))
    table.add_row("Lamaran terkirim", str(data["lamaran_terkirim"]))
    table.add_row("Lamaran hari ini (WIB)", str(data["lamaran_hari_ini"]))
    table.add_row(
        "Sisa kuota",
        "tanpa batas" if data["sisa_kuota"] is None else str(data["sisa_kuota"]),
    )
    table.add_row("Tingkat berhasil", f"{data['tingkat_berhasil']}%")
    console.print(table)

    antre = Table(title="Status antrean")
    antre.add_column("Status", style="cyan")
    antre.add_column("Jumlah", justify="right")
    for nama, jumlah in data["status_antrean"].items():
        if jumlah:
            antre.add_row(nama, str(jumlah))
    console.print(antre)

    if data["per_lokasi"]:
        lokasi = Table(title="Per lokasi")
        lokasi.add_column("Lokasi", style="cyan")
        lokasi.add_column("Lowongan", justify="right")
        lokasi.add_column("Dilamar", justify="right")
        for item in data["per_lokasi"]:
            lokasi.add_row(
                item["lokasi"], str(item["jumlah"]), str(item["dilamar"])
            )
        console.print(lokasi)

    if data.get("per_kata_kunci"):
        kk = Table(title="Per kata kunci")
        kk.add_column("Kata kunci", style="cyan")
        kk.add_column("Lowongan", justify="right")
        kk.add_column("Dilamar", justify="right")
        for item in data["per_kata_kunci"]:
            kk.add_row(
                item["kata_kunci"], str(item["jumlah"]), str(item["dilamar"])
            )
        console.print(kk)

    if data.get("per_sumber"):
        sumber = Table(title="Per sumber")
        sumber.add_column("Sumber", style="cyan")
        sumber.add_column("Lowongan", justify="right")
        sumber.add_column("Dilamar", justify="right")
        for item in data["per_sumber"]:
            sumber.add_row(
                item["sumber"], str(item["jumlah"]), str(item["dilamar"])
            )
        console.print(sumber)

    saran = laporan.saran(data)
    if saran:
        console.print("[bold cyan]Saran:[/]")
        for satu in saran:
            console.print(f"  - {satu}")

    if simpan:
        berkas = laporan.simpan(data=data)
        console.print(f"[green]Laporan disimpan:[/] {berkas}")


def tampilkan_performa():
    """Ukur kecepatan di komputer ini + saran (master prompt pasal 13)."""
    import performa

    console.print("[bold cyan]Mengukur, mohon tunggu beberapa detik...[/]")

    table = Table(title="Diagnosa kecepatan")
    table.add_column("Bagian", style="cyan")
    table.add_column("Waktu", justify="right")
    table.add_column("Status")

    warna = {"ok": "green", "lambat": "red", "lewat": "dim"}
    hasil = performa.kumpulkan()
    for baris in hasil:
        waktu = "tidak tersedia" if baris["ms"] < 0 else f"{baris['ms']:.0f} ms"
        table.add_row(
            baris["bagian"],
            waktu,
            f"[{warna.get(baris['status'], 'white')}]{baris['status']}[/]",
        )
    console.print(table)

    angka = performa.ringkas()
    console.print(
        f"[dim]Lowongan tersimpan: {angka['jumlah_lowongan']} · "
        f"ukuran database: {angka['ukuran_db_mb']} MB · "
        f"Chrome terdeteksi: {'ya' if angka['chrome'] else 'tidak'}[/]"
    )
    console.print(f"[dim]Folder proyek: {angka['folder']}[/]")

    lambat = [b for b in hasil if b["status"] == "lambat"]
    if lambat:
        console.print("[bold yellow]Yang perlu diperhatikan:[/]")
        for baris in lambat:
            console.print(f"  - {baris['bagian']}: {baris['saran']}")
    else:
        console.print("[green]Semua bagian dalam batas wajar.[/]")

    console.print("[bold cyan]Saran umum:[/]")
    for satu in performa.saran_umum():
        console.print(f"  - {satu}")


def buka_dashboard(port: int = 0, tanpa_browser: bool = False):
    """Jalankan dashboard monitoring lokal."""
    import dashboard

    dashboard.jalankan(
        port=port or dashboard.PORT_BAKU, buka_browser=not tanpa_browser
    )


def kelola_jawaban(hapus: str = "", reset: bool = False,
                   isi: str = ""):
    """Lihat, tambah, atau hapus ingatan jawaban formulir."""
    import jawaban as memori

    if reset:
        jumlah = memori.lupakan_semua()
        console.print(f"[yellow]{jumlah} jawaban dihapus dari ingatan.[/]")
        return

    if hapus:
        if memori.lupakan(hapus):
            console.print(f"[green]Dihapus dari ingatan:[/] {hapus}")
        else:
            console.print(f"[yellow]Tidak ditemukan di ingatan:[/] {hapus}")
        return

    if isi:
        if "=" not in isi:
            console.print(
                '[red]Format: jawaban --isi "pertanyaan=jawaban"[/]'
            )
            return
        pertanyaan, nilai = isi.split("=", 1)
        if memori.ingat(pertanyaan.strip(), nilai.strip(), sumber="manual"):
            console.print(
                f"[green]Disimpan:[/] {pertanyaan.strip()} = {nilai.strip()}"
            )
        else:
            console.print("[red]Gagal menyimpan jawaban (kosong?).[/]")
        return

    daftar = memori.daftar()

    if not daftar:
        console.print(
            "[yellow]Ingatan jawaban masih kosong.[/] Isi formulir sekali "
            "saat melamar; isian Anda akan diingat otomatis."
        )
        return

    tabel = Table(title=f"Ingatan jawaban formulir ({len(daftar)})")
    tabel.add_column("Pertanyaan", style="cyan", overflow="fold")
    tabel.add_column("Jawaban", overflow="fold")
    tabel.add_column("Sumber", justify="center")
    tabel.add_column("Dipakai", justify="right")

    for baris in daftar:
        tabel.add_row(
            str(baris.get("pertanyaan") or "")[:60],
            str(baris.get("jawaban") or "")[:40],
            str(baris.get("sumber") or "-"),
            str(baris.get("dipakai") or 0),
        )

    console.print(tabel)
    console.print(
        '[dim]Hapus satu: jawaban --hapus "teks pertanyaan" · '
        "kosongkan: jawaban --reset[/]"
    )


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
        laporan = jalankan_terkunci(
            _jalankan,
            max_pages=max(0, max_pages), keywords=daftar, batas=max(0, batas),
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dihentikan oleh pengguna.[/]")
        return
    except Exception as exc:
        console.print(f"[bold red]Gagal menjalankan Glints:[/] {exc}")
        return

    if not laporan:
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


def cek_glints_cli(keyword: str = "", max_pages: int = 1, lamar: int = 0,
                   ya: bool = False):
    """Periksa Glints berurutan: baca kartu, saring, simulasi, lalu (opsional) lamar."""
    from glints import cek_glints

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    try:
        lulus = cek_glints(
            keyword=keyword, max_pages=max(1, max_pages),
            lamar=max(0, lamar), ya=ya,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Dihentikan oleh pengguna.[/]")
        return
    except Exception as exc:
        console.print(f"[bold red]Pemeriksaan Glints gagal:[/] {exc}")
        return

    if not lulus:
        raise SystemExit(1)


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
        "Prioritas lokasi",
        ", ".join(getattr(config, "prioritas_lokasi", []) or []) or "(tanpa)",
    )
    table.add_row(
        "Prioritas kategori",
        ", ".join(getattr(config, "prioritas_kategori", []) or []) or "(tanpa)",
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
        "Aktif (JobStreet & Glints; Indeed tanpa logo)",
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


def tampilkan_blacklist():
    """Daftar perusahaan yang dikecualikan (pasal 7: bisa ditinjau balik)."""
    baris = db.get_blacklist()

    if not baris:
        console.print(
            "[dim]Belum ada perusahaan di blacklist. "
            'Tambah dengan: jalankan.bat blacklist "Nama PT"[/]'
        )
        return

    table = Table(title=f"Blacklist ({len(baris)} perusahaan)")
    table.add_column("Perusahaan", style="yellow")
    table.add_column("Alasan", style="white")

    for item in baris:
        table.add_row(item["company_name"], item.get("reason") or "-")

    console.print(table)
    console.print(
        '[dim]Hapus dengan: jalankan.bat blacklist --hapus "Nama PT"[/]'
    )


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


def perbaiki_chrome():
    """Pindahkan profil Chrome bot ke folder cadangan (dibuat ulang bersih).

    Dipakai saat Chrome gagal dibuka (`DevToolsActivePort file doesn't exist`)
    karena profilnya terkunci atau rusak.
    """
    profil = Path(config.profile_dir).expanduser()

    if not profil.exists():
        console.print(
            f"[yellow]Profil Chrome belum ada:[/] {profil}"
        )
        console.print(
            "[dim]Jalankan `python cli.py run` seperti biasa; profil baru "
            "akan dibuat otomatis.[/]"
        )
        return

    cadangan = profil.with_name(
        f"{profil.name}-lama-{time.strftime('%Y%m%d-%H%M%S')}"
    )

    try:
        profil.rename(cadangan)
    except Exception as exc:
        console.print(f"[bold red]Gagal memindahkan profil:[/] {exc}")
        console.print(
            "[yellow]Tutup semua jendela Chrome (cek juga Task Manager) lalu "
            "jalankan perintah ini lagi.[/]"
        )
        return

    console.print(f"[green]Profil lama dipindahkan ke:[/] {cadangan}")
    console.print(
        "Mulai sekarang bot memakai profil Chrome baru. Sesi login lama tidak "
        "terbawa — login sekali lagi saat menjalankan `run`."
    )


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
        "perbaiki-chrome",
        help="Buat ulang profil Chrome bila Chrome gagal dibuka",
    )
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

    glints_cek = glints_sub.add_parser(
        "cek",
        help="Periksa Glints berurutan: baca kartu, saring, simulasi, lamar",
    )
    glints_cek.add_argument(
        "--keyword", default="", help="Kata kunci uji (default: .env)"
    )
    glints_cek.add_argument(
        "--max-pages", type=int, default=1, help="Muat per kata kunci (1)"
    )
    glints_cek.add_argument(
        "--lamar",
        type=int,
        default=0,
        help="Uji kirim N lamaran sungguhan (0 = tidak melamar)",
    )
    glints_cek.add_argument(
        "--ya", action="store_true", help="Lewati konfirmasi sebelum melamar"
    )

    glints_sub.add_parser(
        "simulasi", help="Simulasi alur lamaran Glints (tanpa Chrome)"
    )

    cv_parser = subparsers.add_parser(
        "cv", help="Baca CV dan tampilkan profil untuk skor kecocokan"
    )
    cv_parser.add_argument(
        "--path", default="", help="Berkas CV (.pdf/.docx/.txt/.md)"
    )
    cv_parser.add_argument(
        "--pasang", action="store_true", help="Simpan path ini ke CV_PATH di .env"
    )

    dash_parser = subparsers.add_parser(
        "dashboard", help="Dashboard monitoring + kontrol Start/Pause/Stop"
    )
    dash_parser.add_argument(
        "--port", type=int, default=0, help=f"Port (bawaan {8765})"
    )
    dash_parser.add_argument(
        "--tanpa-browser", action="store_true", help="Jangan buka browser"
    )

    lapor_parser = subparsers.add_parser(
        "laporan", help="Laporan kinerja + saran perbaikan"
    )
    lapor_parser.add_argument(
        "--simpan",
        action="store_true",
        help="Simpan laporan harian ke folder reports/",
    )

    subparsers.add_parser(
        "performa", help="Ukur kecepatan di komputer ini + saran"
    )

    backup_parser = subparsers.add_parser(
        "backup", help="Backup atau pulihkan database lamaran"
    )
    backup_parser.add_argument(
        "--daftar", action="store_true", help="Tampilkan backup yang ada"
    )
    backup_parser.add_argument(
        "--pulihkan", default="", help="Nama berkas backup yang dipulihkan"
    )

    diag_parser = subparsers.add_parser(
        "diagnosa-form",
        help="Baca berkas debug HTML: pertanyaan mana yang belum terisi",
    )
    diag_parser.add_argument(
        "berkas", nargs="?", default="",
        help="Berkas debug (kosong = berkas debug terbaru di folder debug/)",
    )
    diag_parser.add_argument(
        "--semua", action="store_true",
        help="Tampilkan juga pertanyaan yang sudah terisi",
    )

    antre_parser = subparsers.add_parser(
        "antrean", help="Lihat antrean: status dan lowongan yang perlu ditinjau"
    )
    antre_parser.add_argument(
        "--limit", type=int, default=20, help="Jumlah per status (20)"
    )

    lamar_parser = subparsers.add_parser(
        "lamar",
        help="Sekali jalan: JobStreet, Glints, dan Indeed (untuk .bat)",
    )
    lamar_parser.add_argument(
        "--situs", default="",
        help="jobstreet,glints,indeed (bawaan: SITES di .env)",
    )
    lamar_parser.add_argument(
        "--max-pages", type=int, default=0,
        help="Halaman riset per kombinasi (0 = ikut .env)",
    )
    lamar_parser.add_argument(
        "--limit", type=int, default=0, help="Batas lamaran sesi ini (0=tanpa batas)"
    )
    lamar_parser.add_argument(
        "--tanpa-perbarui", action="store_true",
        help="Jangan tarik pembaruan kode dari GitHub",
    )

    indeed_parser = subparsers.add_parser(
        "indeed", help="Cari & lamar lowongan di Indeed"
    )
    indeed_sub = indeed_parser.add_subparsers(dest="indeed_command")

    indeed_run = indeed_sub.add_parser(
        "run", help="Riset lalu lamar lowongan Indeed"
    )
    indeed_run.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help=(
            "Halaman per kombinasi kata kunci & lokasi, maksimal "
            f"{MAKS_HALAMAN_RISET} (ikut RESEARCH_MAX_PAGES)"
        ),
    )
    indeed_run.add_argument(
        "--keywords", default="", help="Kata kunci dipisah koma (0=bawaan .env)"
    )
    indeed_run.add_argument(
        "--limit", type=int, default=0, help="Batas lamaran sesi ini (0=tanpa batas)"
    )

    indeed_cari = indeed_sub.add_parser(
        "cari", help="Tampilkan lowongan Indeed yang layak + URL-nya"
    )
    indeed_cari.add_argument(
        "--keywords", default="", help="Kata kunci dipisah koma (bawaan .env)"
    )
    indeed_cari.add_argument(
        "--max-pages", type=int, default=1, help="Halaman per kombinasi (1)"
    )
    indeed_cari.add_argument(
        "--limit", type=int, default=10, help="Jumlah lowongan ditampilkan (10)"
    )
    indeed_cari.add_argument(
        "--semua", action="store_true", help="Tanpa saringan judul/lokasi/gaji"
    )

    indeed_diag = indeed_sub.add_parser(
        "diagnosa", help="Periksa mengapa kartu Indeed tidak terbaca"
    )
    indeed_diag.add_argument(
        "--keyword", default="", help="Kata kunci yang diuji (default: .env)"
    )
    indeed_diag.add_argument(
        "--location", default="", help="Lokasi yang diuji (opsional)"
    )

    jawab_parser = subparsers.add_parser(
        "jawaban", help="Lihat/ubah ingatan jawaban formulir lamaran"
    )
    jawab_parser.add_argument(
        "--hapus", default="", help="Hapus satu jawaban (teks pertanyaan)"
    )
    jawab_parser.add_argument(
        "--reset", action="store_true", help="Kosongkan semua ingatan jawaban"
    )
    jawab_parser.add_argument(
        "--isi", default="", help='Tambah manual: "pertanyaan=jawaban"'
    )

    bl_parser = subparsers.add_parser(
        "blacklist",
        help="Blacklist company (tanpa argumen = lihat daftar)",
    )
    bl_parser.add_argument(
        "company", nargs="?", default="",
        help="Nama company (kosong = tampilkan daftar)",
    )
    bl_parser.add_argument("--reason", default="", help="Alasan")
    bl_parser.add_argument(
        "--hapus", default="", metavar="NAMA",
        help="Hapus perusahaan dari blacklist",
    )

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

        jalankan_terkunci(main)
    elif args.command == "stats":
        show_stats()
    elif args.command == "config":
        show_config()
    elif args.command == "repair":
        repair_data()
    elif args.command == "perbaiki-chrome":
        perbaiki_chrome()
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
        elif args.glints_command == "cek":
            cek_glints_cli(
                args.keyword, args.max_pages, args.lamar, args.ya
            )
        elif args.glints_command == "simulasi":
            simulasi_glints()
        else:
            glints_parser.print_help()
    elif args.command == "cv":
        tampilkan_cv(args.path, args.pasang)
    elif args.command == "dashboard":
        buka_dashboard(args.port, args.tanpa_browser)
    elif args.command == "laporan":
        tampilkan_laporan(args.simpan)
    elif args.command == "performa":
        tampilkan_performa()
    elif args.command == "backup":
        tampilkan_backup(args.daftar, args.pulihkan)
    elif args.command == "diagnosa-form":
        diagnosa_form(args.berkas, args.semua)
    elif args.command == "antrean":
        tampilkan_antrean(args.limit)
    elif args.command == "lamar":
        lamar_semua_situs(
            args.situs, args.max_pages, args.limit, not args.tanpa_perbarui
        )
    elif args.command == "indeed":
        if args.indeed_command == "run":
            jalankan_indeed(args.max_pages, args.keywords, args.limit)
        elif args.indeed_command == "cari":
            cari_indeed(
                args.keywords, args.max_pages, args.limit, args.semua
            )
        elif args.indeed_command == "diagnosa":
            diagnosa_indeed_cli(args.keyword, args.location)
        else:
            indeed_parser.print_help()
    elif args.command == "jawaban":
        kelola_jawaban(args.hapus, args.reset, args.isi)
    elif args.command == "blacklist":
        if args.hapus:
            nama = args.hapus.strip()
            if db.hapus_blacklist(nama):
                console.print(f"[green]{nama} dihapus dari blacklist[/]")
            else:
                console.print(f"[yellow]{nama} tidak ada di blacklist[/]")
        elif args.company:
            blacklist_company(args.company, args.reason)
        else:
            tampilkan_blacklist()
    else:
        parser.print_help()
