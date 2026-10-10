"""Small, allowlisted timings from the actual MCP process; never log inputs."""

from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import json
import os
import re
import sys
import threading
import time

from .config import DATA_DIR

LOG_DIR = DATA_DIR / "cache" / "diagnostics"
_lock = threading.Lock()
_current = None
_active = {}


def _windows():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    kernel.SetProcessInformation.argtypes = kernel.GetProcessInformation.argtypes
    return kernel, kernel.GetCurrentProcess()


class PowerState(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ("version", "control_mask", "state_mask")]


def power_state():
    if sys.platform != "win32":
        return None
    try:
        kernel, handle = _windows()
        state = PowerState(1, 0, 0)
        if not kernel.GetProcessInformation(handle, 4, ctypes.byref(state), ctypes.sizeof(state)):
            return dict(error_code=ctypes.get_last_error())
        return dict(control_mask=state.control_mask, state_mask=state.state_mask)
    except (OSError, AttributeError):
        return dict(error_code=-1)


def _set_power(control_mask, state_mask):
    before = power_state()
    success, error = False, None
    if sys.platform == "win32":
        try:
            kernel, handle = _windows()
            state = PowerState(1, control_mask, state_mask)
            success = bool(kernel.SetProcessInformation(handle, 4, ctypes.byref(state), ctypes.sizeof(state)))
            if not success:
                error = ctypes.get_last_error()
        except (OSError, AttributeError):
            error = -1
    return dict(success=success, before=before, after=power_state(), error_code=error)


def configure_execution_speed():
    """Opt this process out of execution-speed throttling, keeping priority."""
    return _set_power(1, 0)


def process_snapshot():
    result = dict(power=power_state())
    if sys.platform != "win32":
        return result
    try:
        kernel, handle = _windows()
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_uint32), ("load_pct", ctypes.c_uint32)] + [
                (name, ctypes.c_uint64) for name in ("total_physical", "available_physical", "total_pagefile",
                                                   "available_pagefile", "total_virtual", "available_virtual", "extended_virtual")]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
            result.update(available_physical_bytes=memory.available_physical, memory_load_pct=memory.load_pct)
        class ProcessMemory(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_uint32), ("page_fault_count", ctypes.c_uint32)] + [
                (name, ctypes.c_size_t) for name in ("peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
                                                   "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile", "private_bytes")]
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        counters = ProcessMemory()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            result.update(page_fault_count=counters.page_fault_count, working_set_bytes=counters.working_set, private_bytes=counters.private_bytes)
    except (OSError, AttributeError):
        result["memory_error"] = True
    return result


def _append(record):
    # Only internal numeric measurements and fixed labels reach this writer.
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _lock, (LOG_DIR / f"mcp-{os.getpid()}.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    except (OSError, ValueError):
        pass  # Diagnostics must never change tool results or availability.


@contextmanager
def call_record(tool, arguments):
    global _current
    fields = arguments if isinstance(arguments, dict) else {}
    record = dict(kind="call", pid=os.getpid(), utc=datetime.now(timezone.utc).isoformat(),
                  tool=tool if isinstance(tool, str) and re.fullmatch(r"gz_[a-z_]{1,40}", tool) else "unknown", stages=[], before=process_snapshot())
    identifier = fields.get("project_id")
    if isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier):
        record["project_id"] = identifier
    for key in ("version", "base_version"):
        if type(fields.get(key)) is int:
            record[key] = fields[key]
    started, cpu = time.perf_counter(), time.process_time()
    stop_sampling = threading.Event()
    memory_samples = [record["before"]]
    def sample_memory():
        while not stop_sampling.wait(.25):
            memory_samples.append(process_snapshot())
    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampling = False
    try:
        sampler.start()
        sampling = True
    except RuntimeError:
        pass
    with _lock:
        _active.clear()
        _current = record
    try:
        yield record
    finally:
        record.update(elapsed_seconds=time.perf_counter() - started, process_cpu_seconds=time.process_time() - cpu, after=process_snapshot())
        stop_sampling.set()
        if sampling:
            sampler.join(timeout=1)
        memory_samples.append(record["after"])
        record["memory_samples"] = len(memory_samples)
        for key, field, aggregate in (("working_set_bytes", "peak_observed_working_set_bytes", max),
                                     ("private_bytes", "peak_observed_private_bytes", max),
                                     ("available_physical_bytes", "min_observed_available_physical_bytes", min)):
            values = [sample[key] for sample in memory_samples if key in sample]
            if values:
                record[field] = aggregate(values)
        with _lock:
            _active.clear()
            _current = None
        _append(record)


@contextmanager
def stage(name):
    with _lock:
        record = _current
        stack = _active.setdefault(threading.get_ident(), [])
        stack.append(name)
    started = time.perf_counter()
    try:
        yield
    finally:
        with _lock:
            stack.pop()
        if record is not None and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            with _lock:
                duration = time.perf_counter() - started
                existing = next((row for row in record["stages"] if row["name"] == name), None)
                if existing is not None:
                    existing["elapsed_seconds"] += duration
                    existing["count"] += 1
                elif len(record["stages"]) < 128:
                    record["stages"].append(dict(name=name, elapsed_seconds=duration, count=1))


def current_stage():
    labels = {
        "compare.site": "正在准备三方案的数据",
        "compare.initial-": "正在计算不同倾角的遮挡和发电量",
        "compare.candidate-": "正在计算不同倾角的遮挡和发电量",
        "compare.capacity.": "正在算「多装」方案（1/3）",
        "compare.payback.": "正在算「最快回本」方案（2/3）",
        "compare.balanced.": "正在算「折中」方案（3/3）",
        "analysis.shading": "正在计算遮挡",
        "analysis.yield": "正在计算发电量",
        "analysis.economics": "正在计算收益",
        "analysis.rules": "正在检查规则",
        "analysis.save": "正在保存分析结果",
        "shading.": "正在计算遮挡",
    }
    with _lock:
        names = [name for stack in _active.values() for name in stack]
    return next((label for prefix, label in labels.items() if any(name.startswith(prefix) for name in names)), "正在准备/计算，请稍候")


def startup():
    """Disable execution throttling once; no background project calculations."""
    _append(dict(kind="startup", pid=os.getpid(), power_change=configure_execution_speed(), snapshot=process_snapshot()))
