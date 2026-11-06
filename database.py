"""Akses database SQLite untuk lowongan, lamaran, dan blacklist."""

import sqlite3
import threading
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import config

# Status yang dianggap "lowongan sudah pernah dilamar".
APPLIED_STATUSES = ("applied", "already_applied")

# Status yang memakan kuota harian (hanya lamaran yang dikirim alat ini).
QUOTA_STATUSES = ("applied",)

TITLE_FALLBACK = "(judul tidak tersedia)"

# Master prompt pasal 9.2: kuota harian mengikuti WIB (Asia/Jakarta), bukan
# zona waktu komputer. `applied_at` disimpan SQLite dalam UTC, jadi batas hari
# dihitung dalam WIB lalu dikonversi ke UTC sebelum dipakai pada query.
WIB = timezone(timedelta(hours=7))


def rentang_hari_wib(sekarang: Optional[datetime] = None) -> tuple[str, str]:
    """Awal dan akhir hari ini menurut WIB, dalam teks UTC (format SQLite)."""
    kini = sekarang or datetime.now(WIB)
    kini = (
        kini.replace(tzinfo=WIB) if kini.tzinfo is None else kini.astimezone(WIB)
    )

    mulai = kini.replace(hour=0, minute=0, second=0, microsecond=0)
    selesai = mulai + timedelta(days=1)

    format_ = "%Y-%m-%d %H:%M:%S"
    return (
        mulai.astimezone(timezone.utc).strftime(format_),
        selesai.astimezone(timezone.utc).strftime(format_),
    )


# Status antrean lowongan (master prompt pasal 4.2).
STATUS_ANTREAN = (
    "found",
    "collected",
    "filtered",
    "classified",
    "qualified",
    "ready_to_apply",
    "applying",
    "applied",
    "failed",
    "review_required",
    "rejected",
    "expired",
)


def _nilai_logo(nilai) -> int | None:
    """True/False -> 1/0; tidak diketahui (mis. dari situs lain) -> NULL."""
    if nilai is None:
        return None
    return 1 if nilai else 0


