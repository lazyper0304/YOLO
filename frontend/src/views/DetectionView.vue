<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ModelSelector from '@/components/detection/ModelSelector.vue'
import { LayoutShell } from '@/components'
import { useDetectionStore } from '@/stores/detection'
import { useConfigStore } from '@/stores/config'
import { useKnowledgeBaseStore } from '@/stores/knowledge_base'
import { useTaskList } from '@/composables/useTaskList'
import { detectionApi } from '@/api/detection'
import { getTask } from '@/api/tasks'
import type { DetectionMode } from '@/types/detection'
import { Delete, Refresh, Aim, MagicStick, Link } from '@element-plus/icons-vue'

const detectionStore = useDetectionStore()
const configStore = useConfigStore()
const kbStore = useKnowledgeBaseStore()
const taskList = useTaskList()

const tasks = taskList.tasks

// --- State ---
const uploading = ref(false)
const showCreateDialog = ref(false)
const createFile = ref<File | null>(null)
const createFileName = ref('')
const taskName = ref('')
const llmAnalysisScope = ref<'full' | 'region'>('full')
const sourceType = ref<'image' | 'video' | 'webcam'>('image')
const webcamActive = ref(false)
const webcamVideoRef = ref<HTMLVideoElement | null>(null)
const webcamStream = ref<MediaStream | null>(null)
const webcamCapturedFrame = ref<Blob | null>(null)

// Video config
const frameIntervalSeconds = ref(5)
const analysisPrompt = ref('')
const generatingPrompt = ref(false)
const selectedPromptKBIds = ref<number[]>([])
const estimatedFrameCount = ref(0)
const estimatedDurationSeconds = ref(0)

// --- Helpers ---
function thumbnailUrl(path: string): string {
  // Convert absolute filesystem path to web-relative /uploads/... URL
  if (!path) return ''
  // Extract everything after 'uploads\' or 'uploads/'
  const idx = path.search(/uploads[\\/]/i)
  if (idx !== -1) return '/' + path.slice(idx)
  return '/' + path
}

// --- Lifecycle ---
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  // Load side data (non-blocking — failures shouldn't prevent task list loading)
  await Promise.all([configStore.fetchLLMConfigs(), configStore.fetchYOLOModels()]).catch(() => {})
  await taskList.loadTasks({ page_size: 50 }).catch(() => {})
  pollTimer = setInterval(() => taskList.loadTasks({ page_size: 50 }).catch(() => {}), 2000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})

// --- Dialog management ---
function switchSource(type: string) {
  sourceType.value = type as any
  createFile.value = null
  createFileName.value = ''
  webcamCapturedFrame.value = null
  estimatedFrameCount.value = 0
  estimatedDurationSeconds.value = 0
}

function openCreateDialog(mode: DetectionMode) {
  detectionStore.reset()
  detectionStore.setMode(mode)
  detectionStore.selectedModelId = null
  detectionStore.selectedLLMConfigId = null
  createFile.value = null; createFileName.value = ''; taskName.value = ''
  sourceType.value = 'image'; webcamActive.value = false; webcamCapturedFrame.value = null
  frameIntervalSeconds.value = 5; analysisPrompt.value = ''
  estimatedFrameCount.value = 0; estimatedDurationSeconds.value = 0
  if (webcamStream.value) stopWebcam()
  showCreateDialog.value = true
}

function handleFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  createFile.value = file; createFileName.value = file.name
  if (file.type.startsWith('video/')) {
    const v = document.createElement('video'); v.preload = 'metadata'
    v.onloadedmetadata = () => {
      if (v.duration > 0 && frameIntervalSeconds.value > 0) {
        estimatedFrameCount.value = Math.ceil(v.duration / frameIntervalSeconds.value)
        estimatedDurationSeconds.value = Math.round(estimatedFrameCount.value * (detectionStore.currentMode === 'yolo_only' ? 1 : 15))
      }
      URL.revokeObjectURL(v.src)
    }
    v.src = URL.createObjectURL(file)
  }
}

