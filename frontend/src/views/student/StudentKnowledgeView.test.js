// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import StudentKnowledgeView from './StudentKnowledgeView.vue'
import { getAiTopics } from '../../api/ai'
const { query, replace } = vi.hoisted(() => ({ query: {}, replace: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query }), useRouter: () => ({ replace }), RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('../../api/ai', () => ({ getAiTopics: vi.fn() }))
beforeEach(() => { vi.resetAllMocks(); getAiTopics.mockResolvedValue([
  { id: 1, chapter: '图搜索', name: '广度优先搜索 BFS', description: '队列与无权最短路' },
  { id: 2, chapter: '分治算法', name: '归并排序', description: '分解与合并' },
]) })
it('按章节和关键词筛选，选择知识点后更新链接', async () => {
  const w = mount(StudentKnowledgeView, { global: { stubs: { AiConversation: true } } }); await flushPromises()
  expect(w.findAll('.topic-list button')).toHaveLength(2)
  await w.get('#topic-chapter').setValue('分治算法'); expect(w.findAll('.topic-list button')).toHaveLength(1)
  await w.get('.topic-list button').trigger('click'); expect(replace).toHaveBeenCalledWith({ query: { topic: '2' } })
  await w.get('#topic-search').setValue('不存在'); expect(w.text()).toContain('没有匹配'); w.unmount()
})
