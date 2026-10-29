# AlgoPeer：跨班随机分配与稀疏 Bayesian 鲁棒聚合算法规格

版本：聚合 `2.1.0` / 分配 `1.0.0`
状态：2026-10-22 功能分支实现；以跨班公平随机评审为唯一管线，不保留固定组业务模式。
适用范围：两个班的有效提交者参与随机评阅，每份作品来自对方班五名不同学生；`review_panel` 仅界定推断方向。

分配、补评和历史关系的业务设计见 [最终方案](../docs/跨班公平随机评审与稀疏贝叶斯聚合最终方案.md)，本文件记录实现细节。

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

小样本五人逐项一致时，聚合分为逐项中位数之和，正常最终分仍使用上述 `0.60 / 0.40` 公式。

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
|`panel_id`|int|评审方向 ID。|
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

**小样本一致评分豁免（1.0.1）：**仅当 `fallback_reason=PANEL_TOO_SMALL`，某份作品的自己的五名不同评审人全部完成评分，每个 Rubric 项的五人原始分与满分均一致，且五人的评分项集合完整、无重复时，该作品不因 `WIDE_CREDIBLE_INTERVAL` 升级为 HIGH。每个评分维度可以有不同分数，只要求该维度五人一致。判断逐份作品进行，不扩展到整个 Panel。

少于五份评分、重复评审人、评分项缺失/重复、任何维度不一致、满分不一致或 `MODEL_NOT_CONVERGED`，均不适用豁免。四对一离群、有效模型的异常后验及其他硬规则仍保留；行为信号仍记录，必要时按 LOW/MEDIUM 的显式处理流程执行。

### 5.2 评分人标记

对满足规则 1 或规则 2 的评审人，创建：

```text
reviewer_flag = SUSPECTED_OUTLIER
```

含义是“评分显著异常，需要复核”，不是系统认定其主观恶意。

检测在完整评分后执行。异常证据仅教师可见，评审人不读取他人分数或异常阈值对比；原始评分保持不变。

### 5.3 行为异常：一般风险证据

评阅用时和评语字数仅作为客观记录，不参与风险分、风险等级或复核依据。低熵评分信号保留。

