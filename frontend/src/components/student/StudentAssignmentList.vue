<script setup>
import AssignmentArtwork from '../AssignmentArtwork.vue'
import UiIcon from '../UiIcon.vue'
import {
  assignmentAction,
  assignmentTypeLabel,
  assignmentDestination,
  formatDeadline,
  submissionClosed,
  submissionLabel,
  stateLabel
} from '../../presentation/assignments'
defineProps({ assignments: { type: Array, required: true } })
</script>
<template>
  <ul class="assignment-list" aria-label="我的作业列表">
    <li
      v-for="assignment in assignments"
      :key="assignment.id"
      class="assignment-card"
      :data-kind="assignment.type"
    >
      <div class="assignment-cover" aria-hidden="true">
        <AssignmentArtwork :assignment="assignment" />
      </div>
      <div class="assignment-body">
        <h2>{{ assignment.title }}</h2>
        <div class="assignment-details">
          <span>{{
            assignmentTypeLabel(assignment.type)
          }}</span
          ><span
            >提交截止：{{ formatDeadline(assignment.submit_deadline) }}</span
          ><span v-if="assignment.review_deadline"
            >评审截止：{{ formatDeadline(assignment.review_deadline) }}</span
          >
        </div>
        <p class="submission-state">{{ submissionLabel(assignment) }}</p>
      </div>
      <div class="assignment-action">
        <span class="status-badge" :data-state="assignment.status">{{
          assignment.status === 'PUBLISHED_RESULT'
            ? '成绩已发布'
            : submissionClosed(assignment)
              ? '已截止'
              : stateLabel(assignment.status)
        }}</span
        ><RouterLink :to="assignmentDestination(assignment)" class="action-link"
          >{{ assignmentAction(assignment) }}<UiIcon name="arrow"
        /></RouterLink>
      </div>
    </li>
  </ul>
</template>
<style scoped>
.assignment-list {
  display: flex;
  flex-direction: column;
  list-style: none;
  padding: 4px 20px;
  margin: 0;
  background: var(--surface-translucent);
  border-radius: 28px;
  gap: 0;
}
.assignment-card {
  display: grid;
  grid-template-columns: 138px minmax(0, 1fr) auto;
  gap: 22px;
  align-items: center;
  padding: 18px 0;
  min-width: 0;
  background: transparent;
  border: 0;
}
.assignment-cover {
  height: 112px;
  border-radius: 20px;
  overflow: hidden;
  background: var(--art-gradient);
  position: relative;
}
.assignment-cover .assignment-artwork {
  width: 100%;
  height: 100%;
}
.project-play {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 26px;
  height: 26px;
  padding: 7px;
  border-radius: 50%;
  color: var(--ink);
  background: white;
}
.assignment-body {
  min-width: 0;
}
.assignment-body h2 {
  font-size: 18px;
  font-weight: 650;
  line-height: 1.5;
  overflow-wrap: anywhere;
  margin: 0 0 8px;
  text-wrap: pretty;
}
.assignment-details {
  display: flex;
  gap: 5px 14px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.8;
}
.submission-state {
  font-size: 12px;
  color: var(--muted);
  margin: 7px 0 0;
}
.assignment-action {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  max-width: 180px;
}
.action-link {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-height: 44px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  color: var(--primary);
}
.action-link:hover {
  color: var(--primary-hover);
}
.action-link .ui-icon {
  width: 16px;
  height: 16px;
}
@media (max-width: 1100px) {
  .assignment-card {
    grid-template-columns: 112px minmax(0, 1fr);
    gap: 10px 16px;
  }
  .assignment-cover {
    grid-row: 1/3;
    height: 125px;
  }
  .assignment-action {
    grid-column: 2;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    max-width: none;
    gap: 8px;
  }
  .assignment-body h2 {
    font-size: 17px;
  }
}
@media (max-width: 760px) {
  .assignment-list {
    padding: 2px 14px;
    border-radius: 24px;
  }
  .assignment-card {
    grid-template-columns: 88px minmax(0, 1fr);
    padding: 17px 0;
    gap: 8px 12px;
  }
  .assignment-cover {
    height: 112px;
    border-radius: 17px;
    align-self: center;
  }
  .assignment-body h2 {
    font-size: 16px;
    margin-bottom: 6px;
  }
  .assignment-details {
    gap: 2px;
    flex-direction: column;
    font-size: 11px;
  }
  .submission-state {
    font-size: 11px;
  }
  .assignment-action {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 4px 8px;
  }
  .action-link {
    font-size: 12px;
    min-height: 40px;
  }
  .status-badge {
    font-size: 11px;
  }
}
</style>
