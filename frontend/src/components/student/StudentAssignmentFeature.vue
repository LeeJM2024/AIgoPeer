<script setup>
import AssignmentArtwork from '../AssignmentArtwork.vue'
import UiIcon from '../UiIcon.vue'
import {
  assignmentAction,
  assignmentDestination,
  formatDeadline,
  submissionClosed,
  submissionLabel,
  stateLabel
} from '../../presentation/assignments'
defineProps({ assignment: { type: Object, required: true } })
</script>
<template>
  <article
    class="featured-assignment assignment-card"
    aria-label="当前课程作业"
  >
    <div class="feature-copy">
      <div class="feature-meta">
        <span>{{
          assignment.type === 'PROGRAMMING' ? '编程练习' : '期末项目'
        }}</span
        ><span class="status-badge" :data-state="assignment.status">{{
          assignment.status === 'PUBLISHED_RESULT'
            ? '成绩已发布'
            : submissionClosed(assignment)
              ? '已截止'
              : stateLabel(assignment.status)
        }}</span>
      </div>
      <h2>{{ assignment.title }}</h2>
      <p>{{ submissionLabel(assignment) }}</p>
      <div class="feature-deadline">
        提交截止　{{ formatDeadline(assignment.submit_deadline) }}
      </div>
      <RouterLink
        class="button feature-action"
        :to="assignmentDestination(assignment)"
        >{{ assignmentAction(assignment) }}<UiIcon name="arrow"
      /></RouterLink>
    </div>
    <figure class="feature-art">
      <AssignmentArtwork :assignment="assignment" />
      <figcaption>算法主题插画 · 非题目测试数据</figcaption>
    </figure>
  </article>
</template>
<style scoped>
.featured-assignment {
  display: grid;
  grid-template-columns: 49% 51%;
  min-height: 338px;
  background: linear-gradient(110deg, #e5eeff, #f9fcff);
  border-radius: 32px;
  overflow: hidden;
  color: white;
}
.feature-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 32px 40px 32px 30px;
  border-radius: 30px 100px 100px 30px;
  background: var(--feature-gradient);
  min-width: 0;
}
.feature-meta {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: var(--studio-muted);
  flex-wrap: wrap;
}
.feature-meta .status-badge {
  background: rgb(255 255 255 / 16%);
  color: white !important;
}
.feature-copy h2 {
  color: white;
  font-size: 30px;
  line-height: 1.4;
  letter-spacing: -0.8px;
  margin: 22px 0 10px;
  overflow-wrap: anywhere;
}
.feature-copy > p {
  font-size: 14px;
  color: var(--studio-muted);
  margin: 0 0 20px;
  line-height: 1.8;
}
.feature-deadline {
  margin-top: auto;
  padding-top: 12px;
  font-size: 12px;
  color: var(--studio-muted);
}
.feature-action {
  justify-content: space-between;
  margin-top: 16px;
  background: white;
  color: var(--ink);
  border-radius: 14px;
  font-size: 14px;
  max-width: 100%;
}
.feature-action:hover {
  background: var(--primary-soft);
  color: var(--ink);
}
.feature-art {
  display: flex;
  flex-direction: column;
  justify-content: center;
  margin: 0;
  padding: 14px 16px 12px;
  min-width: 0;
}
.feature-art .assignment-artwork {
  height: auto;
  max-height: 310px;
  aspect-ratio: 1.5;
  flex: 1;
}
.feature-art figcaption {
  font-size: 11px;
  text-align: center;
  color: var(--muted);
  padding-top: 6px;
}
@media (max-width: 1200px) {
  .feature-copy {
    padding: 26px 32px 26px 24px;
    border-radius: 28px 72px 72px 28px;
  }
  .feature-copy h2 {
    font-size: 26px;
  }
  .featured-assignment {
    min-height: 310px;
  }
  .feature-art {
    padding: 10px;
  }
}
@media (max-width: 1000px) and (min-width: 761px) {
  .featured-assignment {
    grid-template-columns: 54% 46%;
  }
  .feature-copy {
    padding-right: 24px;
  }
  .feature-copy h2 {
    font-size: 24px;
  }
}
@media (max-width: 760px) {
  .featured-assignment {
    grid-template-columns: minmax(0, 1fr);
    border-radius: 28px;
  }
  .feature-art {
    grid-row: 1;
    padding: 8px 12px 12px;
  }
  .feature-art .assignment-artwork {
    height: 210px;
    flex: none;
  }
  .feature-art figcaption {
    padding-top: 0;
    font-size: 10px;
  }
  .feature-copy {
    padding: 26px 24px 28px;
    border-radius: 48px 48px 26px 26px;
  }
  .feature-copy h2 {
    font-size: 26px;
    margin-top: 18px;
  }
  .feature-deadline {
    padding-top: 12px;
  }
  .feature-action {
    width: 100%;
  }
}
</style>
