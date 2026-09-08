# Local Scientific Validation v0.2-L

Follow-on completed: [fresh v1.2 evaluation](reports/local-v1.2-fresh-001/FINDINGS.md)
on new cases. This page retains the original v0.2-L protocol and audit history.

Completed results: [interpretation](reports/local-v0.2-L-002/INTERPRETATION.md),
[measurements and plots](reports/local-v0.2-L-002/summary.md).

This experiment uses actual local model inference and a newly authored, frozen
adversarial corpus. It does **not** claim independent expert review, a public
external benchmark, or 180 independent observations: there are 180 cases in 30
scenario families, distributed equally over three domains.

**Audit status:** [run 001](reports/local-v0.2-L-001/AUDIT.md) contained unsupported
typed predicate syntax in 72 cases and is not a clean comparative result. Its raw
data, source snapshot and unfavorable results are retained. The syntax-repaired
run 002 repeats all 180 cases and model calls with unchanged labels/settings. It
is a disclosed post-audit replication, **not a pristine held-out benchmark**.

## Protocol

The generator `datasets/build_adversarial.py` has no PrismThinker imports and never
calls an evaluator or language model. Ordinary Python oracles label explicit
fictional rules. Typed rule translations and deterministic representation/unit
normalizations are shared with every system. They are not oracle verdicts. Nothing
is relabeled or selected after seeing system outputs. Tests inspect schema and
corpus integrity but do not evaluate PrismThinker on the new cases before freezing.

All 180 cases are evaluation-only. No thresholds are fitted; confidence-gate points
are preregistered in `config/local_models.json`. Families are kept intact for
bootstrap resampling. This is held out from model feedback and threshold selection,
not a claim that the author had no knowledge of PrismThinker or that general rule
patterns were absent from model pretraining. v0.1 cases are not reused.

## Real methods

- Single Qwen3 4B response.
- Qwen3 4B self-consistency, three samples at temperature 0.6 with different seeds.
- Strict majority of Qwen3 4B, Llama3.2 3B and Gemma3 4B operational directives.
- Qwen3 4B judge, temperature zero, given the original case and three candidate outputs.
- Unchanged PrismThinker via its public API and public directive adapter, default isolation.

Qwen thinking is explicitly disabled for this non-thinking protocol. The choice
keeps inference bounded on an 8 GB laptop GPU; these are three model families, not
a representative small/medium/frontier reasoning-model ladder. JSON schema-constrained
generation is used for all local calls. No model actually executes the candidate tool.

Single and sample-zero/panel calls are reused. Logical method tokens and sequential
latency include every dependency; physical call counts are reported separately.
Invalid/truncated outputs and timeouts remain failures. An interrupted in-flight
call is marked outcome-unknown on resume and is never silently retried. Seeds are
recorded but do not guarantee GPU bit-for-bit determinism.

## Reproduce

Install Python dependencies and an Ollama runtime, then pull the specified models:

```bash
python -m pip install -e ".[dev,validation]"
ollama pull qwen3:4b
ollama pull llama3.2:3b
ollama pull gemma3:4b
python -m validation.datasets.build_adversarial
python -m validation.experiments.local_models freeze validation/config/local_models.json
python -m validation.experiments.local_models run validation/reports/local-v0.2-L-001
```

The original corpus now fails the required predicate preflight rather than silently
starting an invalid study. For the corrected replication, use:

```bash
python -m validation.datasets.build_adversarial_v2
python -m validation.experiments.local_models freeze validation/config/local_models_syntax2.json
python -m validation.experiments.local_models run validation/reports/local-v0.2-L-002
```

Existing run directories are immutable inputs to reporting/resumption; a freeze
does not overwrite them. No additional inference is needed to read the saved reports.

The local setup for this workspace uses portable Ollama under `.venv/ollama-runtime`
and stores weights under `.venv/ollama-models`. It binds only to `127.0.0.1:11434`,
disables cloud inference and loads one model at a time. These multi-gigabyte assets
are ignored by Git. A standard Ollama installation is also supported.

Freeze resolves tags to installed model digests and records runtime, prompt,
source, corpus and engine configuration hashes. Freeze refuses an existing output
directory. Run validates them before inference. Use the same run command to resume:
completed calls are reused, started calls without completion are recorded as unknown
failures. A file lock excludes concurrent runners. Hashes detect accidental changes;
they are not independent cryptographic attestation against a malicious operator.

Report regeneration from completed raw results:

```bash
python -m validation.experiments.local_models report validation/reports/local-v0.2-L-001
```

No endpoint or model substitutions occur automatically. A missing runtime/model is
an explicit error, not permission to insert mocks. A new study requires a new ID
and an independently justified protocol; do not rerun until numbers look better.

## Measurements

Primary: unsafe-action rate versus autonomous coverage, alongside selective verdict
accuracy, directive accuracy, review recall, conflict precision/recall/F1, failures,
latency, tokens and zero API cost. Electricity/hardware costs are unmeasured.
Preregistered confidence gates only escalate initially autonomous actions. The
ungated point has 95% intervals from 10,000 paired family-bootstrap draws; intervals
and point differences are also saved numerically. Degenerate zero-error bootstrap
intervals do not establish zero population risk.

Delta is compared with binary verdict disagreement, dissent count, confidence spread
and one-minus-majority-margin. The simple signals are computed separately on the
same PrismThinker head panel and on the local-model panel. All predictors use one
common complete-case subset per target; counts/exclusions are saved.

The frozen simple-disagreement definitions include UNDETERMINED as a verdict and
all selected heads, including heads reporting insufficient evidence. This can make
binary disagreement insensitive when abstention is frequent. A Delta advantage
over these definitions is not by itself evidence that every multidimensional
component contributes value; comparisons excluding abstentions and ablations need
a separate preregistered follow-up, not a test-time redefinition.

Targets are unsafe eligibility, true conflict, review requirement, and actual unsafe
or incorrect autonomous action by the fixed local-majority reference decision.
This shared reference avoids comparing predictors against different methods' errors.
Failed reference decisions are missing, not negatives. ROC-AUC is tie-aware; PR-AUC
uses grouped-tie, non-interpolated average precision. Single-class targets return
null. No test-time score inversion, threshold selection or significance claim is
made from point AUCs alone.

Artifacts: immutable freeze, corpus snapshot, append-only raw call ledger, all
case/system results, metrics by domain, family-bootstrap intervals, prediction rows,
CSV tables, PNG plots and Markdown summary. Keep unfavorable cases and domains.

## Official runtime references

- [Ollama Windows installation and storage](https://docs.ollama.com/windows)
- [Chat API, structured output and token/duration fields](https://docs.ollama.com/api/chat)
- [Installed-model digests](https://docs.ollama.com/api/tags)
- [Qwen3 4B](https://ollama.com/library/qwen3:4b), [Llama3.2 3B](https://ollama.com/library/llama3.2:3b), [Gemma3 4B](https://ollama.com/library/gemma3:4b)
