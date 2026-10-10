"""Pure deterministic MAP-EM aggregation for one fixed five-reviewer panel."""

from __future__ import annotations

from collections import defaultdict
from math import exp, log, pi, sqrt
from statistics import median

from app.schemas.review import (
    AggregateItem,
    AggregateRequest,
    AggregateResponse,
    AnomalyFinding,
    ReviewerProfile,
)

ALGORITHM_NAME = "panel_bayesian_robust"
ALGORITHM_VERSION = "1.0.0"
DEFAULT_PARAMETERS: dict[str, float | int] = {
    "theta_prior_mean": 0.5, "theta_prior_std": 0.25, "bias_prior_std": 0.15,
    "sigma_min": 0.05, "sigma_prior_mean": 0.12, "pi_alpha": 1.0, "pi_beta": 20.0,
    "max_iterations": 100, "convergence_tolerance": 0.000001, "random_seed": 20261003,
}


def _clip(x: float) -> float: return min(1.0, max(0.0, x))
def _score(x: float) -> float: return round(x + 1e-12, 2)
def _density(x: float, mean: float, sigma: float) -> float:
    sigma = max(sigma, 1e-9); z = (x - mean) / sigma
    return exp(-z * z / 2) / (sigma * sqrt(2 * pi))
def _posterior(x: float, mean: float, sigma: float, prior: float) -> float:
    prior = min(1 - 1e-8, max(1e-8, prior)); normal = (1 - prior) * _density(x, mean, sigma)
    return prior / (prior + normal)
def _entropy(xs: list[float]) -> float:
    bins = min(5, len(xs))
    if bins < 3: return 1.0
    counts = [0] * bins
    for x in xs: counts[min(bins - 1, int(_clip(x) * bins))] += 1
    return -sum((n / len(xs)) * log(n / len(xs)) for n in counts if n) / log(bins)


