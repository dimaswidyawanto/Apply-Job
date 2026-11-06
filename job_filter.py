"""Aturan penyaringan dan pemeringkatan lowongan."""

import contextlib
import re
from typing import Dict, List, Optional

from config import config
from database import db

# Nama lain yang sering dipakai JobStreet untuk satu wilayah.
LOCATION_ALIASES = {
    "bandung": ("kabupaten bandung", "kota bandung"),
    "cimahi": ("cimahi",),
    "jakarta": ("jakarta selatan", "jakarta pusat", "jakarta barat",
                "jakarta timur", "jakarta utara", "jabodetabek"),
    "tangerang": ("tangerang selatan", "serpong", "bsd", "karawaci",
                  "cikupa"),
    "jababeka": ("cikarang", "bekasi", "jababeka"),
    "purwakarta": ("purwakarta",),
    "bogor": ("kabupaten bogor", "kota bogor", "cibinong", "sentul"),
}


AWALAN_PERUSAHAAN = ("pt", "cv", "ud", "pd", "koperasi", "persero", "tbk")

# --- Bobot skor kecocokan (dipakai untuk memilih TOP 50) ---
SKOR_POSISI_KATA_KUNCI = 10   # kata kunci pencarian muncul di judul
SKOR_POSISI_MINAT = 4         # masih satu bidang (TITLE_KEYWORDS) di judul
SKOR_POSISI_MAKS = 30
SKOR_LOKASI = 8               # lokasi termasuk daftar lokasi target
SKOR_LOKASI_TIDAK_DIKETAHUI = 4
SKOR_KUALIFIKASI = 4          # bidang kerja yang diminta ada di deskripsi
SKOR_KUALIFIKASI_MAKS = 8
SKOR_PENGALAMAN = 6
SKOR_PENGALAMAN_TIDAK_DIKETAHUI = 3
SKOR_PENDIDIKAN = 4
SKOR_PENDIDIKAN_TIDAK_DIKETAHUI = 2
SKOR_KETERAMPILAN = 2
SKOR_KETERAMPILAN_MAKS = 8
SKOR_GAJI = 5
SKOR_GAJI_LAYAK = 5


def normalisasi_perusahaan(nama: str) -> str:
    """Bentuk baku nama perusahaan untuk pencocokan longgar."""
    teks = str(nama or "").lower()
    teks = re.sub(r"[^a-z0-9 ]+", " ", teks)
    return " ".join(
        kata for kata in teks.split() if kata not in AWALAN_PERUSAHAAN
    )


def normalisasi_judul(judul: str) -> str:
    """Bentuk baku judul lowongan untuk mendeteksi duplikat."""
    teks = str(judul or "").lower()
    teks = re.sub(r"\(.*?\)", " ", teks)
    teks = re.sub(r"[^a-z0-9 ]+", " ", teks)
    return " ".join(teks.split())


# Satuan yang sering dipakai di kartu lowongan.
_SATUAN_GAJI = (
    ("juta", 1_000_000),
    ("jt", 1_000_000),
    ("rb", 1_000),
    ("ribu", 1_000),
)


def _nilai_gaji(angka: str, satuan: str, ada_satuan_juta: bool) -> float:
    """Ubah satu potongan "2,5jt" / "4.500.000" menjadi rupiah."""
    teks = angka.strip()
    try:
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", teks):
            nilai = float(teks.replace(".", ""))
        elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", teks):
            nilai = float(teks.replace(",", ""))
        elif re.fullmatch(r"\d+,\d+", teks):
            nilai = float(teks.replace(",", "."))
        else:
            nilai = float(teks)
    except ValueError:
        return 0.0

    satuan = (satuan or "").lower()

    for nama, pengali in _SATUAN_GAJI:
        if satuan.startswith(nama):
            return nilai * pengali

    # Tanpa satuan: angka besar sudah rupiah, angka kecil dianggap juta.
    if nilai >= 1_000:
        return nilai
    if ada_satuan_juta or nilai < 100:
        return nilai * 1_000_000
    return nilai


