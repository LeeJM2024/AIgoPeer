import JSZip from 'jszip'
import { expect, it } from 'vitest'
import { inspectProjectArchive } from './projectArchive'

async function archive(extra = {}, omit = []) {
  const zip = new JSZip()
  const files = {
    'slides.pptx': 'slides', 'video.mp4': 'video', 'README.md': 'readme', 'src/main.cpp': 'code',
    'tests/1.in': '1', 'tests/1.out': '1', 'tests/2.in': '2', 'tests/2.out': '2',
    'tests/3.in': '3', 'tests/3.out': '3', ...extra
  }
  for (const [path, contents] of Object.entries(files)) if (!omit.includes(path)) zip.file(path, contents)
  return zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' })
}

it('识别材料与同名用例，保留真实路径，不猜测例题页码', async () => {
  const result = await inspectProjectArchive(await archive({ 'tests/10.in': '', 'tests/10.out': '' }))
  expect(result.form).toMatchObject({ pptPath: 'slides.pptx', videoPath: 'video.mp4', readmePath: 'README.md', sourcePaths: 'src/main.cpp', examplePages: '' })
  expect(result.form.tests.map((t) => t.inputPath)).toEqual(['tests/1.in', 'tests/2.in', 'tests/3.in', 'tests/10.in'])
})

it('清单补充页码，并在多个PPT中指定正确文件', async () => {
  const result = await inspectProjectArchive(await archive({
    'other.pptx': '', 'manifest.json': JSON.stringify({ ppt_path: 'slides.pptx', examples: [{ location: 'PPT', pages: [4, 5, 6] }] })
  }))
  expect(result.manifestUsed).toBe(true)
  expect(result.form.pptPath).toBe('slides.pptx')
  expect(result.form.examplePages).toBe('4,5,6')
  expect(result.candidates.pptPath).toHaveLength(2)
})

it('没有清单时不擅自选择多份材料，并提示缺失视频与测试', async () => {
  const result = await inspectProjectArchive(await archive({ 'second.pptx': '' }, ['video.mp4', 'tests/3.out']))
  expect(result.form.pptPath).toBe('')
  expect(result.form.videoPath).toBe('')
  expect(result.notices.join()).toContain('发现多个PPT文件')
  expect(result.notices.join()).toContain('未找到视频文件')
  expect(result.form.tests[2]).toEqual({ inputPath: '', expectedPath: '' })
})

it('损坏清单退回文件识别；清单声明的缺失材料保留路径并提示，页码不接受重复和非整数', async () => {
  const broken = await inspectProjectArchive(await archive({ 'manifest.json': '{invalid' }))
  expect(broken.form.videoPath).toBe('video.mp4')
  expect(broken.notices.join()).toContain('读取失败')
  const missing = await inspectProjectArchive(await archive({ 'manifest.json': JSON.stringify({
    ppt_path: 'missing.pptx', tests: [{ input_path: null }], source_paths: ['missing.cpp'],
    examples: [{ location: 'PPT', pages: [4, 4, 5.5] }]
  }) }))
  expect(missing.form.pptPath).toBe('missing.pptx')
  expect(missing.notices.join()).toContain('ppt_path 未匹配')
  expect(missing.form.examplePages).toBe('')
  expect(missing.form.tests[0].inputPath).toBe('tests/1.in')
})

it('保留外层目录并支持该目录中的相对清单路径', async () => {
  const zip = new JSZip()
  zip.file('作业/slides.pptx', '')
  zip.file('作业/manifest.json', JSON.stringify({ ppt_path: 'slides.pptx', examples: [{ location: 'PPT', pages: [1, 2, 3] }] }))
  const result = await inspectProjectArchive(await zip.generateAsync({ type: 'uint8array' }))
  expect(result.form.pptPath).toBe('作业/slides.pptx')
  expect(result.form.examplePages).toBe('1,2,3')
})

it('拒绝无效ZIP和越界路径，限制清单解压大小', async () => {
  await expect(inspectProjectArchive(new Uint8Array([1, 2, 3]))).rejects.toThrow()
  await expect(inspectProjectArchive(await archive({ '../evil.cpp': '' }))).rejects.toThrow('不规范的路径')
  const huge = await inspectProjectArchive(await archive({ 'manifest.json': ' '.repeat(300000) }))
  expect(huge.notices.join()).toContain('256 KB')
  expect(huge.form.pptPath).toBe('slides.pptx')
})
