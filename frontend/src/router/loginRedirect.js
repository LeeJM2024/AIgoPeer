// Only return to a known, protected route that the signed-in role can use.
export function loginRedirect(router, redirect, role) {
  const fallback = role === 'TEACHER' ? '/teacher' : '/student'
  if (typeof redirect !== 'string' || !redirect.startsWith('/') ||
      redirect.startsWith('//') || /[\\\u0000-\u0020]/.test(redirect)) return fallback
  const target = router.resolve(redirect)
  if (!target.matched.length || target.meta.public || target.redirectedFrom ||
      target.matched.some(record => record.redirect) ||
      (target.meta.teacher && role !== 'TEACHER') ||
      (target.meta.student && role !== 'STUDENT')) return fallback
  return target.fullPath
}
