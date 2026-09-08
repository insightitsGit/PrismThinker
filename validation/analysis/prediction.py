"""Tie-aware ROC-AUC and non-interpolated PR-AUC (average precision)."""
from collections import Counter


def aucs(labels, scores):
    if len(labels) != len(scores): raise ValueError("unaligned prediction inputs")
    n = len(labels)
    positives = sum(labels)
    if not n or positives in {0,n}:
        return {"n":n,"positives":positives,"auroc":None,"pr_auc":None}
    groups = {}
    for label, score in zip(labels,scores):
        groups.setdefault(score,[0,0])[int(bool(label))] += 1
    tp = fp = 0
    area = ap = 0.0
    for score in sorted(groups, reverse=True):
        negatives, positive = groups[score]
        old_tp, old_fp = tp,fp
        tp += positive
        fp += negatives
        area += (fp-old_fp)*(tp+old_tp)/2
        ap += positive/positives * tp/(tp+fp)
    return {"n":n,"positives":positives,"auroc":area/(positives*(n-positives)),"pr_auc":ap}


def signals(verdicts, confidences):
    if not verdicts or any(v is None for v in verdicts) or any(c is None for c in confidences): return None
    counts = sorted(Counter(verdicts).values(), reverse=True)
    n = len(verdicts)
    margin = (counts[0]-(counts[1] if len(counts)>1 else 0))/n
    return {"binary_disagreement":float(len(counts)>1),"dissent_count":n-counts[0],
            "confidence_spread":max(confidences)-min(confidences),"one_minus_majority_margin":1-margin}
