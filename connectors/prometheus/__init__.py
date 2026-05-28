"""Prometheus connector.

Scrapes a configured set of metric queries over a window. Output is one
EvidenceBlob per PromQL series.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..base import Connector, EvidenceBlob, Target


class PrometheusConnector(Connector):
    name = "prometheus"
    category = "performance"

    # Default series set. Tenant-overrideable in Phase 3 via the admin console.
    DEFAULT_QUERIES = {
        "cpu_busy_pct_avg":
            'avg by (instance) (1 - rate(node_cpu_seconds_total{mode="idle"}[5m]))',
        "memory_used_pct":
            '1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)',
        "disk_io_util_pct":
            'rate(node_disk_io_time_seconds_total[5m])',
        "net_errs_per_sec":
            'rate(node_network_receive_errs_total[5m]) + '
            'rate(node_network_transmit_errs_total[5m])',
        "load1": 'node_load1',
    }
    WINDOW = timedelta(hours=24)
    STEP = "5m"

    async def collect(self, target: Target) -> list[EvidenceBlob]:
        import httpx  # noqa: F401 — deferred import
        end = datetime.now(timezone.utc)
        start = end - self.WINDOW
        out: list[EvidenceBlob] = []
        for name, promql in self.DEFAULT_QUERIES.items():
            payload = await self._query_range(target, promql, start, end)
            out.append(EvidenceBlob(
                source_tool=f"prometheus.{name}",
                source_tool_version="auditcore-prometheus/0.1.0",
                category="performance",
                collected_at=end,
                raw=json.dumps(payload).encode(),
                scope={
                    "prometheus_url": target.identifier,
                    "query": promql,
                    "window_hours": int(self.WINDOW.total_seconds() / 3600),
                    "step": self.STEP,
                },
            ))
        return out

    async def _query_range(self, target: Target, promql: str,
                           start: datetime, end: datetime) -> dict:
        return {"status": "stub", "query": promql,
                "start": start.isoformat(), "end": end.isoformat(),
                "data": {"result": []}}
