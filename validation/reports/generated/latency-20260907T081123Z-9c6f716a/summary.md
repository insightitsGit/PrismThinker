# Local latency diagnostic

Run: latency-20260907T081123Z-9c6f716a

Unmodified PrismThinker, synthetic validation cases. No architecture changes or optimizations.

Headline distributions use unprofiled calls. Warmups and cProfile calls are saved but excluded. Each case/repetition uses both modes in seeded randomized order; engines are reused but isolated head processes are still created per evaluation.

## isolated

Evaluations: 36; outer failures: 0; internal head errors: 0.

- total (ms): {"n": 36, "mean": 494.06763889257695, "p50": 479.89920002873987, "p95": 625.6217750487849, "p99": 631.5420950530097}
- evaluate (ms): {"n": 36, "mean": 493.60441388691675, "p50": 479.47330004535615, "p95": 625.2273501013406, "p99": 631.1584350070916}
- input_adapter (ms): {"n": 36, "mean": 0.3466638865777188, "p50": 0.2673499984666705, "p95": 0.7237250101752579, "p99": 0.8310399367474018}
- egress (ms): {"n": 36, "mean": 0.012441654689610004, "p50": 0.009899958968162537, "p95": 0.020550040062516928, "p99": 0.03586000530049202}
- serialization (ms): {"n": 36, "mean": 0.1013305672030482, "p50": 0.08849997539073229, "p95": 0.1578249502927065, "p99": 0.20893504843115798}

Separate cProfile cumulative stage measurements (ms):

- classifier: {"n": 12, "mean": 0.11595, "p50": 0.11635000000000001, "p95": 0.14231, "p99": 0.143982}
- selector: {"n": 12, "mean": 0.022966666666666666, "p50": 0.0227, "p95": 0.02637, "p99": 0.027514000000000004}
- evidence: {"n": 12, "mean": 0.0053, "p50": 0.0052, "p95": 0.0062900000000000005, "p99": 0.006378000000000001}
- pool: {"n": 12, "mean": 499.89994166666673, "p50": 508.83950000000004, "p95": 577.393, "p99": 596.65092}
- worker_launch: {"n": 12, "mean": 268.3097416666667, "p50": 269.4429, "p95": 324.041605, "p99": 328.827441}
- worker_ready_wait: {"n": 12, "mean": 225.63793333333334, "p50": 217.55085000000003, "p95": 273.040525, "p99": 275.551385}
- worker_cleanup: {"n": 12, "mean": 5.077966666666667, "p50": 5.145, "p95": 6.619289999999999, "p99": 7.405218000000001}
- contradiction: {"n": 12, "mean": 0.2074, "p50": 0.1789, "p95": 0.3640899999999999, "p99": 0.42489800000000005}
- uncertainty: {"n": 12, "mean": 0.033966666666666666, "p50": 0.0288, "p95": 0.06020499999999999, "p99": 0.07028100000000001}
- counterfactual: {"n": 12, "mean": 0.007491666666666667, "p50": 0.007800000000000001, "p95": 0.012069999999999997, "p99": 0.014094000000000002}
- disposition: {"n": 12, "mean": 0.033758333333333335, "p50": 0.033, "p95": 0.064085, "p99": 0.06729700000000001}

## thread

Evaluations: 36; outer failures: 0; internal head errors: 0.

- total (ms): {"n": 36, "mean": 2.340502810612735, "p50": 2.1448000334203243, "p95": 4.365575034171343, "p99": 4.722590011078864}
- evaluate (ms): {"n": 36, "mean": 1.9041638588532805, "p50": 1.7527500167489052, "p95": 3.613100154325366, "p99": 3.9034448913298547}
- input_adapter (ms): {"n": 36, "mean": 0.33549720602523947, "p50": 0.29479991644620895, "p95": 0.6372499628923833, "p99": 0.725345010869205}
- egress (ms): {"n": 36, "mean": 0.014024993611706628, "p50": 0.008950009942054749, "p95": 0.021124957129359245, "p99": 0.08649993687868104}
- serialization (ms): {"n": 36, "mean": 0.08458335004332992, "p50": 0.06750004831701517, "p95": 0.15497510321438313, "p99": 0.16681995475664735}

