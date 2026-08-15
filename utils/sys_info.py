# =============================================================================
# RootForgeKit — Asynchronous System Information Collector
# Uses psutil + platform APIs to gather hardware telemetry in a background
# QThread so the UI never blocks during heavy polling.
# =============================================================================

import platform
import subprocess
import time
from datetime import timedelta

import psutil
from PySide6.QtCore import QThread, Signal


class SystemInfoWorker(QThread):
    """
    Background worker that collects hardware & OS telemetry and emits it
    as a dictionary via the `info_ready` signal.

    Usage:
        worker = SystemInfoWorker()
        worker.info_ready.connect(my_update_function)
        worker.start()
    """
    info_ready = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def stop(self):
        """Signal the thread to stop on next cycle."""
        self._running = False

    def run(self):
        """Collect all system info and emit once. Re-run by calling start() again."""
        if not self._running:
            return
        data = {
            "os": self._get_os_info(),
            "cpu": self._get_cpu_info(),
            "gpu": self._get_gpu_info(),
            "ram": self._get_ram_info(),
            "disks": self._get_disk_info(),
            "network": self._get_network_info(),
            "motherboard": self._get_motherboard_info(),
            "uptime": self._get_uptime(),
        }
        self.info_ready.emit(data)

    # -------------------------------------------------------------------------
    # OS Information
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_os_info() -> dict:
        uname = platform.uname()
        return {
            "system": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "platform": platform.platform(),
        }

    # -------------------------------------------------------------------------
    # CPU Information
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_cpu_info() -> dict:
        freq = psutil.cpu_freq()
        return {
            "name": platform.processor() or "Unknown CPU",
            "physical_cores": psutil.cpu_count(logical=False) or 0,
            "logical_cores": psutil.cpu_count(logical=True) or 0,
            "max_freq_mhz": round(freq.max, 1) if freq and freq.max else 0,
            "current_freq_mhz": round(freq.current, 1) if freq else 0,
            "usage_percent": psutil.cpu_percent(interval=0.5),
        }

    # -------------------------------------------------------------------------
    # GPU Information (best-effort via subprocess)
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_gpu_info() -> list[dict]:
        gpus = []
        system = platform.system()

        # Try NVIDIA first (cross-platform)
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        gpus.append({
                            "name": parts[0],
                            "vram_total_mb": parts[1],
                            "vram_used_mb": parts[2],
                            "temp_c": parts[3],
                        })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Windows fallback: WMIC
        if not gpus and system == "Windows":
            try:
                result = subprocess.run(
                    ["wmic", "path", "win32_videocontroller", "get",
                     "Name,AdapterRAM", "/format:csv"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n")[1:]:
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3 and parts[1]:
                            vram_bytes = int(parts[1]) if parts[1].isdigit() else 0
                            gpus.append({
                                "name": parts[2] if len(parts) > 2 else "Unknown GPU",
                                "vram_total_mb": str(vram_bytes // (1024 * 1024)),
                                "vram_used_mb": "N/A",
                                "temp_c": "N/A",
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
                pass

        # macOS fallback: system_profiler
        if not gpus and system == "Darwin":
            try:
                result = subprocess.run(
                    ["system_profiler", "SPDisplaysDataType"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    name = "Unknown GPU"
                    vram = "N/A"
                    for line in result.stdout.split("\n"):
                        line = line.strip()
                        if "Chipset Model:" in line:
                            name = line.split(":", 1)[1].strip()
                        elif "VRAM" in line:
                            vram = line.split(":", 1)[1].strip()
                    gpus.append({
                        "name": name, "vram_total_mb": vram,
                        "vram_used_mb": "N/A", "temp_c": "N/A",
                    })
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        # Linux fallback: lspci
        if not gpus and system == "Linux":
            try:
                result = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if "VGA" in line or "3D" in line or "Display" in line:
                            gpus.append({
                                "name": line.split(":", 2)[-1].strip() if ":" in line else line,
                                "vram_total_mb": "N/A",
                                "vram_used_mb": "N/A",
                                "temp_c": "N/A",
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        return gpus if gpus else [{"name": "No GPU detected", "vram_total_mb": "N/A",
                                    "vram_used_mb": "N/A", "temp_c": "N/A"}]

    # -------------------------------------------------------------------------
    # RAM Information
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_ram_info() -> dict:
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024 ** 3), 2),
            "used_gb": round(mem.used / (1024 ** 3), 2),
            "available_gb": round(mem.available / (1024 ** 3), 2),
            "percent": mem.percent,
        }

    # -------------------------------------------------------------------------
    # Disk / Storage Information
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_disk_info() -> list[dict]:
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                })
            except PermissionError:
                continue
        return disks

    # -------------------------------------------------------------------------
    # Network Interfaces
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_network_info() -> list[dict]:
        interfaces = []
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for iface, addr_list in addrs.items():
            ipv4 = ""
            mac = ""
            for addr in addr_list:
                if addr.family.name == "AF_INET":
                    ipv4 = addr.address
                elif addr.family.name == "AF_LINK" or addr.family.name == "AF_PACKET":
                    mac = addr.address
            is_up = stats[iface].isup if iface in stats else False
            speed = stats[iface].speed if iface in stats else 0
            interfaces.append({
                "name": iface,
                "ipv4": ipv4,
                "mac": mac,
                "is_up": is_up,
                "speed_mbps": speed,
            })
        return interfaces

    # -------------------------------------------------------------------------
    # Motherboard / BIOS (best-effort)
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_motherboard_info() -> dict:
        info = {"manufacturer": "N/A", "product": "N/A", "bios_vendor": "N/A", "bios_version": "N/A"}
        system = platform.system()

        if system == "Windows":
            try:
                # Baseboard
                res = subprocess.run(
                    ["wmic", "baseboard", "get", "Manufacturer,Product", "/format:csv"],
                    capture_output=True, text=True, timeout=5,
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().split("\n")[1:]:
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3:
                            info["manufacturer"] = parts[1]
                            info["product"] = parts[2]
                # BIOS
                res = subprocess.run(
                    ["wmic", "bios", "get", "Manufacturer,SMBIOSBIOSVersion", "/format:csv"],
                    capture_output=True, text=True, timeout=5,
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().split("\n")[1:]:
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3:
                            info["bios_vendor"] = parts[1]
                            info["bios_version"] = parts[2]
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        elif system == "Linux":
            # Read from /sys/devices/virtual/dmi/id/ (requires root)
            dmi_path = "/sys/devices/virtual/dmi/id"
            mapping = {
                "board_vendor": "manufacturer",
                "board_name": "product",
                "bios_vendor": "bios_vendor",
                "bios_version": "bios_version",
            }
            for filename, key in mapping.items():
                try:
                    with open(f"{dmi_path}/{filename}", "r") as f:
                        info[key] = f.read().strip()
                except (FileNotFoundError, PermissionError):
                    pass

        elif system == "Darwin":
            try:
                res = subprocess.run(
                    ["system_profiler", "SPHardwareDataType"],
                    capture_output=True, text=True, timeout=5,
                )
                if res.returncode == 0:
                    for line in res.stdout.split("\n"):
                        line = line.strip()
                        if "Model Name:" in line:
                            info["product"] = line.split(":", 1)[1].strip()
                        elif "Model Identifier:" in line:
                            info["manufacturer"] = "Apple"
                            info["bios_vendor"] = "Apple"
                # Boot ROM version
                res2 = subprocess.run(
                    ["system_profiler", "SPHardwareDataType"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in res2.stdout.split("\n"):
                    if "Boot ROM Version:" in line:
                        info["bios_version"] = line.split(":", 1)[1].strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        return info

    # -------------------------------------------------------------------------
    # System Uptime
    # -------------------------------------------------------------------------
    @staticmethod
    def _get_uptime() -> str:
        boot_time = psutil.boot_time()
        elapsed = time.time() - boot_time
        return str(timedelta(seconds=int(elapsed)))
