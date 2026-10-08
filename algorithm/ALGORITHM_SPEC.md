# AlgoPeer：五人跨班评审 Bayesian 鲁棒聚合算法规格

版本：`1.0.0-draft`
状态：已确认的算法方案，待实现与测试
适用范围：每个 `review_panel` 固定 5 名评审人，对目标班全部有效作品按 Rubric 评分。

## 1. 目标与成绩政策

算法目标不是证明某位学生“主观恶意”，而是：

1. 校正评审人长期偏严、偏宽与评分不稳定；
2. 识别单次极端、疑似定向的异常评分；
3. 对低风险作品给出可解释的五人聚合分与置信度；
4. 对高风险作品停止使用五人聚合，转由同一教师基于完整证据录入一次复核最终分决定成绩。

成绩规则：

```text
低风险作品：
最终分 = 0.60 × 第一次教师独立评分
       + 0.40 × 五人 Bayesian 鲁棒聚合分

高风险作品：
最终分 = 教师复核最终分
```

高风险作品的第一次教师分、五人原始分和 Bayesian 聚合分均保留审计，但不参与最终分计算。

明确不做：

* 不修改原始评分；
* 不因异常自动处罚评审人；
* 不做学生自助回避；
* 不尝试识别“五人完全一致的串通评分”。

## 2. 候选算法与最终选型

|候选方案|结论|原因|
|---|---|---|
|简单平均|不采用|单个极端分数会明显拉动结果。|
|逐项中位数|保留为安全基线与回退|5 人中最多 2 人极端时具有天然鲁棒性，但不能校正长期严宽差异。|
|Bayesian Peer Grading + 异常混合模型|正式选型|可联合估计作品真实分、评分者偏差、评分噪声和单次异常概率。|
|要求评审人预测他人分数的校准法|暂不采用|需要增加前端交互与额外行为假设，不适合 MVP。|

正式算法名称：

```text
panel_bayesian_robust
```

参考文献：