def aggregate_panel_scores(request: AggregateRequest) -> AggregateResponse:
    params = {**DEFAULT_PARAMETERS, **request.parameters}
    # (reviewer, submission, rubric, task, normalized value, max, duration, chars)
    data = [(o.reviewer_id, o.submission_id, item.rubric_item_id, o.task_id,
             _clip(item.score / item.max_score), item.max_score, o.duration_seconds, o.comment_length)
            for o in request.observations for item in o.rubric_scores]
    if not data:
        return AggregateResponse(assignment_id=request.assignment_id, panel_id=request.panel_id,
            algorithm_name=ALGORITHM_NAME, algorithm_version=ALGORITHM_VERSION, parameters=params,
            results=[], reviewer_profiles=[], anomalies=[], fallback_reason="NO_OBSERVATIONS")
    by_key: dict[tuple[int, int], list[tuple]] = defaultdict(list); by_reviewer: dict[int, list[tuple]] = defaultdict(list)
    by_task: dict[int | None, list[tuple]] = defaultdict(list)
    for row in data:
        by_key[(row[1], row[2])].append(row); by_reviewer[row[0]].append(row); by_task[row[3]].append(row)
    submissions = sorted({row[1] for row in data}); reviewers = sorted(by_reviewer)
    fallback = "PANEL_TOO_SMALL" if len(submissions) < 3 else None
    theta = {key: median(row[4] for row in rows) for key, rows in by_key.items()}
    bias = {r: 0.0 for r in reviewers}; sigma = {r: float(params["sigma_prior_mean"]) for r in reviewers}
    prior = {r: float(params["pi_alpha"]) / (float(params["pi_alpha"]) + float(params["pi_beta"])) for r in reviewers}
    posterior: dict[tuple, float] = {row: 0.0 for row in data}; converged = fallback is not None
    precision = 1 / float(params["theta_prior_std"]) ** 2; bias_precision = 1 / float(params["bias_prior_std"]) ** 2
    sigma_min = float(params["sigma_min"])
    if not fallback:
        for _ in range(int(params["max_iterations"])):
            before = (theta.copy(), bias.copy(), sigma.copy(), prior.copy())
            for row in data: posterior[row] = _posterior(row[4], _clip(theta[(row[1], row[2])] + bias[row[0]]), sigma[row[0]], prior[row[0]])
            for key, rows in by_key.items():
                weights = [(1-posterior[row]) / max(sigma[row[0]]**2, sigma_min**2) for row in rows]
                theta[key] = _clip((precision * float(params["theta_prior_mean"]) + sum(w * (row[4] - bias[row[0]]) for row, w in zip(rows, weights))) / (precision + sum(weights)))
            for r, rows in by_reviewer.items():
                weights = [(1-posterior[row]) / max(sigma[r]**2, sigma_min**2) for row in rows]
                bias[r] = sum(w * (row[4] - theta[(row[1], row[2])]) for row, w in zip(rows, weights)) / (bias_precision + sum(weights))
            center = sum(bias.values()) / len(bias)
            for r, rows in by_reviewer.items():
                bias[r] -= center; normal = [1-posterior[row] for row in rows]
                sigma[r] = max(sigma_min, sqrt((2 * float(params["sigma_prior_mean"])**2 + sum(w * (row[4]-theta[(row[1],row[2])]-bias[r])**2 for row,w in zip(rows,normal))) / (2+sum(normal))))
                prior[r] = min(1-1e-6, max(1e-6, (float(params["pi_alpha"]) + sum(posterior[row] for row in rows)) / (float(params["pi_alpha"])+float(params["pi_beta"])+len(rows))))
            old = before
            delta = max([abs(theta[k]-old[0][k]) for k in theta] + [abs(bias[r]-old[1][r]) + abs(sigma[r]-old[2][r]) + abs(prior[r]-old[3][r]) for r in reviewers])
            if delta < float(params["convergence_tolerance"]): converged = True; break
        if not converged: fallback = "MODEL_NOT_CONVERGED"
    if fallback == "MODEL_NOT_CONVERGED":
        theta = {key: median(row[4] for row in rows) for key, rows in by_key.items()}

    durations = [row[6] for row in data if row[6] > 0]; panel_duration = median(durations) if durations else 0
    anomalies: list[AnomalyFinding] = []; high_submissions: set[int] = set()
    for task_id, rows in by_task.items():
        reviewer, submission = rows[0][0], rows[0][1]; rules: list[str] = []; evidence = [] ; hard = False
        for row in rows:
            peers = [x[4] for x in by_key[(submission,row[2])] if x[0] != reviewer]; pm = median(peers) if peers else row[4]; span = max(peers)-min(peers) if len(peers)>1 else 1
            p = posterior[row]; hard = hard or (len(peers)==4 and span<=.15 and abs(row[4]-pm)>=.30)
            if p >= .95 and "POSTERIOR_OUTLIER" not in rules: rules.append("POSTERIOR_OUTLIER")
            if abs(theta[(submission,row[2])] - median(x[4] for x in by_key[(submission,row[2])])) >= .15 and "MODEL_MEDIAN_CONFLICT" not in rules: rules.append("MODEL_MEDIAN_CONFLICT")
            weights = sum((1-posterior[x])/max(sigma[x[0]]**2,sigma_min**2) for x in by_key[(submission,row[2])]); se=sqrt(1/(precision+weights)); lo,hi=_clip(theta[(submission,row[2])]-1.96*se),_clip(theta[(submission,row[2])]+1.96*se)
            if hi-lo >= .20 and "WIDE_CREDIBLE_INTERVAL" not in rules: rules.append("WIDE_CREDIBLE_INTERVAL")
            evidence.append({"rubric_item_id":row[2],"max_score":row[5],"reviewer_score":_score(row[4]*row[5]),"other_four_median":_score(pm*row[5]),"other_four_span":_score(span*row[5]),"normalized_deviation":round(abs(row[4]-pm),6),"posterior_anomaly_probability":round(p,6),"bayesian_score":_score(theta[(submission,row[2])]*row[5]),"median_score":_score(median(x[4] for x in by_key[(submission,row[2])])*row[5]),"ci_lower":_score(lo*row[5]),"ci_upper":_score(hi*row[5])})
        if hard: rules.insert(0,"FOUR_VS_ONE_OUTLIER")
        short_duration = rows[0][6] < max(120,.25*panel_duration); short_comment=rows[0][7]<30; entropy=_entropy([x[4] for x in rows]); low_entropy=len(rows)>=3 and entropy<=.2
        risk=100*min(1,.45*hard+.35*max(posterior[x] for x in rows)+.1*short_duration+.05*short_comment+.05*low_entropy)
        level="HIGH" if rules else "MEDIUM" if risk>=50 or sum((short_duration,short_comment,low_entropy))>=2 else "LOW"
        if level=="HIGH": high_submissions.add(submission)
        # LOW without any triggered signal is a normal observation, not an open case.
        rules.extend(name for enabled,name in ((short_duration,'SHORT_DURATION'),(short_comment,'SHORT_COMMENT'),(low_entropy,'LOW_SCORE_DIVERSITY')) if enabled)
        anomalies.append(AnomalyFinding(review_task_id=task_id,submission_id=submission,reviewer_id=reviewer,risk_level=level,risk_score=round(risk,4),evidence={"risk_level":level,"risk_score":round(risk,4),"rules_triggered":rules,"rubric_evidence":evidence,"behavior_evidence":{"duration_seconds":rows[0][6],"comment_char_count":rows[0][7],"normalized_entropy":round(entropy,6)}}))
    results=[]
    for submission in submissions:
        scores={}; medians={}; confidence={}; intervals={}
        for (sid,item),rows in by_key.items():
            if sid!=submission: continue
            maximum=rows[0][5]; value=theta[(sid,item)]; weights=sum((1-posterior[x])/max(sigma[x[0]]**2,sigma_min**2) for x in rows); se=sqrt(1/(precision+weights)); lo,hi=_clip(value-1.96*se),_clip(value+1.96*se)
            scores[item]=_score(value*maximum); medians[item]=_score(median(x[4] for x in rows)*maximum); intervals[item]=(_score(lo*maximum),_score(hi*maximum)); confidence[item]=round(1-min(1,(hi-lo)/.2),6)
        results.append(AggregateItem(submission_id=submission,total_score=_score(sum(scores.values())),rubric_scores=scores,median_scores=medians,confidence=confidence,confidence_intervals=intervals,risk_level="HIGH" if submission in high_submissions else "LOW",fallback_reason=fallback))
    profiles=[ReviewerProfile(reviewer_id=r,bias=round(bias[r],8),sigma=round(sigma[r],8),anomaly_prior=round(prior[r],8),learned=len(by_reviewer[r])>=3) for r in reviewers]
    return AggregateResponse(assignment_id=request.assignment_id,panel_id=request.panel_id,algorithm_name=ALGORITHM_NAME,algorithm_version=ALGORITHM_VERSION,parameters=params,results=results,reviewer_profiles=profiles,anomalies=anomalies,fallback_reason=fallback)
