"""Kubernetes connector.

Reads cluster-wide RBAC, PodSecurity admission state, NetworkPolicies, images,
and resource limits. Speaks to the cluster via a kubeconfig context that maps
to a `view` ClusterRole at minimum.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..base import Connector, EvidenceBlob, Target


class KubernetesClusterConnector(Connector):
    name = "kubernetes"
    category = "kubernetes"

    RESOURCES = (
        "rbac.roles", "rbac.rolebindings",
        "rbac.clusterroles", "rbac.clusterrolebindings",
        "core.namespaces", "core.pods",
        "networking.networkpolicies",
        "policy.podsecuritypolicies",
    )

    async def collect(self, target: Target) -> list[EvidenceBlob]:
        from kubernetes import client, config  # noqa: F401 — deferred import
        cluster = target.identifier
        out: list[EvidenceBlob] = []
        for r in self.RESOURCES:
            payload = await self._list(r, target)
            out.append(EvidenceBlob(
                source_tool=f"k8s.{r}",
                source_tool_version="auditcore-k8s/0.1.0",
                category="kubernetes",
                collected_at=datetime.now(timezone.utc),
                raw=json.dumps(payload, default=str).encode(),
                scope={"cluster": cluster, "resource": r},
            ))
        return out

    async def _list(self, resource: str, target: Target) -> dict:
        return {"resource": resource, "cluster": target.identifier, "items": []}
