<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftSidebar from '@/components/layout/LeftSidebar.vue'
import ModelSelector from '@/components/detection/ModelSelector.vue'
import { useDetectionStore } from '@/stores/detection'
import { useConfigStore } from '@/stores/config'
import client from '@/api/client'
import type { DetectionMode } from '@/types/detection'
import { Delete, Refresh, Aim, MagicStick, Link } from '@element-plus/icons-vue'

const detectionStore = useDetectionStore()
const configStore = useConfigStore()

interface TaskItem {
  id: number; task_name: string; mode: string; source_type: string; source_path: string
  status: string; result_json: any; thumbnail_path: string | null; created_at: string
}

const tasks = ref<TaskItem[]>([])
const uploading = ref(false)
const showCreateDialog = ref(false)
const createFile = ref<File | null>(null)
const createFileName = ref('')
const taskName = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await Promise.all([configStore.fetchLLMConfigs(), configStore.fetchYOLOModels()])
  await fetchTasks()
  pollTimer = setInterval(fetchTasks, 2000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

async function fetchTasks() {
  try {
    const res = await client.get('/api/tasks', { params: { page_size: 50 } })
    tasks.value = res.data.data?.items || []
  } catch { /* ignore */ }
}

function openCreateDialog(mode: DetectionMode) {
  detectionStore.reset()
  detectionStore.setMode(mode)
  detectionStore.selectedModelId = null
  detectionStore.selectedLLMConfigId = null
  createFile.value = null
  createFileName.value = ''
  taskName.value = ''
  showCreateDialog.value = true
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    createFile.value = file
    createFileName.value = file.name
  }
}

async function submitTask() {
  if (!createFile.value) {
    ElMessage.warning('请选择图片')
    return
  }
  if (!detectionStore.currentMode) {
    detectionStore.setMode('yolo_only')
  }

  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', createFile.value)
    form.append('mode', detectionStore.currentMode)
    form.append('task_name', taskName.value.trim())
    if (detectionStore.currentMode !== 'llm_only' && detectionStore.selectedModelId) {
      form.append('model_id', String(detectionStore.selectedModelId))
    }
    if (detectionStore.currentMode !== 'yolo_only' && detectionStore.selectedLLMConfigId) {
      form.append('llm_config_id', String(detectionStore.selectedLLMConfigId))
    }

    await client.post('/api/tasks', form)
    ElMessage.success('任务已创建')
    showCreateDialog.value = false
    await fetchTasks()
  } catch (err: any) {
    ElMessage.error(err?.message || '创建失败')
  } finally {
    uploading.value = false
  }
}

async function deleteTask(id: number) {
  try {
    await ElMessageBox.confirm('确定删除此任务？', '确认', { type: 'warning' })
  } catch { return }
  try {
    await client.delete(`/api/tasks/${id}`)
    await fetchTasks()
  } catch { /* ignore */ }
}

function statusTagType(s: string) {
  if (s === 'completed') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}

function statusLabel(s: string) {
  if (s === 'pending') return '等待中'
  if (s === 'running') return '运行中'
  if (s === 'completed') return '已完成'
  if (s === 'failed') return '失败'
  return s
}

function getBBoxCount(task: TaskItem): number {
  return task.result_json?.bboxes?.length || 0
}

const detailVisible = ref(false)
const detailTask = ref<any>(null)

async function viewDetail(task: TaskItem) {
  try {
    const res = await client.get('/api/tasks/' + task.id)
    detailTask.value = res.data.data
    detailVisible.value = true
  } catch {
    detailTask.value = task
    detailVisible.value = true
  }
}

const hasRunning = computed(() => tasks.value.some(t => t.status === 'running'))

const selectedIds = ref<Set<number>>(new Set())
const selectAll = computed({
  get: () => tasks.value.length > 0 && tasks.value.every(t => selectedIds.value.has(t.id)),
  set: (val: boolean) => {
    if (val) tasks.value.forEach(t => selectedIds.value.add(t.id))
    else selectedIds.value.clear()
  },
})

function toggleSelect(id: number) {
  if (selectedIds.value.has(id)) selectedIds.value.delete(id)
  else selectedIds.value.add(id)
  selectedIds.value = new Set(selectedIds.value) // trigger reactivity
}

