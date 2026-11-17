"""Deteksi dinding verifikasi anti-bot (Cloudflare/captcha) pada teks hasil.

Modul ini **tidak** mencoba melewati tantangan apa pun. Tugasnya hanya satu:
menjawab "apakah kegagalan ini karena dinding verifikasi?" supaya bot bisa

1. berhenti dengan rapi (bukan mengulang terus),
2. mencatat status `requires_human` (bukan `error` biasa, bukan `applied`),
3. berhenti mencoba kandidat berikutnya setelah beberapa kegagalan beruntun —
   setiap percobaan yang tertahan tetap memakan waktu,
4. melaporkan bahwa sesi butuh tindakan manusia.

Aturan pemakaian (master prompt pasal 16): CAPTCHA/Cloudflare → PAUSE, LOG,
REQUEST HUMAN ACTION, RESUME AFTER VALIDATION. Tidak ada bypass.
"""

# Status di database untuk lamaran yang tertahan dinding verifikasi.
STATUS_PERLU_MANUSIA = "requires_human"

# Berapa kegagalan blokir berturut-turut sebelum situs dihentikan. Setelah
# angka ini, percobaan berikutnya hampir pasti tertahan juga, dan setiap
# percobaan memakan AUTO_APPLY_STEP_TIMEOUT.
BATAS_BLOKIR_BERHENTI = 3

# Kalimat khas halaman/jendela tantangan. Sengaja sempit: hanya penanda
# Cloudflare/captcha, bukan "akses ditolak" umum yang bisa berarti lain.
TANDA_BLOKIR = (
    "cloudflare",
    "just a moment",
    "tunggu sebentar",
    "verifikasi tambahan",
    "additional verification",
    "melakukan verifikasi",
    "verify you are human",
    "verifikasi anda",
    "attention required",
    "checking your browser",
    "captcha",
    "unusual traffic",
)


def kena_blokir(teks) -> bool:
    """True bila teks (alasan hasil/judul halaman) menunjukkan dinding verifikasi."""
    isi = " ".join(str(teks or "").lower().split())

    if not isi:
        return False

    return any(tanda in isi for tanda in TANDA_BLOKIR)


class PenghitungBlokir:
    """Menghitung kegagalan blokir beruntun untuk satu situs.

    Hasil yang bukan blokir mengembalikan penghitung ke nol, supaya satu
    tantangan yang lewat (diselesaikan manusia) tidak ikut menghentikan situs.
    """

    def __init__(self, batas: int = BATAS_BLOKIR_BERHENTI):
        self.batas = max(1, int(batas or BATAS_BLOKIR_BERHENTI))
        self.jumlah = 0

    def catat(self, blokir: bool) -> bool:
        """Catat satu hasil; True bila situs harus dihentikan."""
        if not blokir:
            self.jumlah = 0
            return False

        self.jumlah += 1
        return self.jumlah >= self.batas

    def reset(self) -> None:
        self.jumlah = 0
