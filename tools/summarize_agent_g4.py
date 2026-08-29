#!/usr/bin/env python3
# Copyright (c) 2026-present Ngo Quoc Huy
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Produce bounded, secret-sanitized summaries for a successful G4 stage log."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REDACTIONS = (
    (re.compile(r"(?i)(bearer\s+)[^\s,}]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(://[^/:\s]+:)[^@\s]+(@)"), r"\1[REDACTED]\2"),
    (re.compile(r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization|credential)\s*[=:]\s*)[^\s,}]+"), r"\1[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[REDACTED_JWT]"),
)
COUNT_PATTERNS = {
    "passed": re.compile(r"(?<![A-Za-z0-9_])(\d+)\s+passed\b", re.IGNORECASE),
    "failed": re.compile(r"(?<![A-Za-z0-9_])(\d+)\s+failed\b", re.IGNORECASE),
    "skipped": re.compile(r"(?<![A-Za-z0-9_])(\d+)\s+skipped\b", re.IGNORECASE),
    "xfail": re.compile(r"(?<![A-Za-z0-9_])(\d+)\s+xfailed\b|(?<![A-Za-z0-9_])(\d+)\s+xfail\b", re.IGNORECASE),
    "deselected": re.compile(r"(?<![A-Za-z0-9_])(\d+)\s+deselected\b", re.IGNORECASE),
}
METRIC_PATTERNS = {
    "workload_throughput": re.compile(r"\b(?:throughput|requests_per_second|rps)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "workload_latency_p95_ms": re.compile(r"\b(?:latency_p95_ms|p95_latency_ms)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "workload_latency_p99_ms": re.compile(r"\b(?:latency_p99_ms|p99_latency_ms)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "workload_error_rate": re.compile(r"\b(?:error_rate|errors_per_request)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "workload_saturation": re.compile(r"\b(?:saturation|saturation_ratio)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "workload_queue_p95_ms": re.compile(r"\b(?:queue_p95_ms|queueing_p95_ms)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "workload_sustained_duration_s": re.compile(r"\b(?:sustained_duration_s|sustained_seconds)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "resource_cpu_pct": re.compile(r"\b(?:cpu_pct|cpu_percent)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "resource_cpu_seconds": re.compile(r"\b(?:cpu_seconds|cpu_sec)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "resource_memory_mb": re.compile(r"\b(?:memory_mb|rss_mb)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "resource_db_connections": re.compile(r"\b(?:db_connections|database_connections)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "resource_io_mb": re.compile(r"\b(?:io_mb|disk_io_mb)=([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
}


def sanitize(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _json_summary(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("summary"), dict):
        return None
    return value["summary"]


def _json_stage_result(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for line in reversed(text.splitlines()):
        for start, character in enumerate(line):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(line[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("event") in {"agent.g4.gateway.load", "agent.g4.rollback"}:
                return value
    return None


def _numeric(value: Any, default: str = "na") -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return str(value)


def summarize(text: str) -> dict[str, str]:
    sanitized = sanitize(text)
    result = {
        "collected": "1",
        "passed": "1",
        "failed": "0",
        "skipped": "0",
        "xfail": "0",
        "deselected": "0",
        "duration_ms": "0",
        "migration_leaf": "not_applicable",
        "workload_throughput": "na",
        "workload_latency_p95_ms": "na",
        "workload_latency_p99_ms": "na",
        "workload_error_rate": "na",
        "workload_saturation": "na",
        "workload_queue_p95_ms": "na",
        "workload_sustained_duration_s": "na",
        "workload_requests": "na",
        "workload_workers": "na",
        "workload_agents": "na",
        "resource_cpu_pct": "na",
        "resource_cpu_seconds": "na",
        "resource_memory_mb": "na",
        "resource_db_connections": "na",
        "resource_io_mb": "na",
        "evidence_sha256": hashlib.sha256(sanitized.encode("utf-8")).hexdigest(),
    }
    structured = _json_summary(text)
    if structured is not None:
        counts = structured.get("counts", {})
        for key in ("collected", "passed", "failed", "skipped", "xfail", "deselected"):
            if isinstance(counts.get(key), int) and counts[key] >= 0:
                result[key] = str(counts[key])
        result["duration_ms"] = _numeric(structured.get("durationMs"), result["duration_ms"])
        if isinstance(structured.get("migrationLeaf"), str):
            result["migration_leaf"] = structured["migrationLeaf"]
        workload = structured.get("workload", {})
        if isinstance(workload, dict):
            for key in METRIC_PATTERNS:
                json_key = key.removeprefix("workload_").removeprefix("resource_")
                aliases = {
                    "throughput": "throughput",
                    "latency_p95_ms": "latencyP95Ms",
                    "error_rate": "errorRate",
                    "saturation": "saturation",
                    "cpu_pct": "cpuPct",
                    "memory_mb": "memoryMb",
                    "io_mb": "ioMb",
                }
                result[key] = _numeric(workload.get(aliases.get(json_key, json_key)), result[key])
        return result

    stage_result = _json_stage_result(text)
    if stage_result is not None:
        result["workload_requests"] = _numeric(stage_result.get("requests"), result["workload_requests"])
        result["workload_workers"] = _numeric(stage_result.get("workers"), result["workload_workers"])
        result["workload_agents"] = _numeric(stage_result.get("agents"), result["workload_agents"])
        result["workload_throughput"] = _numeric(
            stage_result.get("throughputPerSecond"), result["workload_throughput"]
        )
        result["workload_error_rate"] = _numeric(stage_result.get("errorRate"), result["workload_error_rate"])
        result["workload_saturation"] = _numeric(stage_result.get("saturation"), result["workload_saturation"])
        result["workload_sustained_duration_s"] = _numeric(
            stage_result.get("sustainedDurationSeconds"), result["workload_sustained_duration_s"]
        )
        latency = stage_result.get("latencyMs")
        if isinstance(latency, dict):
            result["workload_latency_p95_ms"] = _numeric(latency.get("p95"), result["workload_latency_p95_ms"])
            result["workload_latency_p99_ms"] = _numeric(latency.get("p99"), result["workload_latency_p99_ms"])
        queueing = stage_result.get("queueingMs")
        if isinstance(queueing, dict):
            result["workload_queue_p95_ms"] = _numeric(queueing.get("p95"), result["workload_queue_p95_ms"])
        resources = stage_result.get("resources")
        if isinstance(resources, dict):
            result["resource_db_connections"] = _numeric(
                resources.get("maxDatabaseConnections"), result["resource_db_connections"]
            )
            result["resource_memory_mb"] = _numeric(
                resources.get("maxResidentSetMb"), result["resource_memory_mb"]
            )
            result["resource_cpu_seconds"] = _numeric(resources.get("cpuSeconds"), result["resource_cpu_seconds"])
        readback = stage_result.get("readback")
        if isinstance(readback, dict):
            schema = readback.get("schema")
            if isinstance(schema, dict) and isinstance(schema.get("migrationLeaf"), str):
                result["migration_leaf"] = schema["migrationLeaf"]

    collected = re.findall(r"\bcollected\s+(\d+)\s+items?", sanitized, re.IGNORECASE)
    if collected:
        result["collected"] = collected[-1]
    for key, pattern in COUNT_PATTERNS.items():
        matches = pattern.findall(sanitized)
        if matches:
            last = matches[-1]
            result[key] = str(next((item for item in (last if isinstance(last, tuple) else (last,)) if item), 0))
    passed = int(result["passed"])
    if result["collected"] == "1" and passed > 1:
        result["collected"] = str(passed)
    duration = re.findall(r"\bin\s+([0-9]+(?:\.[0-9]+)?)s\b|\bduration_ms=([0-9]+(?:\.[0-9]+)?)", sanitized, re.IGNORECASE)
    if duration:
        first, second = duration[-1]
        result["duration_ms"] = str(round(float(second) if second else float(first) * 1000, 3))
    leaves = re.findall(r"\b(?:migration[_ ]leaf|leaf)[=: ]+([0-9]{4}[A-Za-z0-9_-]*)", sanitized, re.IGNORECASE)
    if leaves:
        result["migration_leaf"] = leaves[-1]
    for key, pattern in METRIC_PATTERNS.items():
        matches = pattern.findall(sanitized)
        if matches:
            result[key] = matches[-1]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--print-sanitized-log", action="store_true")
    args = parser.parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    sanitized = sanitize(text)
    if args.print_sanitized_log:
        print(sanitized, end="")
        return 0
    print(" ".join(f"{key}={value}" for key, value in summarize(text).items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