async function batchDelete() {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定删除 ${ids.length} 个任务？`, '批量删除', { type: 'warning' })
  } catch { return }
  try {
    await client.post('/api/tasks/batch-delete', ids)
    ElMessage.success(`已删除 ${ids.length} 个任务`)
    selectedIds.value.clear()
    await fetchTasks()
  } catch { /* ignore */ }
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 overflow-auto bg-gray-50">
        <div class="max-w-5xl mx-auto p-8">
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-2xl font-bold">任务列表</h2>
            <div class="flex items-center gap-2">
              <el-button v-if="selectedIds.size > 0" type="danger" size="small" @click="batchDelete">删除选中 ({{ selectedIds.size }})</el-button>
              <el-button type="primary" :icon="Aim" @click="openCreateDialog('yolo_only')">YOLO检测</el-button>
              <el-button type="primary" :icon="MagicStick" @click="openCreateDialog('llm_only')">LLM分析</el-button>
              <el-button type="primary" :icon="Link" @click="openCreateDialog('collaborative')">协同模式</el-button>
              <el-button :icon="Refresh" size="small" @click="fetchTasks">刷新</el-button>
            </div>
          </div>

          <!-- Running indicator -->
          <div v-if="hasRunning" class="mb-4 text-sm text-orange-500 flex items-center gap-2">
            <el-icon class="is-loading"><Refresh /></el-icon> 有任务正在处理中...
          </div>

          <!-- Task list -->
          <div v-if="tasks.length > 0" class="flex items-center gap-2 mb-2 px-1">
            <el-checkbox v-model="selectAll" size="small">全选</el-checkbox>
          </div>
          <div v-if="tasks.length === 0" class="text-center text-gray-400 py-16 text-sm">暂无任务，点击上方按钮开始检测</div>

          <div class="space-y-3">
            <div
              v-for="task in tasks" :key="task.id"
              @click="viewDetail(task)"
              class="bg-white rounded-lg shadow-sm p-4 flex items-center gap-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <el-checkbox :model-value="selectedIds.has(task.id)" class="flex-shrink-0" @click.stop @change="toggleSelect(task.id)" />
              <div class="w-16 h-16 bg-gray-100 rounded flex-shrink-0 overflow-hidden">
                <div class="w-full h-full flex items-center justify-center text-gray-400 text-xs">图片</div>
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <span v-if="task.task_name" class="text-sm font-medium text-gray-700 mr-2">{{ task.task_name }}</span>
                  <el-tag :type="statusTagType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
                  <el-tag size="small">{{ task.mode === 'yolo_only' ? 'YOLO' : task.mode === 'llm_only' ? 'LLM' : '协同' }}</el-tag>
                  <el-tag v-if="task.source_type === 'video'" size="small" type="warning">视频</el-tag>
                  <span v-if="task.status === 'completed' && getBBoxCount(task) > 0" class="text-xs text-gray-500">
                    检测到 {{ getBBoxCount(task) }} 个目标
                  </span>
                </div>
                <div class="text-xs text-gray-400">{{ task.created_at }}</div>
              </div>
              <div class="flex items-center gap-1 flex-shrink-0">
                <el-button
                  v-if="task.status !== 'running'"
                  size="small"
                  @click.stop="deleteTask(task.id)"
                  :icon="Delete"
                  type="danger"
                  plain
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- Create Task Dialog -->
    <el-dialog v-model="showCreateDialog" width="440px" :close-on-click-modal="false">
      <template #header>
        <span class="text-base font-bold">
          {{ detectionStore.currentMode === 'yolo_only' ? 'YOLO检测' : detectionStore.currentMode === 'llm_only' ? 'LLM分析' : '协同模式' }}
        </span>
      </template>

      <div class="space-y-4">
        <!-- Task name -->
        <div>
          <label class="text-sm text-gray-600 block mb-1.5">任务名称 <span class="text-gray-300">(可选)</span></label>
          <el-input v-model="taskName" placeholder="输入任务名称，便于识别" size="small" />
        </div>

        <!-- Image upload -->
        <div>
          <label class="text-sm text-gray-600 block mb-1.5">选择图片</label>
          <label class="block cursor-pointer">
            <div class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
              <template v-if="createFileName">
                <p class="text-sm text-gray-700">{{ createFileName }}</p>
              </template>
              <template v-else>
                <p class="text-sm text-gray-400">点击选择文件</p>
              </template>
            </div>
            <input type="file" accept="image/*,video/*" class="hidden" @change="handleFileSelect" />
          </label>
        </div>

        <!-- YOLO Model (yolo_only / collaborative) -->
        <div v-if="detectionStore.currentMode !== 'llm_only'">
          <label class="text-sm text-gray-600 block mb-1.5">YOLO 模型</label>
          <ModelSelector type="yolo" />
        </div>

        <!-- LLM Config (llm_only / collaborative) -->
        <div v-if="detectionStore.currentMode !== 'yolo_only'">
          <label class="text-sm text-gray-600 block mb-1.5">LLM 配置</label>
          <ModelSelector type="llm" />
        </div>

        <!-- Mode hint -->
        <div class="text-xs text-gray-400 bg-gray-50 rounded p-2">
          <template v-if="detectionStore.currentMode === 'yolo_only'">
            将使用 YOLO 模型对图片进行目标检测，返回边界框坐标和类别。
          </template>
          <template v-else-if="detectionStore.currentMode === 'llm_only'">
            将使用多模态大模型对图片进行分析理解。
          </template>
          <template v-else>
            先由 YOLO 检测目标，再由大模型对检测结果进行协同分析。
          </template>
        </div>
      </div>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitTask">创建任务</el-button>
      </template>
    </el-dialog>

    <!-- Task Detail Dialog -->
    <el-dialog v-model="detailVisible" title="任务详情" width="680px" top="5vh">
      <template v-if="detailTask">
        <div class="space-y-4">
          <!-- Annotated image or video -->
          <div v-if="detailTask.annotated_image" class="bg-gray-100 rounded overflow-hidden">
            <img :src="'data:image/jpeg;base64,' + detailTask.annotated_image" class="w-full" />
          </div>
          <div v-if="detailTask.result_json?.video_path" class="bg-black rounded overflow-hidden">
            <video controls class="w-full" :src="'http://localhost:8888/' + detailTask.result_json.video_path"></video>
          </div>

          <div class="flex gap-4 text-sm">
            <el-tag :type="statusTagType(detailTask.status)">{{ statusLabel(detailTask.status) }}</el-tag>
            <el-tag>{{ detailTask.mode === 'yolo_only' ? 'YOLO' : detailTask.mode === 'llm_only' ? 'LLM' : '协同' }}</el-tag>
            <span class="text-gray-400">{{ detailTask.created_at }}</span>
          </div>

          <!-- Video detection summary -->
          <div v-if="detailTask.result_json?.source_type === 'video' && detailTask.result_json?.detection_summary">
            <h4 class="text-sm font-semibold text-gray-500 mb-2">
              视频检测结果 ({{ detailTask.result_json.frame_count }}帧, {{ detailTask.result_json.total_objects }}个目标)
            </h4>
            <div class="space-y-1">
              <div v-for="s in detailTask.result_json.detection_summary" :key="s.class" class="flex items-center gap-2 text-sm">
                <el-tag size="small" type="success">{{ s.class }}</el-tag>
                <span class="text-gray-500">出现 {{ s.count }} 次, 平均置信度 {{ (s.avg_confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- BBoxes -->
          <div v-if="detailTask.result_json?.bboxes?.length">
            <h4 class="text-sm font-semibold text-gray-500 mb-2">检测目标 ({{ detailTask.result_json.bboxes.length }})</h4>
            <div class="flex flex-wrap gap-1">
              <el-tag v-for="(b, i) in detailTask.result_json.bboxes" :key="i" size="small" type="success">
                {{ b.class_name }} {{ (b.confidence * 100).toFixed(0) }}%
              </el-tag>
            </div>
          </div>

          <!-- LLM Analysis -->
          <div v-if="detailTask.result_json?.llm_analysis?.summary">
            <h4 class="text-sm font-semibold text-gray-500 mb-1">摘要</h4>
            <p class="text-sm text-gray-700">{{ detailTask.result_json.llm_analysis.summary }}</p>
          </div>

          <div v-if="detailTask.result_json?.llm_analysis?.detailed_analysis">
            <h4 class="text-sm font-semibold text-gray-500 mb-1">详细分析</h4>
            <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ detailTask.result_json.llm_analysis.detailed_analysis }}</p>
          </div>

          <!-- Error -->
          <div v-if="detailTask.result_json?.error" class="text-sm text-red-500 bg-red-50 rounded p-3">
            {{ detailTask.result_json.error }}
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>
