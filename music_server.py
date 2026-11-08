# music_server.py
# Server musik lokal (HTTP) pengganti server musik Tiongkok untuk firmware Xiaozhi-music.
#
# Alur:
#   ESP32 --GET /stream_pcm?song=..&artist=..--> JSON {title, artist, audio_url, lyric_url}
#   ESP32 --GET /audio/<id>.mp3-->  MP3 stream (YouTube -> yt-dlp -> ffmpeg -> MP3)
#   ESP32 --GET /opus/<id>.bin?rate=24000&frame=60--> paket Opus berframe (dipakai firmware, hemat bandwidth)
#   (opsional) /pcm/<id>.pcm = PCM mentah
#
# Jalankan di PC/server yang satu jaringan WiFi dengan ESP32:
#   python music_server.py            (port default 8765, ubah dengan MUSIC_PORT di .env)
#
# Syarat: pip install flask yt-dlp   dan   ffmpeg ada di PATH.
import logging
import os
import re
import subprocess
import sys
import time

from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request

load_dotenv()

import music_common as mc  # noqa: E402  (setelah load_dotenv agar env terbaca)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - MusicServer - %(message)s")
logger = logging.getLogger("MusicServer")

app = Flask(__name__)

PORT = int(os.environ.get("MUSIC_PORT", "8765"))
BITRATE = os.environ.get("MUSIC_BITRATE", "128k")        # untuk /audio (MP3)
OPUS_BITRATE = os.environ.get("MUSIC_OPUS_BITRATE", "48k")  # untuk /opus (dipakai ESP32)
URL_CACHE_DETIK = 600          # URL audio YouTube dipakai ulang 10 menit
_meta_cache = {}               # id -> (waktu, info)


def _resolve_audio(vid):
    """Dapatkan URL audio langsung dari YouTube untuk video id tertentu."""
    now = time.time()
    if vid in _meta_cache and now - _meta_cache[vid][0] < URL_CACHE_DETIK:
        return _meta_cache[vid][1]
    mc._butuh_ytdlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "format": "bestaudio/best", "socket_timeout": 15}
    with mc.yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    _meta_cache[vid] = (now, info)
    return info


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/stream_pcm")
def stream_pcm():
    """Cari lagu dan kembalikan metadata + alamat audio (pola sama dengan server musik asli)."""
    song = (request.args.get("song") or "").strip()
    artist = (request.args.get("artist") or "").strip()
    logger.info(f"Permintaan lagu: song='{song}' artist='{artist}' dari {request.remote_addr}")
    if not song:
        return jsonify({"error": "parameter song kosong"}), 400
    try:
        hasil = mc.cari_lagu(song, artist, 1)
    except Exception as e:
        logger.error(f"Pencarian gagal: {e}")
        return jsonify({"error": str(e)}), 502
    if not hasil:
        return jsonify({"error": "lagu tidak ditemukan"}), 404

    lagu = hasil[0]
    base = request.host_url.rstrip("/")   # alamat server ini sesuai yang dipakai ESP32
    logger.info(f"-> {lagu['artis']} - {lagu['judul']} ({lagu['id']})")
    return jsonify({
        "artist": lagu["artis"],
        "title": lagu["judul"],
        "audio_url": f"{base}/audio/{lagu['id']}.mp3",
        "lyric_url": f"{base}/lyric/{lagu['id']}.lrc",
    })


@app.get("/lyric/<vid>.lrc")
def lyric(vid):
    """Lirik belum tersedia; kirim satu baris LRC berisi judul agar firmware tidak error."""
    if not re.fullmatch(r"[\w-]{11}", vid):
        abort(400)
    judul = request.args.get("t", "")
    return Response(f"[00:00.00]{judul}\n", mimetype="text/plain; charset=utf-8")


