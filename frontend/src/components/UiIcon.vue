<script setup>
defineProps({ name: { type: String, required: true } })
const paths = {
  home: 'M3 10 12 3l9 7M5 9v11h5v-6h4v6h5V9',
  assignments: 'M8 4H5v17h14V4h-3M8 3h8v4H8zM8 12h8M8 16h5',
  people: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 4a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  book: 'M12 5v16M12 5C9 3 5 3 2 4v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 1',
  video: 'M3 5h18v14H3zM10 9l5 3-5 3z',
  arrow: 'M5 12h14M14 7l5 5-5 5',
  logout: 'M9 4H4v16h5M10 12h11M17 8l4 4-4 4',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  chevron: 'm9 5 7 7-7 7',
  plus: 'M12 5v14M5 12h14',
  review: 'M9 3H4v18h16V3h-5M9 3h6v4H9zM8 14l3 3 5-6',
  clock: 'M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  shield: 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7l-9-4zM8 12l3 3 5-6',
  check: 'm5 12 4 4L19 6',
  code: 'm8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16',
  pause: 'M8 5v14M16 5v14',
  play: 'm8 5 11 7-11 7z',
  replay: 'M3 11a9 9 0 1 1 2 7M3 4v7h7',
  eye: 'M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  eyeOff: 'm3 3 18 18M10.6 5.1 12 5c7 0 10 7 10 7a18 18 0 0 1-3 4M6.5 6.5A19 19 0 0 0 2 12s3 7 10 7c2 0 4-.6 5.5-1.5M10 10a3 3 0 0 0 4 4',
}
</script>
<template>
  <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.book" /></svg>
</template>
<style scoped>.ui-icon { width:20px; height:20px; flex-shrink:0; }</style>