function onIntervalChange() {
  if (createFile.value?.type.startsWith('video/')) {
    const v = document.createElement('video'); v.preload = 'metadata'
    v.onloadedmetadata = () => {
      if (v.duration > 0 && frameIntervalSeconds.value > 0) {
        estimatedFrameCount.value = Math.ceil(v.duration / frameIntervalSeconds.value)
        estimatedDurationSeconds.value = Math.round(estimatedFrameCount.value * (detectionStore.currentMode === 'yolo_only' ? 1 : 15))
      }
      URL.revokeObjectURL(v.src)
    }
    v.src = URL.createObjectURL(createFile.value!)
  }
}

function formatDuration(s: number) {
  if (s < 60) return `${s}秒`
  if (s < 3600) return `${Math.floor(s / 60)}分${s % 60}秒`
  return `${Math.floor(s / 3600)}时${Math.floor((s % 3600) / 60)}分`
}

async function generatePrompt() {
  if (!analysisPrompt.value.trim()) { ElMessage.warning('请先描述您的视频分析需求'); return }
  generatingPrompt.value = true
  try {
    const res = await detectionApi.generatePrompt(analysisPrompt.value, detectionStore.selectedLLMConfigId, selectedPromptKBIds.value)
    analysisPrompt.value = res.data.data?.prompt || ''
    ElMessage.success('提示词已生成')
  } catch (err: any) { ElMessage.error(err?.message || '生成失败') }
  finally { generatingPrompt.value = false }
}

// --- Submit ---
async function submitTask() {
  if (sourceType.value === 'webcam') {
    if (!webcamCapturedFrame.value) { ElMessage.warning('请先拍照'); return }
  } else {
    if (!createFile.value) { ElMessage.warning('请选择文件'); return }
  }
  uploading.value = true
  try {
    const form = new FormData()
    if (sourceType.value === 'webcam') {
      form.append('file', new Blob([webcamCapturedFrame.value!], { type: 'image/jpeg' }), 'webcam.jpg')
    } else {
      form.append('file', createFile.value!, createFile.value!.name)
      if (sourceType.value === 'video') form.append('source_type', 'video')
    }
    form.append('mode', detectionStore.currentMode)
    form.append('task_name', taskName.value.trim())
    if (detectionStore.currentMode !== 'llm_only' && detectionStore.selectedModelId)
      form.append('model_id', String(detectionStore.selectedModelId))
    if (detectionStore.currentMode !== 'yolo_only' && detectionStore.selectedLLMConfigId)
      form.append('llm_config_id', String(detectionStore.selectedLLMConfigId))

    if (sourceType.value === 'video') {
      form.append('frame_interval_seconds', String(frameIntervalSeconds.value))
    }
    if (detectionStore.currentMode !== 'yolo_only' && analysisPrompt.value.trim()) {
      form.append('analysis_prompt', analysisPrompt.value.trim())
    }

    if (detectionStore.currentMode === 'collaborative') {
      form.append('llm_analysis_scope', llmAnalysisScope.value)
    }

    const td = await taskList.submitTask(form)
    if ((td.estimated_frame_count ?? 0) > 0)
      ElMessage.success(`任务已创建，预计分析${td.estimated_frame_count}帧，耗时约${formatDuration(td.estimated_duration_seconds ?? 0)}`)
    else ElMessage.success('任务已创建')

    showCreateDialog.value = false
  } catch (err: any) { ElMessage.error(err?.message || '创建失败') }
  finally { uploading.value = false }

  // Always refresh list after attempting to create (independent of create success/failure)
  try { await taskList.loadTasks({ page_size: 50 }) } catch { /* polling timer will retry */ }
}

// --- Webcam ---
async function startWebcam() {
  try {
    const s = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
    webcamStream.value = s; await nextTick()
    if (webcamVideoRef.value) { webcamVideoRef.value.srcObject = s; await webcamVideoRef.value.play() }
    webcamActive.value = true
  } catch { ElMessage.error('无法访问摄像头') }
}

function stopWebcam() {
  if (webcamStream.value) { webcamStream.value.getTracks().forEach(t => t.stop()); webcamStream.value = null }
  webcamActive.value = false
}

function captureWebcam() {
  const video = webcamVideoRef.value
  if (!video) return
  const c = document.createElement('canvas'); c.width = video.videoWidth; c.height = video.videoHeight
  c.getContext('2d')!.drawImage(video, 0, 0)
  c.toBlob(b => { if (b) { webcamCapturedFrame.value = b; createFileName.value = '摄像头截图.jpg' } }, 'image/jpeg', 0.9)
  ElMessage.success('已拍照')
}

