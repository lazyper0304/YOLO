<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDashboardStats, fetchDailyStats, fetchModePie, type DashboardData } from '@/api/dashboard'
import { getSystemStatus } from '@/api/system'
import { LayoutShell } from '@/components'
import { Monitor, TrendCharts, Setting, Cpu } from '@element-plus/icons-vue'
import * as echarts from 'echarts'

const router = useRouter()

const stats = ref<DashboardData>({
  today_detections: 0, total_detections: 0,
  mode_breakdown: { yolo_only: 0, llm_only: 0, collaborative: 0 },
  yolo_models: 0, llm_configs: 0, recent_detections: [],
})

const dailyData = ref<{ dates: string[]; counts: number[] }>({ dates: [], counts: [] })
const pieData = ref<{ name: string; value: number }[]>([])

const chartRef = ref<HTMLDivElement | null>(null)
const barRef = ref<HTMLDivElement | null>(null)
const pieRef = ref<HTMLDivElement | null>(null)

let chartLine: echarts.ECharts | null = null
let chartBar: echarts.ECharts | null = null
let chartPie: echarts.ECharts | null = null

// ── 实时监控 ──
const cpuPercent = ref(0)
const memPercent = ref(0)
const cpuHistory = ref<number[]>([])
const memHistory = ref<number[]>([])
const timeLabels = ref<string[]>([])
const MAX_POINTS = 60  // 2分钟窗口 (2s间隔)
const cpuRef = ref<HTMLDivElement | null>(null)
const memRef = ref<HTMLDivElement | null>(null)
let chartCpu: echarts.ECharts | null = null
let chartMem: echarts.ECharts | null = null
let monitorTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  try {
    const data = await fetchDashboardStats()
    stats.value = data
  } catch { /* ignore */ }

  // Fetch chart data
  try {
    const [dailyRes, pieRes] = await Promise.all([
      fetchDailyStats(14),
      fetchModePie(),
    ])
    dailyData.value = dailyRes
    pieData.value = pieRes.series || []
  } catch { /* ignore */ }

  await nextTick()
  initCharts()

  // 启动实时监控轮询
  await pollSystemStatus()
  monitorTimer = setInterval(pollSystemStatus, 2000)
})

onUnmounted(() => {
  chartLine?.dispose()
  chartBar?.dispose()
  chartPie?.dispose()
  chartCpu?.dispose()
  chartMem?.dispose()
  if (monitorTimer) clearInterval(monitorTimer)
})

// ── 实时监控函数 ──

function color(v: number) {
  if (v > 80) return '#F56C6C'
  if (v > 50) return '#E6A23C'
  return '#67C23A'
}

async function pollSystemStatus() {
  try {
    const status = await getSystemStatus()
    cpuPercent.value = status.cpu_percent
    memPercent.value = status.memory_percent

    // 记录时间标签
    const now = new Date()
    const label = now.getSeconds().toString().padStart(2, '0') + '"'

    cpuHistory.value.push(status.cpu_percent)
    memHistory.value.push(status.memory_percent)
    timeLabels.value.push(label)

    // 保持滚动窗口
    if (cpuHistory.value.length > MAX_POINTS) {
      cpuHistory.value.shift()
      memHistory.value.shift()
      timeLabels.value.shift()
    }

    updateMonitorCharts()
  } catch { /* ignore */ }
}

function makeMonitorOption(data: number[], currentVal: number, colorBase: string) {
  return {
    tooltip: {
      trigger: 'axis',
      formatter: (params: any[]) => {
        const p = params[0]
        return `当前: <b>${p.value}%</b><br/>时间: ${p.axisValue}`
      },
    },
    grid: { left: 40, right: 12, top: 28, bottom: 24 },
    xAxis: {
      type: 'category',
      data: timeLabels.value,
      axisLabel: { fontSize: 9, color: '#9ca3af', interval: 9 },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: '#f3f4f6', type: 'dashed' } },
      axisLabel: { fontSize: 9, color: '#9ca3af', formatter: '{value}%' },
    },
    series: [{
      data,
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { color: colorBase, width: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: colorBase + '40' },
          { offset: 1, color: colorBase + '08' },
        ]),
      },
      markLine: {
        silent: true,
        symbol: 'none',
        label: { show: true, fontSize: 10, color: '#6b7280', formatter: '当前 {c}%' },
        data: [{ yAxis: currentVal }],
        lineStyle: { color: '#d1d5db', type: 'dashed', width: 1 },
      },
    }],
  }
}

function updateMonitorCharts() {
  const cpuOpt = makeMonitorOption(cpuHistory.value, cpuPercent.value, '#3b82f6')
  const memOpt = makeMonitorOption(memHistory.value, memPercent.value, '#22c55e')
  chartCpu?.setOption(cpuOpt, { notMerge: false })
  chartMem?.setOption(memOpt, { notMerge: false })
}

function initMonitorCharts() {
  if (cpuRef.value) {
    chartCpu = echarts.init(cpuRef.value)
  }
  if (memRef.value) {
    chartMem = echarts.init(memRef.value)
  }
}

