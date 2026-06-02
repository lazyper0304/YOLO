<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import client from '@/api/client'

const router = useRouter()
const authStore = useAuthStore()

const cpuPercent = ref(0)
const memPercent = ref(0)
const gpuUtil = ref(0)
const gpuUsed = ref(0)
const gpuTotal = ref(0)
const gpuTemp = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

async function fetchStatus() {
  try {
    const res = await client.get('/api/system/status')
    const d = res.data.data
    cpuPercent.value = d.cpu_percent
    memPercent.value = d.memory_percent
    if (d.gpu?.available) {
      gpuUtil.value = d.gpu.utilization
      gpuUsed.value = d.gpu.memory_used_mb
      gpuTotal.value = d.gpu.memory_total_mb
      gpuTemp.value = d.gpu.temperature || 0
    }
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchStatus()
  timer = setInterval(fetchStatus, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

function color(percent: number) {
  if (percent > 80) return '#F56C6C'
  if (percent > 50) return '#E6A23C'
  return '#67C23A'
}
</script>

<template>
  <header class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 flex-shrink-0 z-10">
    <h1 class="text-lg font-bold text-gray-800">YOLO 目标检测平台</h1>

    <div class="flex items-center gap-4 text-xs text-gray-500">
      <span :style="{ color: color(cpuPercent) }">CPU {{ cpuPercent }}%</span>
      <span :style="{ color: color(memPercent) }">MEM {{ memPercent }}%</span>
      <span v-if="gpuTotal" :style="{ color: color(gpuUtil) }">
        GPU {{ gpuUtil }}% {{ gpuUsed }}/{{ gpuTotal }}MB {{ gpuTemp }}°C
      </span>
    </div>

    <div class="flex items-center gap-3">
      <span class="text-sm text-gray-600">{{ authStore.username }}</span>
      <el-button type="danger" size="small" plain @click="handleLogout">退出</el-button>
    </div>
  </header>
</template>
