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
}
</script>
<template>
  <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.book" /></svg>
</template>
<style scoped>.ui-icon { width:20px; height:20px; flex-shrink:0; }</style>
