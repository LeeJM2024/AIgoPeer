# AlgoPeer

《算法设计与分析》课程作业与跨班评审平台。项目采用“单仓库 + 模块化单体”：Vue 3 前端、FastAPI 后端、PostgreSQL、Redis，算法代码作为独立 Python 包由后端内部调用。

## 当前骨架包含什么

* 两班固定五人交叉评审的数据表、迁移和服务接口；
* 认证与权限的统一入口（教师、学生、指定评审人）；
* 教师分版本化、锁定和算法无权写教师分的数据库约束；
* 组员 2 的学生/评审端页面和 API 客户端占位；
* 组员 3 的任务初始化、聚合、异常检测算法接口和可测纯函数；
* Docker Compose 本地环境与最小测试入口。

## 第一次启动

1. 复制 `.env.example` 为 `.env`，修改密码与 JWT 密钥。
2. 启动基础服务和后端：`docker compose up --build`。
3. 打开 `http://localhost:8000/docs` 查看后端 OpenAPI；健康检查为 `GET /api/health`。
4. 前端开发时进入 `frontend` 后执行 `npm install` 和 `npm run dev`。

后端容器启动时会执行 `alembic upgrade head`。开发中数据库结构只能新建 Alembic 迁移，禁止手工改库。

## 目录

* `backend/`：FastAPI、迁移、权限、服务层；
* `frontend/`：Vue 页面、路由、API 客户端；
* `algorithm/`：成员 3 的可复现实验和算法实现；
* `tests/`：后端单元/接口测试；
* `docs/`：给组员的接入说明；

顶层的 `01-需求说明.md` 至 `05-协作与测试.md` 是本项目的正式设计依据。接口有变更时，必须同时改 `04-接口文档.md`、迁移和测试。