// --- Status helpers ---
function statusTagType(s: string) {
  if (s === 'completed') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'paused') return 'info'
  if (s === 'failed') return 'danger'
  return 'info'
}

function statusLabel(s: string) {
  const map: Record<string, string> = { pending: '等待中', paused: '已暂停', running: '运行中', completed: '已完成', failed: '失败' }
  return map[s] || s
}

function getBBoxCount(task: { result_json?: any }): number { return task.result_json?.bboxes?.length || 0 }

// --- Task detail ---
const detailVisible = ref(false)
const detailTask = ref<any>(null)
const detailSelectedFrame = ref(0)

async function viewDetail(task: { id: number }) {
  try {
    detailTask.value = await getTask(task.id)
    detailVisible.value = true; detailSelectedFrame.value = 0
  } catch { detailTask.value = task; detailVisible.value = true }
}

function selectDetailFrame(i: number) { detailSelectedFrame.value = i }

// --- Delete & batch ---
async function handleDeleteTask(id: number) {
  try { await ElMessageBox.confirm('确定删除此任务？', '确认', { type: 'warning' }) } catch { return }
  try { await taskList.removeTask(id) } catch { /* ignore */ }
}

const selectedIds = ref<Set<number>>(new Set())
const selectAll = computed({
  get: () => tasks.value.length > 0 && tasks.value.every(t => selectedIds.value.has(t.id)),
  set: v => { if (v) tasks.value.forEach(t => selectedIds.value.add(t.id)); else selectedIds.value.clear() }
})
function toggleSelect(id: number) {
  if (selectedIds.value.has(id)) selectedIds.value.delete(id); else selectedIds.value.add(id)
  selectedIds.value = new Set(selectedIds.value)
}
async function batchDelete() {
  const ids = [...selectedIds.value]; if (!ids.length) return
  try { await ElMessageBox.confirm(`确定删除 ${ids.length} 个任务？`, '批量删除', { type: 'warning' }) } catch { return }
  try { await taskList.removeTasks(ids); selectedIds.value.clear(); await taskList.loadTasks({ page_size: 50 }) } catch { /* ignore */ }
}

const hasRunning = computed(() => taskList.runningTasks.value.length > 0)
</script>

