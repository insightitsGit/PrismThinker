from __future__ import annotations

from datetime import datetime, timezone

from prismthinker.adapters.vectorprism import VectorPrismDocument

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 8, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def corpus_documents() -> list[VectorPrismDocument]:
    return [
        VectorPrismDocument(
            id="priv.retention.policy",
            text=(
                "Privacy control: checkout session cache holding payment PII must not use "
                "cache_ttl of 30 seconds or more. GDPR retention and PII cache policy require "
                "a short TTL when contains_pii is true."
            ),
            source="policy.privacy",
            metadata={
                "trust": 0.95,
                "numeric_claims": {"cache_ttl": 30.0},
                "policy_rule": {
                    "id": "pii-cache",
                    "modality": "prohibition",
                    "predicate": "fact.contains_pii == true and fact.cache_ttl >= 30",
                    "severity": "hard_veto",
                    "text": "PII cache retention",
                },
            },
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="priv.ttl.60.incident",
            text=(
                "Incident review: checkout cache_ttl stayed at 60 seconds while contains_pii "
                "was true. Payment tokens and email hashes sat in Redis longer than the "
                "privacy retention window."
            ),
            source="incidents.privacy",
            metadata={"trust": 0.88, "numeric_claims": {"cache_ttl": 60.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="priv.ttl.10.ok",
            text=(
                "Approved pattern: reduce cache_ttl to 10 seconds for checkout PII. Short TTL "
                "clears session tokens before the 30 second prohibition threshold."
            ),
            source="runbooks.privacy",
            metadata={"trust": 0.9, "numeric_claims": {"cache_ttl": 10.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sre.p99.healthy",
            text=(
                "SRE telemetry: checkout p99_latency_ms is 90 against a 200ms SLA. Throughput "
                "and cache hit ratio are inside budget. No SLA breach."
            ),
            source="prom.checkout",
            metadata={
                "trust": 0.86,
                "numeric_claims": {"p99_latency_ms": 90.0, "qps": 420.0},
                "causal_graph": {
                    "nodes": ["cache_ttl", "p99_latency_ms"],
                    "edges": [
                        {
                            "source": "cache_ttl",
                            "target": "p99_latency_ms",
                            "signed": -1,
                            "edge_id": "e-ttl-lat",
                        }
                    ],
                },
            },
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sre.p99.breach",
            text=(
                "SRE page: p99_latency_ms climbed to 900. The 200ms SLA is breached. "
                "Latency budget and throughput SLA are red."
            ),
            source="prom.checkout",
            metadata={"trust": 0.84, "numeric_claims": {"p99_latency_ms": 900.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sre.qps.ok",
            text=(
                "Capacity note: observed qps is 480 with headroom to 800. Throughput SLA is "
                "healthy; no need to shed load."
            ),
            source="prom.edge",
            metadata={"trust": 0.8, "numeric_claims": {"qps": 480.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="health.phi.retention",
            text=(
                "Healthcare HIPAA: patient chart cache retention_days must stay at or below 7. "
                "PHI retention beyond one week is prohibited."
            ),
            source="policy.healthcare",
            metadata={"trust": 0.97, "numeric_claims": {"retention_days": 7.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="health.phi.30",
            text=(
                "Current store: EHR fragment cache retention_days is 30. PHI records remain "
                "searchable for a month."
            ),
            source="ehr.ops",
            metadata={"trust": 0.9, "numeric_claims": {"retention_days": 30.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="fin.notional.limit",
            text=(
                "Finance compliance: automated equity trade notional_usd must not exceed "
                "250000 without a human desk. Hard veto on oversized tickets."
            ),
            source="policy.finance",
            metadata={"trust": 0.96, "numeric_claims": {"notional_usd": 250000.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="fin.ticket.400k",
            text=(
                "Proposed ticket: buy mega-cap basket, notional_usd 400000. Desk has not "
                "countersigned the ticket."
            ),
            source="oms.equities",
            metadata={"trust": 0.91, "numeric_claims": {"notional_usd": 400000.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sec.exfil.deny",
            text=(
                "Security policy: export_pii must stay false. Bulk customer export and data "
                "exfiltration of PII is denied."
            ),
            source="policy.security",
            metadata={"trust": 0.98},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sec.exfil.attempt",
            text=(
                "DLP alert: export_pii is true on a warehouse dump job. Customer emails would "
                "leave the VPC."
            ),
            source="dlp.alerts",
            metadata={"trust": 0.93, "numeric_claims": {"rows_exported": 120000.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="legal.gdpr.consent",
            text=(
                "Legal GDPR: marketing send requires consent == true. Must not process email "
                "when consent is missing."
            ),
            source="policy.legal",
            metadata={"trust": 0.97},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="legal.gdpr.no_consent",
            text=(
                "CRM extract: consent is false for this cohort. GDPR legal hold says do not "
                "allow the campaign send."
            ),
            source="crm.legal",
            metadata={"trust": 0.89},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sci.pvalue.rep1",
            text=(
                "Study replicate 1: treatment reduced error. Observed p-value 0.012 on the "
                "primary endpoint. Sample distribution looks regular."
            ),
            source="lab.stats",
            metadata={"trust": 0.82, "numeric_claims": {"pvalue": 0.012}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sci.pvalue.rep2",
            text=(
                "Study replicate 2: posterior predictive check passed. p-value 0.018. "
                "Distribution of residuals is acceptable."
            ),
            source="lab.stats",
            metadata={"trust": 0.81, "numeric_claims": {"pvalue": 0.018}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sci.pvalue.rep3",
            text=(
                "Study replicate 3: sample n=240, p-value 0.009. Combined distribution still "
                "under the 0.05 threshold."
            ),
            source="lab.stats",
            metadata={"trust": 0.8, "numeric_claims": {"pvalue": 0.009, "n": 240.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sci.pvalue.thin",
            text=(
                "Pilot only: two p-value draws, 0.04 and 0.06. Distribution claim is thin; "
                "need another sample."
            ),
            source="lab.pilot",
            metadata={"trust": 0.55, "numeric_claims": {"pvalue": 0.04}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="sci.pvalue.thin2",
            text=(
                "Pilot second draw: p-value 0.06. Still only two observations for the "
                "distribution."
            ),
            source="lab.pilot",
            metadata={"trust": 0.54, "numeric_claims": {"pvalue": 0.06}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="causal.ttl.latency",
            text=(
                "Causal graph note: increasing cache_ttl raises hit rate and then lowers "
                "p99_latency_ms on checkout. Path cache_ttl -> hit_rate -> p99_latency_ms."
            ),
            source="sre.causal",
            metadata={
                "trust": 0.78,
                "numeric_claims": {"cache_ttl": 60.0, "p99_latency_ms": 180.0},
                "causal_graph": {
                    "nodes": ["cache_ttl", "hit_rate", "p99_latency_ms"],
                    "edges": [
                        {
                            "source": "cache_ttl",
                            "target": "hit_rate",
                            "signed": 1,
                            "edge_id": "e-ttl-hit",
                        },
                        {
                            "source": "hit_rate",
                            "target": "p99_latency_ms",
                            "signed": -1,
                            "edge_id": "e-hit-lat",
                        },
                    ],
                },
            },
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="causal.unrelated.cost",
            text=(
                "Cost dashboard is not on the latency path. cloud_spend does not cause "
                "p99_latency_ms in the checkout causal graph."
            ),
            source="finops.graph",
            metadata={"trust": 0.7, "numeric_claims": {"cloud_spend": 4200.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="formal.ttl.range",
            text=(
                "Schema constraint: cache_ttl is an int between 1 and 300. Values outside "
                "that range are structurally invalid."
            ),
            source="schema.checkout",
            metadata={"trust": 0.92, "numeric_claims": {"cache_ttl": 300.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="ev.latency.low",
            text=(
                "Canary probe A: measured latency 10ms on the edge POP. Numeric claim "
                "latency=10."
            ),
            source="canary.edge",
            metadata={"trust": 0.9, "numeric_claims": {"latency": 10.0}},
            retrieved_at=T0,
        ),
        VectorPrismDocument(
            id="ev.latency.high",
            text=(
                "Canary probe B: measured latency 40ms on a different POP. Numeric claim "
                "latency=40. This reading negates the 10ms claim."
            ),
            source="canary.core",
            metadata={
                "trust": 0.2,
                "numeric_claims": {"latency": 40.0},
                "negates_id": "ev.latency.low",
            },
            retrieved_at=T1,
        ),
        VectorPrismDocument(
            id="ev.stale.old",
            text=(
                "Same metrics source, stale scrape: checkout latency snapshot is 12 days old. "
                "Do not treat as current SRE truth."
            ),
            source="prom.checkout",
            metadata={"trust": 0.4, "freshness_hours": 288.0, "numeric_claims": {"p99_latency_ms": 110.0}},
            retrieved_at=T0,
        ),
        VectorPrismDocument(
            id="ev.stale.fresh",
            text=(
                "Same metrics source, fresh scrape: checkout p99_latency_ms is 110 from a "
                "2 hour old scrape."
            ),
            source="prom.checkout",
            metadata={"trust": 0.85, "freshness_hours": 2.0, "numeric_claims": {"p99_latency_ms": 110.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="open.mixed.policy.sla",
            text=(
                "Long-running debate: should we keep cache_ttl, honor GDPR PII retention, "
                "and still hit p99 SLA throughput? Policy, empirical p-value style "
                "telemetry, and pragmatic SLA all collide."
            ),
            source="design.reviews",
            metadata={"trust": 0.6, "numeric_claims": {"cache_ttl": 60.0, "p99_latency_ms": 180.0}},
            retrieved_at=T2,
        ),
        VectorPrismDocument(
            id="math.identity",
            text="Arithmetic identity tables used by the axiomatic fast path. 2 + 2 equals 4.",
            source="kb.math",
            metadata={"trust": 1.0},
            retrieved_at=T2,
        ),
    ]
