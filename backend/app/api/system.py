"""System status API: CPU, memory, GPU usage."""

import psutil
from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=dict)
async def system_status():
    """Return current system resource usage."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    mem_percent = mem.percent

    gpu_info: dict = {"available": False, "name": "", "memory_used_mb": 0, "memory_total_mb": 0, "utilization": 0, "temperature": 0}
    try:
        from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetName
        from pynvml import nvmlDeviceGetMemoryInfo, nvmlDeviceGetUtilizationRates
        from pynvml import nvmlDeviceGetTemperature, nvmlShutdown, NVML_TEMPERATURE_GPU

        nvmlInit()
        handle = nvmlDeviceGetHandleByIndex(0)
        gpu_info["available"] = True
        gpu_info["name"] = nvmlDeviceGetName(handle)

        mem_info = nvmlDeviceGetMemoryInfo(handle)
        gpu_info["memory_used_mb"] = mem_info.used // (1024 * 1024)
        gpu_info["memory_total_mb"] = mem_info.total // (1024 * 1024)

        util = nvmlDeviceGetUtilizationRates(handle)
        gpu_info["utilization"] = util.gpu

        try:
            temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            gpu_info["temperature"] = temp
        except Exception:
            pass

        nvmlShutdown()
    except Exception:
        pass

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "cpu_percent": cpu_percent,
            "memory_percent": mem_percent,
            "gpu": gpu_info,
        },
    }