def _ffmpeg_stream(vid, out_args, mimetype, transform=None):
    """Ambil audio YouTube untuk video id, ubah dengan ffmpeg, lalu alirkan ke klien."""
    if not re.fullmatch(r"[\w-]{11}", vid):
        abort(400)
    try:
        info = _resolve_audio(vid)
    except Exception as e:
        logger.error(f"Gagal mengambil audio {vid}: {e}")
        abort(502)

    headers = info.get("http_headers") or {}
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
           "-user_agent", headers.get("User-Agent", "Mozilla/5.0"),
           "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
           "-i", info["url"], "-vn", *out_args, "pipe:1"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        logger.error("ffmpeg tidak ditemukan di PATH")
        abort(500)
    logger.info(f"Streaming dimulai: {vid} ({info.get('title', '')})")

    def alir():
        try:
            if transform:
                yield from transform(proc.stdout)
            else:
                while True:
                    potongan = proc.stdout.read(4096)
                    if not potongan:
                        break
                    yield potongan
        finally:               # ESP32 berhenti/ganti lagu -> hentikan ffmpeg
            proc.kill()
            logger.info(f"Streaming selesai: {vid}")

    return Response(alir(), mimetype=mimetype, headers={"Cache-Control": "no-store"})


def ogg_opus_packets(stream):
    """Baca stream Ogg-Opus dan hasilkan paket Opus satu per satu (tanpa 2 paket header)."""
    def baca(n):
        buf = b""
        while len(buf) < n:
            c = stream.read(n - len(buf))
            if not c:
                return None
            buf += c
        return buf

    sisa, lewati = b"", 2          # paket 1-2 = OpusHead & OpusTags
    while True:
        h = baca(27)
        if h is None or h[:4] != b"OggS":
            return
        tabel = baca(h[26])
        if tabel is None:
            return
        isi = baca(sum(tabel))
        if isi is None:
            return
        pos = 0
        for lace in tabel:
            sisa += isi[pos:pos + lace]
            pos += lace
            if lace < 255:         # paket selesai
                if lewati:
                    lewati -= 1
                else:
                    yield sisa
                sisa = b""


def opus_berframe(stream):
    """Format ke ESP32: setiap paket diawali panjangnya (2 byte, big-endian)."""
    for paket in ogg_opus_packets(stream):
        yield len(paket).to_bytes(2, "big") + paket


@app.get("/audio/<vid>.mp3")
def audio(vid):
    """Alirkan audio sebagai MP3 (untuk pemutar yang punya decoder MP3)."""
    return _ffmpeg_stream(vid, ["-ac", "2", "-ar", "44100", "-c:a", "libmp3lame",
                                "-b:a", BITRATE, "-f", "mp3"], "audio/mpeg")


@app.get("/opus/<vid>.bin")
def opus(vid):
    """Alirkan paket Opus berframe [2 byte panjang][paket]... untuk dimasukkan langsung ke
    decoder Opus ESP32 (jalur yang sama dengan suara AI). Parameter: rate (default 24000),
    frame = durasi frame ms (default 60)."""
    try:
        rate = int(request.args.get("rate", 24000))
        frame = int(request.args.get("frame", 60))
    except ValueError:
        abort(400)
    if rate not in (8000, 12000, 16000, 24000, 48000) or frame not in (20, 40, 60):
        abort(400)
    args = ["-ac", "1", "-ar", str(rate), "-c:a", "libopus", "-application", "audio",
            "-b:a", OPUS_BITRATE, "-vbr", "on", "-frame_duration", str(frame),
            "-page_duration", "120000", "-f", "ogg"]
    return _ffmpeg_stream(vid, args, "application/octet-stream", transform=opus_berframe)


@app.get("/pcm/<vid>.pcm")
def pcm(vid):
    """Alirkan audio sebagai PCM 16-bit mentah (tanpa header), langsung bisa ditulis ke speaker.
    Parameter: rate = sample rate speaker ESP32 (default 24000), ch = 1 (mono) atau 2."""
    try:
        rate = int(request.args.get("rate", 24000))
        ch = int(request.args.get("ch", 1))
    except ValueError:
        abort(400)
    if rate not in (8000, 16000, 22050, 24000, 32000, 44100, 48000) or ch not in (1, 2):
        abort(400)
    return _ffmpeg_stream(vid, ["-ac", str(ch), "-ar", str(rate), "-f", "s16le"],
                          "application/octet-stream")


if __name__ == "__main__":
    logger.info(f"Server musik berjalan di port {PORT}. Gunakan http://<IP-PC-Anda>:{PORT} di firmware.")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
