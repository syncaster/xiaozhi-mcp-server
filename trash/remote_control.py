# remote_control.py
import sys
import logging
import json
import subprocess
from typing import Dict, Any

from fastmcp import FastMCP

# Logging
logger = logging.getLogger("RemoteControl")
logger.setLevel(logging.INFO)

# Fix encoding Windows
if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

# Inisialisasi MCP Server
mcp = FastMCP("Remote Device Control")

# ==================== TOOL 1: Execute Command ====================
@mcp.tool()
def execute_command(command: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Menjalankan perintah shell di perangkat remote/lokal.
    Gunakan dengan hati-hati! Hanya untuk perintah yang aman.
    """
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timeout"}
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return {"success": False, "error": str(e)}

# ==================== TOOL 2: Get Device Status ====================
@mcp.tool()
def get_device_status() -> Dict[str, Any]:
    """Mendapatkan status dasar perangkat (CPU, Memory, dll)."""
    try:
        # Contoh untuk Linux
        if sys.platform.startswith("linux"):
            cpu = subprocess.getoutput("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'")
            mem = subprocess.getoutput("free -h | awk 'NR==2{print $3 \"/\" $2}'")
            return {
                "success": True,
                "cpu_usage": cpu.strip(),
                "memory": mem.strip(),
                "platform": sys.platform
            }
        else:
            return {
                "success": True,
                "platform": sys.platform,
                "message": "Basic status only"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==================== TOOL 3: Restart Service ====================
@mcp.tool()
def restart_service(service_name: str) -> Dict[str, Any]:
    """Restart service (contoh: nginx, sshd, dll). Hanya untuk sistem yang mendukung systemctl."""
    try:
        result = subprocess.run(
            f"systemctl restart {service_name}", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        return {
            "success": result.returncode == 0,
            "message": f"Service {service_name} restarted",
            "output": result.stdout or result.stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# Run server
if __name__ == "__main__":
    mcp.run(transport="stdio")