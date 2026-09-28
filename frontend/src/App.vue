<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <header class="app-header">
    <RouterLink class="brand" to="/">AlgoPeer</RouterLink>
    <nav>
      <RouterLink to="/">测试台</RouterLink>
      <RouterLink to="/student">我的作业</RouterLink>
      <RouterLink to="/reviewer/tasks">评审任务</RouterLink>
    </nav>
  </header>
  <main class="page-shell"><RouterView /></main>
</template>
