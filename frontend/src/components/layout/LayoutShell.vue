<script setup lang="ts">
import AppHeader from './AppHeader.vue'
import LeftSidebar from './LeftSidebar.vue'
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden bg-gray-50">
    <AppHeader />
    <div class="flex-1 flex overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 overflow-auto">
        <slot />
      </main>
      <slot name="right-panel" />
    </div>
  </div>
</template>