def rentang_gaji(teks: str) -> tuple[int, int]:
    """Rentang gaji (terendah, tertinggi) dari teks kartu lowongan.

    Contoh: "Rp 2-3jt" -> (2_000_000, 3_000_000),
    "Rp 4-4,5jt" -> (4_000_000, 4_500_000),
    "Rp2.000.000 - 3.000.000/Bulan" -> (2_000_000, 3_000_000).
    Teks tanpa angka (mis. "Gaji Tidak Ditampilkan") -> (0, 0).
    """
    isi = str(teks or "").lower()
    if not isi:
        return (0, 0)

    isi = isi.replace("\u2013", "-").replace("\u2014", "-")

    pola = re.compile(
        r"(\d[\d.,]*)\s*(juta|jt|ribu|rb)?",
    )
    ada_juta = bool(re.search(r"\d\s*(?:juta|jt)\b", isi))

    nilai = []
    for cocok in pola.finditer(isi):
        angka, satuan = cocok.group(1), cocok.group(2)
        hasil = _nilai_gaji(angka, satuan, ada_juta)
        if hasil > 0:
            nilai.append(hasil)

    if not nilai:
        return (0, 0)

    return (int(min(nilai)), int(max(nilai)))


def alasan_tidak_layak(job: Dict, saringan: Optional["JobFilter"] = None) -> str:
    """Aturan kelayakan tunggal JobStreet, Glints, dan Indeed.

    Kembalikan alasan penolakan, atau "" bila lowongan layak dilamar. Dipakai
    ketiga situs supaya tidak ada kriteria yang berbeda antarplatform.
    """
    if job.get("sudah_dilamar"):
        return "sudah pernah dilamar"

    job_id = str(job.get("job_id") or "").strip()
    if job_id and db.is_already_applied(job_id):
        return "Sudah tercatat dilamar"

    saringan = saringan or JobFilter()
    lolos, kenapa = saringan.should_apply(job)
    return "" if lolos else kenapa


