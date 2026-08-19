import os
import sys
import platform
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class HardwareProfile:
    cpu_count: int
    total_ram_gb: float
    available_ram_gb: float
    gpu_name: Optional[str]
    gpu_vram_gb: float
    has_cuda: bool
    is_capable_for_local_ocr: bool
    recommended_mode: str  # "gpu", "cpu_high", "cpu_light", "online_only"
    recommended_threads: int
    enable_mkldnn: bool
    status_summary: str
    warning_reason: Optional[str] = None


def _get_ram_windows() -> Tuple[float, float]:
    """Lấy thông tin RAM trên Windows thông qua Windows API (GlobalMemoryStatusEx)."""
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total_gb = stat.ullTotalPhys / (1024 ** 3)
            avail_gb = stat.ullAvailPhys / (1024 ** 3)
            return round(total_gb, 2), round(avail_gb, 2)
    except Exception as e:
        logger.debug("Lỗi lấy RAM qua ctypes: %s", e)

    # Fallback nếu psutil có sẵn
    try:
        import psutil
        vm = psutil.virtual_memory()
        return round(vm.total / (1024 ** 3), 2), round(vm.available / (1024 ** 3), 2)
    except Exception:
        pass

    return 8.0, 4.0  # Mặc định an toàn


def _get_gpu_info() -> Tuple[Optional[str], float, bool]:
    """Kiểm tra sự hiện diện của NVIDIA GPU / CUDA."""
    try:
        # Thử chạy nvidia-smi để lấy tên GPU và VRAM
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            lines = res.stdout.strip().split("\n")
            if lines:
                parts = lines[0].split(",")
                gpu_name = parts[0].strip()
                vram_mb = float(parts[1].strip()) if len(parts) > 1 else 0
                vram_gb = round(vram_mb / 1024.0, 2)
                return gpu_name, vram_gb, True
    except Exception:
        pass

    # Kiểm tra qua PyTorch / Paddle nếu có
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2)
            return name, vram_gb, True
    except Exception:
        pass

    return None, 0.0, False


def assess_hardware() -> HardwareProfile:
    """
    Tự động quét phần cứng máy tính và đưa ra cấu hình tối ưu cho PaddleOCR / PP-Structure:
    - Nếu RAM < 4GB hoặc CPU < 2 cores -> Đánh giá quá yếu, chuyển sang Online VLM.
    - Nếu có GPU CUDA >= 4GB VRAM -> Kích hoạt chế độ GPU Acceleration.
    - Nếu chạy CPU -> Tối ưu số luồng (cpu_threads) và bật MKLDNN.
    """
    cpu_count = os.cpu_count() or 1
    total_ram, avail_ram = _get_ram_windows()
    gpu_name, gpu_vram, has_cuda = _get_gpu_info()

    # Điều kiện đánh giá máy tính quá yếu:
    # 1. Tổng RAM < 4.0 GB hoặc RAM khả dụng < 1.5 GB
    # 2. Hoặc số luồng CPU < 2
    if total_ram < 3.8 or avail_ram < 1.4 or cpu_count < 2:
        reason = (
            f"RAM quá thấp ({total_ram} GB total, {avail_ram} GB khả dụng) "
            f"hoặc CPU quá yếu ({cpu_count} cores)."
        )
        return HardwareProfile(
            cpu_count=cpu_count,
            total_ram_gb=total_ram,
            available_ram_gb=avail_ram,
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram,
            has_cuda=has_cuda,
            is_capable_for_local_ocr=False,
            recommended_mode="online_only",
            recommended_threads=1,
            enable_mkldnn=False,
            status_summary="Cấu hình quá yếu cho Local OCR - Đã tự động kích hoạt Online VLM OCR",
            warning_reason=reason,
        )

    # Có GPU NVIDIA hỗ trợ CUDA
    if has_cuda and gpu_vram >= 3.0:
        return HardwareProfile(
            cpu_count=cpu_count,
            total_ram_gb=total_ram,
            available_ram_gb=avail_ram,
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram,
            has_cuda=True,
            is_capable_for_local_ocr=True,
            recommended_mode="gpu",
            recommended_threads=min(4, cpu_count),
            enable_mkldnn=False,
            status_summary=f"Kích hoạt GPU Acceleration ({gpu_name} - {gpu_vram}GB VRAM)",
        )

    # Chạy trên CPU mạnh (RAM >= 8GB, CPU >= 4 cores)
    if total_ram >= 7.5 and cpu_count >= 4:
        threads = min(8, max(2, cpu_count - 2))
        return HardwareProfile(
            cpu_count=cpu_count,
            total_ram_gb=total_ram,
            available_ram_gb=avail_ram,
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram,
            has_cuda=False,
            is_capable_for_local_ocr=True,
            recommended_mode="cpu_high",
            recommended_threads=threads,
            enable_mkldnn=True,
            status_summary=f"Kích hoạt CPU High-Performance (MKLDNN On, {threads} threads)",
        )

    # Chạy trên CPU trung bình (RAM 4GB - 8GB)
    threads = min(2, cpu_count)
    return HardwareProfile(
        cpu_count=cpu_count,
        total_ram_gb=total_ram,
        available_ram_gb=avail_ram,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram,
        has_cuda=False,
        is_capable_for_local_ocr=True,
        recommended_mode="cpu_light",
        recommended_threads=threads,
        enable_mkldnn=False,
        status_summary=f"Kích hoạt CPU Lightweight Mode ({threads} threads)",
    )


_cached_profile: Optional[HardwareProfile] = None


def get_system_hardware() -> HardwareProfile:
    """Trả về HardwareProfile dạng singleton."""
    global _cached_profile
    if _cached_profile is None:
        _cached_profile = assess_hardware()
    return _cached_profile
