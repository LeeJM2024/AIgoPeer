const MAX_MANIFEST_BYTES = 256 * 1024
const safePath = (path) => typeof path === 'string' && path.length > 0 &&
  !path.startsWith('/') && !path.includes('\\') && !path.includes(':') &&
  path.split('/').every((part) => part && part !== '.' && part !== '..')
const sortPaths = (paths) => paths.sort((a, b) => a.localeCompare(b, 'zh-CN', { numeric: true }))

export function emptyProjectForm() {
  return {
    pptPath: '', videoPath: '', readmePath: '', sourcePaths: '', examplePages: '',
    tests: Array.from({ length: 3 }, () => ({ inputPath: '', expectedPath: '' }))
  }
}

// Only decompress the small optional manifest; videos and slides stay compressed.
function readManifest(entry) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    const stream = entry.internalStream('uint8array')
    stream.on('data', (chunk) => {
      size += chunk.length
      if (size > MAX_MANIFEST_BYTES) {
        stream.pause()
        reject(new Error('清单文件超过 256 KB'))
      } else chunks.push(chunk)
    }).on('error', reject).on('end', () => {
      const bytes = new Uint8Array(size)
      let offset = 0
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length }
      try { resolve(JSON.parse(new TextDecoder().decode(bytes).replace(/^\uFEFF/, ''))) }
      catch { reject(new Error('清单不是有效的 JSON')) }
    }).resume()
  })
}

export async function inspectProjectArchive(data) {
  const { default: JSZip } = await import('jszip')
  const zip = await JSZip.loadAsync(data)
  const entries = Object.values(zip.files).filter((entry) => !entry.dir)
  if (entries.some((entry) => !safePath(entry.unsafeOriginalName || entry.name))) {
    throw new Error('ZIP 中存在不规范的路径，请使用相对路径重新打包。')
  }
  const paths = sortPaths(entries.map((entry) => entry.name)
    .filter((path) => !path.split('/').some((part) => part.startsWith('.') || part === '__MACOSX')))
  const candidates = {
    pptPath: paths.filter((p) => /\.pptx$/i.test(p)),
    videoPath: paths.filter((p) => /\.mp4$/i.test(p)),
    readmePath: paths.filter((p) => /(^|\/)readme(?:\.md|\.txt)?$/i.test(p))
  }
  const form = emptyProjectForm()
  for (const [field, options] of Object.entries(candidates)) {
    if (options.length === 1) form[field] = options[0]
  }
  form.sourcePaths = paths.filter((p) => /\.(cpp|cc|cxx|c|h|hpp|py|java|js|ts|go|rs|cs|kt)$/i.test(p)).join('\n')
  const pairs = paths.filter((p) => /\.in$/i.test(p))
    .map((inputPath) => ({ inputPath, expectedPath: paths.find((p) =>
      p.replace(/\.out$/i, '.in') === inputPath.replace(/\.in$/i, '.in') && /\.out$/i.test(p)) || '' }))
    .filter((pair) => pair.expectedPath)
  form.tests = pairs.length ? pairs : form.tests
  while (form.tests.length < 3) form.tests.push({ inputPath: '', expectedPath: '' })
  const notices = []
  let manifestUsed = false
  const manifests = paths.filter((p) => /(^|\/)manifest\.json$/i.test(p))
  if (manifests.length === 1) {
    try {
      const manifest = await readManifest(zip.file(manifests[0]))
      if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) throw new Error('清单应为 JSON 对象')
      const base = manifests[0].slice(0, -'manifest.json'.length)
      const resolvePath = (p) => safePath(p) ? (paths.includes(p) ? p : paths.includes(base + p) ? base + p : '') : ''
      for (const [key, field] of [['ppt_path', 'pptPath'], ['video_path', 'videoPath'], ['readme_path', 'readmePath']]) {
        if (manifest[key] !== undefined) {
          const resolved = resolvePath(manifest[key])
          const declared = resolved || (safePath(manifest[key]) ? base + manifest[key] : '')
          const pattern = { pptPath: /\.pptx$/i, videoPath: /\.mp4$/i, readmePath: /(^|\/)readme(?:\.md|\.txt)?$/i }[field]
          if (declared && pattern.test(declared)) form[field] = declared
          if (!resolved) notices.push(`清单中的 ${key} 未匹配到相应材料，请核对。`)
        }
      }
      if (Array.isArray(manifest.source_paths)) {
        const sources = manifest.source_paths.map(resolvePath)
        if (sources.length && sources.every(Boolean)) form.sourcePaths = sources.join('\n')
        else notices.push('清单中的源码路径不完整，已保留文件识别结果。')
      }
      if (Array.isArray(manifest.tests)) {
        const tests = manifest.tests.map((test) => ({
          inputPath: resolvePath(test?.input_path), expectedPath: resolvePath(test?.expected_path)
        }))
        if (tests.length >= 3 && tests.every((t) => t.inputPath && t.expectedPath)) form.tests = tests
        else notices.push('清单中的测试路径不完整，已保留同名配对结果。')
      }
      const pages = manifest.examples?.filter?.((e) => e?.location === 'PPT').flatMap((e) => e.pages || [])
      if (pages?.length >= 3 && pages.every((p) => Number.isInteger(p) && p > 0) && new Set(pages).size === pages.length) {
        form.examplePages = pages.join(',')
      }
      manifestUsed = true
    } catch (err) { notices.push(`manifest.json 读取失败：${err.message}。已按文件名识别。`) }
  } else if (manifests.length > 1) notices.push('发现多份 manifest.json，已按文件名识别，请手动填写例题页码。')
  for (const [field, label] of [['pptPath', 'PPT'], ['videoPath', '视频'], ['readmePath', 'README']]) {
    if (!candidates[field].length) notices.push(`未找到${label}文件，请补充材料或核对路径。`)
    else if (!form[field]) notices.push(`发现多个${label}文件，请选择本次提交使用的文件。`)
  }
  if (!form.sourcePaths) notices.push('未识别到源码，请手动填写源码路径。')
  if (form.tests.some((t) => !t.inputPath || !t.expectedPath)) notices.push('未找到三组完整测试，请补全输入和预期输出路径。')
  if (!form.examplePages) notices.push('请填写至少三个例题所在的 PPT 页码；包内 manifest.json 可提供该信息。')
  return { form, candidates, notices, manifestUsed }
}
