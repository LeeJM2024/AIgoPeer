// Presentation only: these labels and destinations do not grant submission rights.
const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'short'
})
export const formatDeadline = (value) =>
  value ? dateFormatter.format(new Date(value)) : '未设置'
export const submissionClosed = (assignment) =>
  Boolean(
    assignment.submit_deadline &&
      new Date(assignment.submit_deadline).getTime() <= Date.now()
  )
export const stateLabel = (status) =>
  ({
    DRAFT: '草稿',
    PUBLISHED: '进行中',
    SUBMITTING: '提交中',
    REVIEWER_INITIALIZING: '分配评审中',
    REVIEWER_GRADING: '跨班评审中',
    AGGREGATING: '汇总评审中',
    TEACHER_GRADING: '教师评分中',
    PUBLISHED_RESULT: '成绩已发布'
  })[status] || '状态待更新'
const materialStatus = (status) =>
  ({
    VALID: '通过',
    INVALID: '未通过',
    PENDING: '检查中',
    SUPERSEDED: '历史版本',
    SUBMITTED: '已提交'
  })[status] || status
const codeStatus = (status) =>
  ({
    QUEUED: '排队中',
    RUNNING: '判题中',
    AC: '通过',
    WA: '答案错误',
    TLE: '超出时间限制',
    RE: '运行错误',
    CE: '编译错误',
    SYSTEM_ERROR: '判题异常'
  })[status] ?? status
export function submissionLabel(assignment) {
  if (!assignment.submission) return '未提交'
  if (assignment.type === 'PROGRAMMING')
    return `最近一次：${codeStatus(assignment.submission.status)}`
  if (!assignment.submission.material_check_status)
    return `已提交（${materialStatus(assignment.submission.status)}）`
  return `已提交（材料检查：${materialStatus(assignment.submission.material_check_status)}）`
}
export function assignmentAction(assignment) {
  if (
    assignment.type === 'FINAL_PROJECT' &&
    assignment.status === 'PUBLISHED_RESULT'
  )
    return '查看最终成绩'
  if (assignment.type === 'FINAL_PROJECT')
    return submissionClosed(assignment) ||
      !['PUBLISHED', 'SUBMITTING'].includes(assignment.status)
      ? '查看提交与材料检查'
      : assignment.submission
        ? '查看并重新上传'
        : '认领并上传'
  if (submissionClosed(assignment)) return '查看题目与结果'
  if (!assignment.submission) return '查看题目并提交'
  return ['QUEUED', 'RUNNING'].includes(assignment.submission.status)
    ? '查看判题进度'
    : '继续编写'
}
export function assignmentDestination(assignment) {
  const page =
    assignment.type === 'FINAL_PROJECT'
      ? assignment.status === 'PUBLISHED_RESULT'
        ? 'grade'
        : 'project-submission'
      : 'programming-submission'
  return `/student/assignments/${assignment.id}/${page}`
}
export function assignmentArt(assignment = {}) {
  const title = `${assignment.title || ''} ${assignment.topic?.name || ''}`
  if (/归并|merge/i.test(title)) return 'merge'
  if (/背包|动态规划|knapsack|\bdp\b/i.test(title)) return 'dp'
  if (/图算法|最短路径|Dijkstra|图论|图的|graph/i.test(title)) return 'graph'
  if (/树|递归|分治|tree/i.test(title)) return 'tree'
  if (/整数求和|两数之和|a\s*\+\s*b/i.test(title)) return 'sum'
  if (assignment.type === 'FINAL_PROJECT') return 'lesson'
  return 'code'
}
export function pendingAssignments(assignments) {
  return assignments
    .filter(
      (item) =>
        !submissionClosed(item) &&
        ['PUBLISHED', 'SUBMITTING'].includes(item.status) &&
        (!item.submission ||
          (item.type === 'PROGRAMMING' &&
            !['AC', 'QUEUED', 'RUNNING'].includes(item.submission.status)) ||
          (item.type === 'FINAL_PROJECT' &&
            (item.submission.status === 'INVALID' ||
              item.submission.material_check_status === 'INVALID')))
    )
    .sort(
      (a, b) =>
        new Date(a.submit_deadline || '9999-01-01').getTime() -
        new Date(b.submit_deadline || '9999-01-01').getTime()
    )
}
