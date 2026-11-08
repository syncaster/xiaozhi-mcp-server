# gps_mcp.py
# MCP Server untuk GPS data (Xiaozhi)
from mcp.server.fastmcp import FastMCP
import logging
import sys
import json
import time
from typing import Optional

# Fix encoding Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GPS_MCP")

mcp = FastMCP("GPS")

# ==================== DATA GPS (simulasi / ganti dengan real) ====================
# Untuk testing dulu. Nanti diganti dengan data real dari ESP32.
_gps_cache = {
    "latitude": -6.2088,          # contoh Jakarta
    "longitude": 106.8456,
    "altitude": 10.5,             # meter
    "speed": 0.0,                 # km/h
    "course": 0.0,                # derajat
    "satellites": 8,
    "hdop": 1.2,
    "fix": True,
    "timestamp": time.time(),
    "raw_nmea": ""
}

def update_gps_from_device(data: dict):
    """Dipanggil kalau ada data real dari ESP32 (via MQTT / HTTP / WebSocket)."""
    global _gps_cache
    _gps_cache.update(data)
    _gps_cache["timestamp"] = time.time()
    logger.info(f"GPS updated: {_gps_cache}")

# ==================== TOOLS ====================

@mcp.tool()
def get_gps_location() -> dict:
    """
    Ambil posisi GPS saat ini (latitude, longitude, altitude, kecepatan, dll).
    Gunakan tool ini ketika user bertanya 'di mana saya', 'lokasi saya', 'koordinat GPS', atau butuh data lokasi.
    """
    data = _gps_cache.copy()
    if not data.get("fix"):
        return {
            "success": False,
            "message": "GPS belum mendapatkan fix (belum ada sinyal satelit). Coba lagi nanti."
        }
    
    return {
        "success": True,
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "altitude_m": data["altitude"],
        "speed_kmh": data["speed"],
        "course_deg": data["course"],
        "satellites": data["satellites"],
        "hdop": data["hdop"],
        "timestamp": data["timestamp"],
        "maps_url": f"https://www.google.com/maps?q={data['latitude']},{data['longitude']}"
    }

@mcp.tool()
def get_gps_raw() -> dict:
    """Ambil data GPS mentah (NMEA) untuk debugging."""
    return {
        "success": True,
        "raw": _gps_cache.get("raw_nmea", ""),
        "cache": _gps_cache
    }

@mcp.tool()
def set_gps_data(
    latitude: float,
    longitude: float,
    altitude: float = 0.0,
    speed: float = 0.0,
    course: float = 0.0,
    satellites: int = 0,
    hdop: float = 99.0,
    fix: bool = True
) -> dict:
    """
    Update data GPS secara manual (untuk testing atau dari perangkat lain).
    Biasanya dipanggil dari ESP32 via MQTT/HTTP, bukan oleh user langsung.
    """
    update_gps_from_device({
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "speed": speed,
        "course": course,
        "satellites": satellites,
        "hdop": hdop,
        "fix": fix
    })
    return {"success": True, "message": "GPS data updated"}

# ==================== START ====================
if __name__ == "__main__":
    logger.info("GPS MCP Server starting...")
    mcp.run(transport="stdio")