class JobFilter:
    def __init__(self):
        self.exclude_keywords = [
            k.strip().lower() for k in config.exclude_keywords if k.strip()
        ]
        self.senior_keywords = [
            "senior", "sr.", "lead", "principal", "director", "head of",
            "chief", "vp ", "vice president", "manager",
        ]

    def should_apply(self, job: Dict) -> tuple[bool, str]:
        job_id = str(job.get("job_id") or "").strip()
        title = str(job.get("title") or "").strip()
        company = str(job.get("company") or "").strip()
        description = str(job.get("description") or "")
        salary_text = str(job.get("salary") or "")
        location = str(job.get("location") or "").strip()

        if not title:
            return False, "Judul lowongan tidak terbaca"

        if job_id and db.is_already_applied(job_id):
            return False, "Sudah pernah apply"

        if company:
            dikecualikan = self._perusahaan_dikecualikan(company)
            if dikecualikan:
                return False, f"Perusahaan di-blacklist: {dikecualikan}"

        # Logo/gambar perusahaan (pasal 6.1): WAJIB di JobStreet & Glints.
        # Indeed menandai `logo_diabaikan` karena kartunya tidak memuat logo,
        # jadi lowongan Indeed tidak ikut tertolak.
        if config.require_company_logo and not job.get("logo_diabaikan"):
            if job.get("has_logo") is False:
                return False, "Tanpa logo perusahaan"
            if "has_logo" in job and job["has_logo"] is None:
                # Pasal 6.1: bila validitas gambar tidak dapat dipastikan,
                # lowongan masuk REVIEW_REQUIRED dan tidak langsung dilamar.
                # Field yang tidak ada sama sekali (sumber lama) tidak dihitung
                # "tidak pasti" agar lowongan lama tidak ikut tertahan.
                return False, "Logo tidak dapat dipastikan"

        title_lower = title.lower()

        if config.require_keyword_match and not self._matches_interest(title_lower):
            return False, "Judul tidak sesuai minat"

        for keyword in self.exclude_keywords:
            if keyword in title_lower:
                return False, f"Title mengandung excluded: '{keyword}'"

        for keyword in self.senior_keywords:
            if keyword in title_lower:
                return False, f"Posisi terlalu senior: '{keyword}'"

        age_days = job.get("age_days")
        if (
            config.max_age_days > 0
            and isinstance(age_days, int)
            and age_days > config.max_age_days
        ):
            return False, (
                f"Lowongan lebih lama dari {config.max_age_days} hari"
            )

        if (
            config.strict_location
            and location
            and not self._location_matches(location)
        ):
            daftar = ", ".join(config.locations) or config.location
            return False, f"Lokasi di luar daftar ({daftar}): {location}"

        if config.min_salary > 0 and salary_text:
            parsed_salary = self._parse_salary(salary_text)
            if parsed_salary and parsed_salary < config.min_salary:
                return False, f"Salary terlalu rendah: {parsed_salary:,}"

        exp_years = self._extract_experience(description)
        if exp_years is not None and exp_years > config.max_experience:
            return False, f"Experience terlalu tinggi: {exp_years} tahun"

        return True, "OK"

    def _perusahaan_dikecualikan(self, company: str) -> str:
        """Nama perusahaan yang dikecualikan; "" bila boleh dilamar."""
        nama = normalisasi_perusahaan(company)
        if not nama:
            return ""

        daftar = list(getattr(config, "blocked_companies", []) or [])
        daftar += list(getattr(config, "blacklist_companies", []) or [])

        with contextlib.suppress(Exception):
            daftar += [
                item.get("company_name", "") for item in db.get_blacklist()
            ]

        for item in daftar:
            kunci = normalisasi_perusahaan(item)
            if not kunci:
                continue

            # Nama pendek seperti "ifa" dicocokkan per kata supaya tidak
            # menolak perusahaan lain yang kebetulan memuat huruf sama.
            if len(kunci) <= 4:
                if re.search(rf"\b{re.escape(kunci)}\b", nama):
                    return str(item).strip()
                continue

            if kunci in nama or nama in kunci:
                return str(item).strip()

        return ""

    @staticmethod
    def _matches_interest(title_lower: str) -> bool:
        """Judul harus memuat salah satu kata kunci minat."""
        kata_kunci = config.title_keywords or config.keywords

        for kata in kata_kunci:
            kata = kata.strip().lower()
            if kata and kata in title_lower:
                return True

        return False

    @staticmethod
    def _location_matches(job_location: str) -> bool:
        """Apakah lokasi lowongan termasuk salah satu wilayah yang dicari."""
        text = str(job_location or "").lower()

        if not text:
            return True

        if config.allow_remote and "remote" in text:
            return True

        for target in config.locations:
            key = target.strip().lower()
            if not key:
                continue

            if key in text:
                return True

            for alias in LOCATION_ALIASES.get(key, ()):
                if alias in text:
                    return True

        return False

    @staticmethod
    def _to_number(token: str) -> float:
        """Mengubah potongan angka Indonesia menjadi float.

        Contoh: "7.000.000" -> 7000000, "7,5" -> 7.5, "8500000" -> 8500000.
        """
        token = token.strip()

        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
            return float(token.replace(".", ""))

        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", token):
            return float(token.replace(",", ""))

        if re.fullmatch(r"\d+,\d+", token):
            return float(token.replace(",", "."))

        if re.fullmatch(r"\d+\.\d{1,2}", token):
            return float(token)

        digits = re.sub(r"[^\d]", "", token)
        return float(digits) if digits else 0.0

    def _parse_salary(self, salary_text: str) -> int:
        """Mengambil batas bawah gaji dari teks seperti
        "Rp 7.000.000 – Rp 10.500.000 per month"."""
        text = str(salary_text or "").lower()
        text = re.sub(r"\b(?:rp|idr)\b\.?", " ", text)

        tokens = re.findall(r"\d[\d.,]*", text)
        values = [self._to_number(token) for token in tokens]
        values = [value for value in values if value > 0]

        if not values:
            return 0

        multiplier = 1
        if "juta" in text:
            multiplier = 1_000_000
        elif "ribu" in text or "rb" in text:
            multiplier = 1_000

        salary = int(min(values) * multiplier)

        # Angka kecil tanpa satuan, misal "gaji 8", dianggap satuan juta.
        if multiplier == 1 and salary < 1_000:
            salary *= 1_000_000

        return salary

    def _extract_experience(self, text: str) -> Optional[int]:
        patterns = [
            (
                r"(\d+)\+?\s*(?:years?|tahun)\s*(?:of\s+)?"
                r"(?:experience|pengalaman)"
            ),
            r"(?:minimal?|minimum|at least)\s*(\d+)\s*(?:years?|tahun)",
            r"(\d+)\s*-\s*\d+\s*(?:years?|tahun)",
        ]
        text = str(text or "")
        min_years = None

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                years = int(match.group(1))
                if min_years is None or years < min_years:
                    min_years = years

        return min_years

    def rank_jobs(
        self, jobs: List[Dict], prefer_newest: Optional[bool] = None
    ) -> List[Dict]:
        """Urutkan lowongan. Bila prefer_newest, yang paling baru didahulukan."""
        if prefer_newest is None:
            prefer_newest = config.prefer_newest and bool(config.sort_mode)

        scored_jobs = []

        for job in jobs:
            rincian = self.score_breakdown(job)
            job["_skor_rincian"] = rincian
            job["_score"] = sum(rincian.values())
            scored_jobs.append(job)

        if prefer_newest:
            # Lowongan tanpa info umur ditaruh paling akhir.
            scored_jobs.sort(
                key=lambda item: (
                    item.get("age_days") is None,
                    item.get("age_days") or 0,
                    -item["_score"],
                )
            )
        else:
            # Kecocokan tertinggi dulu; bila skornya sama, yang paling baru.
            scored_jobs.sort(
                key=lambda item: (
                    -item["_score"],
                    item.get("age_days") is None,
                    item.get("age_days") or 0,
                )
            )

        return scored_jobs

    def _calculate_score(self, job: Dict) -> int:
        """Total skor kecocokan (jumlah seluruh dimensi)."""
        return sum(self.score_breakdown(job).values())

    def score_breakdown(self, job: Dict) -> Dict[str, int]:
        """Nilai kecocokan per dimensi.

        Dimensi mengikuti permintaan pengguna: posisi, lokasi, kualifikasi,
        pengalaman, pendidikan, keterampilan, tanggal publikasi, dan gaji.
        Nilai yang tidak bisa dibaca dari kartu lowongan tidak dihukum
        (diberi poin netral), supaya tidak ada lowongan yang gugur hanya
        karena datanya tidak tercantum.
        """
        title = str(job.get("title") or "").lower()
        description = str(job.get("description") or "").lower()
        location = str(job.get("location") or "").strip()
        salary = str(job.get("salary") or "").strip()

        rincian = {
            "posisi": 0,
            "lokasi": 0,
            "kualifikasi": 0,
            "pengalaman": 0,
            "pendidikan": 0,
            "keterampilan": 0,
            "tanggal": 0,
            "gaji": 0,
        }

        # --- 1. Kesesuaian posisi dengan target pekerjaan ---
        skor_posisi = 0
        for keyword in config.keywords:
            kw = keyword.strip().lower()
            if kw and kw in title:
                skor_posisi += SKOR_POSISI_KATA_KUNCI

        if skor_posisi == 0:
            # Tidak persis sama pun, judul yang masih satu bidang tetap
            # dihargai lebih tinggi daripada judul di luar minat.
            for kata in config.title_keywords:
                kata = kata.strip().lower()
                if kata and kata in title:
                    skor_posisi += SKOR_POSISI_MINAT
                    break

        rincian["posisi"] = min(SKOR_POSISI_MAKS, skor_posisi)

        # --- 2. Kesesuaian lokasi ---
        if not location:
            rincian["lokasi"] = SKOR_LOKASI_TIDAK_DIKETAHUI
        elif self._location_matches(location):
            rincian["lokasi"] = SKOR_LOKASI

        # --- 3. Kesesuaian kualifikasi (bidang yang diminta lowongan) ---
        skor_kualifikasi = 0
        for kata in config.title_keywords:
            kata = kata.strip().lower()
            if len(kata) >= 4 and kata in description:
                skor_kualifikasi += SKOR_KUALIFIKASI
        rincian["kualifikasi"] = min(SKOR_KUALIFIKASI_MAKS, skor_kualifikasi)

        # --- 4. Kesesuaian pengalaman kerja ---
        pengalaman = self._extract_experience(description)
        if pengalaman is None:
            rincian["pengalaman"] = SKOR_PENGALAMAN_TIDAK_DIKETAHUI
        elif pengalaman <= config.max_experience:
            rincian["pengalaman"] = SKOR_PENGALAMAN

        # --- 5. Kesesuaian pendidikan ---
        syarat_pendidikan = _peringkat_pendidikan(description)
        milik = _peringkat_pendidikan(config.education_level)
        if syarat_pendidikan is None:
            rincian["pendidikan"] = SKOR_PENDIDIKAN_TIDAK_DIKETAHUI
        elif milik and milik >= syarat_pendidikan:
            rincian["pendidikan"] = SKOR_PENDIDIKAN

        # --- 6. Kesesuaian keterampilan ---
        skor_keterampilan = 0
        for kata in config.skill_keywords:
            kata = kata.strip().lower()
            if kata and kata in description:
                skor_keterampilan += SKOR_KETERAMPILAN
        rincian["keterampilan"] = min(
            SKOR_KETERAMPILAN_MAKS, skor_keterampilan
        )

        # --- 7. Tanggal publikasi (yang paling baru diprioritaskan) ---
        umur = job.get("age_days")
        if isinstance(umur, int):
            if umur <= 0:
                rincian["tanggal"] = 5
            elif umur == 1:
                rincian["tanggal"] = 3
            elif umur <= 3:
                rincian["tanggal"] = 2
            elif umur <= 7:
                rincian["tanggal"] = 1
        else:
            teks_tanggal = str(job.get("date_posted") or "").lower()
            if any(w in teks_tanggal for w in ["hari ini", "today", "baru"]):
                rincian["tanggal"] = 5
            elif any(w in teks_tanggal for w in ["kemarin", "yesterday"]):
                rincian["tanggal"] = 3

        # --- 8. Gaji: tercantum dan memenuhi harapan ---
        if salary and salary != "Tidak disebutkan":
            rincian["gaji"] = SKOR_GAJI
            gaji = rentang_gaji(salary)[1]
            harapan = _angka_rupiah(getattr(config, "expected_salary", ""))
            if gaji and harapan and gaji >= harapan:
                rincian["gaji"] += SKOR_GAJI_LAYAK

        return rincian


