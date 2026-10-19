# 2026-10-19 修复复验证据

对应代码提交：`68bd33e6fb68bcd6fa083e166793f9053d3f96a7`，分支 `fix/verification-defects`。仅包含公开、脱敏的结构化结果和文本日志，不包含环境文件、密码、令牌、数据库或材料压缩包。

| 文件 | 用途 |
| --- | --- |
| reviewed-source-version.json | 当前提交及 12 个变更文件的 Git blob / SHA-256；前端复审后的 105 项测试 |
| repair-summary.json、final-source-hashes.json、audit.json | 前次修复复验时的范围账、工作区字节哈希和环境审计，保留当时未提交及前端 102 项的历史状态；当前提交版本以 reviewed-source-version.json 为准 |
| full-backend-ready.xml / .txt | 后端全量 166 项通过，0 跳过；末次判题退出码调整前已启动 |
| targeted-final.xml | 末次判题调整后相关后端 34 项通过；与全量有重叠 |
| frontend-final.json | 复审前前端 102 项通过 |
| frontend-reviewed.json、frontend-build-reviewed.txt | 复审补齐教师反向返回检查后，前端 105 项通过及生产构建 |
| review-redirect-before.json | 修改前新增三项教师返回测试准确失败，记录真实遗漏，不是无效脚本 |
| review-browser.json | 最终四个真实浏览器教师返回场景通过 |
| live-judge-final.json、live-browser-judge.json | 原 500ms 判题复验及页面提交与 Docker 生命周期关联 |
| live-docker-diagnostics-final.json、live-infrastructure.json、live-isolation.json | 实际资源约束、基础设施重试及他人提交隔离 |
| live-browser.json、live-upload.json | 实际会话并发/返回地址与知识点配置→认领→材料检查 |
| invalid-executions.json | 前次测试工具/环境问题，不纳入产品通过统计 |
| ruff-final.txt | 后端静态检查通过 |

完整运行目录仍位于本机 `tmp/verification/fix-20261018`，原始 213 文件快照和 10 份发布成绩保持不变。归档中的绝对路径、容器 ID 和时间属于执行时记录。原范围账的 107 项通过沿用原始验收证据，六项失败完成修复复验；未声称本轮重新人工执行全部 113 项。
