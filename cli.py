import argparse
import contextlib
import subprocess
import time
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

import cache_riset
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
    if laporan.get("perlu_manusia"):
        console.print(
            "[bold red]BUTUH TINDAKAN ANDA:[/] Indeed meminta verifikasi "
            "(Cloudflare). Selesaikan di jendela Chrome, lalu jalankan lagi — "
            "status lamaran tertahan dicatat sebagai requires_human."
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


def tampilkan_antrean(batas: int = 20, situs: str = ""):
    """Lihat isi antrean: sebaran status + lowongan yang perlu ditinjau."""
    from database import _situs_sql
    from database import db as _db

    hitung = _db.hitung_status_antrean(situs)

    judul = "Antrean lowongan"
    if situs:
        judul = f"Antrean lowongan — {situs.title()}"
    ringkas = Table(title=judul)
    ringkas.add_column("Status", style="cyan")
    ringkas.add_column("Jumlah", justify="right")
    for nama, jumlah in hitung.items():
        if jumlah:
            ringkas.add_row(nama, str(jumlah))
    console.print(ringkas)

    perhatian = []
    saringan = ""
    parameter_tambahan: list = []
    if situs:
        saringan = f"AND {_situs_sql()} = ?"
        parameter_tambahan.append(situs)

    with _db._get_conn() as conn:  # noqa: SLF001 (pembacaan langsung, aman)
        for status in ("review_required", "failed", "expired"):
            for baris in conn.execute(
                f"""
                SELECT title, company, url, alasan, status_antrean
                  FROM jobs
                 WHERE status_antrean = ?
                   {saringan}
                 ORDER BY diperbarui_at DESC, id DESC
                 LIMIT ?
                """,
                (status, *parameter_tambahan, max(1, batas)),
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
    for baris in data.get("kuota_situs") or []:
        sisa = baris["sisa"]
        table.add_row(
            f"Kuota {baris['nama']}",
            f"{baris['terpakai']}/{baris['batas']}"
            + (" (tanpa batas)" if sisa is None else f" — sisa {sisa}"),
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


def cek_target(situs: str = "jobstreet", batas: int = 0):
    """Hitung peluang mencapai target 50 dari isi database (tanpa melamar).

    Menjawab: "kalau target 50 belum tercapai, apa yang menghalangi?" —
    dengan menilai ulang lowongan yang sudah tersimpan pada beberapa
    skenario aturan.
    """
    import target_audit

    nama = str(situs or "jobstreet").strip().lower()
    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print(f"[cyan]Situs:[/] {nama} · penilaian ulang isi database")

    hasil = target_audit.hitung(db, situs=nama, batas=max(0, batas))

    console.print(f"[dim]{hasil['kuota']}[/]")

    ganda = db.hitung_lamaran_ganda(situs=nama)
    if ganda:
        console.print(
            f"[yellow]Catatan:[/] ada {ganda} baris lamaran ganda di database "
            "(job yang sama tercatat lebih dari sekali, mis. dari versi lama). "
            "Hitungan kuota memakai job unik, jadi slot tidak hangus."
        )

    if hasil["kandidat"] == 0:
        console.print(
            "[yellow]Tidak ada lowongan tersimpan yang belum dilamar. "
            "Jalankan riset dulu (run --auto).[/]"
        )
        return hasil

    tabel = Table(title="Perkiraan lamaran yang bisa dikirim dari isi database")
    tabel.add_column("Aturan", style="cyan")
    tabel.add_column("Lolos", justify="right", style="green")
    tabel.add_column("Tambahan", justify="right", style="yellow")

    dasar = hasil["skenario"][0]["lolos"] if hasil["skenario"] else 0

    for baris in hasil["skenario"]:
        tabel.add_row(
            baris["nama"],
            str(baris["lolos"]),
            "-" if baris["lolos"] == dasar else f"+{baris['lolos'] - dasar}",
        )

    console.print(tabel)

    sisa_slot = hasil["sisa_slot"]
    console.print(
        f"[dim]{hasil['kandidat']} lowongan tersimpan belum dilamar · "
        f"sisa slot siklus ini: "
        f"{'tanpa batas' if sisa_slot is None else sisa_slot}[/]"
    )

    if hasil["alasan"]:
        console.print("\n[bold]Alasan lowongan tertolak dengan aturan sekarang:[/]")

        for alasan, jumlah in hasil["alasan"].most_common(8):
            console.print(f"  {jumlah:>6}  {alasan}")

    for baris in target_audit.saran(hasil):
        console.print(f"[yellow]Saran:[/] {baris}")

    return hasil


def _situs_lowongan(job: dict) -> str:
    """Situs asal lowongan dari awalan `job_id` atau kolom `sumber`."""
    sumber = str(job.get("sumber") or job.get("situs") or "").strip().lower()
    job_id = str(job.get("job_id") or "")
    awalan = job_id.split(":", 1)[0].strip().lower() if ":" in job_id else ""

    for calon in (awalan, sumber):
        if calon in ("jobstreet", "glints", "indeed"):
            return calon

    return awalan or sumber or "jobstreet"


def _umur_lowongan(job: dict):
    """Umur lowongan (hari) dari tanggal yang tersimpan; None bila tak terbaca."""
    import umur as umur_modul

    teks = str(job.get("date_posted") or job.get("posted_at") or "").strip()

    if not teks or teks.lower().startswith("0000"):
        return None

    return umur_modul.umur_dari_teks(teks)


# Kategori alasan penolakan untuk ringkasan dry-run (bahan laporan live).
KATEGORI_PENOLAKAN = (
    ("duplikat", ("sudah pernah", "sudah tercatat", "sudah dilamar")),
    ("terlalu_tua", ("max_age_days", "terlalu lama")),
    ("tanpa_tanggal", ("date_unknown", "tidak terbaca")),
    ("lokasi", ("lokasi",)),
    ("judul", ("judul", "minat", "title", "peran lain")),
    ("blacklist", ("blacklist",)),
    ("logo", ("logo",)),
    ("gaji", ("salary", "gaji")),
    ("pengalaman", ("experience", "pengalaman")),
    ("senior", ("senior",)),
)


def kategori_penolakan(alasan: str) -> str:
    """Kategori singkat satu alasan penolakan ('' bila lolos)."""
    teks = str(alasan or "").strip().lower()

    if not teks or teks == "ok":
        return ""

    for nama, penanda in KATEGORI_PENOLAKAN:
        if any(kata in teks for kata in penanda):
            return nama

    return "lainnya"


def _penilaian_tersimpan(situs: str = ""):
    """Nilai semua lowongan tersimpan yang belum dilamar (tanpa melamar).

    Mengembalikan daftar pasangan `(data_lowongan, hasil_telusuri)` supaya
    pemakai bisa memilih: `dry_run` cukup butuh hasilnya, `laporan_bukti`
    butuh judul/perusahaan/lokasi/tanggalnya juga.
    """
    from job_filter import JobFilter, telusuri_keputusan

    nama = str(situs or "").strip().lower()
    saringan = JobFilter()
    penilaian = []

    for job in db.lowongan_belum_dilamar():
        asal = _situs_lowongan(job)

        if nama and asal != nama:
            continue

        data = dict(job)
        data["situs"] = asal
        data["age_days"] = _umur_lowongan(job)
        data["has_logo"] = (
            None if data.get("has_logo") is None else bool(data.get("has_logo"))
        )
        penilaian.append((data, telusuri_keputusan(data, saringan)))

    return penilaian


def _segar_bila_diminta(args) -> None:
    """`--segar`: matikan cache riset untuk sesi ini (ambil ulang dari situs).

    Penting setelah perbaikan parser tanggal/umur: cache menyimpan lowongan
    yang sudah dinormalisasi — termasuk `age_days` hasil kode LAMA — sehingga
    sesi berikutnya bisa memakai umur yang salah sampai TTL habis.
    """
    if getattr(args, "segar", False):
        cache_riset.paksa_segar()
        console.print(
            "[cyan]Cache riset dimatikan untuk sesi ini (--segar):[/] "
            "lowongan diambil ulang dari situs."
        )


def dry_run(situs: str = "", batas: int = 5):
    """Jejak keputusan lowongan tersimpan TANPA mengirim lamaran.

    Menunjukkan urutan yang benar-benar dijalankan: FOUND → DUPLICATE →
    FILTER → SCORE → AGE → DECISION. Tidak membuka browser, tidak menyentuh
    kuota, dan tidak mengubah status lamaran.
    """
    nama = str(situs or "").strip().lower()
    dinilai = [hasil for _data, hasil in _penilaian_tersimpan(nama)]

    console.print("[bold]DRY RUN[/] — tidak ada lamaran yang dikirim")
    console.print(
        f"[dim]Kode: {versi_kode()} · situs: {nama or 'semua'} · "
        f"{len(dinilai)} lowongan tersimpan belum dilamar[/]"
    )

    if not dinilai:
        console.print(
            "[yellow]Tidak ada lowongan tersimpan untuk diuji. Jalankan riset "
            "dulu (run --auto), lalu dry-run lagi.[/]"
        )
        return {"total": 0, "apply": 0, "skip": 0, "lowongan": []}

    batas = max(1, int(batas or 5))
    for nomor, hasil in enumerate(dinilai[:batas], start=1):
        console.print(
            f"\n[bold]{nomor}. {hasil['keputusan']}[/] · skor "
            f"{hasil['skor']} · {hasil['job_id']}"
        )

        for langkah in hasil["tahapan"]:
            warna = {
                "SKIP": "yellow",
                "APPLY": "green",
                "OK": "dim",
            }.get(langkah["status"], "white")
            keterangan = langkah.get("alasan") or ""

            if langkah["tahap"] == "SCORE":
                rincian = ", ".join(
                    f"{nama_dimensi} {nilai}"
                    for nama_dimensi, nilai in langkah.get("rincian", {}).items()
                    if nilai
                )
                keterangan = rincian or "tanpa dimensi bernilai"

            if langkah["tahap"] == "AGE" and not keterangan:
                umur_hari = langkah.get("umur_hari")
                batas_umur = int(getattr(config, "max_age_days", 0) or 0)
                keterangan = (
                    f"umur {umur_hari} hari · MAX_AGE_DAYS={batas_umur}"
                    if isinstance(umur_hari, int)
                    else "tanggal tidak terbaca (DATE_UNKNOWN) · "
                    f"MAX_AGE_DAYS={batas_umur}"
                )

            console.print(
                f"  [{warna}]{langkah['tahap']:<9}[/] "
                f"{langkah['status']:<6} {keterangan}"
            )

    jumlah_apply = sum(1 for item in dinilai if item["keputusan"] == "APPLY")
    tanpa_tanggal = sum(
        1
        for item in dinilai
        if next(
            (t for t in item["tahapan"] if t["tahap"] == "AGE"), {}
        ).get("umur_hari")
        is None
    )

    console.print(
        f"\n[bold]Ringkasan:[/] {jumlah_apply} APPLY · "
        f"{len(dinilai) - jumlah_apply} SKIP dari {len(dinilai)} lowongan "
        "(tidak ada yang dikirim)"
    )

    if tanpa_tanggal:
        # Penting untuk kejujuran: aturan umur tidak bisa menilai lowongan
        # yang tanggalnya tidak tersimpan (mis. baris lama di database).
        console.print(
            f"[yellow]Catatan:[/] {tanpa_tanggal} dari {len(dinilai)} lowongan "
            "tanpa tanggal tersimpan (DATE_UNKNOWN) — aturan MAX_AGE_DAYS tidak "
            "dapat menilainya. Riset baru akan mengisi tanggalnya."
        )

    per_situs: dict = {}

    for item in dinilai:
        nama_situs = item.get("platform") or "tidak diketahui"
        baris = per_situs.setdefault(
            nama_situs, {"total": 0, "apply": 0, "tanpa_tgl": 0}
        )
        baris["total"] += 1

        # Baris tanpa tanggal (DATE_UNKNOWN) diloloskan, jadi tidak pernah
        # muncul sebagai alasan penolakan. Dihitung sendiri supaya kelihatan
        # berapa lowongan yang tidak bisa dinilai aturan umur.
        tahap_umur = next(
            (t for t in item["tahapan"] if t["tahap"] == "AGE"), {}
        )
        if tahap_umur.get("umur_hari") is None:
            baris["tanpa_tgl"] += 1

        if item["keputusan"] == "APPLY":
            baris["apply"] += 1
            continue

        kategori = kategori_penolakan(item["alasan"]) or "lainnya"
        baris[kategori] = baris.get(kategori, 0) + 1

    tabel = Table(title="Ringkasan dry-run per situs")
    kolom = (
        "Situs",
        "Total",
        "APPLY",
        "SKIP",
        "Duplikat",
        "Tua",
        "Tanpa tgl",
        "Lokasi",
        "Judul",
        "Lain",
    )

    for judul in kolom:
        tabel.add_column(judul)

    for nama_situs, baris in sorted(per_situs.items()):
        total = baris["total"]
        apply_count = baris["apply"]
        # "Lain" = blacklist, logo, gaji, pengalaman, senior, dan sisanya.
        lain = sum(
            nilai
            for kunci, nilai in baris.items()
            if kunci
            not in (
                "total",
                "apply",
                "duplikat",
                "terlalu_tua",
                "tanpa_tanggal",
                "tanpa_tgl",
                "lokasi",
                "judul",
            )
        )
        tabel.add_row(
            nama_situs,
            str(total),
            str(apply_count),
            str(total - apply_count),
            str(baris.get("duplikat", 0)),
            str(baris.get("terlalu_tua", 0)),
            str(baris.get("tanpa_tgl", 0)),
            str(baris.get("lokasi", 0)),
            str(baris.get("judul", 0)),
            str(lain),
        )

    console.print(tabel)

    return {
        "total": len(dinilai),
        "apply": jumlah_apply,
        "skip": len(dinilai) - jumlah_apply,
        "tanpa_tanggal": tanpa_tanggal,
        "per_situs": per_situs,
        "lowongan": dinilai,
    }


def laporan_bukti(situs: str = "", batas: int = 20, simpan: bool = False):
    """Tabel bukti validasi (pasal 3) + ringkasan per situs (pasal 14).

    Seluruh isinya berasal dari lowongan yang SUDAH tersimpan: tidak membuka
    browser, tidak memakai kuota, tidak mengubah data. Dipakai untuk menyusun
    laporan akhir tanpa menghitung manual.
    """
    import umur as umur_modul

    nama = str(situs or "").strip().lower()
    penilaian = _penilaian_tersimpan(nama)
    batas = max(1, int(batas or 20))
    tampil = penilaian[:batas]

    waktu = umur_modul.sekarang_wib().strftime("%Y-%m-%d %H:%M")

    judul_atas = (
        "# Bukti validasi dari database\n\n"
        f"- Kode: {versi_kode()}\n"
        f"- Waktu (WIB): {waktu}\n"
        f"- Database: {config.db_path}\n"
        f"- Situs: {nama or 'semua'}\n"
        f"- Lowongan tersimpan belum dilamar: {len(penilaian)} "
        f"(ditampilkan {len(tampil)})"
    )

    aturan = (
        "\n- Aturan aktif: "
        f"MAX_AGE_DAYS={int(config.max_age_days or 0)} · "
        f"filter judul={'aktif' if config.require_keyword_match else 'tidak'} · "
        f"filter lokasi ketat={'aktif' if config.strict_location else 'tidak'} · "
        f"wajib logo={'aktif' if config.require_company_logo else 'tidak'}"
    )

    kolom = (
        "platform", "job_id", "judul", "perusahaan", "lokasi", "tanggal",
        "umur (hari)", "blacklist", "judul", "lokasi", "duplikat", "skor",
        "keputusan", "alasan",
    )
    baris = ["| " + " | ".join(kolom) + " |"]
    baris.append("|" + "|".join(["---"] * len(kolom)) + "|")

    def sel(teks, lebar=40):
        return str(teks if teks not in (None, "") else "-").replace("|", "/")[:lebar]

    for data, hasil in tampil:
        tahap = {t["tahap"]: t for t in hasil["tahapan"]}
        umur_hari = tahap.get("AGE", {}).get("umur_hari")
        kategori = kategori_penolakan(hasil["alasan"])

        baris.append(
            "| "
            + " | ".join(
                [
                    sel(hasil.get("platform")),
                    sel(hasil.get("job_id")),
                    sel(data.get("title")),
                    sel(data.get("company"), 24),
                    sel(data.get("location"), 18),
                    sel(data.get("date_posted"), 12),
                    sel(umur_hari, 4),
                    "TOLAK" if kategori == "blacklist" else "-",
                    "TOLAK" if kategori == "judul" else "-",
                    "TOLAK" if kategori == "lokasi" else "-",
                    "YA" if tahap.get("DUPLICATE", {}).get("status") == "SKIP" else "-",
                    sel(hasil.get("skor"), 4),
                    sel(hasil.get("keputusan")),
                    sel(hasil["alasan"], 44),
                ]
            )
            + " |"
        )

    # Ringkasan per situs (pasal 14).
    rekap: dict = {}
    for _data, hasil in penilaian:
        nama_situs = hasil.get("platform") or "tidak diketahui"
        bar = rekap.setdefault(
            nama_situs,
            {
                "total": 0, "apply": 0, "duplikat": 0, "terlalu_tua": 0,
                "tanpa_tgl": 0, "judul": 0, "lokasi": 0, "blacklist": 0,
                "lain": 0,
            },
        )
        bar["total"] += 1

        tahap = {t["tahap"]: t for t in hasil["tahapan"]}
        if tahap.get("AGE", {}).get("umur_hari") is None:
            bar["tanpa_tgl"] += 1

        if hasil["keputusan"] == "APPLY":
            bar["apply"] += 1
            continue

        kategori = kategori_penolakan(hasil["alasan"])
        if kategori in ("duplikat", "terlalu_tua", "judul", "lokasi", "blacklist"):
            bar[kategori] += 1
        else:
            bar["lain"] += 1

    kolom2 = (
        "platform", "total", "apply", "skip", "duplikat", "terlalu tua",
        "tanpa tanggal", "judul", "lokasi", "blacklist", "lain",
    )
    rekap_md = ["", "## Ringkasan per situs", "", "| " + " | ".join(kolom2) + " |"]
    rekap_md.append("|" + "|".join(["---"] * len(kolom2)) + "|")

    for nama_situs, bar in sorted(rekap.items()):
        rekap_md.append(
            "| "
            + " | ".join(
                str(nilai)
                for nilai in (
                    nama_situs,
                    bar["total"],
                    bar["apply"],
                    bar["total"] - bar["apply"],
                    bar["duplikat"],
                    bar["terlalu_tua"],
                    bar["tanpa_tgl"],
                    bar["judul"],
                    bar["lokasi"],
                    bar["blacklist"],
                    bar["lain"],
                )
            )
            + " |"
        )

    catatan = []
    if not penilaian:
        catatan.append(
            "Tidak ada lowongan tersimpan yang belum dilamar — jalankan riset dulu."
        )

    tanpa_tgl = sum(
        1
        for _data, hasil in penilaian
        if {t["tahap"]: t for t in hasil["tahapan"]}.get("AGE", {}).get(
            "umur_hari"
        )
        is None
    )
    if tanpa_tgl:
        catatan.append(
            f"{tanpa_tgl} dari {len(penilaian)} lowongan tanpa tanggal tersimpan "
            "(DATE_UNKNOWN) — aturan MAX_AGE_DAYS tidak dapat menilainya. "
            "Baris seperti ini ditandai '-' pada kolom umur."
        )

    teks = (
        judul_atas
        + aturan
        + "\n\n## Tabel bukti per lowongan\n\n"
        + "\n".join(baris)
        + "\n"
        + "\n".join(rekap_md)
        + "\n"
        + ("\n".join(f"\n> {c}" for c in catatan) if catatan else "")
    )

    # soft_wrap: jangan bungkus baris — tabel markdown harus utuh saat
    # disalin ke laporan.
    console.print(teks, markup=False, highlight=False, soft_wrap=True)

    if simpan:
        import laporan as laporan_modul

        folder = Path(laporan_modul.FOLDER_LAPORAN)
        folder.mkdir(parents=True, exist_ok=True)
        jejak = umur_modul.sekarang_wib().strftime("%Y-%m-%d-%H%M")
        berkas = folder / f"bukti-live-{jejak}.md"
        berkas.write_text(teks, encoding="utf-8")
        console.print(f"\n[green]Tersimpan:[/] {berkas}")

    return {"total": len(penilaian), "ditampilkan": len(tampil), "per_situs": rekap}


def kelola_jawaban(hapus: str = "", reset: bool = False,
                   isi: str = "", rapikan: bool = False,
                   tetapkan: str = ""):
    """Lihat, tambah, hapus, atau rapikan ingatan jawaban formulir."""
    import jawaban as memori

    if rapikan:
        _tampilkan_konflik(memori)
        return

    if tetapkan:
        _tetapkan_jawaban(memori, tetapkan)
        return

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


def _tampilkan_konflik(memori) -> None:
    """Tabel kelompok jawaban yang maksudnya sama tetapi nilainya berbeda."""
    daftar = memori.konflik()

    if not daftar:
        console.print(
            "[green]Tidak ada jawaban yang bertentangan.[/] Semua pertanyaan "
            "sejenis sudah dijawab dengan nilai yang sama."
        )
        return

    tabel = Table(
        title=f"Jawaban bertentangan ({len(daftar)} kelompok)",
        caption=(
            'Pilih satu nilai resmi per kelompok, lalu jalankan: '
            'jalankan.bat jawaban --tetapkan "subjek=nilai"'
        ),
    )
    tabel.add_column("Jenis", style="cyan")
    tabel.add_column("Subjek", style="cyan", overflow="fold")
    tabel.add_column("Nilai yang tersimpan", overflow="fold")
    tabel.add_column("Disarankan", overflow="fold")

    for kelompok in daftar:
        nilai = "\n".join(
            f"{teks} (dipakai {info['dipakai']}x, {info['jumlah']} baris)"
            for teks, info in sorted(
                kelompok["nilai"].items(),
                key=lambda item: (-item[1]["dipakai"], -item[1]["jumlah"], item[0]),
            )
        )
        tabel.add_row(
            kelompok["keluarga"],
            kelompok["subjek"] or "(semua)",
            nilai,
            memori._nilai_terbanyak(kelompok["nilai"]),
        )

    console.print(tabel)
    console.print(
        "[dim]Disarankan = nilai yang paling sering dipakai. Ini hanya usulan; "
        "jawaban resmi tetap Anda yang menentukan.[/]"
    )


def _tetapkan_jawaban(memori, isi: str) -> None:
    """Samakan semua jawaban satu subjek: `--tetapkan "purchasing=3 years"`."""
    if "=" not in isi:
        console.print(
            '[red]Format: jawaban --tetapkan "subjek=nilai"[/] '
            'contoh: jawaban --tetapkan "purchasing=3 years"'
        )
        return

    subjek, nilai = isi.split("=", 1)
    subjek, nilai = subjek.strip(), nilai.strip()

    if not subjek or not nilai:
        console.print('[red]Subjek dan nilai tidak boleh kosong.[/]')
        return

    jumlah = memori.tetapkan(subjek, nilai)

    if jumlah:
        console.print(
            f"[green]{jumlah} jawaban disamakan:[/] {subjek} = {nilai}"
        )
    else:
        console.print(
            f"[yellow]Tidak ada jawaban yang cocok dengan subjek:[/] {subjek}"
        )


def tabel_situs(judul: str = "Status per situs"):
    """Tabel ringkasan tiap situs, supaya JobStreet/Glints/Indeed tidak tercampur."""
    daftar = db.ringkasan_per_situs()
    if not daftar:
        console.print("[dim]Belum ada lowongan tercatat.[/]")
        return

    table = Table(title=judul)
    table.add_column("Situs", style="cyan")
    table.add_column("Lowongan", justify="right")
    table.add_column("Terkirim", justify="right", style="green")
    table.add_column("Perlu manual", justify="right", style="yellow")
    table.add_column("Gagal", justify="right", style="red")
    table.add_column("Ditolak", justify="right")
    table.add_column("Kedaluwarsa", justify="right")

    import kuota as kuota_modul

    for baris in daftar:
        table.add_row(
            kuota_modul.NAMA_SITUS.get(
                str(baris["situs"]).lower(), str(baris["situs"]).title()
            ),
            str(baris["total"]),
            str(baris["terkirim"]),
            str(baris["perlu_manual"]),
            str(baris["gagal"]),
            str(baris["ditolak"]),
            str(baris["kedaluwarsa"]),
        )

    console.print(table)


def tampilkan_status_situs():
    """Ringkasan terpisah per situs + kuota harian (tanpa membuka browser)."""
    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    tabel_situs()

    try:
        import kuota

        console.print()
        kuota_tabel = Table(
            title="Kuota per situs — siklus 24 jam (50 wajib tercapai)"
        )
        kuota_tabel.add_column("Situs", style="cyan")
        kuota_tabel.add_column("Siklus ini", justify="right")
        kuota_tabel.add_column("Target", justify="right")
        kuota_tabel.add_column("Sisa", justify="right", style="yellow")
        kuota_tabel.add_column("Reset berikutnya", style="blue")
        kuota_tabel.add_column("Status", style="green")

        for baris in kuota.ringkasan_situs():
            sisa = baris["sisa"]
            kuota_tabel.add_row(
                baris["nama"],
                str(baris["terpakai"]),
                "tanpa batas" if sisa is None else str(baris["batas"]),
                "-" if sisa is None else str(sisa),
                baris["berakhir"] or "-",
                "tercapai" if sisa == 0 else "belum",
            )

        console.print(kuota_tabel)
    except Exception:
        pass

    from lamar_semua import NAMA_SITUS, situs_terpilih

    aktif = situs_terpilih("")
    console.print(
        "[dim]Situs aktif di .env:[/] "
        + ", ".join(NAMA_SITUS.get(nama, nama) for nama in aktif)
    )

    try:
        import jawaban as ingatan

        jumlah = ingatan.jumlah()
        pesan = (
            f"[cyan]Ingatan jawaban:[/] {jumlah} jawaban tersimpan"
            if jumlah
            else "[yellow]Ingatan jawaban:[/] belum ada jawaban tersimpan"
        )
        console.print(
            f"{pesan} [dim](lihat: jalankan.bat jawaban)[/]"
        )
    except Exception:
        pass


def show_stats():
    stats = db.get_stats()
    table = Table(title="Statistik")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    for key, value in stats.items():
        table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)
    tabel_situs("Statistik per situs")


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


def cek_tanggal(limit: int = 5, max_pages: int = 1, keywords: str = ""):
    """Periksa dari mana tanggal lowongan JobStreet terbaca (tanpa melamar).

    Membuka hasil pencarian sungguhan, lalu untuk setiap kartu menampilkan
    elemen tanggal yang ditemukan, sumber yang dipakai, nilai yang tersimpan,
    dan umur hasil hitung. Dipakai membuktikan perbaikan pembacaan tanggal
    tanpa memakai kuota lamaran dan tanpa menyentuh database.
    """
    from scraper import JobStreetBot

    daftar_keyword = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    if not daftar_keyword:
        daftar_keyword = list(config.keywords)[:1] or ["inventory"]

    console.print(f"[cyan]Versi kode:[/] {versi_kode()}")
    console.print("[cyan]Situs:[/] JobStreet — pemeriksaan tanggal lowongan")
    console.print(
        f"[dim]Kata kunci: {', '.join(daftar_keyword)} | halaman: {max_pages} "
        f"| batas tampil: {limit} | tidak ada lamaran dikirim[/]"
    )

    bot = JobStreetBot()
    terbaca: list[dict] = []

    try:
        bot.init_browser()
        if not bot.login():
            console.print("[bold red]Login belum selesai. Pemeriksaan dibatalkan.[/]")
            return

        for keyword in daftar_keyword:
            for page in range(1, max(1, max_pages) + 1):
                bot.search_jobs(
                    keyword,
                    page,
                    location=config.location,
                    saat_kartu=lambda card, job: terbaca.append(
                        {**job, "tanggal": bot._diagnosa_tanggal(card)}
                    ),
                )
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

    table = Table(title="Pembacaan tanggal lowongan")
    table.add_column("Judul", style="cyan", max_width=32)
    table.add_column("Elemen tanggal", style="dim", max_width=26)
    table.add_column("Sumber", max_width=22)
    table.add_column("Tersimpan", max_width=20)
    table.add_column("Umur", justify="center")

    sumber_dipakai: dict = {}

    for job in terbaca[: max(1, limit)]:
        info = job["tanggal"]
        elemen = "-"
        if info["elemen"]:
            _sel, atribut, teks = info["elemen"][0]
            elemen = atribut or teks or _sel

        age_days = job.get("age_days")
        table.add_row(
            escape((job.get("title") or "-")[:32]),
            escape(str(elemen)[:26]),
            escape(info["sumber"]),
            escape((job.get("date_posted") or "DATE_UNKNOWN")[:20]),
            "-" if age_days is None else f"{age_days} hari",
        )
        kunci = info["sumber"]
        sumber_dipakai[kunci] = sumber_dipakai.get(kunci, 0) + 1

    console.print(table)

    diperiksa = len(terbaca[: max(1, limit)])
    bertanggal = sum(1 for job in terbaca[:diperiksa] if job["tanggal"]["hasil"])
    console.print(
        f"[bold]{bertanggal}[/] dari [bold]{diperiksa}[/] kartu tanggalnya "
        f"terbaca; {diperiksa - bertanggal} tanpa tanggal (DATE_UNKNOWN)."
    )

    for sumber, jumlah in sorted(sumber_dipakai.items()):
        console.print(f"[dim]   sumber '{escape(sumber)}': {jumlah} kartu[/]")

    relatif = sum(
        1
        for job in terbaca[:diperiksa]
        if job.get("date_posted")
        and not str(job.get("date_posted"))[:4].isdigit()
    )
    if relatif:
        console.print(
            f"[yellow]{relatif} kartu masih menyimpan label relatif[/] — "
            "umurnya akan terbaca 0 hari selamanya."
        )

    if bertanggal == 0:
        console.print(
            "[yellow]Tidak satu pun tanggal terbaca. Kirimkan tabel ini agar "
            "selector tanggal disesuaikan dengan markup terbaru.[/]"
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
    if laporan.get("perlu_manusia"):
        console.print(
            "[bold red]BUTUH TINDAKAN ANDA:[/] Glints meminta verifikasi. "
            "Selesaikan di jendela Chrome, lalu jalankan lagi."
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
    table.add_row("Wajib ada logo perusahaan", config.teks_wajib_logo())
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
    table.add_row(
        "Tanggal tak terbaca",
        "Ditolak" if config.tolak_umur_tak_diketahui else "Tetap dicoba",
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


def jalankan_run(situs: str = "jobstreet", max_pages: int = 0) -> None:
    """Jalankan `run` untuk satu situs saja.

    Bawaan tetap JobStreet supaya `run --auto` tidak berubah perilakunya;
    memilih situs lain berarti situs selebihnya benar-benar tidak dibuka.
    """
    situs = str(situs or "jobstreet").strip().lower()

    if situs in ("", "jobstreet"):
        console.print(
            "[bold]Situs:[/] JobStreet — Glints & Indeed tidak dibuka"
        )
        from main import main as mesin_jobstreet

        jalankan_terkunci(mesin_jobstreet)
        return

    from lamar_semua import NAMA_SITUS, situs_terpilih

    daftar = situs_terpilih(situs)
    if not daftar:
        console.print(
            "[bold red]Nama situs tidak dikenal:[/] "
            f"{situs}. Pilih: jobstreet, glints, indeed, semua"
        )
        raise SystemExit(2)

    nama = ", ".join(NAMA_SITUS.get(item, item) for item in daftar)
    console.print(f"[bold]Situs:[/] {nama} — situs lain tidak dibuka")
    lamar_semua_situs(
        ",".join(daftar),
        max(0, int(max_pages or 0)),
        0,
        False,
    )


def show_applications(limit: int = 50, situs: str = "",
                      alasan: bool = False):
    rows = db.get_recent_applications(limit, situs=situs)

    judul = f"Riwayat Lamaran ({limit} terakhir)"
    if situs:
        judul = f"Riwayat Lamaran {situs.title()} ({limit} terakhir)"
    table = Table(title=judul)
    table.add_column("Tanggal", style="cyan", no_wrap=True)
    table.add_column("Posisi", style="white")
    table.add_column("Perusahaan", style="yellow")
    table.add_column("Status", style="green", no_wrap=True)
    if alasan:
        # Alasan yang dicatat bot dipakai untuk menelusuri kenapa lamaran
        # berakhir "perlu manual" dan tidak pernah terkirim.
        table.add_column("Alasan", overflow="fold")

    if not rows:
        console.print("[dim]Belum ada lamaran yang tercatat.[/]")
        return

    for row in rows:
        kolom = [
            row["applied_at"][:19],
            row["title"][:40],
            row["company"][:25],
            row["status"],
        ]
        if alasan:
            kolom.append(str(row.get("notes") or ""))
        table.add_row(*kolom)

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

    run_parser = subparsers.add_parser(
        "run",
        help="Jalankan pencarian lowongan (bawaan: JobStreet saja)",
    )
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
        "--situs",
        default="jobstreet",
        help=(
            "Situs yang dijalankan: jobstreet (bawaan), glints, indeed, "
            "atau \"semua\" (JobStreet+Glints+Indeed)"
        ),
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
    run_parser.add_argument(
        "--segar",
        action="store_true",
        help=(
            "Abaikan cache riset dan ambil ulang lowongan dari situs "
            "(bawaan: cache CACHE_RISET_MENIT menit)"
        ),
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
    history_parser.add_argument(
        "--situs",
        default="",
        help="Saring satu situs: jobstreet, glints, indeed (kosong = semua)",
    )
    history_parser.add_argument(
        "--alasan",
        action="store_true",
        help="Tampilkan alasan yang dicatat bot (untuk menelusuri kegagalan)",
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

    tanggal_parser = subparsers.add_parser(
        "cek-tanggal",
        help="Periksa pembacaan tanggal lowongan JobStreet (tanpa melamar)",
    )
    tanggal_parser.add_argument(
        "--limit", type=int, default=5, help="Jumlah kartu yang ditampilkan"
    )
    tanggal_parser.add_argument(
        "--max-pages", type=int, default=1, help="Jumlah halaman (default 1)"
    )
    tanggal_parser.add_argument(
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
    glints_run.add_argument(
        "--segar",
        action="store_true",
        help="Abaikan cache riset dan ambil ulang lowongan dari situs",
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

    bukti_parser = subparsers.add_parser(
        "laporan-bukti",
        help="Tabel bukti validasi dari database (tanpa browser, tanpa kuota)",
    )
    bukti_parser.add_argument(
        "--situs", default="", help="jobstreet / glints / indeed (kosong = semua)"
    )
    bukti_parser.add_argument(
        "--limit", type=int, default=20, help="Jumlah lowongan yang ditampilkan"
    )
    bukti_parser.add_argument(
        "--simpan", action="store_true", help="Simpan ke reports/bukti-live-*.md"
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
    antre_parser.add_argument(
        "--situs",
        default="",
        help="Saring satu situs: jobstreet, glints, indeed (kosong = semua)",
    )

    subparsers.add_parser(
        "status",
        help="Ringkasan terpisah per situs (JobStreet/Glints/Indeed)",
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

    target_parser = subparsers.add_parser(
        "cek-target",
        help="Perkirakan peluang mencapai target 50 dari isi database",
    )
    target_parser.add_argument(
        "--situs", default="jobstreet",
        help="jobstreet, glints, indeed (bawaan: jobstreet)",
    )
    target_parser.add_argument(
        "--limit", type=int, default=0,
        help="Batasi lowongan yang dinilai (0 = semua)",
    )

    dry_parser = subparsers.add_parser(
        "dry-run",
        help="Jejak keputusan FOUND→DUPLICATE→FILTER→SCORE→AGE→DECISION "
        "tanpa melamar",
    )
    dry_parser.add_argument(
        "--situs", default="",
        help="jobstreet, glints, indeed (kosong = semua)",
    )
    dry_parser.add_argument(
        "--limit", type=int, default=5,
        help="Jumlah lowongan yang ditampilkan (bawaan: 5)",
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
    indeed_run.add_argument(
        "--segar",
        action="store_true",
        help="Abaikan cache riset dan ambil ulang lowongan dari situs",
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
    jawab_parser.add_argument(
        "--rapikan",
        action="store_true",
        help="Tampilkan jawaban sejenis yang nilainya bertentangan",
    )
    jawab_parser.add_argument(
        "--tetapkan",
        default="",
        help='Samakan satu kelompok: "subjek=nilai" (mis. "purchasing=3 years")',
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

        _segar_bila_diminta(args)

        # Pemisahan situs: `run` tanpa --situs tetap JobStreet saja, persis
        # seperti sebelumnya. Situs lain dijalankan lewat jalur yang sama
        # dengan "Lamar Glints.bat"/"Lamar Indeed.bat".
        jalankan_run(getattr(args, "situs", "jobstreet"), args.max_pages or 0)
    elif args.command == "stats":
        show_stats()
    elif args.command == "status":
        tampilkan_status_situs()
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
        show_applications(
            args.limit,
            getattr(args, "situs", ""),
            getattr(args, "alasan", False),
        )
    elif args.command == "uji-lamar":
        uji_lamar(args.url)
    elif args.command == "cek-logo":
        cek_logo(args.limit, args.max_pages, args.keywords)
    elif args.command == "cek-tanggal":
        cek_tanggal(args.limit, args.max_pages, args.keywords)
    elif args.command == "glints":
        if args.glints_command == "run":
            _segar_bila_diminta(args)
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
    elif args.command == "laporan-bukti":
        laporan_bukti(args.situs, args.limit, args.simpan)
    elif args.command == "laporan":
        tampilkan_laporan(args.simpan)
    elif args.command == "performa":
        tampilkan_performa()
    elif args.command == "backup":
        tampilkan_backup(args.daftar, args.pulihkan)
    elif args.command == "diagnosa-form":
        diagnosa_form(args.berkas, args.semua)
    elif args.command == "antrean":
        tampilkan_antrean(args.limit, getattr(args, "situs", ""))
    elif args.command == "lamar":
        lamar_semua_situs(
            args.situs, args.max_pages, args.limit, not args.tanpa_perbarui
        )
    elif args.command == "indeed":
        if args.indeed_command == "run":
            _segar_bila_diminta(args)
            jalankan_indeed(args.max_pages, args.keywords, args.limit)
        elif args.indeed_command == "cari":
            cari_indeed(
                args.keywords, args.max_pages, args.limit, args.semua
            )
        elif args.indeed_command == "diagnosa":
            diagnosa_indeed_cli(args.keyword, args.location)
        else:
            indeed_parser.print_help()
    elif args.command == "cek-target":
        cek_target(args.situs, args.limit)
    elif args.command == "dry-run":
        dry_run(args.situs, args.limit)
    elif args.command == "jawaban":
        kelola_jawaban(
            args.hapus,
            args.reset,
            args.isi,
            getattr(args, "rapikan", False),
            getattr(args, "tetapkan", ""),
        )
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
