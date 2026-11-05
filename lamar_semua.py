"""Satu klik: perbarui kode, lalu lamar otomatis di JobStreet, Glints, Indeed.

Dipakai oleh "Lamar Otomatis.bat". Alur:

1. (opsional) tarik pembaruan kode dari repo pengembangan,
2. jalankan sesi JobStreet → Glints → Indeed berurutan,
3. kuota harian tetap satu hitungan (`kuota.py`), jadi situs berikutnya hanya
   memakai sisa jatah,
4. kirim **satu** laporan harian Telegram di akhir, bukan tiga.

Semua aturan per situs tetap milik modulnya masing-masing; berkas ini hanya
mengatur urutan dan ringkasan.
"""

import argparse
import contextlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from rich.console import Console
from rich.table import Table

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
CABANG_BAKU = "arena/4ab2b9fa-dimastes"
URL_ARENA = "https://github.com/dimasw1997/dimastes.git"


# --------------------------------------------------------------- pembaruan ---
def _git(*argumen: str, timeout: int = 240) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *argumen],
        cwd=str(AKAR),
        capture_output=True,
        text=True,
        timeout=timeout,
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

        if "Already up to date" in (gabung.stdout or ""):
            return True, "kode sudah paling baru"
        return True, "kode diperbarui"
    except subprocess.TimeoutExpired:
        return False, "pembaruan kelamaan — dilewati"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"pembaruan gagal: {exc}"


# ------------------------------------------------------------------ situs ---
def situs_terpilih(teks: str = "") -> List[str]:
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


def _jalankan_situs(nama: str, max_pages: int, batas: int) -> Dict:
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


# --------------------------------------------------------------- ringkasan ---
def _tabel(hasil: Dict[str, Dict], dilewati: Dict[str, str]) -> None:
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
) -> Dict[str, Dict]:
    """Jalankan seluruh situs terpilih dan kembalikan hasil per situs."""
    console.print("[bold cyan]Lamar otomatis — JobStreet · Glints · Indeed[/]")

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
    console.print(f"[cyan]{kuota.ringkasan()}[/]")

    hasil: Dict[str, Dict] = {}
    dilewati: Dict[str, str] = {}

    for nama in daftar:
        if kuota.habis():
            pesan = kuota.pesan_habis()
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
    console.print(f"[bold]{kuota.ringkasan()}[/]")

    # Satu laporan harian untuk semua situs.
    try:
        notifier.send_daily_report(db.get_stats())
    except Exception as exc:
        console.print(f"[yellow]Laporan harian gagal dikirim: {exc}[/]")

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
    arg = parser.parse_args()

    jalankan(
        situs=arg.situs,
        max_pages=max(0, arg.max_pages),
        batas=max(0, arg.limit),
        perbarui=not arg.tanpa_perbarui,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