1. Zarkoob et al., AAAI 2023, [Better Peer Grading through Bayesian Inference](https://ojs.aaai.org/index.php/AAAI/article/view/25757)：贝叶斯同伴评分、评分者偏差、可靠性、低投入行为及离散 Rubric。
2. Stelmakh, Shah, Singh, AAAI 2021, [Catch Me if I Can: Detecting Strategic Behaviour in Peer Assessment](https://ojs.aaai.org/index.php/AAAI/article/view/16611)：战略性评分的统计检测与误报控制。
3. Lu, Kong, NeurIPS 2023, [Calibrating “Cheap Signals” in Peer Review without a Prior](https://proceedings.neurips.cc/paper_files/paper/2023/hash/41badd36e935f8a80175e95d8bc6192e-Abstract-Conference.html)：无先验校准思路；本项目不采用其“预测他人分数”的交互。
4. Agarwal et al., ICML 2020, [Rank Aggregation from Pairwise Comparisons in the Presence of Adversarial Corruptions](https://proceedings.mlr.press/v119/agarwal20a.html)：对抗污染需要显式建模与异常处理。

## 3. 输入

聚合以单个 `panel_id` 为边界，严禁混合两个 Panel 数据。

|字段|类型/单位|范围/说明|
|---|---|---|
|`assignment_id`|int|作业 ID。|
|`panel_id`|int|固定五人评审组 ID。|
|`submission_id`|int|被评作品 ID。|
|`reviewer_id`|int|评审人 ID，仅内部算法使用。|
|`rubric_item_id`|int|Rubric 项 ID。|
|`score`|decimal|`0 <= score <= max_score`。|
|`max_score`|decimal|该 Rubric 项满分，必须大于 0。|
|`started_at` / `submitted_at`|ISO 8601|用于计算评审耗时。|
|`comment`|string|评语原文，仅算法内部统计长度；不进入公开结果。|
|`task_status`|enum|只有 `SUBMITTED` 评分进入正式聚合。|

归一化分数：

```text
x[r,s,k] = score[r,s,k] / max_score[k]
```

其中 `r` 为评审人、`s` 为作品、`k` 为 Rubric 项，`x ∈ [0, 1]`。

## 4. Bayesian 鲁棒模型

### 4.1 隐变量

```text
theta[s,k]：作品 s 在 Rubric 项 k 的潜在真实归一化分
bias[r]：评审人 r 的长期严宽偏差；负值表示偏严，正值表示偏宽
sigma[r]：评审人 r 的评分噪声；越小表示越稳定
pi[r]：评审人 r 的异常评分先验概率
z[r,s,k]：该次评分是否异常，0=正常，1=异常
```

约束：

```text
0 <= theta[s,k] <= 1
sum(bias[r]) = 0
sigma[r] >= sigma_min
```

### 4.2 观测模型

正常评分采用截断正态分布；异常评分采用宽分布：

```text
z[r,s,k] ~ Bernoulli(pi[r])

当 z = 0：
x[r,s,k] ~ TruncatedNormal(theta[s,k] + bias[r], sigma[r]^2, 0, 1)

当 z = 1：
x[r,s,k] ~ Uniform(0, 1)
```

离散 Rubric 分数按区间处理。例如满分 20、录入 18 分，对应归一化区间：

```text
[(18 - 0.5) / 20, (18 + 0.5) / 20]
```

边界截断到 `[0, 1]`。

建议先验参数：

```json
{
  "theta_prior_mean": 0.50,
  "theta_prior_std": 0.25,
  "bias_prior_std": 0.15,
  "sigma_min": 0.05,
  "sigma_prior_mean": 0.12,
  "pi_alpha": 1,
  "pi_beta": 20
}
```

这些参数均基于归一化分数尺度。

### 4.3 推断与可靠性权重

首版采用确定性的 MAP-EM 推断，而非随机 MCMC，便于测试和复现。

单次评分异常后验概率：

```text
p_anomaly[r,s,k] = P(z[r,s,k] = 1 | 全部 Panel 评分)
```

该评分进入作品潜在真实分估计的有效精度权重：

```text
w[r,s,k] = (1 - p_anomaly[r,s,k]) / max(sigma[r]^2, sigma_min^2)
```

逐项潜在真实分的可实现近似更新式：

```text
theta[s,k]
= clip(
    (lambda * theta_prior_mean
      + sum_r w[r,s,k] * (x[r,s,k] - bias[r]))
    / (lambda + sum_r w[r,s,k]),
    0,
    1
  )
```

其中：

```text
lambda = 1 / theta_prior_std^2
```

评分者偏差以带先验收缩的加权残差均值更新；`sigma[r]` 以正常评分的加权残差平方更新；`pi[r]` 以异常后验均值和 Beta 先验更新。迭代上限 `100` 次，参数变化小于 `1e-6` 时收敛。

解释：

* 评审人长期偏低 5 分，会被 `bias[r]` 校正；
* 评分者长期不稳定，会有较大的 `sigma[r]`；
* 某人只对一份作品异常低分，`p_anomaly` 会升高；
* 原始评分不改写；统计影响变化不等于纪律处罚。

### 4.4 逐项分、总分与置信度

Bayesian 聚合逐项分：

```text
aggregate_score[s,k] = round(theta[s,k] * max_score[k], 2)
```

总分：

```text
aggregate_total[s] = sum_k aggregate_score[s,k]
```

近似标准误：

```text
SE[s,k] = sqrt(1 / (lambda + sum_r w[r,s,k]))
```

95% 可信区间：

```text
CI[s,k] = max_score[k] × clip(theta[s,k] ± 1.96 × SE[s,k], 0, 1)
```

置信度：

```text
confidence[s,k] = 1 - min(1, CI_width_normalized[s,k] / 0.20)
```

其中：

```text
CI_width_normalized = (CI_upper - CI_lower) / max_score[k]
```

五人逐项中位数必须同时保存：

```text
median_score[s,k] = median(score[1..5, s, k])
```

它不替代 Bayesian 结果，但用于风险检测、回退和解释。

## 5. 高风险与异常规则

### 5.1 强制高风险规则

以下任一条件成立，作品进入 `HIGH` 风险并停止采用五人聚合作为最终分依据：

1. **四人共识、单人极端离群**

```text
span(其余四人归一化分数) <= 0.15
且
abs(该评审分数 - median(其余四人分数)) >= 0.30
```

2. **Bayesian 单次异常评分**

```text
p_anomaly[r,s,k] >= 0.95
```

3. **模型与中位数显著冲突**

```text
abs(theta[s,k] - median_normalized[s,k]) >= 0.15
```

4. **模型不确定性过高**

```text
CI_width_normalized[s,k] >= 0.20
```

任一 Rubric 项触发，即整份作品触发高风险。

### 5.2 评分人标记

对满足规则 1 或规则 2 的评审人，创建：

```text
reviewer_flag = SUSPECTED_OUTLIER
```

含义是“评分显著异常，需要复核”，不是系统认定其主观恶意。

评审人提示流程：

1. 若该评审是最后提交且其他四人已完成，提交前可提示其复核并要求补充评分依据；
2. 不向其透露其他人分数、作者身份或异常阈值的具体对比值；
3. 评审人可坚持原分数，系统保留原始记录；
4. 五人完成后仍由后台任务进行最终异常检测；
5. 作者、其他评审人与普通学生均不可见标记。

### 5.3 行为异常：一般风险证据

行为信号不单独触发教师二次盲审，但写入风险证据；与评分异常叠加时供教师判断。

|信号|规则|默认参数|
|---|---|---|
|评审耗时过短|`duration_seconds < max(120, 0.25 × panel_median_duration)`|秒|
|评语过短|去空白后字符数 `< 30`|字符|
|低熵评分|至少 3 个 Rubric 项，归一化分数分为 5 桶后 `normalized_entropy <= 0.20`|无量纲|
|低投入组合|耗时过短、评语过短、低熵中至少两项成立|一般风险|

归一化熵：

```text
H = -sum_b p[b] * log(p[b]) / log(B)
```

其中 `B = min(5, Rubric 项数)`。

### 5.4 风险分与证据格式

单个评审任务风险分：

```text
risk_score = 100 × clip(
  0.45 × hard_outlier
  + 0.35 × max_k(p_anomaly[r,s,k])
  + 0.10 × short_duration
  + 0.05 × short_comment
  + 0.05 × low_entropy,
  0,
  1
)
```

`HIGH` 风险以 5.1 的硬条件为准；`MEDIUM` 为 `risk_score >= 50` 或存在两个行为信号；否则为 `LOW`。

证据 JSON 示例：

```json
{
  "risk_level": "HIGH",
  "risk_score": 96.4,
  "rules_triggered": ["FOUR_VS_ONE_OUTLIER", "POSTERIOR_OUTLIER"],
  "rubric_evidence": [{
    "rubric_item_id": 1,
    "max_score": 20,
    "reviewer_score": 12,
    "other_four_median": 18,
    "other_four_span": 1,
    "normalized_deviation": 0.30,
    "posterior_anomaly_probability": 0.97,
    "bayesian_score": 18.1,
    "median_score": 18.0,
    "ci_lower": 17.3,
    "ci_upper": 18.8
  }],
  "behavior_evidence": {
    "duration_seconds": 95,
    "comment_char_count": 18,
    "normalized_entropy": 0.12
  }
}
```

## 6. 高风险后的教师流程

高风险作品状态建议为：

```text
ESCALATED_FOR_TEACHER_FINAL_REVIEW
```

教师复核页面展示匿名作品材料、第一次教师分、五人原始评分、Bayesian 聚合分、异常规则和证据。教师不需要重新填写 Rubric，只需在总分范围内填写复核最终分和理由；提交即锁定。

教师锁定复核最终分后：

```text
final_score = teacher_final_review_score
final_grade_source = TEACHER_FINAL_REVIEW
```

相关 HIGH 异常自动记为已由复核处理；MEDIUM/LOW 异常仍需教师显式确认或驳回。第一次教师分、五人原始分、算法运行和复核最终分均不可覆盖或删除。

## 7. 小样本与失败回退

|情形|行为|
|---|---|
|某作品少于 5 份已提交评分|不生成正式聚合；返回 `INSUFFICIENT_REVIEWS`。|
|某评审人少于 3 份已完成评分|不单独学习其 `bias/sigma/pi`；使用群体先验。|
|整个 Panel 可用作品少于 3 份|不启用 Bayesian 校正；逐项中位数作为聚合分，`fallback_reason=PANEL_TOO_SMALL`。|
|EM 未在 100 次内收敛|逐项中位数回退，`fallback_reason=MODEL_NOT_CONVERGED`，同时写一般风险。|
|数值异常、缺失 Rubric 或分数越界|拒绝该运行，记录失败 `algorithm_run`，不写入聚合结果。|
|Bayesian 结果可信区间过宽|按高风险规则升级，不让低置信模型直接决定成绩。|

## 8. 可复现性

每次运行必须记录：

```json
{
  "algorithm_name": "panel_bayesian_robust",
  "algorithm_version": "1.0.0",
  "random_seed": 20261003,
  "inference": "MAP-EM",
  "max_iterations": 100,
  "convergence_tolerance": 0.000001,
  "parameters_json": {},
  "input_hash": "sha256(...)"
}
```

输入哈希规则：

1. 对输入按 `panel_id -> submission_id -> reviewer_id -> rubric_item_id` 排序；
2. 保留评分、满分、任务状态、开始/提交时间、评语字符数；
3. 使用 RFC 8785 JSON Canonicalization Scheme 序列化；
4. 计算 UTF-8 字节的 SHA-256。

即使 MAP-EM 为确定性算法，也保留固定随机种子，用于确定性初始化、模拟实验和未来 MCMC 扩展。

## 9. 测试样本

### 9.1 正常样本

两项 Rubric，均满分 20；五人对作品 A 评分：

|评审人|项 1|项 2|
|---|---:|---:|
|R1|18|17|
|R2|19|18|
|R3|18|17|
|R4|17|18|
|R5|18|17|

预期：

```json
{
  "risk_level": "LOW",
  "median_scores": [18, 17],
  "bayesian_scores": [17.8, 17.4],
  "aggregate_total_approx": 35.2,
  "all_posterior_anomaly_probabilities_below": 0.50,
  "final_formula": "0.60 * first_teacher_score + 0.40 * 35.2"
}
```

### 9.2 单人异常样本

R5 在该作品上明显低于其他四人；R5 在该 Panel 的其他作品上与群体接近，因此不是长期偏严。

|评审人|项 1|项 2|
|---|---:|---:|
|R1|18|17|
|R2|19|18|
|R3|18|17|
|R4|18|18|
|R5|12|10|

预期：

```json
{
  "risk_level": "HIGH",
  "flagged_reviewer_id": "R5",
  "rules_include": [
    "FOUR_VS_ONE_OUTLIER",
    "POSTERIOR_OUTLIER"
  ],
  "item_1_other_four_median": 18,
  "item_1_other_four_span": 1,
  "item_1_r5_deviation": 6,
  "item_1_r5_posterior_anomaly_probability_at_least": 0.95,
  "aggregate_status": "ESCALATED_FOR_TEACHER_FINAL_REVIEW",
  "final_formula": "teacher_final_review_score"
}
```

## 10. 论文依据与项目工程参数的边界

### 论文依据

* 贝叶斯潜在真实分、评分者偏差和可靠性估计；
* 对离散 Rubric 的统计处理；
* 战略性评分与异常检测的必要性；
* 对抗污染应显式建模，不能只用简单平均。

### 项目自行设定的工程参数

* `0.60 / 0.40` 的常规最终分权重；
* 高风险后改用第二次匿名教师评分；
* 四人跨度 `15%`、单人偏离 `30%`；
* 后验异常阈值 `95%`；
* 模型/中位数差异 `15%`；
* 可信区间宽度 `20%`；
* 耗时、评语长度、低熵阈值；
* 只防单人或少数极端评分，不处理五人一致串通；
* 发布后冻结算法参数。