|信号|规则|默认参数|
|---|---|---|
|低熵评分|至少 3 个 Rubric 项，归一化分数分为 5 桶后 `normalized_entropy <= 0.20`|无量纲|

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
  + 0.05 × low_entropy,
  0,
  1
)
```

`HIGH` 风险以 5.1 的硬条件为准；`MEDIUM` 为 `risk_score >= 50`；历史关系检测也可产生 MEDIUM 提示；否则为 `LOW`。

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
|某评审人少于 3 份不同作品的已完成评分|不单独学习其 `bias/sigma/pi`；使用群体先验，`learned=False`。|
|整个 Panel 可用作品少于 3 份|不启用 Bayesian 校正；逐项中位数作为聚合分，`fallback_reason=PANEL_TOO_SMALL`，所有画像 `learned=False`。|
|小样本且某份作品五人每项一致|保留中位数回退与未学习标记，该作品豁免区间宽 HIGH；正常成绩按教师初评分 60% + 中位数聚合分 40%。|
|EM 未在 100 次内收敛|纯函数逐项中位数回退，`fallback_reason=MODEL_NOT_CONVERGED`，画像恢复先验、`learned=False`，放弃失败迭代后验；后端将运行标为 FAILED，不落库正式聚合、画像或异常记录。|
|数值异常、缺失 Rubric 或分数越界|拒绝该运行，记录失败 `algorithm_run`，不写入聚合结果。|
|Bayesian 结果可信区间过宽|按高风险规则升级，小样本五人逐项一致的作品适用上述豁免。|

### 7.1 画像学习含义与输入边界

作品数按每名评审人的不同 `submission_id` 计数，不使用 Rubric 展开行数。同一作品有三个维度仍然只算一份作品。

`learned=True` 表示该评审人达到三份作品门槛，且本轮 EM 成功收敛、其画像结果被接受。仅具备资格或完成了失败迭代都不能标为已学习。无学习资格者固定使用 `bias=0`、`sigma=sigma_prior_mean`、`pi=pi_alpha/(pi_alpha+pi_beta)`；偏差更新、噪声/先验更新和偏差居中都不会改变其先验。

纯函数与正式后端均使用稀疏实际评分；正式后端要求每份作品自己的五名不同有效评委均提交完整 Rubric。不同作品可以具有不同评委集合。纯函数返回结果不代表允许发布。`task_id` 可省略，异常证据仍按评审人和作品分别分组。

### 7.2 回退区间的含义

小样本或未收敛回退时保留区间与置信度，区间使用先验噪声、以逐项中位数为中心计算，是未校准模型的近似不确定性区间，**不是中位数估计的可信区间**。风险检测和结果输出使用同一次区间计算，不因豁免伪造更窄的区间或更高置信度。

例如五人均给 85/100，小样本区间仍为 `[74.72, 95.28]`、置信度仍为 0，但该作品豁免区间宽 HIGH。如耗时与评语正常且无其他风险信号，则无需教师最终复核。异常证据和落库 `confidence_json` 中的 `uncertainty_evidence` 记录 `interval_kind`、`fallback_reason`、`posterior_available` 和 `wide_interval_exempt`。

回退时 `posterior_anomaly_probability=0` 是未学习的兼容占位值，应结合 `posterior_available=False` 解读，不能把它当作已证明评分正常。风险等级由硬规则确定，风险分是独立的行为/异常加权量，两者不要求按数值一一对应。

## 8. 可复现性

每次运行必须记录：

```json
{
  "algorithm_name": "panel_bayesian_robust",
  "algorithm_version": "2.1.0",
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
3. 使用 Python JSON 的排序键和固定分隔符序列化评分行，将评分摘要与历史标准化残差快照一起序列化；不声明 RFC 8785 兼容；
4. 计算 UTF-8 字节的 SHA-256。

即使 MAP-EM 为确定性算法，也保留固定随机种子，用于确定性初始化、模拟实验和未来 MCMC 扩展。

算法名称、版本由纯函数常量统一提供。运行参数记录完整 `DEFAULT_PARAMETERS`（含学习门槛、五人数量、一致豁免开关、区间及风险阈值、行为规则与风险权重），以及 `inference=MAP-EM`、`low_evidence_policy=2`、画像学习/回退区间/失败落库策略。

复用要求作业、Panel、算法名称、版本、输入哈希、数值参数和策略配置全部一致且运行 COMPLETED。仅缺少旧的 `low_evidence_policy` 标记时，可使用原有 LOW 证据补齐机制；该兼容例外不放宽其他配置匹配。旧版 1.0.0 不会被新版误复用。

未发布且没有已锁定教师复核最终分时，对同一评分快照重新聚合会保留旧运行、旧聚合和原始异常证据；旧运行的 OPEN 异常归档为 DISMISSED，注明替代运行并写系统审计，新运行产生的实际异常仍需按教师流程处理。复核状态随最新结果更新，避免旧版区间宽复核状态残留。不同输入快照的旧异常不会被自动归档。已发布作业或已有锁定复核最终分的作品禁止新版重新聚合。

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
* 高风险后由同一教师查看完整证据录入复核最终分；
* 四人跨度 `15%`、单人偏离 `30%`；
* 后验异常阈值 `95%`；
* 模型/中位数差异 `15%`；
* 可信区间宽度 `20%`；
* 小样本五份完整评分逐项一致时豁免区间宽 HIGH；
* 耗时、评语长度、低熵阈值；
* 只防单人或少数极端评分，不处理五人一致串通；
* 发布后冻结算法参数。

## 11. 随机分配实现

`allocation.allocate_reviews(works,seed,history)` 使用 SciPy/HiGHS 0–1 MILP 同时求解两个方向。候选变量约 `2*n1*n2`，约束为每份恰5、班内 floor/ceil 配额、双向作者关系和≤1。历史代价按最近20份相关且早于当前的作业累计 `21-age`；每条边加入 `Random(seed)/(candidate_count+1)`，总扰动小于1，因此整数历史代价优先。

求解返回最优后再做最多3000次候选双边交换、最多8轮结构修复，只接受不增加历史代价、保持全部硬约束且减少连通分量的交换。连通性作为可测结构指标，不保证所有可行输入均能修成单分量。最终再次校验并保存任务、负载、配额、历史/名单快照、版本、输入哈希、约束规模和耗时。不可行或求解超限只保留失败记录。

`n1*n2 >= 5*(n1+n2)` 为必要容量条件；因此即便两班各5人也无法同时满足五评和禁止直接互评。100:40对应700条任务、8000个候选变量，个人配额为2与12～13。

最坏整数求解为指数搜索；稀疏矩阵存储按候选变量和约束非零项增长，结构修复另受固定搜索上限控制。

## 12. 稀疏推断与历史关系

评分按作品、评委与Rubric实际邻接建立索引，不补零、不构造全笛卡尔评分矩阵。每个方向独立推断；方向内按评委—作品图连通分量，将有学习资格评委的偏差均值居中，无资格者保持零偏差和先验噪声。画像记录 `completed_works,observation_count,graph_component,learned`。迭代目标扫描为 `O(I*M*K)`，存储为 `O(M*K+R+S*K)`。

只对后验可用的任务保存标准化残差：
`mean_k((score/max - bias - theta/max)/max(sigma,0.05))`。
当前运行读取早于当前作业、班级相关的最近20份作业，每份/方向仅取最新成功聚合，避免多次聚合重复累计。

关系检测的工程阈值：

- 当前残差绝对值至少2才参与关系提示。
- 同一评委—作者同方向异常支持至少3份不同作业：`REPEATED_SIGNED_RELATIONSHIP`，HIGH。
- 每条正向关系至少2份作业支持，构成长2～4的闭环：`PERSISTENT_POSITIVE_CYCLE`，HIGH。
- 历史重复且异常残差集中：`CONCENTRATED_RELATIONSHIP_RESIDUALS`，MEDIUM。
- 证据包含相关任务、作业、运行、残差、方向、样本数与关系环；支持数按作业去重，不按Rubric展开行计数。

历史关系检测不等于判定主观恶意；阈值为本项目工程选择。论文为贝叶斯稀疏建模与受约束随机化提供依据，MAP-EM、结构交换和关系规则是本项目融合实现，不声称复现论文全部推断过程。

### 12.1 全先验画像场景的区间规则

100:40与120:40中大班评委仅评1～2份，画像使用先验。五份先验噪声 `sigma=.12` 的正常评分即会产生约21%的区间宽度，原20%阈值会系统性升级这一方向的正常作品。模拟后新增参数 `prior_only_wide_interval_threshold=.25`：仅模型收敛且某评分项的全部评委均无画像学习资格时使用25%；小样本回退和其他场景仍用20%。

保存的近似区间不收窄，画像仍为未学习，原风险分公式不变；逐项证据记录实际 `ci_risk_threshold`，教师可见判定线。四对一、异常后验、模型冲突和历史关系HIGH均照常生效。此调整来自本次工程模拟，不来自论文默认阈值。

## 13. 替补与数据库一致性

教师仅能替换未提交任务，原因必填；从同方向参与快照中筛选未接触该作品、无直接互评且仍属对应班级的人，按当前有效负载、历史重复、ID确定人选。原任务停用、新任务建立、替补历史与审计在同一事务；已提交数据不可修改。原草稿留档但不进入正式评分。

初始均衡与替补后的实际负载区分。每份必须始终有五个有效任务，五份完整评分未齐时不正式聚合、不发布。高风险仍由初评的同一教师查看完整证据后录入一个最终分。