class Database:
    def __init__(self, db_path: str | None = None):
        # Path absolut supaya database tidak "hilang" ketika program
        # dijalankan dari folder kerja yang berbeda.
        self.db_path = str(db_path or config.db_path)
        self._conn = None
        self._lock = threading.Lock()
        self._init_db()
        self._aktifkan_wal()

    def _aktifkan_wal(self):
        """WAL + synchronous NORMAL: tulis jauh lebih cepat, tetap aman.

        Tanpa ini setiap simpanan menunggu fsync penuh (puluhan ms), sehingga
        sesi dengan ratusan lowongan terasa lambat.
        """
        try:
            conn = self._koneksi()
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()
        except sqlite3.Error:
            pass

    def _koneksi(self):
        """Satu koneksi yang dipakai ulang.

        Membuat koneksi baru untuk setiap query memakan ~1 ms per operasi —
        pada sesi berisi ratusan lowongan itu jadi beberapa detik terbuang.
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _get_conn(self):
        with self._lock:
            conn = self._koneksi()

            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise


    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT,
                    location TEXT,
                    salary TEXT,
                    description TEXT,
                    url TEXT NOT NULL,
                    date_posted TEXT,
                    has_logo INTEGER,
                    logo_src TEXT,
                    date_scraped TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    status TEXT DEFAULT 'applied',
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    response TEXT,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS blacklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT UNIQUE NOT NULL,
                    reason TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS form_answers (
                    kunci TEXT PRIMARY KEY,
                    pertanyaan TEXT NOT NULL,
                    jawaban TEXT NOT NULL,
                    jenis TEXT DEFAULT '',
                    sumber TEXT DEFAULT 'pengguna',
                    dipakai INTEGER DEFAULT 0,
                    dibuat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    diubah TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_applications_job_id
                    ON applications (job_id);
                CREATE INDEX IF NOT EXISTS idx_applications_status
                    ON applications (status);
                CREATE INDEX IF NOT EXISTS idx_applications_applied_at
                    ON applications (applied_at);
                """
            )
            self._migrate(conn)

    @staticmethod
    def _migrate(conn):
        """Menambahkan kolom yang belum ada pada database versi lama."""
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(applications)")
        }

        for column, definition in (
            ("response", "TEXT"),
            ("notes", "TEXT"),
        ):
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE applications ADD COLUMN {column} {definition}"
                )

        # Kolom tambahan pada tabel lowongan (database versi lama belum punya).
        job_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jobs)")
        }

        for column, definition in (
            ("has_logo", "INTEGER"),
            ("logo_src", "TEXT"),
            # Status antrean & alasan penilaian (master prompt pasal 4.1-4.3).
            ("status_antrean", "TEXT"),
            ("alasan", "TEXT"),
            ("posted_at", "TEXT"),
            ("dikumpulkan_at", "TIMESTAMP"),
            ("diperbarui_at", "TIMESTAMP"),
            ("skor", "REAL"),
        ):
            if column not in job_columns:
                conn.execute(
                    f"ALTER TABLE jobs ADD COLUMN {column} {definition}"
                )

    # ------------------------------------------------------------------
    # Ingatan jawaban formulir
    # ------------------------------------------------------------------
    def simpan_jawaban(self, kunci: str, pertanyaan: str, jawaban: str,
                       jenis: str = "", sumber: str = "pengguna") -> bool:
        """Simpan satu jawaban formulir; jawaban lama untuk kunci itu ditimpa."""
        kunci = str(kunci or "").strip()
        jawaban = str(jawaban or "").strip()

        if not kunci or not jawaban:
            return False

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO form_answers
                    (kunci, pertanyaan, jawaban, jenis, sumber, dipakai)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(kunci) DO UPDATE SET
                    jawaban = excluded.jawaban,
                    pertanyaan = excluded.pertanyaan,
                    jenis = excluded.jenis,
                    sumber = excluded.sumber,
                    diubah = CURRENT_TIMESTAMP
                """,
                (kunci, str(pertanyaan or kunci).strip(), jawaban, jenis, sumber),
            )
        return True

    def cari_jawaban(self, kunci: str) -> Optional[dict]:
        """Ambil satu jawaban berdasarkan kuncinya (None bila belum ada)."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM form_answers WHERE kunci = ?",
                (str(kunci or "").strip(),),
            ).fetchone()

        return dict(row) if row else None

    def daftar_jawaban(self) -> list:
        """Semua jawaban yang tersimpan, terbaru diubah lebih dulu."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM form_answers ORDER BY diubah DESC, kunci ASC"
            ).fetchall()

        return [dict(row) for row in rows]

    def hitung_jawaban(self) -> int:
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS jumlah FROM form_answers"
            ).fetchone()["jumlah"]

    def tandai_jawaban_dipakai(self, kunci: str) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE form_answers
                SET dipakai = dipakai + 1, diubah = diubah
                WHERE kunci = ?
                """,
                (str(kunci or "").strip(),),
            )

    def hapus_jawaban(self, kunci: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM form_answers WHERE kunci = ?",
                (str(kunci or "").strip(),),
            )
            return cur.rowcount > 0

    def reset_jawaban(self) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM form_answers")
            return cur.rowcount

    # ------------------------------------------------------------------
    # Lowongan
    # ------------------------------------------------------------------
    def add_job(self, job_data: dict) -> bool:
        """Menyimpan lowongan. Data yang tidak lengkap ditolak."""
        job_id = str(job_data.get("job_id") or "").strip()
        title = str(job_data.get("title") or "").strip()
        url = str(job_data.get("url") or "").strip()

        # Jangan pernah menyimpan lowongan tanpa judul/URL/ID: baris
        # seperti itu tidak bisa dipakai dan hanya mengotori database.
        if not job_id or not title or not url:
            return False

        with self._get_conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        job_id, title, company, location,
                        salary, description, url, date_posted,
                        has_logo, logo_src,
                        status_antrean, alasan, posted_at, dikumpulkan_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        job_id,
                        title,
                        str(job_data.get("company") or ""),
                        str(job_data.get("location") or ""),
                        str(job_data.get("salary") or ""),
                        str(job_data.get("description") or ""),
                        url,
                        str(job_data.get("date_posted") or ""),
                        _nilai_logo(job_data.get("has_logo")),
                        str(job_data.get("logo_src") or ""),
                        str(job_data.get("status_antrean") or "found"),
                        str(job_data.get("alasan") or ""),
                        str(job_data.get("date_posted") or ""),
                    ),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def set_status_antrean(self, job_id: str, status: str,
                           alasan: str = "", skor: Optional[float] = None) -> bool:
        """Ubah status antrean satu lowongan (pasal 4.2)."""
        job_id = str(job_id or "").strip()
        status = str(status or "").strip().lower()

        if not job_id or status not in STATUS_ANTREAN:
            return False

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                   SET status_antrean = ?,
                       alasan = COALESCE(NULLIF(?, ''), alasan),
                       skor = COALESCE(?, skor),
                       diperbarui_at = CURRENT_TIMESTAMP
                 WHERE job_id = ?
                """,
                (status, str(alasan or ""), skor, job_id),
            )
            return cursor.rowcount > 0

    def hitung_status_antrean(self) -> dict:
        """Jumlah lowongan per status antrean (untuk dashboard)."""
        hasil = {status: 0 for status in STATUS_ANTREAN}

        with self._get_conn() as conn:
            for row in conn.execute(
                """
                SELECT COALESCE(NULLIF(status_antrean, ''), 'found') AS status,
                       COUNT(*) AS jumlah
                  FROM jobs
                 GROUP BY status
                """
            ):
                hasil[str(row["status"])] = int(row["jumlah"])

        return hasil

    def get_job(self, job_id: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ? LIMIT 1", (job_id,)
            ).fetchone()

        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Lamaran
    # ------------------------------------------------------------------
    def is_already_applied(self, job_id: str) -> bool:
        """Status 'applied' maupun 'already_applied' dihitung sudah melamar."""
        job_id = str(job_id or "").strip()

        if not job_id:
            return False

        placeholders = ", ".join("?" for _ in APPLIED_STATUSES)

        with self._get_conn() as conn:
            result = conn.execute(
                f"""
                SELECT 1
                FROM applications
                WHERE job_id = ? AND status IN ({placeholders})
                LIMIT 1
                """,
                (job_id, *APPLIED_STATUSES),
            ).fetchone()

            return result is not None

    def record_application(
        self,
        job_id: str,
        status: str = "applied",
        notes: str = "",
    ):
        """Mencatat lamaran tanpa membuat baris ganda untuk job yang sama."""
        job_id = str(job_id or "").strip()
        status = str(status or "applied").strip().lower() or "applied"

        if not job_id:
            return

        with self._get_conn() as conn:
            if status in APPLIED_STATUSES:
                # Job yang sama cukup dicatat sekali sebagai terkirim.
                placeholders = ", ".join("?" for _ in APPLIED_STATUSES)
                existing = conn.execute(
                    f"""
                    SELECT 1 FROM applications
                    WHERE job_id = ? AND status IN ({placeholders})
                    LIMIT 1
                    """,
                    (job_id, *APPLIED_STATUSES),
                ).fetchone()

                if existing:
                    return

            conn.execute(
                """
                INSERT INTO applications (job_id, status, notes)
                VALUES (?, ?, ?)
                """,
                (job_id, status, notes),
            )

    def get_today_apply_count(self) -> int:
        """Jumlah lamaran terkirim hari ini (dipakai untuk batas harian).

        Hari dihitung menurut WIB (pasal 9.2), bukan zona waktu komputer.
        """
        placeholders = ", ".join("?" for _ in QUOTA_STATUSES)
        mulai, selesai = rentang_hari_wib()

        with self._get_conn() as conn:
            result = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM applications
                WHERE applied_at >= ? AND applied_at < ?
                  AND status IN ({placeholders})
                """,
                (mulai, selesai, *QUOTA_STATUSES),
            ).fetchone()

            return int(result["count"])

    def get_recent_applications(self, limit: int = 50) -> list[dict]:
        """Riwayat lamaran; judul/perusahaan kosong diberi teks pengganti."""
        limit = max(1, int(limit))

        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT a.applied_at,
                       COALESCE(NULLIF(TRIM(j.title), ''), ?) AS title,
                       COALESCE(NULLIF(TRIM(j.company), ''), 'Tidak diketahui')
                           AS company,
                       a.status,
                       COALESCE(j.url, '') AS url
                FROM applications a
                LEFT JOIN jobs j ON a.job_id = j.job_id
                ORDER BY a.applied_at DESC, a.id DESC
                LIMIT ?
                """,
                (TITLE_FALLBACK, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["applied_at"] = str(item.get("applied_at") or "")
            result.append(item)

        return result

    # ------------------------------------------------------------------
    # Blacklist
    # ------------------------------------------------------------------
    def is_blacklisted(self, company_name: str) -> bool:
        company_name = str(company_name or "").strip()

        if not company_name:
            return False

        with self._get_conn() as conn:
            result = conn.execute(
                "SELECT 1 FROM blacklist WHERE company_name = ? LIMIT 1",
                (company_name,),
            ).fetchone()

            return result is not None

    def get_blacklist(self) -> list[dict]:
        """Semua perusahaan yang dikecualikan beserta alasannya."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT company_name, reason FROM blacklist ORDER BY company_name"
            ).fetchall()

        return [dict(row) for row in rows]

    def add_blacklist(self, company_name: str, reason: str = ""):
        company_name = str(company_name or "").strip()

        if not company_name:
            return

        with self._get_conn() as conn, suppress(sqlite3.IntegrityError):
            conn.execute(
                """
                    INSERT INTO blacklist (company_name, reason)
                    VALUES (?, ?)
                    """,
                (company_name, reason),
            )

    # ------------------------------------------------------------------
    # Statistik & perbaikan data
    # ------------------------------------------------------------------
    def get_stats(self) -> dict:
        placeholders = ", ".join("?" for _ in APPLIED_STATUSES)

        with self._get_conn() as conn:
            total_jobs = conn.execute(
                "SELECT COUNT(*) AS count FROM jobs"
            ).fetchone()["count"]

            total_applied = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM applications
                WHERE status IN ({placeholders})
                """,
                APPLIED_STATUSES,
            ).fetchone()["count"]

            mulai, selesai = rentang_hari_wib()
            today_applied = conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM applications
                WHERE applied_at >= ? AND applied_at < ?
                  AND status IN ({placeholders})
                """,
                (mulai, selesai, *APPLIED_STATUSES),
            ).fetchone()["count"]

            return {
                "total_jobs_found": int(total_jobs),
                "total_applied": int(total_applied),
                "today_applied": int(today_applied),
            }

    def repair_data(self) -> dict:
        """Merapikan data lama tanpa menghapus lowongan.

        - Judul/perusahaan/lokasi kosong diisi teks pengganti.
        - Status lamaran dinormalkan (huruf kecil, tanpa spasi).
        - Baris lamaran ganda untuk job yang sama dihapus.
        """
        report = {
            "empty_titles_fixed": 0,
            "empty_companies_fixed": 0,
            "statuses_normalized": 0,
            "duplicate_applications_removed": 0,
        }

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                SET title = ?
                WHERE title IS NULL OR TRIM(title) = ''
                """,
                (TITLE_FALLBACK,),
            )
            report["empty_titles_fixed"] = cursor.rowcount

            cursor = conn.execute(
                """
                UPDATE jobs
                SET company = 'Tidak diketahui'
                WHERE company IS NULL OR TRIM(company) = ''
                """
            )
            report["empty_companies_fixed"] = cursor.rowcount

            cursor = conn.execute(
                """
                UPDATE applications
                SET status = LOWER(TRIM(status))
                WHERE status IS NOT NULL
                  AND status <> LOWER(TRIM(status))
                """
            )
            report["statuses_normalized"] = cursor.rowcount

            placeholders = ", ".join("?" for _ in APPLIED_STATUSES)
            cursor = conn.execute(
                f"""
                DELETE FROM applications
                WHERE status IN ({placeholders})
                  AND id NOT IN (
                      SELECT MIN(id) FROM applications
                      WHERE status IN ({placeholders})
                      GROUP BY job_id
                  )
                """,
                (*APPLIED_STATUSES, *APPLIED_STATUSES),
            )
            report["duplicate_applications_removed"] = max(0, cursor.rowcount)

        return report


db = Database()
