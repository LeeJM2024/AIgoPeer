"""add student topic claims and versioned project submissions

Revision ID: 20260928_0002
Revises: 20260928_0001
Create Date: 2026-09-28
"""

from alembic import op

revision = "20260928_0002"
down_revision = "20260928_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE topics (
          id BIGSERIAL PRIMARY KEY,
          code VARCHAR(8) NOT NULL UNIQUE,
          chapter VARCHAR(100) NOT NULL,
          name VARCHAR(200) NOT NULL,
          description TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE topic_claims (
          id BIGSERIAL PRIMARY KEY,
          assignment_id BIGINT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
          student_id BIGINT NOT NULL REFERENCES users(id),
          topic_id BIGINT NOT NULL REFERENCES topics(id),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(assignment_id, student_id)
        );
        CREATE INDEX ix_topic_claims_assignment_topic ON topic_claims(assignment_id, topic_id);

        ALTER TABLE submissions
          ADD COLUMN topic_claim_id BIGINT REFERENCES topic_claims(id),
          ADD COLUMN version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
          ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE,
          ADD COLUMN manifest_json JSONB;

        WITH ranked_submissions AS (
          SELECT
            id,
            row_number() OVER (
              PARTITION BY assignment_id, author_id
              ORDER BY submitted_at ASC NULLS FIRST, id ASC
            ) AS next_version,
            row_number() OVER (
              PARTITION BY assignment_id, author_id
              ORDER BY submitted_at DESC NULLS LAST, id DESC
            ) AS recency_rank
          FROM submissions
        )
        UPDATE submissions AS submission
        SET version = ranked_submissions.next_version,
            is_current = ranked_submissions.recency_rank = 1
        FROM ranked_submissions
        WHERE submission.id = ranked_submissions.id;

        CREATE UNIQUE INDEX uq_submissions_current_author_assignment
          ON submissions(assignment_id, author_id) WHERE is_current;

        ALTER TABLE material_checks
          ADD COLUMN warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN details_json JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
    )
    op.execute(
        """
        INSERT INTO topics(code, chapter, name, description) VALUES
          ('01', '算法分析基础', '渐近符号与复杂度分析', 'O、Ω、Θ 与时间、空间复杂度分析。'),
          ('02', '图搜索', '广度优先搜索 BFS', '队列、分层遍历与无权图最短路。'),
          ('03', '图搜索', '深度优先搜索 DFS', '递归或显式栈、回溯与连通性。'),
          ('04', '图搜索', '拓扑排序', '有向无环图、入度法与判环。'),
          ('05', '贪心算法', '贪心策略设计与适用条件', '贪心选择性质、最优子结构与反例。'),
          ('06', '贪心算法', '贪心算法的正确性证明', '交换论证和最优值下界。'),
          ('07', '分治算法', '分治框架与递归设计', '子问题、递归参数、终止条件与合并。'),
          ('08', '分治算法', '归并算法与分治合并策略', '有序序列合并与循环不变式。'),
          ('09', '分治算法', '分治递推式与主定理', '递归树、主定理与操作计数实验。'),
          ('10', '动态规划', '最优子结构与状态转移设计', '状态、转移、边界与正确性。'),
          ('11', '动态规划', '记忆化搜索与递推实现', '自顶向下与自底向上实现比较。'),
          ('12', '网络流', '残量网络与增广路算法', '容量、残量、反向边与 BFS 增广。'),
          ('13', '网络流', '最大流最小割定理', '割容量、残量图与最优性。'),
          ('14', '高级数据结构', '并查集', '路径压缩、按秩合并与摊还复杂度。'),
          ('15', '高级数据结构', '树状数组', 'lowbit、前缀和与区间和。'),
          ('16', '高级数据结构', '线段树与懒标记', '区间分解、查询、更新和下传。'),
          ('17', '字符串匹配', 'KMP 算法与失配函数', '前缀函数、失配回退与线性匹配。'),
          ('18', '字符串匹配', 'Trie 前缀树', '共享前缀存储、插入与查询。'),
          ('19', '图优化算法', 'Kruskal 最小生成树算法', '割性质、安全边与并查集判环。'),
          ('20', '图优化算法', 'Prim 最小生成树算法', '跨割候选边与优先队列。'),
          ('21', '图优化算法', 'Dijkstra 最短路径算法', '非负权、松弛、优先队列与路径还原。'),
          ('22', '图优化算法', 'Bellman-Ford 算法', '多轮松弛、负权边与负环检测。'),
          ('23', '计算复杂性', 'P、NP 与多项式归约', '验证、NP 完全与归约方向。'),
          ('24', '高级算法专题', '近似算法与近似比分析', '可行解、性能界和近似保证。'),
          ('25', '高级算法专题', '随机化算法与成功概率分析', '随机选择、重复运行与成功概率。'),
          ('26', '高级算法专题', '在线算法与竞争分析', '即时决策、离线最优与竞争比。');
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS uq_submissions_current_author_assignment;
        ALTER TABLE material_checks DROP COLUMN IF EXISTS details_json, DROP COLUMN IF EXISTS warnings;
        ALTER TABLE submissions DROP COLUMN IF EXISTS manifest_json, DROP COLUMN IF EXISTS is_current,
          DROP COLUMN IF EXISTS version, DROP COLUMN IF EXISTS topic_claim_id;
        DROP TABLE IF EXISTS topic_claims;
        DROP TABLE IF EXISTS topics;
        """
    )
