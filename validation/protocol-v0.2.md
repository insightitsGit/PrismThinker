# Focused live-model validation protocol (planned, not executed)

Primary question: does PrismThinker offer lower unsafe-action rate at comparable
autonomous coverage, or higher coverage at comparable unsafe-action rate?

The central figure will show **unsafe-action rate (y) versus autonomous coverage
(x)**, including uncertainty intervals and sample counts. Ordinary verdict accuracy
and directive accuracy remain separate secondary outcomes. No mock scores belong
in a competitive live-model figure.

## Population and labels

Acquire 100–200 held-out cases across agent execution, policy/compliance and
evidence-intensive reasoning, distinct from a separately collected calibration and
validation corpus. Public synthetic templates from v0.1 cannot become genuinely
held-out merely by assigning them new IDs. Group related variants and shared source
incidents before splitting. Include difficult safe actions, unsafe consensus,
insufficient evidence and genuine disagreement, not mostly obvious vetoes.

Independent annotation should specify verdict, safe execution, conflict, required
review and nonempty acceptable directives with rationale. Resolve annotator
disagreements before model execution. Record original source IDs, licenses, mapping
limitations and annotation provenance. Never infer operational labels from observed
PrismThinker directives. Keep adjudication history and failed cases.

## Systems and fairness

Compare live single LLM, self-consistency, multi-model majority vote, LLM-as-judge,
and the public PrismThinker API. Pin actual supported model IDs and judge settings
when execution is configured. Record prompts, raw responses, sampling settings,
tokens, costs, retries, failures and latency. Use the same underlying evidence and
typed facts for all systems; record the cost and error rate of any LLM that creates
PrismThinker's structured input. Treat that input-construction step as part of the
system when claiming an end-to-end advantage.

Use comparable model families, plus both unconstrained and budget-matched views.
A scripted fixture is not a language model. The deterministic PrismThinker engine
does not itself make a live-model comparison: any upstream model must be explicit.

## Selection and freezing

Choose action-policy thresholds on calibration/validation only using the safety /
coverage tradeoff, not maximum raw accuracy. Freeze all prompts, model IDs, adapters,
thresholds, metrics, exclusions and dataset hashes before test execution. Implement
an append-only run-once ledger with resume semantics: failed calls remain failed
unless a predeclared retry policy permits retries. Freeze the full curve's operating
points before the test; do not choose a favorable test threshold afterward.

Report paired differences with group-bootstrap confidence intervals (10,000 samples,
95%, fixed seed), absolute counts, missingness, worst-case failure sensitivity and
per-domain results. A zero observed unsafe count in a small sample is not zero risk.
Inspect Δ versus simple disagreement separately; do not infer superiority from
conflict F1 on a scripted fixture.

## Release gate

Before execution, supply independently reviewed data and configure live providers
and an API budget. The current harness has baseline interfaces but no live provider
transport or held-out freeze ledger. Missing prerequisites must remain explicit;
do not substitute mocks and label the result a live benchmark. Keep the main README
concise and link detailed reports, including negative findings and compute costs.
