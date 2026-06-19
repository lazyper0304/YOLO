<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getSystemStatus } from '@/api/system'
import { SwitchButton } from '@element-plus/icons-vue'

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
    const d = await getSystemStatus()
    cpuPercent.value = d.cpu_percent
    memPercent.value = d.memory_percent
    if (d.gpu?.available) {
      gpuUtil.value = d.gpu.utilization
      gpuUsed.value = d.gpu.memory_used_mb
      gpuTotal.value = d.gpu.memory_total_mb
      gpuTemp.value = d.gpu.temperature || 0
    }
  } catch { /* */ }
}

onMounted(() => { fetchStatus(); timer = setInterval(fetchStatus, 5000) })
onUnmounted(() => { if (timer) clearInterval(timer) })

function handleLogout() { authStore.logout(); router.push('/login') }

function color(v: number) {
  if (v > 80) return '#F56C6C'
  if (v > 50) return '#E6A23C'
  return '#67C23A'
}
</script>

<template>
  <header class="h-11 bg-white border-b border-gray-200 flex items-center justify-between px-4 flex-shrink-0">
    <div class="flex items-center gap-3">
      <span class="text-sm font-bold text-gray-700 tracking-tight">YOLO 目标检测分析平台</span>
      <div class="flex items-center gap-1.5 text-[10px]">
        <span v-if="gpuTotal" class="flex items-center gap-1 text-gray-400">
          <span class="inline-block w-1.5 h-1.5 rounded-full" :style="{ background: color(gpuUtil) }"></span>
          GPU {{ gpuUtil }}%
        </span>
        <span class="flex items-center gap-1 text-gray-400">
          <span class="inline-block w-1.5 h-1.5 rounded-full" :style="{ background: color(cpuPercent) }"></span>
          CPU {{ cpuPercent }}%
        </span>
        <span class="flex items-center gap-1 text-gray-400">
          <span class="inline-block w-1.5 h-1.5 rounded-full" :style="{ background: color(memPercent) }"></span>
          MEM {{ memPercent }}%
        </span>
      </div>
    </div>

    <div class="flex items-center gap-3">
      <span class="text-xs text-gray-500">{{ authStore.username }}</span>
      <el-button text size="small" type="danger" :icon="SwitchButton" @click="handleLogout">退出</el-button>
    </div>
  </header>
</template>
