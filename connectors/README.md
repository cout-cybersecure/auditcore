# Connectors

Pull-mode integrations that run on the AuditCore control plane (not on the client). Each connector produces evidence bundle items in the same format as the Go collector — the difference is just where it executes.

## Contract

Every connector implements [`base.py`](base.py)'s `Connector` ABC:

```python
class Connector(ABC):
    name: str           # canonical, matches `source_tool`
    category: str       # one of: security, performance, cloud, kubernetes, database, hardware, inventory

    async def collect(self, target: Target) -> list[EvidenceBlob]: ...
```

`EvidenceBlob` is a tiny dataclass — raw bytes + version + per-item metadata — so the connector layer can hand off to the same ingestion-api endpoint as the collector.

## Authentication

Connectors NEVER take long-lived credentials in code. They accept either:
- An ARN/role identifier (cloud connectors → STS assume-role on the control plane)
- A short-lived bearer token / kubeconfig context (k8s)
- A read-only DSN from Vault (databases)

## Catalog

| Connector | Module | Reads | Min permission |
|---|---|---|---|
| aws_account | [aws/](aws/) | IAM, S3, EC2, VPC, CloudTrail, Config | `SecurityAudit` |
| kubernetes_cluster | [kubernetes/](kubernetes/) | RBAC, PodSecurity, NetworkPolicies, images, limits | `view` ClusterRole |
| postgres_database | [postgres/](postgres/) | `pg_stat_statements`, indexes, replication views | `pg_monitor` |
| prometheus_metrics | [prometheus/](prometheus/) | metric scrapes for selected series | bearer token / none |
