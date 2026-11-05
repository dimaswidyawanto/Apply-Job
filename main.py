import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import MAKS_HALAMAN_RISET, batas_halaman_riset, config
from database import db
from job_filter import dedupe_jobs, job_filter
from notifier import notifier
from scraper import JobStreetBot

console = Console()

# Riset hanya sampai halaman 5 untuk setiap kombinasi kata kunci × lokasi
# (lihat config.MAKS_HALAMAN_RISET). Halaman 6 dan seterusnya tidak pernah
# dibuka — setelah halaman 5 selesai, lanjut ke kata kunci/lokasi berikutnya.
BATAS_HALAMAN_RISET = MAKS_HALAMAN_RISET

# Nama lokasi yang tidak dikenali JobStreet -> nama lain yang hasilnya sama.
# "Jababeka" sering menghasilkan halaman kosong; Cikarang adalah kawasan
# industrinya dan hampir selalu punya hasil.
ALIAS_PENCARIAN = {
    "jababeka": "Cikarang",
    "cikarang": "Bekasi",
}


class AutoApplyEngine:
    def __init__(self):
        self.bot = JobStreetBot()
        self.seen_job_ids = set()
        self.session_stats = {
            "found": 0,
            "new": 0,
            "applied": 0,
            "already": 0,
            "manual": 0,
            "skipped": 0,
            "errors": 0,
        }
        self.manual_jobs = []
        self.stop_requested = False
        self.alias_lokasi = {}
        self.gagal_lokasi = {}
        self._logo_diingatkan = False
        # Duplikat yang muncul lagi dari kata kunci/lokasi lain (dihitung
        # untuk laporan riset).
        self.duplikat_dilewati = 0
        # Pengukuran waktu fase riset (laporan kemajuan & perkiraan sisa).
        self.riset_mulai = 0.0
        self.riset_selesai = 0
        self.riset_total = 0
        self.durasi_riset = 0.0
        self.waktu_halaman = 0.0
        self.jumlah_halaman = 0

    def run(self):
        self._print_banner()
        self._print_config()

        if not config.auto_apply:
            console.print(
                "[bold yellow]Mode manual aktif: setiap lowongan akan "
                "menunggu Enter dan lamaran Anda kirim sendiri. "
                "Pakai `run --auto` (atau AUTO_APPLY=true di .env) untuk "
                "mengirim lamaran otomatis.[/]\n"
            )

        try:
            self.bot.init_browser()

            if not self.bot.login():
                console.print("[bold red]Login belum selesai. Program berhenti.[/]")
                return

            # Riset dulu (kumpulkan → nilai → peringkat → TOP 50) wajib
            # dipakai bila ada batas harian: tanpa riset, "50 terbaik"
            # tidak mungkin ditentukan. Bila batas harian 0, pengguna boleh
            # memilih mode lama (lamar sambil mencari).
            riset_dulu = config.auto_apply and (
                config.collect_before_apply or config.max_apply_per_day > 0
            )

            if riset_dulu:
                if not config.collect_before_apply:
                    console.print(
                        "[dim]Batas harian aktif → riset semua kandidat dulu "
                        "agar yang dilamar benar-benar yang paling cocok.[/]"
                    )
                self._kumpulkan_lalu_lamar()
            else:
                # Melamar sambil mencari, tetap dari posting terbaru.
                self._streaming_halaman()

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Proses dihentikan.[/]")

        except Exception as exc:
            console.print(f"[bold red]Terjadi error: {exc}[/]")
            self.session_stats["errors"] += 1
            notifier.send_error(str(exc))

        finally:
            self.bot.close()
            self._print_results()

            try:
                notifier.send_daily_report(db.get_stats())
            except Exception as exc:
                console.print(f"[yellow]Laporan harian gagal dikirim: {exc}[/]")

    def _satu_halaman(self, keyword: str, page: int, location: str = ""):
        """Cari & saring satu halaman.

        Kembalikan (daftar lowongan siap dilamar, jumlah lowongan terbaca).
        Jumlah 0 berarti halaman itu tidak memuat hasil apa pun.
        """
        mulai_halaman = time.monotonic()
        jobs = self.bot.search_jobs(keyword, page, location=location)
        lama_halaman = time.monotonic() - mulai_halaman
        self.waktu_halaman += lama_halaman
        self.jumlah_halaman += 1

        if lama_halaman >= 10:
            console.print(
                f"[dim]Halaman ini butuh {lama_halaman:.1f} detik "
                "(situs lambat / kartu lama muncul).[/]"
            )

        self._peringatkan_logo(jobs)

        if not jobs:
            console.print(f"Tidak ada lowongan terbaca di halaman {page}.")
            return [], 0

        # Lewati hasil duplikat atau yang tidak memiliki judul/URL/ID.
        new_jobs = []

        for job in jobs:
            title = (job.get("title") or "").strip()
            url = (job.get("url") or "").strip()
            job_id = str(job.get("job_id") or "").strip()

            if not title or not url or not job_id:
                # Tandai supaya lowongan rusak yang sama tidak dihitung
                # berkali-kali untuk setiap kata kunci.
                kunci = job_id or url
                if kunci:
                    self.seen_job_ids.add(kunci)

                console.print(
                    "[yellow]Lowongan dilewati: judul, URL, atau ID tidak terbaca.[/]"
                )
                self.session_stats["skipped"] += 1
                continue

            if job_id in self.seen_job_ids:
                self.duplikat_dilewati += 1
                continue

            self.seen_job_ids.add(job_id)

            # Lowongan yang sudah berlabel Applied / sudah pernah dilamar
            # dilewati diam-diam: tidak ditampilkan dan tidak memakai kuota.
            if job.get("applied") or db.is_already_applied(job_id):
                self.session_stats["already"] += 1

                if job.get("applied"):
                    # Simpan detailnya supaya tetap tampil rapi di riwayat.
                    db.add_job(job)
                    db.record_application(
                        job_id,
                        "already_applied",
                        "Ditandai sudah dilamar di JobStreet",
                    )
                continue

            # Lowongan lama yang belum pernah dilamar tetap ditinjau
            # kembali; yang benar-benar baru dihitung terpisah.
            if db.add_job(job):
                self.session_stats["new"] += 1

            new_jobs.append(job)

        self.session_stats["found"] += len(new_jobs)

        if not new_jobs:
            return [], len(jobs)

        eligible_jobs = []

        for job in new_jobs:
            try:
                should_apply, reason = job_filter.should_apply(job)
            except Exception as exc:
                console.print(
                    f"[yellow]Lowongan dilewati karena gagal diperiksa: {exc}[/]"
                )
                self.session_stats["errors"] += 1
                continue

            if should_apply:
                eligible_jobs.append(job)
            else:
                title = job.get("title", "Tanpa judul")
                console.print(f"[dim]Dilewati: {title[:50]} — {reason}[/]")
                self.session_stats["skipped"] += 1

        eligible_jobs = job_filter.rank_jobs(eligible_jobs)

        console.print(
            f"{len(eligible_jobs)} dari {len(new_jobs)} "
            "lowongan baru lolos filter."
        )

        return eligible_jobs, len(jobs)

    def _peringatkan_logo(self, jobs: list):
        """Ingatkan bila semua kartu di satu halaman terbaca tanpa logo.

        Bila di situs logonya terlihat, berarti aturan deteksi perlu
        disesuaikan — tanpa peringatan ini filter akan diam-diam membuang
        semua lowongan.
        """
        if not config.require_company_logo or self._logo_diingatkan:
            return

        if len(jobs) < 3:
            return

        tanpa_logo = sum(1 for job in jobs if job.get("has_logo") is False)

        if tanpa_logo == len(jobs):
            self._logo_diingatkan = True
            console.print(
                f"[yellow]Semua {len(jobs)} kartu terbaca tanpa logo. Bila di "
                "situs logonya terlihat, jalankan `python cli.py cek-logo` dan "
                "kirimkan tabelnya agar deteksi disesuaikan.[/]"
            )

    def _cari_dengan_alias(self, keyword: str, page: int, location: str):
        """Cari satu halaman; bila lokasi tidak dikenali, coba aliasnya."""
        lokasi = self.alias_lokasi.get(location, location)
        eligible, terbaca = self._satu_halaman(keyword, page, lokasi)

        if terbaca:
            return eligible, terbaca

        cadangan = ALIAS_PENCARIAN.get(location.strip().lower())

        if cadangan and lokasi == location:
            eligible, terbaca = self._satu_halaman(keyword, page, cadangan)
            if terbaca:
                self.alias_lokasi[location] = cadangan
                console.print(
                    f"[dim]Lokasi '{location}' tidak dikenali JobStreet; "
                    f"memakai '{cadangan}'.[/]"
                )

        return eligible, terbaca

    def _catat_lokasi(self, location: str, terbaca: int) -> bool:
        """True bila lokasi sudah tidak layak dilanjutkan."""
        if terbaca:
            self.gagal_lokasi[location] = 0
            return False

        gagal = self.gagal_lokasi.get(location, 0) + 1
        self.gagal_lokasi[location] = gagal

        if gagal >= 3:
            console.print(
                f"[bold yellow]Lokasi '{location}' tidak memberi hasil di "
                "3 kata kunci terakhir — dilewati. Coba nama lain di "
                "LOCATIONS (mis. Cikarang, Bekasi).[/]"
            )
            return True

        return False

    def _cari_keyword(
        self,
        keyword: str,
        location: str = "",
        halaman_maks: Optional[int] = None,
        cek_kuota: bool = True,
    ) -> list:
        """Cari & saring satu kata kunci untuk satu lokasi.

        Maksimal `MAKS_HALAMAN_RISET` (5) halaman: halaman 1 → 5 berurutan,
        lalu berhenti. `halaman_maks` yang lebih besar atau 0 tetap dipakai
        sebagai 5, jadi halaman 6 tidak pernah dibuka.
        """
        if halaman_maks is None:
            halaman_maks = config.max_pages

        halaman_maks = batas_halaman_riset(halaman_maks)

        terkumpul = []

        for page in range(1, halaman_maks + 1):
            if cek_kuota and self._batas_harian_tercapai():
                return terkumpul

            sebelum = len(self.seen_job_ids)
            eligible, terbaca = self._cari_dengan_alias(
                keyword, page, location
            )

            if terbaca == 0:
                break

            # Hasil sudah diurutkan dari yang terbaru: begitu satu halaman
            # tidak memuat lowongan baru, halaman berikutnya pasti lebih lama.
            if page > 1 and len(self.seen_job_ids) == sebelum:
                console.print(
                    "[dim]Halaman ini tidak memuat lowongan baru; "
                    "pencarian kata kunci ini dihentikan.[/]"
                )
                break

            terkumpul.extend(eligible)

        return terkumpul

    def _batas_harian_tercapai(self) -> bool:
        if (
            config.max_apply_per_day > 0
            and db.get_today_apply_count() >= config.max_apply_per_day
        ):
            console.print(
                f"[bold yellow]Batas harian tercapai "
                f"({config.max_apply_per_day}).[/]"
            )
            return True

        return False

    def _lamar(self, job: dict) -> bool:
        """Lamar satu lowongan. False = seluruh sesi harus berhenti."""
        if (
            config.max_apply_per_day > 0
            and db.get_today_apply_count() >= config.max_apply_per_day
        ):
            console.print("[bold yellow]Batas lamaran harian tercapai.[/]")
            return False

        if (
            config.auto_apply
            and config.auto_apply_max_per_session > 0
            and self.session_stats["applied"]
            >= config.auto_apply_max_per_session
        ):
            console.print(
                "[bold yellow]Batas lamaran otomatis per sesi "
                f"({config.auto_apply_max_per_session}) tercapai. "
                "Sisa lowongan dilewati.[/]"
            )
            return False

        title = (job.get("title") or "").strip()

        try:
            # Mode otomatis: bot mengirim lamaran sendiri.
            # Mode manual: halaman dibuka untuk Anda tinjau.
            hasil = self.bot.apply_job(job)

        except KeyboardInterrupt:
            raise

        except Exception as exc:
            console.print(
                f"[bold red]Error saat memproses lowongan "
                f"'{title}': {exc}[/]"
            )
            self.session_stats["errors"] += 1
            return True

        if hasil.status == "login_required":
            self.session_stats["errors"] += 1
            self.stop_requested = True
            console.print(
                "[bold red]Sesi login JobStreet sudah habis. "
                "Sesi dihentikan agar tidak menumpuk error.[/]"
            )
            notifier.send_error("Sesi login JobStreet habis")
            return False

        if hasil.applied:
            self.session_stats["applied"] += 1
            notifier.send_apply_success(job)

        elif hasil.status == "manual_required":
            self.session_stats["manual"] += 1
            self.manual_jobs.append((job, hasil.reason))

        else:
            self.session_stats["skipped"] += 1

        # Jeda hanya untuk lamaran yang benar-benar diproses;
        # lowongan yang dilewati langsung lanjut ke berikutnya.
        delay = max(0, int(config.delay_between_apply))

        if delay and (hasil.applied or hasil.status == "error"):
            console.print(
                f"[dim]Jeda {delay} detik sebelum lowongan berikutnya...[/]"
            )
            time.sleep(delay)

        return True

    def _streaming_halaman(self):
        """Lamar sambil mencari: per halaman, dari posting terbaru.

        Halaman 1 semua kata kunci dan lokasi diselesaikan lebih dulu
        (lowongan paling baru), baru turun ke halaman 2 yang lebih lama.
        """
        selesai = set()
        lokasi_mati = set()

        for page in range(1, config.max_pages + 1):
            for location in config.locations:
                if location in lokasi_mati:
                    continue

                if page == 1:
                    console.print(f"\n[bold blue]{'#' * 60}[/]")
                    console.print(f"[bold blue]LOKASI: {location}[/]")
                    console.print(f"[bold blue]{'#' * 60}[/]")

                for keyword in config.keywords:
                    keyword = keyword.strip()

                    if not keyword or (keyword, location) in selesai:
                        continue

                    if self.stop_requested:
                        return

                    if self._batas_harian_tercapai():
                        return

                    if page == 1:
                        console.print(f"\n{'=' * 60}")
                        console.print(
                            f"[bold]Lokasi: {location} — kata kunci: "
                            f"{keyword}[/]"
                        )
                        console.print(f"{'=' * 60}")

                    eligible, terbaca = self._cari_dengan_alias(
                        keyword, page, location
                    )

                    if terbaca == 0:
                        selesai.add((keyword, location))
                        if self._catat_lokasi(location, terbaca):
                            lokasi_mati.add(location)
                            break
                        continue

                    self._catat_lokasi(location, terbaca)

                    if not eligible and page > 1 and config.sort_mode:
                        selesai.add((keyword, location))

                    for job in eligible:
                        if not self._lamar(job):
                            return

    def _riset_lowongan(self) -> list:
        """Fase riset: kumpulkan sebanyak mungkin lowongan dari semua
        kategori (kata kunci) dan semua lokasi yang ditentukan.

        Riset TIDAK dibatasi 50. Batas 50 hanya berlaku saat mengirim
        lamaran. Hasil gabungan dibersihkan dari duplikat.
        """
        kata_kunci = config.keywords_riset
        halaman = config.research_max_pages
        batas_jobs = config.research_max_jobs

        self.riset_mulai = time.monotonic()
        self.riset_selesai = 0
        self.riset_total = len(config.locations) * len(kata_kunci)
        self.waktu_halaman = 0.0
        self.jumlah_halaman = 0

        console.print(
            f"\n[bold blue]RISET LOWONGAN[/] — {len(kata_kunci)} kata kunci "
            f"× {len(config.locations)} lokasi, maksimal {halaman} halaman "
            f"per kombinasi kata kunci & lokasi "
            f"(batas tetap {MAKS_HALAMAN_RISET}), urut tanggal terbaru."
        )

        kandidat = []
        lokasi_mati = set()

        for location in config.locations:
            if location in lokasi_mati:
                continue

            console.print(f"\n[bold blue]{'#' * 60}[/]")
            console.print(f"[bold blue]LOKASI: {location}[/]")
            console.print(f"[bold blue]{'#' * 60}[/]")

            jumlah_lokasi = 0

            for keyword in kata_kunci:
                keyword = keyword.strip()

                if not keyword:
                    continue

                if self.stop_requested:
                    break

                console.print(f"\n{'=' * 60}")
                console.print(
                    f"[bold]Lokasi: {location} — kata kunci: {keyword}[/]"
                )
                console.print(f"{'=' * 60}")

                hasil = self._cari_keyword(
                    keyword,
                    location=location,
                    halaman_maks=halaman,
                    cek_kuota=False,
                )
                kandidat.extend(hasil)
                jumlah_lokasi += len(hasil)
                self.riset_selesai += 1
                self._lapor_kemajuan(len(kandidat))

                if batas_jobs and len(kandidat) >= batas_jobs:
                    # Potong tepat di batas: satu kata kunci bisa sekaligus
                    # menambah banyak lowongan.
                    kandidat = kandidat[:batas_jobs]
                    console.print(
                        f"[cyan]Batas riset RESEARCH_MAX_JOBS="
                        f"{batas_jobs} tercapai — riset dihentikan.[/]"
                    )
                    break

            # Lokasi yang tidak memberi hasil di beberapa kata kunci terakhir
            # dilewati supaya riset tidak menghabiskan waktu di sana.
            if self._catat_lokasi(location, jumlah_lokasi):
                lokasi_mati.add(location)

            if self.stop_requested or (batas_jobs and len(kandidat) >= batas_jobs):
                break

        unik = dedupe_jobs(kandidat)
        # Duplikat = yang dilewati saat pembacaan (kata kunci/lokasi lain)
        # + yang baru ketahuan setelah digabung.
        dibuang = (len(kandidat) - len(unik)) + self.duplikat_dilewati
        terbaca = len(kandidat) + self.duplikat_dilewati

        console.print(
            f"\n[bold green]Riset selesai:[/] {terbaca} lowongan "
            f"terbaca dari {len(kata_kunci)} kategori × {len(config.locations)} "
            f"lokasi → [bold]{len(unik)} unik[/] "
            f"({dibuang} duplikat dibuang)."
        )

        self.durasi_riset = time.monotonic() - self.riset_mulai

        if self.jumlah_halaman:
            rata = self.waktu_halaman / self.jumlah_halaman
            console.print(
                f"[cyan]Waktu riset:[/] {self._durasi(self.durasi_riset)} "
                f"untuk {self.jumlah_halaman} halaman "
                f"(rata-rata {rata:.1f} detik/halaman, "
                f"{self.riset_total} kombinasi kata kunci × lokasi)."
            )

        if batas_jobs:
            console.print(
                f"[dim]Batas riset aktif: RESEARCH_MAX_JOBS={batas_jobs}.[/]"
            )
        else:
            console.print(
                "[dim]Riset tanpa batas 50 — batas 50 hanya untuk lamaran "
                "yang dikirim hari ini.[/]"
            )

        return unik

    def _kumpulkan_lalu_lamar(self):
        """Riset sebanyak mungkin → dedup → skor → ranking → TOP 50 → lamar."""
        kandidat = self._riset_lowongan()

        if not kandidat:
            console.print(
                "[yellow]Tidak ada lowongan baru yang lolos filter.[/]"
            )
            return

        # Urutkan: kecocokan tertinggi dulu (bawaan) atau posting terbaru.
        urut_terbaru = config.rank_by == "newest"
        kandidat = job_filter.rank_jobs(kandidat, prefer_newest=urut_terbaru)

        keterangan_urut = (
            "posting terbaru" if urut_terbaru else "kecocokan tertinggi"
        )
        console.print(
            f"\n[bold green]Penilaian selesai: {len(kandidat)} lowongan "
            f"dinilai (posisi, lokasi, kualifikasi, pengalaman, pendidikan, "
            f"keterampilan, tanggal, gaji) dan diurutkan dari "
            f"{keterangan_urut}.[/]"
        )

        # Bandingkan dulu, baru lamar: ambil hanya yang terbaik sebanyak sisa
        # kuota hari ini, supaya batas harian dipakai untuk lowongan paling
        # cocok — bukan untuk yang kebetulan ditemukan lebih dulu.
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
                return

            if len(kandidat) > sisa:
                console.print(
                    f"[bold]{len(kandidat)} kandidat[/] (dari seluruh "
                    f"kategori & lokasi) bersaing untuk [bold]{sisa} slot[/] "
                    f"— diambil {sisa} yang paling cocok."
                )
                kandidat = kandidat[:sisa]

        if not kandidat:
            console.print("[yellow]Tidak ada lowongan yang dilamar.[/]")
            return

        self._tampilkan_perbandingan(kandidat)
        self._tampilkan_rincian_skor(kandidat)

        for job in kandidat:
            if self.stop_requested:
                break

            umur = job.get("age_days")
            keterangan = (
                "hari ini" if umur == 0
                else f"{umur} hari lalu" if isinstance(umur, int)
                else "tanggal tak terbaca"
            )
            console.print(
                f"[dim]({keterangan})[/] {job.get('title', '')[:60]}"
            )

            if not self._lamar(job):
                return

    @staticmethod
    def _durasi(detik: float) -> str:
        """Ubah detik menjadi teks singkat: 45s, 5m 12s, 1j 02m 05s."""
        total = max(0, int(detik))
        jam, sisa = divmod(total, 3600)
        menit, detik_ke = divmod(sisa, 60)

        if jam:
            return f"{jam}j {menit:02d}m {detik_ke:02d}s"
        if menit:
            return f"{menit}m {detik_ke:02d}s"
        return f"{detik_ke}s"

    def _lapor_kemajuan(self, terkumpul: int):
        """Perkiraan sisa waktu riset setelah satu kombinasi selesai."""
        if not self.riset_total or not self.riset_mulai:
            return

        lama = time.monotonic() - self.riset_mulai
        per_kombinasi = lama / max(1, self.riset_selesai)
        sisa_kombinasi = max(0, self.riset_total - self.riset_selesai)
        sisa = per_kombinasi * sisa_kombinasi

        console.print(
            f"[dim]Kemajuan riset: {self.riset_selesai}/{self.riset_total} "
            f"kombinasi, {terkumpul} lowongan terkumpul, "
            f"{self._durasi(lama)} berlalu — perkiraan sisa "
            f"{self._durasi(sisa)}.[/]"
        )

    @staticmethod
    def _tampilkan_rincian_skor(kandidat: list, maksimal: int = 3):
        """Tunjukkan dari dimensi mana skor kecocokan kandidat teratas berasal."""
        if not kandidat:
            return

        table = Table(
            title="Rincian skor kandidat teratas",
            show_lines=False,
        )
        table.add_column("Judul", style="cyan", max_width=34)
        for nama in ("Posisi", "Lokasi", "Kualifikasi", "Pengalaman",
                     "Pendidikan", "Keterampilan", "Tanggal", "Gaji", "Total"):
            table.add_column(nama, justify="right", style="dim")

        for job in kandidat[:maksimal]:
            rincian = job.get("_skor_rincian") or {}
            table.add_row(
                str(job.get("title") or "-")[:34],
                *[
                    str(rincian.get(kunci, 0))
                    for kunci in ("posisi", "lokasi", "kualifikasi",
                                  "pengalaman", "pendidikan", "keterampilan",
                                  "tanggal", "gaji")
                ],
                f"[green]{job.get('_score', 0)}[/]",
            )

        console.print(table)

    @staticmethod
    def _tampilkan_perbandingan(kandidat: list, maksimal: int = 10):
        """Tampilkan kandidat teratas beserta skor kecocokannya."""
        if not kandidat:
            return

        table = Table(
            title=f"Kandidat yang akan dilamar (dibandingkan dari {len(kandidat)})",
            show_lines=False,
        )
        table.add_column("#", justify="right", style="dim")
        table.add_column("Skor", justify="right", style="green")
        table.add_column("Judul", style="cyan", max_width=44)
        table.add_column("Perusahaan", max_width=26)
        table.add_column("Umur", style="dim", max_width=14)

        for nomor, job in enumerate(kandidat[:maksimal], start=1):
            umur = job.get("age_days")
            keterangan = (
                "hari ini" if umur == 0
                else f"{umur} hari lalu" if isinstance(umur, int)
                else "-"
            )
            table.add_row(
                str(nomor),
                str(job.get("_score", 0)),
                (job.get("title") or "-")[:44],
                (job.get("company") or "-")[:26],
                keterangan,
            )

        console.print(table)

        if len(kandidat) > maksimal:
            console.print(
                f"[dim]… dan {len(kandidat) - maksimal} lowongan lain di "
                "bawahnya (tidak dilamar pada sesi ini).[/]"
            )

    def _print_banner(self):
        banner = """
    ==========================================
        JobStreet Job Review System
    ==========================================
        """
        console.print(Panel(banner, style="bold blue"))

    def _print_config(self):
        table = Table(title="Konfigurasi", show_header=False)
        table.add_column("Pengaturan", style="cyan")
        table.add_column("Nilai", style="green")

        table.add_row("Kata kunci", ", ".join(config.keywords))
        table.add_row(
            "Lokasi pencarian",
            ", ".join(config.locations) if config.locations else "(semua)",
        )
        table.add_row(
            "Filter judul minat",
            "Aktif" if config.require_keyword_match else "Tidak aktif",
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
        table.add_row(
            "Mode browser",
            "Headless" if config.headless else "Terlihat",
        )
        table.add_row(
            "Mode lamaran",
            "Otomatis" if config.auto_apply
            else "Tinjau dan kirim secara manual",
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
            "Notifikasi Telegram",
            "Aktif" if notifier.enabled else "Tidak aktif",
        )

        console.print(table)
        console.print()

    def _print_results(self):
        console.print(f"\n{'=' * 60}")

        table = Table(title="Hasil Sesi")
        table.add_column("Keterangan", style="cyan")
        table.add_column("Jumlah", style="green", justify="right")

        table.add_row("Lowongan diproses", str(self.session_stats["found"]))
        table.add_row(
            "Lowongan baru di database", str(self.session_stats["new"])
        )
        table.add_row(
            "Lamaran dikonfirmasi terkirim", str(self.session_stats["applied"])
        )
        table.add_row(
            "Sudah dilamar (dilewati)", str(self.session_stats["already"])
        )
        table.add_row(
            "Dilewati (butuh isian khusus)", str(self.session_stats["manual"])
        )
        table.add_row(
            "Dilewati / tidak dikonfirmasi", str(self.session_stats["skipped"])
        )
        table.add_row("Error", str(self.session_stats["errors"]))

        try:
            stats = db.get_stats()
            table.add_row(
                "Total lowongan di database", str(stats["total_jobs_found"])
            )
            table.add_row("Total lamaran tercatat", str(stats["total_applied"]))
            table.add_row("Lamaran tercatat hari ini", str(stats["today_applied"]))
        except Exception as exc:
            console.print(f"[yellow]Statistik database tidak tersedia: {exc}[/]")

        console.print(table)

        if self.manual_jobs:
            console.print(
                "\n[bold yellow]Lowongan yang dilewati otomatis "
                "(tidak perlu Anda kerjakan):[/]"
            )
            for job, reason in self.manual_jobs:
                console.print(
                    f"  • {job.get('title')} — {job.get('company', '')}"
                )
                console.print(f"    {job.get('url')}  [dim]({reason})[/]")


def main():
    AutoApplyEngine().run()


if __name__ == "__main__":
    main()