<template>
  <LayoutShell>
    <div class="p-8">
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-2xl font-bold">任务列表</h2>
        <div class="flex items-center gap-2">
          <el-button v-if="selectedIds.size > 0" type="danger" size="small" @click="batchDelete">删除选中 ({{ selectedIds.size }})</el-button>
          <el-button type="primary" :icon="Aim" @click="openCreateDialog('yolo_only')">YOLO检测</el-button>
          <el-button type="primary" :icon="MagicStick" @click="openCreateDialog('llm_only')">LLM分析</el-button>
          <el-button type="primary" :icon="Link" @click="openCreateDialog('collaborative')">协同模式</el-button>
          <el-button :icon="Refresh" size="small" @click="taskList.loadTasks({ page_size: 50 })">刷新</el-button>
        </div>
      </div>

      <div v-if="hasRunning" class="mb-4 text-sm text-orange-500 flex items-center gap-2">
        <el-icon class="is-loading"><Refresh /></el-icon> 有任务正在处理中...
      </div>

      <div v-if="tasks.length > 0" class="flex items-center gap-2 mb-2 px-1">
        <el-checkbox v-model="selectAll" size="small">全选</el-checkbox>
      </div>
      <div v-if="tasks.length === 0" class="text-center text-gray-400 py-16 text-sm">暂无任务，点击上方按钮开始检测</div>

      <div class="space-y-3">
        <div v-for="task in tasks" :key="task.id" @click="viewDetail(task)"
          class="bg-white rounded-lg shadow-sm p-4 flex items-center gap-4 cursor-pointer hover:shadow-md transition-shadow">
          <el-checkbox :model-value="selectedIds.has(task.id)" class="flex-shrink-0" @click.stop @change="toggleSelect(task.id)" />
          <div class="w-16 h-16 bg-gray-100 rounded flex-shrink-0 overflow-hidden">
            <img v-if="task.thumbnail_path && task.status === 'completed'" :src="thumbnailUrl(task.thumbnail_path)" class="w-full h-full object-cover" />
            <div v-else class="w-full h-full flex items-center justify-center text-gray-400 text-xs">{{ task.source_type === 'video' ? '视频' : '图片' }}</div>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span v-if="task.task_name" class="text-sm font-medium text-gray-700 mr-2">{{ task.task_name }}</span>
              <el-tag :type="statusTagType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
              <el-tag size="small">{{ task.mode === 'yolo_only' ? 'YOLO' : task.mode === 'llm_only' ? 'LLM' : '协同' }}</el-tag>
              <el-tag v-if="task.source_type === 'video'" size="small" type="warning">视频</el-tag>
              <span v-if="task.status === 'completed' && (getBBoxCount(task) > 0 || task.result_json?.total_objects)" class="text-xs text-gray-500">
                检测到 {{ task.result_json?.total_objects || getBBoxCount(task) }} 个目标
              </span>
            </div>
            <div class="flex items-center gap-3 text-xs text-gray-400">
              <span>{{ task.created_at }}</span>
              <span v-if="task.status === 'running' && task.progress !== undefined" class="text-blue-500">
                进度 {{ task.progress }}%
                <span v-if="task.result_json?.frames_completed !== undefined"> ({{ task.result_json.frames_completed }}/{{ task.result_json.total_frames || '?' }}帧)</span>
              </span>
            </div>
          </div>
          <div class="flex items-center gap-1 flex-shrink-0">
            <el-button v-if="task.status === 'pending'" size="small" type="info" plain
              @click.stop="taskList.togglePause(task.id)">暂停</el-button>
            <el-button v-if="task.status === 'paused'" size="small" type="primary" plain
              @click.stop="taskList.togglePause(task.id)">恢复</el-button>
            <el-button v-if="task.status !== 'running'" size="small" :icon="Delete" type="danger" plain
              @click.stop="handleDeleteTask(task.id)" />
          </div>
        </div>
      </div>
    </div>
  </LayoutShell>

  <!-- Create Task Dialog -->
  <el-dialog v-model="showCreateDialog" top="5vh" width="520px" :close-on-click-modal="false">
    <template #header><span class="text-base font-bold">新增任务</span></template>
    <div class="space-y-4">
      <div>
        <label class="text-sm text-gray-600 block mb-1.5">任务名称 <span class="text-gray-300">(可选)</span></label>
        <el-input v-model="taskName" placeholder="输入任务名称" size="small" />
      </div>
      <div>
        <label class="text-sm text-gray-600 block mb-1.5">来源类型</label>
        <div class="flex gap-1 bg-gray-100 rounded p-0.5">
          <button v-for="t in [{k:'image',l:'图片'},{k:'video',l:'视频'},{k:'webcam',l:'本机摄像头'}]" :key="t.k"
            @click="switchSource(t.k)" :class="sourceType === t.k ? 'bg-white shadow-sm text-blue-600' : 'text-gray-500 hover:text-gray-700'"
            class="flex-1 py-1.5 text-xs rounded transition-colors">{{ t.l }}</button>
        </div>
      </div>
      <div>
        <template v-if="sourceType !== 'webcam'">
          <label class="block cursor-pointer">
            <div class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
              <p v-if="createFileName" class="text-sm text-gray-700">{{ createFileName }}</p>
              <p v-else class="text-sm text-gray-400">点击选择{{ sourceType === 'video' ? '视频' : '图片' }}文件</p>
            </div>
            <input type="file" :accept="sourceType === 'video' ? 'video/*' : 'image/*'" class="hidden" @change="handleFileSelect" />
          </label>
        </template>
        <template v-if="sourceType === 'webcam'">
          <div class="relative bg-black rounded-lg overflow-hidden" style="height: 260px">
            <video ref="webcamVideoRef" class="w-full h-full object-cover absolute inset-0" autoplay playsinline muted />
            <div v-if="!webcamActive" class="absolute inset-0 flex items-center justify-center bg-gray-900">
              <el-button type="primary" size="small" @click="startWebcam">开启摄像头</el-button>
            </div>
          </div>
          <div class="flex gap-2 mt-2 flex-wrap">
            <el-button v-if="!webcamActive" type="primary" size="small" @click="startWebcam">开启</el-button>
            <el-button v-if="webcamActive" size="small" @click="captureWebcam">拍照</el-button>
            <el-button v-if="webcamActive" type="danger" size="small" plain @click="stopWebcam()">关闭</el-button>
          </div>
          <div v-if="webcamCapturedFrame" class="text-xs text-green-600 mt-1">已拍照 ✓</div>
        </template>
      </div>

      <div v-if="detectionStore.currentMode !== 'llm_only'">
        <label class="text-sm text-gray-600 block mb-1.5">YOLO 模型</label>
        <ModelSelector type="yolo" />
      </div>
      <div v-if="detectionStore.currentMode !== 'yolo_only'">
        <label class="text-sm text-gray-600 block mb-1.5">LLM 配置</label>
        <ModelSelector type="llm" />
      </div>

      <div v-if="detectionStore.currentMode === 'collaborative'">
        <label class="text-sm text-gray-600 block mb-1.5">LLM 分析范围</label>
        <el-radio-group v-model="llmAnalysisScope" size="small">
          <el-radio-button value="full">全图分析</el-radio-button>
          <el-radio-button value="region">YOLO局部区域分析</el-radio-button>
        </el-radio-group>
        <div class="text-xs text-gray-400 mt-1">
          <template v-if="llmAnalysisScope === 'full'">LLM 分析完整{{ sourceType === 'video' ? '视频帧' : '图片' }}，结合 YOLO 检测结果进行综合描述</template>
          <template v-else>仅将 YOLO 检测到的局部区域发送给 LLM 分析，减少 token 消耗</template>
        </div>
      </div>

      <div v-if="sourceType === 'video'">
        <label class="text-sm text-gray-600 block mb-1.5">帧截取间隔：{{ frameIntervalSeconds }} 秒 <span class="text-gray-300">(每{{ frameIntervalSeconds }}秒截取一帧分析)</span></label>
        <el-slider v-model="frameIntervalSeconds" :min="1" :max="60" :step="1" show-input size="small" @change="onIntervalChange" />
        <div v-if="estimatedFrameCount > 0" class="text-xs text-blue-500 mt-1">预计截取 {{ estimatedFrameCount }} 帧，耗时约 {{ formatDuration(estimatedDurationSeconds) }}</div>
      </div>

      <div v-if="detectionStore.currentMode !== 'yolo_only'">
        <label class="text-sm text-gray-600 block mb-1.5">LLM 分析提示词 <span class="text-gray-300">(可选)</span></label>
        <el-input v-model="analysisPrompt" type="textarea" :rows="sourceType === 'image' ? 2 : 2" placeholder="描述你希望LLM分析什么..." size="small" />
        <div class="mt-1">
          <el-button size="small" :loading="generatingPrompt" @click="generatePrompt" :disabled="configStore.llmConfigs.length === 0">从对话生成提示词</el-button>
          <el-select v-model="selectedPromptKBIds" multiple collapse-tags collapse-tags-tooltip placeholder="参考知识库" size="small" style="width:150px" clearable><el-option v-for="kb in kbStore.knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id"/></el-select>
          <span v-if="configStore.llmConfigs.length === 0" class="text-xs text-orange-500 ml-2">请先在模型算法管理中配置LLM</span>
        </div>
      </div>

      <div class="text-xs text-gray-400 bg-gray-50 rounded p-2">
        <template v-if="detectionStore.currentMode === 'yolo_only'">将使用 YOLO 模型对每帧进行目标检测，返回边界框坐标和类别统计。</template>
        <template v-else-if="detectionStore.currentMode === 'llm_only'">将使用多模态大模型进行视觉分析。{{ sourceType === 'video' ? `按${frameIntervalSeconds}秒间隔截帧。` : '' }}</template>
        <template v-else>先由 YOLO 检测目标，再由大模型进行协同分析。{{ sourceType === 'video' ? `按${frameIntervalSeconds}秒间隔截帧。` : '' }}</template>
      </div>
    </div>
    <template #footer>
      <el-button @click="showCreateDialog = false">取消</el-button>
      <el-button type="primary" :loading="uploading" @click="submitTask">创建任务</el-button>
    </template>
  </el-dialog>

  <!-- Task Detail Dialog -->
  <el-dialog v-model="detailVisible" title="任务详情" width="720px" top="5vh">
    <template v-if="detailTask">
      <div class="space-y-4">
        <div v-if="detailTask.annotated_image && !detailTask.result_json?.frames" class="bg-gray-100 rounded overflow-hidden">
          <img :src="'data:image/jpeg;base64,' + detailTask.annotated_image" class="w-full" />
        </div>
        <div v-if="detailTask.result_json?.video_path" class="bg-black rounded overflow-hidden">
          <video controls class="w-full" :src="thumbnailUrl(detailTask.result_json.video_path)"></video>
        </div>

        <div class="flex gap-4 text-sm">
          <el-tag :type="statusTagType(detailTask.status)">{{ statusLabel(detailTask.status) }}</el-tag>
          <el-tag>{{ detailTask.mode === 'yolo_only' ? 'YOLO' : detailTask.mode === 'llm_only' ? 'LLM' : '协同' }}</el-tag>
          <span class="text-gray-400">{{ detailTask.created_at }}</span>
          <span v-if="detailTask.progress !== undefined && detailTask.status === 'running'" class="text-blue-500">进度 {{ detailTask.progress }}%</span>
        </div>

        <div v-if="detailTask.analysis_prompt" class="bg-blue-50 rounded p-3 text-sm text-blue-700"><strong>分析提示词：</strong>{{ detailTask.analysis_prompt }}</div>

        <!-- Frame-by-frame results -->
        <div v-if="detailTask.result_json?.frames?.length">
          <h4 class="text-sm font-semibold text-gray-500 mb-2">帧分析结果 ({{ detailTask.result_json.frames_completed || detailTask.result_json.frames.length }}/{{ detailTask.result_json.total_frames || detailTask.result_json.frames.length }})</h4>
          <div class="flex gap-2 flex-wrap mb-3">
            <button v-for="(frame, fi) in detailTask.result_json.frames" :key="fi" @click="selectDetailFrame(fi)"
              :class="detailSelectedFrame === fi ? 'bg-blue-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
              class="px-3 py-1 rounded text-xs transition-colors">帧{{ frame.frame_index }} ({{ frame.time_seconds }}s)</button>
          </div>
          <div v-if="detailTask.result_json.frames[detailSelectedFrame]" class="border rounded p-3 space-y-3">
            <div class="flex items-center gap-2 text-sm">
              <span class="font-medium">帧 {{ detailTask.result_json.frames[detailSelectedFrame].frame_index }}</span>
              <span class="text-gray-400">| 时间 {{ detailTask.result_json.frames[detailSelectedFrame].time_seconds }}s</span>
            </div>
            <div v-if="detailTask.result_json.frames[detailSelectedFrame].thumbnail_path" class="bg-black rounded overflow-hidden">
              <img :src="thumbnailUrl(detailTask.result_json.frames[detailSelectedFrame].thumbnail_path)" class="w-full max-h-48 object-cover" />
            </div>
            <div v-if="detailTask.result_json.frames[detailSelectedFrame].bboxes?.length">
              <span class="text-xs text-gray-500">检测目标:</span>
              <div class="flex flex-wrap gap-1 mt-1">
                <el-tag v-for="(b, i) in detailTask.result_json.frames[detailSelectedFrame].bboxes" :key="i" size="small" type="success">{{ b.class_name }} {{ Math.round(b.confidence * 100) }}%</el-tag>
              </div>
            </div>
            <div v-if="detailTask.result_json.frames[detailSelectedFrame].llm_analysis">
              <span class="text-xs text-gray-500">LLM分析:</span>
              <div v-if="detailTask.result_json.frames[detailSelectedFrame].llm_analysis.summary" class="text-sm text-gray-700 mt-1"><strong>摘要：</strong>{{ detailTask.result_json.frames[detailSelectedFrame].llm_analysis.summary }}</div>
              <div v-if="detailTask.result_json.frames[detailSelectedFrame].llm_analysis.detailed_analysis" class="text-sm text-gray-600 mt-1 whitespace-pre-wrap">{{ detailTask.result_json.frames[detailSelectedFrame].llm_analysis.detailed_analysis }}</div>
              <div v-if="detailTask.result_json.frames[detailSelectedFrame].llm_analysis.region_analyses?.length" class="mt-2 space-y-1">
                <div class="text-xs text-gray-500 mb-1">区域分析 ({{ detailTask.result_json.frames[detailSelectedFrame].llm_analysis.region_analyses.length }}):</div>
                <div v-for="(ra, ri) in detailTask.result_json.frames[detailSelectedFrame].llm_analysis.region_analyses" :key="ri" class="bg-gray-50 rounded px-2 py-1.5 text-xs border border-gray-100">
                  <span class="font-medium text-gray-600">{{ ra.object }}：</span>
                  <span class="text-gray-500">{{ ra.description || '分析中...' }}</span>
                </div>
              </div>
              <div v-if="detailTask.result_json.frames[detailSelectedFrame].llm_analysis.error" class="text-sm text-red-500 mt-1">{{ detailTask.result_json.frames[detailSelectedFrame].llm_analysis.error }}</div>
            </div>
          </div>
        </div>

        <!-- Legacy detection summary -->
        <div v-if="detailTask.result_json?.source_type === 'video' && detailTask.result_json?.detection_summary && !detailTask.result_json?.frames">
          <h4 class="text-sm font-semibold text-gray-500 mb-2">视频检测结果 ({{ detailTask.result_json.total_objects || 0 }}个目标<span v-if="detailTask.result_json.frame_count">, {{ detailTask.result_json.frame_count }}帧</span>)</h4>
          <div class="space-y-1">
            <div v-for="s in detailTask.result_json.detection_summary" :key="s.class" class="flex items-center gap-2 text-sm">
              <el-tag size="small" type="success">{{ s.class }}</el-tag>
              <span class="text-gray-500">出现 {{ s.count }} 次<span v-if="s.avg_confidence">, 平均置信度 {{ (s.avg_confidence * 100).toFixed(0) }}%</span></span>
            </div>
          </div>
        </div>

        <div v-if="detailTask.result_json?.bboxes?.length && !detailTask.result_json?.frames">
          <h4 class="text-sm font-semibold text-gray-500 mb-2">检测目标 ({{ detailTask.result_json.bboxes.length }})</h4>
          <div class="flex flex-wrap gap-1">
            <el-tag v-for="(b, i) in detailTask.result_json.bboxes" :key="i" size="small" type="success">{{ b.class_name }} {{ (b.confidence * 100).toFixed(0) }}%</el-tag>
          </div>
        </div>

        <div v-if="detailTask.result_json?.llm_analysis?.summary && !detailTask.result_json?.frames">
          <h4 class="text-sm font-semibold text-gray-500 mb-1">摘要</h4>
          <p class="text-sm text-gray-700">{{ detailTask.result_json.llm_analysis.summary }}</p>
        </div>
        <div v-if="detailTask.result_json?.llm_analysis?.detailed_analysis && !detailTask.result_json?.frames">
          <h4 class="text-sm font-semibold text-gray-500 mb-1">详细分析</h4>
          <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ detailTask.result_json.llm_analysis.detailed_analysis }}</p>
        </div>
        <div v-if="detailTask.result_json?.llm_analysis?.region_analyses?.length && !detailTask.result_json?.frames" class="space-y-1">
          <h4 class="text-sm font-semibold text-gray-500 mb-1">区域分析 ({{ detailTask.result_json.llm_analysis.region_analyses.length }})</h4>
          <div v-for="(ra, ri) in detailTask.result_json.llm_analysis.region_analyses" :key="ri" class="bg-gray-50 rounded px-3 py-2 border border-gray-100">
            <div class="text-xs font-medium text-gray-600">{{ ra.object }}</div>
            <div class="text-xs text-gray-500 mt-0.5">{{ ra.description || '分析中...' }}</div>
          </div>
        </div>

        <div v-if="detailTask.result_json?.error" class="text-sm text-red-500 bg-red-50 rounded p-3">{{ detailTask.result_json.error }}</div>
      </div>
    </template>
  </el-dialog>
</template>