function initCharts() {
  // Line chart — daily detection trend
  if (chartRef.value) {
    chartLine = echarts.init(chartRef.value)
    chartLine.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 45, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: dailyData.value.dates, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{
        data: dailyData.value.counts,
        type: 'line',
        smooth: true,
        areaStyle: { color: 'rgba(59,130,246,0.12)' },
        lineStyle: { color: '#3b82f6', width: 2 },
        itemStyle: { color: '#3b82f6' },
        symbol: 'circle',
        symbolSize: 6,
      }],
    })
  }

  // Bar chart — daily detection bar
  if (barRef.value) {
    chartBar = echarts.init(barRef.value)
    chartBar.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 45, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: dailyData.value.dates, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', minInterval: 1 },
      series: [{
        data: dailyData.value.counts,
        type: 'bar',
        barWidth: '55%',
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#60a5fa' },
            { offset: 1, color: '#93c5fd' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
      }],
    })
  }

  // Pie chart — mode breakdown
  if (pieRef.value) {
    chartPie = echarts.init(pieRef.value)
    const colors = ['#3b82f6', '#22c55e', '#a855f7']
    chartPie.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '50%'],
        data: pieData.value,
        label: { show: true, fontSize: 11 },
        emphasis: {
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.2)' },
        },
        itemStyle: { color: (params: any) => colors[params.dataIndex] || '#999' },
      }],
    })
  }
  initMonitorCharts()
}

const cards = computed(() => [
  { label: '累计检测', value: stats.value.total_detections, icon: TrendCharts, color: '#67C23A', path: '/history' },
  { label: 'YOLO模型', value: stats.value.yolo_models, icon: Setting, color: '#E6A23C', path: '/models' },
  { label: 'LLM配置', value: stats.value.llm_configs, icon: Monitor, color: '#F56C6C', path: '/models' },
])
</script>

<template>
  <LayoutShell>
    <div class="p-6">
      <h2 class="text-2xl font-bold mb-6">首页概览</h2>

      <!-- Stats Cards -->
      <div class="grid grid-cols-3 gap-4 mb-6">
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

      <!-- 系统资源监控 -->
      <div class="bg-white rounded-lg shadow-sm p-4 mb-6">
        <div class="flex items-center gap-2 mb-1">
          <el-icon :size="16" color="#6b7280"><Cpu /></el-icon>
          <h3 class="text-sm font-semibold text-gray-500">系统资源监控</h3>
          <span class="ml-auto text-[10px] text-gray-400">
            实时刷新 · CPU <span :style="{ color: color(cpuPercent) }" class="font-semibold">{{ cpuPercent }}%</span>
            &nbsp;MEM <span :style="{ color: color(memPercent) }" class="font-semibold">{{ memPercent }}%</span>
          </span>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="flex items-center gap-1.5 mb-1">
              <span class="w-2 h-2 rounded-full inline-block" style="background:#3b82f6"></span>
              <span class="text-xs text-gray-400">CPU 使用率</span>
            </div>
            <div ref="cpuRef" style="height:180px"></div>
          </div>
          <div>
            <div class="flex items-center gap-1.5 mb-1">
              <span class="w-2 h-2 rounded-full inline-block" style="background:#22c55e"></span>
              <span class="text-xs text-gray-400">内存使用率</span>
            </div>
            <div ref="memRef" style="height:180px"></div>
          </div>
        </div>
      </div>

      <!-- Charts: 2x2 grid -->
      <div class="grid grid-cols-2 gap-4 mb-6">
        <!-- Line chart -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="text-sm font-semibold text-gray-500 mb-3">近14天检测趋势</h3>
          <div ref="chartRef" style="height:220px"></div>
        </div>
        <!-- Bar chart -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="text-sm font-semibold text-gray-500 mb-3">近14天检测数量</h3>
          <div ref="barRef" style="height:220px"></div>
        </div>
        <!-- Pie chart -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="text-sm font-semibold text-gray-500 mb-3">检测模式分布</h3>
          <div ref="pieRef" style="height:220px"></div>
        </div>
        <!-- Recent detections -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="text-sm font-semibold text-gray-500 mb-3">最近检测</h3>
          <div class="max-h-[220px] overflow-auto">
            <el-table :data="stats.recent_detections" size="small" stripe>
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column prop="mode" label="模式" width="100">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.mode === 'yolo_only' ? '' : row.mode === 'llm_only' ? 'success' : 'warning'">
                    {{ row.mode === 'yolo_only' ? 'YOLO' : row.mode === 'llm_only' ? 'LLM' : '协同' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="source_type" label="类型" width="80" />
              <el-table-column prop="created_at" label="时间" />
            </el-table>
            <div v-if="stats.recent_detections.length === 0" class="text-center text-gray-400 py-6 text-sm">暂无检测记录</div>
          </div>
        </div>
      </div>
    </div>
  </LayoutShell>
</template>