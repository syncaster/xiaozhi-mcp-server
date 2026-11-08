# music_id.py
# Tool MCP untuk MENCARI lagu Indonesia (viral / terpopuler / berdasarkan judul).
#
# Dipakai dengan dua cara:
#   1. Digabung ke kb_search.py (CARA UTAMA, satu server MCP):
#        kb_search.py memanggil music_id.register(mcp) saat start.
#   2. Berdiri sendiri:  python -m music_id
#
# Server ini hanya mencari & menyebutkan judul. Pemutaran dilakukan firmware lewat tool
# self.music.play_url, yang mengambil audio dari music_server.py (lihat README).
#
# Tool:
#   - lagu_viral_indonesia : daftar lagu yang sedang viral di Indonesia
#   - cari_lagu_indonesia  : cek judul/artis yang tepat sebelum diputar
import logging
import os
import sys

import music_common as mc

logger = logging.getLogger("MusicID-MCP")

PETUNJUK = ("Sebutkan beberapa judul secara singkat dan natural dalam bahasa Indonesia "
            "(judul dan artis saja). Jika user memilih atau minta langsung diputar, panggil tool "
            "pemutar di perangkat self.music.play_url dengan stream_url persis dari daftar ini. "
            "Jangan mengubah URL dan jangan menambah lagu yang tidak ada di daftar.")


def _hasil(daftar):
    out = {"success": True, "jumlah": len(daftar),
           "daftar_lagu": [mc.format_ringkas(l) for l in daftar],
           "petunjuk": PETUNJUK}
    if not os.environ.get("MUSIC_PUBLIC_URL", "").strip():
        out["peringatan"] = ("MUSIC_PUBLIC_URL belum diatur di .env, sehingga stream_url kosong "
                             "dan lagu belum bisa diputar di perangkat.")
    return out


def register(mcp):
    """Daftarkan tool musik ke server FastMCP yang sudah ada."""

    @mcp.tool()
    def lagu_viral_indonesia(jumlah: int = 5) -> dict:
        """
        Ambil daftar lagu yang sedang viral / populer di Indonesia (TikTok, YouTube, dst).
        Gunakan saat user meminta lagu viral, lagu yang lagi hits/trending, rekomendasi lagu
        Indonesia, atau minta diputarkan "lagu viral" tanpa menyebut judul.
        Selalu pakai tool ini (bukan pencarian musik bawaan) untuk lagu Indonesia.
        jumlah: banyaknya lagu, 1 sampai 10 (default 5).
        Setelah dapat daftar, tawarkan atau langsung putar lewat self.music.play_url.
        """
        try:
            jumlah = max(1, min(10, int(jumlah)))
        except (TypeError, ValueError):
            jumlah = 5
        logger.info(f"Xiaozhi meminta {jumlah} lagu viral Indonesia")
        try:
            daftar = mc.lagu_viral(jumlah)
        except Exception as e:
            logger.error(f"Gagal mengambil lagu viral: {e}")
            return {"success": False, "result": f"Gagal mengambil daftar lagu viral: {e}"}
        if not daftar:
            return {"success": False, "result": "Belum ada lagu viral yang ditemukan, coba lagi nanti."}
        return _hasil(daftar)

    @mcp.tool()
    def cari_lagu_indonesia(judul: str, artis: str = "") -> dict:
        """
        Cari judul dan artis yang tepat dari sebuah lagu (terutama lagu Indonesia) sebelum diputar.
        Gunakan saat user menyebut judul lagu tertentu, judul yang kurang jelas atau salah ucap,
        atau hanya sebagian judul. Selalu pakai tool ini (bukan pencarian musik bawaan).
        judul: judul atau sebagian judul lagu. artis: opsional.
        """
        logger.info(f"Xiaozhi mencari lagu: '{judul}' / '{artis}'")
        if not (judul or "").strip():
            return {"success": False, "result": "Sebutkan judul lagunya."}
        try:
            daftar = mc.cari_lagu(judul, artis, 3)
        except Exception as e:
            logger.error(f"Gagal mencari lagu: {e}")
            return {"success": False, "result": f"Gagal mencari lagu: {e}"}
        if not daftar:
            return {"success": False, "result": f"Lagu '{judul}' tidak ditemukan."}
        return _hasil(daftar)

    return mcp


if __name__ == "__main__":
    from fastmcp import FastMCP

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    if sys.platform == "win32":
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    register(FastMCP("Musik Indonesia")).run(transport="stdio")