def _angka_rupiah(teks: str) -> int:
    """Ubah "5000000" / "5jt" / "Rp 5.000.000" menjadi angka rupiah."""
    teks = str(teks or "").strip().lower()
    if not teks:
        return 0

    juta = "jt" in teks or "juta" in teks
    angka = re.findall(r"\d+(?:[.,]\d+)?", teks)
    if not angka:
        return 0

    try:
        nilai = float(angka[0].replace(".", "").replace(",", "."))
    except ValueError:
        return 0

    if juta or nilai < 100:
        nilai *= 1_000_000

    return int(nilai)


def _peringkat_pendidikan(teks: str) -> Optional[int]:
    """Jenjang pendidikan yang disebut pada teks: 1=SMA/SMK ... 4=S2."""
    teks = str(teks or "").lower()

    for pola, peringkat in (
        (r"\bs2\b|magister|pascasarjana", 4),
        (r"\bs1\b|sarjana|strata 1", 3),
        (r"\bd3\b|diploma|d4", 2),
        (r"\bsma\b|\bsmk\b|smu|setara", 1),
    ):
        if re.search(pola, teks):
            return peringkat

    return None


def kunci_duplikat(job: Dict) -> str:
    """Kunci untuk mengenali lowongan yang sama dari pencarian berbeda."""
    job_id = str(job.get("job_id") or "").strip()
    if job_id:
        return f"id:{job_id}"

    url = str(job.get("url") or "").split("?")[0].split("#")[0].rstrip("/")
    if url:
        return f"url:{url.lower()}"

    judul = normalisasi_judul(job.get("title"))
    perusahaan = normalisasi_perusahaan(job.get("company"))
    lokasi = " ".join(str(job.get("location") or "").lower().split())

    return f"isi:{judul}|{perusahaan}|{lokasi}"


def dedupe_jobs(jobs: List[Dict]) -> List[Dict]:
    """Buang lowongan duplikat dari gabungan semua kategori & lokasi.

    Urutan pertama dipertahankan; lowongan berikutnya dengan kunci sama
    dilewati. Bila yang pertama datanya kurang lengkap, kekurangannya
    diisi dari duplikatnya.
    """
    unik: List[Dict] = []
    terlihat: Dict[str, Dict] = {}

    for job in jobs:
        if not isinstance(job, dict):
            continue

        kunci = kunci_duplikat(job)
        if kunci in terlihat:
            asli = terlihat[kunci]
            for medan in ("company", "location", "salary", "description",
                          "date_posted", "url"):
                if not asli.get(medan) and job.get(medan):
                    asli[medan] = job[medan]
            continue

        terlihat[kunci] = job
        unik.append(job)

    return unik


job_filter = JobFilter()
