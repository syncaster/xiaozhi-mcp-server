# music_common.py
# Fungsi bersama untuk music_id.py (MCP) dan music_server.py (HTTP streaming).
# Sumber lagu: YouTube (lewat yt-dlp), jadi katalog lagu Indonesia lengkap.
#
# Pengaturan opsional lewat .env:
#   MUSIC_PUBLIC_URL   = alamat music_server.py yang bisa dijangkau ESP32,
#                        mis. http://192.168.100.7:8765
#   VIRAL_PLAYLIST_URL = URL playlist YouTube berisi lagu viral/tangga lagu pilihan Anda.
#                        Jika diisi, daftar "lagu viral" diambil dari playlist ini.
import logging
import os
import re
import sys
import time
from datetime import datetime

_IMPORT_ERROR = None
try:
    import yt_dlp
except Exception as _e:  # simpan penyebab aslinya, jangan disembunyikan
    yt_dlp = None
    _IMPORT_ERROR = _e

logger = logging.getLogger("MusicID")

MIN_DURASI = 90      # detik, buang klip pendek / intro
MAX_DURASI = 420     # detik, buang kompilasi / mix panjang
CACHE_DETIK = 1800   # daftar viral disimpan 30 menit agar respons cepat

# Kata pada judul yang menandakan BUKAN lagu aslinya
BUANG = re.compile(
    r"karaoke|reaction|react\b|full album|playlist|kompilasi|compilation|non[\s-]?stop|"
    r"jedag|tutorial|chord|kunci gitar|instrumental cover",
    re.I,
)
# Keterangan dalam kurung yang dibuang dari judul: (Official Video), [Lyrics], dst.
NOISE = re.compile(
    r"[\(\[\{][^\)\]\}]*(official|video|lyric|lirik|audio|mv|clip|visualizer|live|"
    r"music|HD|HQ|ost)[^\)\]\}]*[\)\]\}]",
    re.I,
)

_cache = {}


def _butuh_ytdlp():
    if yt_dlp is None:
        raise RuntimeError(
            f"yt-dlp tidak bisa dimuat oleh Python ini ({sys.executable}). "
            f"Penyebab: {type(_IMPORT_ERROR).__name__}: {_IMPORT_ERROR}. "
            f"Install di Python yang sama dengan: \"{sys.executable}\" -m pip install -U yt-dlp")


def _bersih_artis(nama):
    nama = re.sub(r"\s*-\s*Topic$", "", nama or "", flags=re.I)
    nama = re.sub(r"(official|vevo|music|channel|records?)\b", "", nama, flags=re.I)
    return " ".join(nama.split()).strip(" -|")


def pisah_judul(judul_mentah, uploader=""):
    """Kembalikan (artis, judul) dari judul video YouTube."""
    j = NOISE.sub("", judul_mentah or "")
    j = j.split("|")[0]
    j = " ".join(j.split()).strip(" -")
    if " - " in j:
        artis, lagu = j.split(" - ", 1)
        return artis.strip(), lagu.strip()
    return _bersih_artis(uploader), j


def _ke_lagu(e):
    artis, lagu = pisah_judul(e.get("title", ""), e.get("uploader") or e.get("channel") or "")
    vid = e.get("id", "")
    return {
        "id": vid,
        "artis": artis,
        "judul": lagu,
        "durasi": int(e.get("duration") or 0),
        "views": int(e.get("view_count") or 0),
        "judul_asli": e.get("title", ""),
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def _layak(lagu):
    if not re.fullmatch(r"[\w-]{11}", lagu["id"] or ""):
        return False
    if BUANG.search(lagu["judul_asli"]):
        return False
    d = lagu["durasi"]
    return d == 0 or MIN_DURASI <= d <= MAX_DURASI  # 0 = durasi tidak diketahui


def cari_youtube(query, n=10):
    """Cari lagu di YouTube (tanpa mengunduh). Return list lagu yang sudah disaring."""
    _butuh_ytdlp()
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
            "skip_download": True, "socket_timeout": 15}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{int(n)}:{query}", download=False)
    hasil = [_ke_lagu(e) for e in (info or {}).get("entries") or [] if e]
    return [l for l in hasil if _layak(l)]


def _dedupe(daftar):
    lihat, out = set(), []
    for l in daftar:
        kunci = re.sub(r"[^a-z0-9]+", "", l["judul"].lower())
        if kunci and kunci not in lihat:
            lihat.add(kunci)
            out.append(l)
    return out


def _dari_playlist(url, n):
    _butuh_ytdlp()
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
            "skip_download": True, "playlistend": int(n) * 2, "socket_timeout": 15}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return [_ke_lagu(e) for e in (info or {}).get("entries") or [] if e]


def lagu_viral(n=10):
    """Daftar lagu yang sedang viral di Indonesia."""
    n = max(1, min(20, int(n)))
    kunci = ("viral", n)
    if kunci in _cache and time.time() - _cache[kunci][0] < CACHE_DETIK:
        return _cache[kunci][1]

    hasil = []
    playlist = os.environ.get("VIRAL_PLAYLIST_URL", "").strip()
    if playlist:
        try:
            hasil = [l for l in _dari_playlist(playlist, n) if _layak(l)]  # urutan playlist dipertahankan
        except Exception as e:
            logger.warning(f"Playlist viral gagal dibaca: {e}")

    if not hasil:
        tahun = datetime.now().year
        queries = [
            f"lagu viral tiktok indonesia {tahun}",
            f"lagu indonesia terpopuler {tahun}",
            f"top hits indonesia terbaru {tahun}",
        ]
        kumpul = []
        for q in queries:
            try:
                kumpul.extend(cari_youtube(q, 12))
            except Exception as e:
                logger.warning(f"Pencarian '{q}' gagal: {e}")
        hasil = sorted(_dedupe(kumpul), key=lambda l: l["views"], reverse=True)

    hasil = _dedupe(hasil)[:n]
    if hasil:
        _cache[kunci] = (time.time(), hasil)
    return hasil


def cari_lagu(judul, artis="", n=5):
    q = f"{artis} {judul}".strip()
    return _dedupe(cari_youtube(q, max(n, 5)))[:n]


def stream_url(vid):
    """Alamat stream Opus di music_server.py, mis. http://192.168.100.7:8765/opus/<id>.bin
    Butuh MUSIC_PUBLIC_URL di .env. Kosong jika belum diatur."""
    base = os.environ.get("MUSIC_PUBLIC_URL", "").strip().rstrip("/")
    return f"{base}/opus/{vid}.bin" if base else ""


def format_ringkas(l):
    out = {"judul": l["judul"], "artis": l["artis"], "id": l["id"]}
    url = stream_url(l["id"])
    if url:
        out["stream_url"] = url
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    for i, l in enumerate(lagu_viral(10), 1):
        print(f"{i}. {l['artis']} - {l['judul']}  ({l['views']:,} views)")
