"""Satu klik: perbarui kode, lalu lamar otomatis di JobStreet, Glints, Indeed.

Dipakai oleh "Lamar Otomatis.bat". Alur:

1. (opsional) tarik pembaruan kode dari repo pengembangan,
2. jalankan sesi JobStreet → Glints → Indeed berurutan,
3. kuota harian dihitung PER SITUS (`kuota.py`): JobStreet 50, Glints 50,
   Indeed 50 — target satu situs tidak mengurangi jatah situs lain,
4. kirim **satu** laporan harian Telegram di akhir, bukan tiga.

Semua aturan per situs tetap milik modulnya masing-masing; berkas ini hanya
mengatur urutan dan ringkasan.
"""

import argparse
import contextlib
import subprocess
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

import cache_riset
import kuota
from config import config
from database import db
from notifier import notifier

console = Console()

AKAR = Path(__file__).resolve().parent

SITUS_BAKU = ("jobstreet", "glints", "indeed")
NAMA_SITUS = {
    "jobstreet": "JobStreet",
    "glints": "Glints",
    "indeed": "Indeed",
}

REMOTE_BAKU = "arena"
CABANG_BAKU = "main"
URL_ARENA = "https://github.com/dimasw1997/dimastes.git"


# --------------------------------------------------------------- pembaruan ---
def _git(*argumen: str, timeout: int = 240) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *argumen],
        cwd=str(AKAR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def perbarui_kode(remote: str = "", cabang: str = "") -> tuple[bool, str]:
    """Tarik pembaruan dari repo. Tidak pernah menggagalkan sesi lamaran.

    Hasil: (berhasil, pesan singkat).
    """
    remote = remote or REMOTE_BAKU
    cabang = cabang or CABANG_BAKU

    if not (AKAR / ".git").exists():
        return False, "bukan repo Git — pembaruan dilewati"

    try:
        if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
            return False, "bukan repo Git — pembaruan dilewati"

        if _git("remote", "get-url", remote).returncode != 0:
            tambah = _git("remote", "add", remote, URL_ARENA)
            if tambah.returncode != 0:
                return False, f"gagal menambah remote {remote}"

        ambil = _git("fetch", remote)
        if ambil.returncode != 0:
            return False, "tidak bisa menghubungi GitHub (periksa internet)"

        kotor = _git("status", "--porcelain").stdout.strip()
        disimpan = False
        if kotor and _git("stash", "push", "-m", "lamar-otomatis").returncode == 0:
            disimpan = True

        target = f"{remote}/{cabang}"
        gabung = _git("merge", "--no-edit", target)
        if gabung.returncode != 0:
            _git("merge", "--abort")
            gabung = _git("merge", "--no-edit", "--allow-unrelated-histories", target)

        if gabung.returncode != 0:
            _git("merge", "--abort")
            if disimpan:
                _git("stash", "pop")
            return False, "penggabungan bentrok — jalankan tarik.bat dan selesaikan"

        if disimpan:
            _git("stash", "pop")

        # Cabang yang diminta bisa saja sudah usang atau sudah dihapus di
        # GitHub (mis. sisa sesi pengembangan lama). Dulu sesi berhenti di
        # "kode sudah paling baru" padahal perbaikan terbaru ada di `main`
        # sehingga PC ini tetap menjalankan kode lama. Sekarang dibandingkan
        # dengan `main` dan ditarik bila tertinggal.
        tertinggal = _git("rev-list", "--count", f"HEAD..{remote}/main")
        jumlah = (tertinggal.stdout or "0").strip()
        if tertinggal.returncode == 0 and jumlah.isdigit() and int(jumlah) > 0:
            console.print(
                f"[cyan]Ada {jumlah} pembaruan di {remote}/main — "
                "menarik juga.[/]"
            )
            tambahan = _git("merge", "--no-edit", f"{remote}/main")
            if tambahan.returncode != 0:
                _git("merge", "--abort")
                return False, (
                    f"penggabungan {remote}/main bentrok — jalankan tarik.bat"
                )
            versi = _git("rev-parse", "--short", "HEAD").stdout.strip()
            return True, f"kode diperbarui ke {versi}"

        versi = _git("rev-parse", "--short", "HEAD").stdout.strip()
        if "Already up to date" in (gabung.stdout or ""):
            return True, f"kode sudah paling baru ({versi})"
        return True, f"kode diperbarui ke {versi}"
    except subprocess.TimeoutExpired:
        return False, "pembaruan kelamaan — dilewati"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"pembaruan gagal: {exc}"


# ------------------------------------------------------------------ situs ---
def situs_terpilih(teks: str = "") -> list[str]:
    """Daftar situs yang akan dijalankan, urut dan tanpa duplikat."""
    mentah = teks or getattr(config, "situs_aktif", "") or ",".join(SITUS_BAKU)
    diminta = [bagian.strip().lower() for bagian in str(mentah).split(",")]

    hasil = []
    for nama in diminta:
        if not nama:
            continue
        if nama in ("semua", "all", "*"):
            return list(SITUS_BAKU)
        if nama in SITUS_BAKU and nama not in hasil:
            hasil.append(nama)

    # Urutan tetap: JobStreet → Glints → Indeed. JobStreet acuan aturan.
    return [nama for nama in SITUS_BAKU if nama in hasil]


def _jalankan_situs(nama: str, max_pages: int, batas: int) -> dict:
    """Jalankan satu situs tanpa laporan harian sendiri."""
    if nama == "jobstreet":
        from main import AutoApplyEngine

        mesin = AutoApplyEngine()
        mesin.run(laporan_harian=False)
        stats = mesin.session_stats
        return {
            "dibaca": stats["found"],
            "baru": stats["new"],
            "dilamar": stats["applied"],
            "sudah": stats["already"],
            "perlu_manual": stats["manual"],
            "dilewati": stats["skipped"],
            "gagal": stats["errors"],
        }

    if nama == "glints":
        from glints import jalankan_glints

        return jalankan_glints(
            max_pages=max_pages, batas=batas, laporan_harian=False
        )

    from indeed import jalankan_indeed

    return jalankan_indeed(max_pages=max_pages, batas=batas, laporan_harian=False)


def _lepas_profil_sebelum_situs_berikut() -> None:
    """Pastikan Chrome situs sebelumnya sudah melepas profil bersama.

    Ketiga situs memakai folder profil yang sama (`config.profile_dir`). Bila
    Chrome situs sebelumnya belum benar-benar tertutup, situs berikutnya tidak
    bisa membukanya dan turun ke profil baru tanpa sesi login — persis yang
    membuat Glints "Login belum selesai" dan Indeed 0 lowongan pada log
    2026-11-13.
    """
    from pathlib import Path as _Path

    teks = str(getattr(config, "profile_dir", "") or "").strip()
    if not teks:
        return

    import browser

    profil = _Path(teks).expanduser()
    if not browser.profil_terkunci(profil):
        return

    console.print(
        "[dim]Chrome situs sebelumnya masih memegang profil; menunggu...[/]"
    )
    if browser.tunggu_profil_bebas(profil, batas_detik=20.0):
        return

    jumlah = browser.tutup_chrome_bot_tertinggal(profil)
    if jumlah:
        console.print(
            f"[yellow]{jumlah} proses Chrome sisa ditutup agar situs "
            "berikutnya bisa memakai profil yang sama.[/]"
        )
        browser.tunggu_profil_bebas(profil, batas_detik=10.0)


# --------------------------------------------------------------- ringkasan ---
def _tabel(hasil: dict[str, dict], dilewati: dict[str, str]) -> None:
    tabel = Table(title="Ringkasan lamar otomatis")
    tabel.add_column("Situs", style="cyan")
    tabel.add_column("Terbaca", justify="right")
    tabel.add_column("Baru", justify="right")
    tabel.add_column("Terkirim", justify="right", style="green")
    tabel.add_column("Sudah", justify="right")
    tabel.add_column("Manual", justify="right")
    tabel.add_column("Dilewati", justify="right")
    tabel.add_column("Gagal", justify="right", style="red")
    tabel.add_column("Catatan", overflow="fold")

    for nama in SITUS_BAKU:
        data = hasil.get(nama)
        if data:
            tabel.add_row(
                NAMA_SITUS[nama],
                str(data.get("dibaca", 0)),
                str(data.get("baru", 0)),
                str(data.get("dilamar", 0)),
                str(data.get("sudah", 0)),
                str(data.get("perlu_manual", 0)),
                str(data.get("dilewati", 0)),
                str(data.get("gagal", 0)),
                "",
            )
        elif nama in dilewati:
            tabel.add_row(NAMA_SITUS[nama], "-", "-", "-", "-", "-", "-", "-",
                          dilewati[nama])

    console.print()
    console.print(tabel)


def jalankan(
    situs: str = "",
    max_pages: int = 0,
    batas: int = 0,
    perbarui: bool = True,
) -> dict[str, dict]:
    """Jalankan seluruh situs terpilih dan kembalikan hasil per situs."""
    console.print("[bold cyan]Lamar otomatis — JobStreet · Glints · Indeed[/]")
    mulai_sesi = time.monotonic()

    # Backup harian otomatis (pasal 13) — cukup sekali per hari.
    with contextlib.suppress(Exception):
        import backup as backup_modul

        berkas_backup = backup_modul.pastikan_harian()
        if berkas_backup:
            console.print(f"[dim]Backup harian: {berkas_backup}[/]")

    if perbarui:
        berhasil, pesan = perbarui_kode()
        warna = "green" if berhasil else "yellow"
        console.print(f"[{warna}]Pembaruan kode: {pesan}[/]")

    daftar = situs_terpilih(situs)
    if not daftar:
        console.print(
            "[yellow]Tidak ada situs yang dipilih. Pakai --situs "
            "jobstreet,glints,indeed.[/]"
        )
        return {}

    urutan = ", ".join(NAMA_SITUS[nama] for nama in daftar)
    console.print(f"[cyan]Situs yang dijalankan:[/] {urutan}")
    console.print(
        "[cyan]Kuota:[/] "
        f"{kuota.batas()} lamaran per situs per siklus 24 jam "
        "(hitungan tiap situs terpisah, reset 24 jam sejak lamaran pertama)"
    )
    for baris in kuota.ringkasan_situs(daftar=daftar):
        sisa_teks = (
            f" — reset {baris['berakhir']}" if baris["berakhir"] else ""
        )
        console.print(
            f"[dim]   {baris['nama']}: {baris['terpakai']}/"
            f"{baris['batas']} pada siklus ini{sisa_teks}[/]"
        )

    hasil: dict[str, dict] = {}
    dilewati: dict[str, str] = {}

    for urutan_ke, nama in enumerate(daftar):
        if urutan_ke:
            _lepas_profil_sebelum_situs_berikut()

        if kuota.habis(situs=nama):
            pesan = kuota.pesan_habis(nama)
            dilewati[nama] = pesan
            console.print(f"[yellow]Lewati {NAMA_SITUS[nama]}: {pesan}[/]")
            continue

        console.print()
        console.print(f"[bold cyan]=== {NAMA_SITUS[nama]} ===[/]")

        try:
            hasil[nama] = _jalankan_situs(nama, max_pages, batas)
        except KeyboardInterrupt:
            console.print("\n[yellow]Dihentikan oleh Anda.[/]")
            dilewati[nama] = "dihentikan pengguna"
            break
        except Exception as exc:  # satu situs gagal tidak menghentikan lainnya
            dilewati[nama] = f"gagal: {exc}"
            console.print(f"[bold red]Gagal di {NAMA_SITUS[nama]}:[/] {exc}")
            with contextlib.suppress(Exception):
                notifier.send_error(f"{NAMA_SITUS[nama]}: {exc}")

    _tabel(hasil, dilewati)

    terkirim = sum(data.get("dilamar", 0) for data in hasil.values())
    console.print(f"[bold green]Total terkirim sesi ini: {terkirim}[/]")

    # Target harian dihitung per situs: JobStreet 50, Glints 50, Indeed 50.
    kurang_target = []
    for baris in kuota.ringkasan_situs(daftar=daftar):
        console.print(
            f"[bold]{baris['nama']}:[/] {baris['terpakai']}/{baris['batas']} "
            "lamaran pada siklus ini"
            + (f" (reset {baris['berakhir']})" if baris["berakhir"] else "")
        )
        if baris["sisa"]:
            kurang_target.append(
                f"{baris['nama']} kurang {baris['sisa']}"
            )

    if kurang_target:
        console.print(
            "[yellow]Target 50 belum tercapai:[/] "
            + ", ".join(kurang_target)
            + ". Jalankan sesi lagi dalam siklus yang sama, atau tambah "
            "kata kunci/halaman riset. Slot baru dibuka setelah 24 jam dari "
            "lamaran pertama siklus ini."
        )

    # Ringkasan sesi gabungan semua situs (evaluasi berkala pasal 12.4).
    with contextlib.suppress(Exception):
        db.catat_sesi(
            situs=",".join(sorted(hasil)) or "semua",
            ditemukan=sum(int(d.get("dibaca", 0) or 0) for d in hasil.values()),
            baru=sum(int(d.get("baru", 0) or 0) for d in hasil.values()),
            duplikat=sum(
                int(d.get("duplikat", 0) or 0) for d in hasil.values()
            ),
            dilamar=terkirim,
            gagal=len(dilewati),
            durasi=time.monotonic() - mulai_sesi,
        )

    # Satu laporan harian untuk semua situs.
    try:
        notifier.send_daily_report(db.get_stats())
    except Exception as exc:
        console.print(f"[yellow]Laporan harian gagal dikirim: {exc}[/]")

    # Simpan laporan harian ke reports/ (evaluasi berkala tanpa perlu diingat).
    try:
        import laporan as laporan_modul

        berkas = laporan_modul.simpan()
        console.print(f"[dim]Laporan harian disimpan: {berkas}[/]")
    except Exception as exc:
        console.print(f"[yellow]Laporan harian tidak tersimpan: {exc}[/]")

    return hasil


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lamar otomatis di JobStreet, Glints, dan Indeed sekaligus."
    )
    parser.add_argument("--situs", default="",
                        help="jobstreet,glints,indeed (bawaan: SITES di .env)")
    parser.add_argument("--max-pages", type=int, default=0,
                        help="Halaman riset per kombinasi (0 = ikut .env)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Batas lamaran sesi ini (0 = tanpa batas)")
    parser.add_argument("--tanpa-perbarui", action="store_true",
                        help="Jangan tarik pembaruan kode dari GitHub")
    parser.add_argument("--segar", action="store_true",
                        help="Abaikan cache riset, ambil ulang dari situs")
    arg = parser.parse_args()

    if arg.segar:
        cache_riset.paksa_segar()
        console.print(
            "[cyan]Cache riset dimatikan untuk sesi ini (--segar).[/]"
        )

    jalankan(
        situs=arg.situs,
        max_pages=max(0, arg.max_pages),
        batas=max(0, arg.limit),
        perbarui=not arg.tanpa_perbarui,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