Separate cProfile cumulative stage measurements (ms):

- classifier: {"n": 12, "mean": 0.11845000000000001, "p50": 0.11780000000000002, "p95": 0.150515, "p99": 0.15522300000000003}
- selector: {"n": 12, "mean": 0.02299166666666667, "p50": 0.0228, "p95": 0.027725000000000003, "p99": 0.027945000000000005}
- evidence: {"n": 12, "mean": 0.005458333333333333, "p50": 0.0054, "p95": 0.007575, "p99": 0.008235000000000003}
- pool: {"n": 12, "mean": 2.300466666666667, "p50": 2.26185, "p95": 2.67539, "p99": 2.6825180000000004}
- worker_launch: {"n": 0, "mean": null, "p50": null, "p95": null, "p99": null}
- worker_ready_wait: {"n": 0, "mean": null, "p50": null, "p95": null, "p99": null}
- worker_cleanup: {"n": 0, "mean": null, "p50": null, "p95": null, "p99": null}
- contradiction: {"n": 12, "mean": 0.15705000000000002, "p50": 0.14250000000000002, "p95": 0.25249999999999995, "p99": 0.28330000000000005}
- uncertainty: {"n": 12, "mean": 0.022500000000000003, "p50": 0.0216, "p95": 0.029384999999999994, "p99": 0.032597}
- counterfactual: {"n": 12, "mean": 0.005816666666666667, "p50": 0.0052, "p95": 0.008549999999999999, "p99": 0.008990000000000001}
- disposition: {"n": 12, "mean": 0.024258333333333337, "p50": 0.02365, "p95": 0.039435000000000005, "p99": 0.039567000000000005}

## Evaluator compute replay

Sequential, in-process replays of the same selected heads and inputs, separate from the public engine runs. These timings exclude process/thread startup, IPC and engine sanitation. They are not per-worker compute measurements from the isolated run.

- causal: {"latency_ms": {"n": 30, "mean": 0.01781998046984275, "p50": 0.01625006552785635, "p95": 0.02770491410046815, "p99": 0.034069910179823644}, "failures": 0}
- empirical: {"latency_ms": {"n": 60, "mean": 0.013301692282160124, "p50": 0.010750023648142815, "p95": 0.026715081185102463, "p99": 0.03526603570207953}, "failures": 0}
- formal: {"latency_ms": {"n": 60, "mean": 0.03894667218749722, "p50": 0.03300001844763756, "p95": 0.07314519025385377, "p99": 0.09414990199729792}, "failures": 0}
- policy: {"latency_ms": {"n": 50, "mean": 0.033120010048151016, "p50": 0.029950053431093693, "p95": 0.05095498636364936, "p99": 0.06618815241381522}, "failures": 0}
- utility: {"latency_ms": {"n": 50, "mean": 0.004327991046011448, "p50": 0.004049972631037235, "p95": 0.006155099254101515, "p99": 0.008641949389129868}, "failures": 0}

Paired checks: {"pairs": 36, "unavailable_pairs": 0, "decision_mismatches": []}

## Interpretation

Pool time includes startup, scheduling, readiness, IPC, evaluator execution and cleanup. worker_launch and worker_ready_wait are parent-side measurements: ready-wait includes child imports/setup and scheduling, and can overlap head execution. Do not interpret either as pure CPU time.

Profile stages are inclusive and nested: pool contains launch/readiness/cleanup; counterfactual can contain reruns. They must not be stacked or summed as disjoint components. Missing stages have n=0/null rather than invented timings.

The engine's per-head latency fields measure result collection/waiting rather than evaluator computation. Raw values are retained, but direct head replays are used for the separate compute diagnostic.

Serialization measures graph.model_dump_json; total includes input adaptation, evaluate, egress and serialization but excludes artifact I/O and engine construction (recorded in manifest). cProfile runs have instrumentation overhead. Small-sample p99 is an interpolated descriptive value, not a production latency guarantee.

Thread mode changes isolation and timeout semantics; lower latency alone is not a reason to change the default. No persistent workers were introduced. Test data remains locked.
