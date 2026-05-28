"""AWS connector.

Reads with the `SecurityAudit` managed policy. Per-service readers each emit
one EvidenceBlob so downstream parsers stay independent.

Phase 1 surface: IAM, S3, EC2, VPC, CloudTrail, Config.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..base import Connector, EvidenceBlob, Target


class AwsAccountConnector(Connector):
    name = "aws"
    category = "cloud"

    SERVICES = ("iam", "s3", "ec2", "vpc", "cloudtrail", "config")

    async def collect(self, target: Target) -> list[EvidenceBlob]:
        # boto3 import deferred so the connectors package imports without AWS deps.
        import boto3  # noqa: F401  (real call sites in service readers)

        account_id = target.identifier
        out: list[EvidenceBlob] = []
        for svc in self.SERVICES:
            payload = await self._read(svc, target)
            out.append(EvidenceBlob(
                source_tool=f"aws.{svc}",
                source_tool_version="auditcore-aws/0.1.0",
                category="cloud",
                collected_at=datetime.now(timezone.utc),
                raw=json.dumps(payload, default=str).encode(),
                scope={"aws_account_id": account_id, "service": svc},
            ))
        return out

    async def _read(self, service: str, target: Target) -> dict:
        # Per-service readers land in their own modules in this directory.
        # Phase 1 placeholder so the contract is testable end-to-end.
        return {"service": service, "account_id": target.identifier, "items": []}
