// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import SubmissionEvidence from './SubmissionEvidence.vue'
import { getEvidence, getMaterial } from '../../api/teacher'

vi.mock('../../api/teacher', () => ({ getEvidence: vi.fn(), getMaterial: vi.fn() }))

it('教师能查看最新评分与每次修改的前后分数、评语、原因和时间', async () => {
  const snapshot = (score, comment) => ({ rubric_scores: [{ rubric_item_id: 2, name: '正确性', max_score: 100, score }], comment })
  getEvidence.mockResolvedValue({ version: 1, is_current: true, archive_available: false, materials: [], anomalies: [],
    reviews: [{ id: 8, reviewer_name: '评委甲', student_no: 'D201', status: 'SUBMITTED', comment: '最新评语',
      scores: [{ name: '正确性', score: 95, max_score: 100 }], revisions: [
        { version: 2, reason: '第一次误填更正', before: snapshot(80, '初始评语'), after: snapshot(90, '第二版评语'), created_at: '2026-10-28T10:00:00Z' },
        { version: 3, reason: '核对代码后调整', before: snapshot(90, '第二版评语'), after: snapshot(95, '最新评语'), created_at: '2026-10-28T11:00:00Z' }
      ] }] })
  const w = mount(SubmissionEvidence, { props: { submissionId: 5 } })
  await flushPromises()
  expect(w.text()).toContain('评分修改记录（2 次）')
  const records = w.findAll('.revision-entry')
  expect(records).toHaveLength(2)
  expect(records[0].text()).toContain('80 → 90 / 100')
  expect(records[0].text()).toContain('第一次误填更正')
  expect(records[0].text()).toContain('初始评语')
  expect(records[1].text()).toContain('90 → 95 / 100')
  expect(records[1].text()).toContain('核对代码后调整')
  expect(records[1].text()).toContain('最新评语')
  expect(records[1].text()).toContain('2026')
  w.unmount()
})
