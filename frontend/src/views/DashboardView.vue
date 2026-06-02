<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftSidebar from '@/components/layout/LeftSidebar.vue'
import client from '@/api/client'
import { Monitor, TrendCharts, Setting, DataAnalysis } from '@element-plus/icons-vue'

const router = useRouter()

interface DashboardData {
  today_detections: number
  total_detections: number
  mode_breakdown: { yolo_only: number; llm_only: number; collaborative: number }
  yolo_models: number
  llm_configs: number
  recent_detections: { id: number; mode: string; source_type: string; created_at: string }[]
}

const stats = ref<DashboardData>({
  today_detections: 0, total_detections: 0,
  mode_breakdown: { yolo_only: 0, llm_only: 0, collaborative: 0 },
  yolo_models: 0, llm_configs: 0, recent_detections: [],
})

onMounted(async () => {
  try {
    const res = await client.get('/api/dashboard/stats')
    stats.value = res.data.data
  } catch { /* ignore */ }
})

const cards = computed(() => [
  { label: '累计检测', value: stats.value.total_detections, icon: TrendCharts, color: '#67C23A', path: '/history' },
  { label: 'YOLO模型', value: stats.value.yolo_models, icon: Setting, color: '#E6A23C', path: '/models' },
  { label: 'LLM配置', value: stats.value.llm_configs, icon: Monitor, color: '#F56C6C', path: '/models' },
])
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 overflow-auto bg-gray-50">
        <div class="max-w-4xl mx-auto p-8">
          <h2 class="text-2xl font-bold mb-6">首页概览</h2>

          <!-- Stats Cards -->
          <div class="grid grid-cols-3 gap-4 mb-8">
            <div
              v-for="card in cards" :key="card.label"
              class="bg-white rounded-lg shadow-sm p-5 cursor-pointer hover:shadow-md transition-shadow"
              @click="router.push(card.path)"
            >
              <div class="flex items-center justify-between mb-3">
                <span class="text-sm text-gray-400">{{ card.label }}</span>
                <el-icon :size="24" :color="card.color"><component :is="card.icon" /></el-icon>
              </div>
              <div class="text-3xl font-bold" :style="{ color: card.color }">{{ card.value }}</div>
            </div>
          </div>

          <!-- Mode Breakdown -->
          <div class="bg-white rounded-lg shadow-sm p-5 mb-8">
            <h3 class="text-sm font-semibold text-gray-500 mb-4">检测模式分布</h3>
            <div class="flex gap-6">
              <div class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-blue-500"></div>
                <span class="text-sm">YOLO-only: {{ stats.mode_breakdown.yolo_only }}</span>
              </div>
              <div class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-green-500"></div>
                <span class="text-sm">LLM-only: {{ stats.mode_breakdown.llm_only }}</span>
              </div>
              <div class="flex items-center gap-2">
                <div class="w-3 h-3 rounded-full bg-purple-500"></div>
                <span class="text-sm">协同: {{ stats.mode_breakdown.collaborative }}</span>
              </div>
            </div>
          </div>

          <!-- Recent Detections -->
          <div class="bg-white rounded-lg shadow-sm p-5">
            <h3 class="text-sm font-semibold text-gray-500 mb-4">最近检测</h3>
            <el-table :data="stats.recent_detections" size="small" stripe>
              <el-table-column prop="id" label="ID" width="80" />
              <el-table-column prop="mode" label="模式" width="120">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.mode === 'yolo_only' ? '' : row.mode === 'llm_only' ? 'success' : 'warning'">
                    {{ row.mode === 'yolo_only' ? 'YOLO' : row.mode === 'llm_only' ? 'LLM' : '协同' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="source_type" label="类型" width="100" />
              <el-table-column prop="created_at" label="时间" />
            </el-table>
            <div v-if="stats.recent_detections.length === 0" class="text-center text-gray-400 py-6 text-sm">暂无检测记录</div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
