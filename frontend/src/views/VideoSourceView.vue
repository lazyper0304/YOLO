<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoCamera, Upload, Delete, Refresh, VideoPlay, Link } from '@element-plus/icons-vue'
import { LayoutShell } from '@/components'
import { useConfigStore } from '@/stores/config'
import { useCamera } from '@/composables/useCamera'
import { fetchTasks, getTask, createTask, deleteTask as apiDeleteTask } from '@/api/tasks'
import client from '@/api/client'

const configStore = useConfigStore()

// ---- Camera composable ----
const camera = useCamera()

// ---- Tab ----
const activeTab = ref('video')

// ---- Video task interface ----
interface VideoTask {
  id: number; task_name: string; mode: string; source_type: string
  status: string; result_json: any; created_at: string; source_path: string
}

// ---- State ----
const tasks = ref<VideoTask[]>([])
const uploading = ref(false)
const uploadFile = ref<File | null>(null)
const uploadFileName = ref('')
const uploadMode = ref('yolo_only')
const taskName = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// Store
const selectedModelId = ref<number | null>(null)
const selectedLLMConfigId = ref<number | null>(null)

// ---- Camera ----
interface CameraSource {
  id: string; name: string; url: string; type: string; enabled: boolean
}
const cameras = ref<CameraSource[]>([])
const showCameraForm = ref(false)
const cameraForm = ref({ name: '', url: '', type: 'rtsp' })

// ---- Webcam detection ----
const webcamDetecting = ref(false)
const webcamMode = ref('yolo_only')
const webcamModelId = ref<number | null>(null)
const webcamLLMConfigId = ref<number | null>(null)
const webcamResults = ref<any>(null)
const webcamBBoxes = ref<any[]>([])
let webcamTimer: ReturnType<typeof setInterval> | null = null

const webcamCanvasRef = ref<HTMLCanvasElement | null>(null)

// Draw bboxes on canvas overlay
watch(webcamBBoxes, async () => {
  await nextTick()
  const canvas = webcamCanvasRef.value
  const video = camera.videoRef.value
  if (!canvas || !video) return
  canvas.width = video.videoWidth || 640
  canvas.height = video.videoHeight || 480
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  const colors = ['#4ade80', '#60a5fa', '#f472b6', '#fbbf24', '#a78bfa']
  for (let i = 0; i < webcamBBoxes.value.length; i++) {
    const b = webcamBBoxes.value[i]
    const c = colors[i % colors.length]
    ctx.strokeStyle = c
    ctx.lineWidth = 2
    ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1)
    const label = b.class_name + ' ' + (b.confidence * 100).toFixed(0) + '%'
    ctx.fillStyle = c
    ctx.fillRect(b.x1, b.y1 - 20, ctx.measureText(label).width + 8, 20)
    ctx.fillStyle = '#fff'
    ctx.font = '13px sans-serif'
    ctx.fillText(label, b.x1 + 4, b.y1 - 5)
  }
})

async function startWebcam() {
  await camera.startCamera()
  if (!camera.isActive.value) return
}

function stopWebcam() {
  stopWebcamDetection()
  camera.stopCamera()
}

async function toggleWebcamDetection() {
  if (webcamDetecting.value) {
    stopWebcamDetection()
  } else {
    if (!camera.isActive.value) {
      ElMessage.warning('请先开启摄像头')
      return
    }
    if (!webcamModelId.value) {
      ElMessage.warning('请先选择YOLO模型')
      return
    }
    webcamDetecting.value = true
    webcamBBoxes.value = []
    runWebcamDetection()
    webcamTimer = setInterval(runWebcamDetection, 800)
  }
}

async function runWebcamDetection() {
  const frame = camera.captureFrame()
  if (!frame) return
  try {
    const blob = dataURLtoBlob(frame)
    const form = new FormData()
    form.append('file', blob, 'webcam.jpg')
    form.append('model_id', String(webcamModelId.value))

    const res = await client.post('/api/detection/realtime', form)
    webcamBBoxes.value = res.data.data?.bboxes || []
  } catch { webcamBBoxes.value = [] }
}

function stopWebcamDetection() {
  webcamDetecting.value = false
  webcamResults.value = null
  webcamBBoxes.value = []
  if (webcamTimer) { clearInterval(webcamTimer); webcamTimer = null }
}

function dataURLtoBlob(dataURL: string): Blob {
  const parts = dataURL.split(',')
  const mime = parts[0].match(/:(.*?);/)?.[1] || 'image/jpeg'
  const bytes = atob(parts[1])
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  return new Blob([arr], { type: mime })
}

onUnmounted(() => {
  stopWebcam()
  if (pollTimer) clearInterval(pollTimer)
})

// ---- Lifecycle ----
onMounted(async () => {
  await configStore.fetchLLMConfigs().catch(() => {})
  await configStore.fetchYOLOModels().catch(() => {})
  await fetchVideoTasks().catch(() => {})
  pollTimer = setInterval(() => fetchVideoTasks().catch(() => {}), 3000)
  loadCameras()
})

// ---- Video Task APIs ----
async function fetchVideoTasks() {
  try {
    const data = await fetchTasks({ page_size: 100 })
    tasks.value = (data.items || [])
      .filter((t: any) => t.source_type === 'video')
  } catch { /* ignore */ }
}

const videoTasks = computed(() => tasks.value)

// ---- Upload ----
function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!ext || !['mp4', 'avi', 'mov', 'webm'].includes(ext)) {
    ElMessage.warning('仅支持 mp4 / avi / mov / webm 格式')
    return
  }
  uploadFile.value = file
  uploadFileName.value = file.name
}

async function startUpload() {
  if (!uploadFile.value) { ElMessage.warning('请选择视频文件'); return }

  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', uploadFile.value)
    form.append('mode', uploadMode.value)
    form.append('task_name', taskName.value.trim())
    if (uploadMode.value !== 'llm_only' && selectedModelId.value) {
      form.append('model_id', String(selectedModelId.value))
    }
    if (uploadMode.value !== 'yolo_only' && selectedLLMConfigId.value) {
      form.append('llm_config_id', String(selectedLLMConfigId.value))
    }

    await createTask(form)
    ElMessage.success('视频任务已创建，正在处理中')
    uploadFile.value = null
    uploadFileName.value = ''
    taskName.value = ''
  } catch (err: any) {
    ElMessage.error(err?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }

  // Always refresh list after creating
  try { await fetchVideoTasks() } catch { /* ignore */ }
}

// ---- Task Actions ----
async function deleteTask(id: number) {
  try {
    await ElMessageBox.confirm('确定删除此视频任务？', '确认', { type: 'warning' })
  } catch { return }
  try {
    await apiDeleteTask(id)
    await fetchVideoTasks()
  } catch { /* ignore */ }
}

// ---- Detail Dialog ----
const detailVisible = ref(false)
const detailTask = ref<any>(null)

async function viewDetail(task: VideoTask) {
  try {
    detailTask.value = await getTask(task.id)
    detailVisible.value = true
  } catch {
    detailTask.value = task
    detailVisible.value = true
  }
}

// ---- Helpers ----
function statusTagType(s: string) {
  if (s === 'completed') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}

function statusLabel(s: string) {
  if (s === 'pending') return '等待中'
  if (s === 'running') return '处理中'
  if (s === 'completed') return '已完成'
  if (s === 'failed') return '失败'
  return s
}

function formatMode(m: string) {
  if (m === 'yolo_only') return 'YOLO检测'
  if (m === 'llm_only') return 'LLM分析'
  return '协同模式'
}

function formatTime(t: string) {
  if (!t) return ''
  return t.replace('T', ' ').substring(0, 19)
}

// ---- Camera Management ----
function loadCameras() {
  const saved = localStorage.getItem('video_sources_cameras')
  if (saved) cameras.value = JSON.parse(saved)
}

function saveCameras() {
  localStorage.setItem('video_sources_cameras', JSON.stringify(cameras.value))
}

function addCamera() {
  if (!cameraForm.value.name.trim() || !cameraForm.value.url.trim()) {
    ElMessage.warning('请填写摄像头名称和地址')
    return
  }
  cameras.value.push({
    id: Date.now().toString(),
    name: cameraForm.value.name.trim(),
    url: cameraForm.value.url.trim(),
    type: cameraForm.value.type,
    enabled: true,
  })
  saveCameras()
  cameraForm.value = { name: '', url: '', type: 'rtsp' }
  showCameraForm.value = false
  ElMessage.success('摄像头已添加')
}

function toggleCamera(cam: CameraSource) {
  cam.enabled = !cam.enabled
  saveCameras()
}

function removeCamera(id: string) {
  cameras.value = cameras.value.filter(c => c.id !== id)
  saveCameras()
}

// ---- Computed ----
const hasRunning = computed(() => tasks.value.some(t => t.status === 'running'))
</script>

<template>
  <LayoutShell>
    <div class="p-8">
          <h2 class="text-2xl font-bold mb-6">视频源管理</h2>

          <!-- Running indicator -->
          <div v-if="hasRunning" class="mb-4 text-sm text-orange-500 flex items-center gap-2">
            <el-icon class="is-loading"><Refresh /></el-icon> 有视频正在处理中...
          </div>

          <el-tabs v-model="activeTab">
            <!-- ============= VIDEO FILE TAB ============= -->
            <el-tab-pane label="视频文件" name="video">
              <!-- Upload area -->
              <div class="bg-white rounded-lg shadow-sm p-6 mb-6">
                <h3 class="text-base font-semibold mb-4">上传视频文件</h3>
                <div class="grid grid-cols-[1fr_260px] gap-6">
                  <!-- File dropzone -->
                  <label class="block cursor-pointer">
                    <div class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors min-h-[120px] flex flex-col items-center justify-center">
                      <template v-if="uploadFileName">
                        <el-icon :size="40" color="#409EFF"><VideoPlay /></el-icon>
                        <p class="mt-2 text-sm text-gray-700 font-medium">{{ uploadFileName }}</p>
                        <p class="text-xs text-gray-400 mt-1">点击更换文件</p>
                      </template>
                      <template v-else>
                        <el-icon :size="40" color="#c0c4cc"><Upload /></el-icon>
                        <p class="mt-2 text-sm text-gray-500">点击选择视频文件</p>
                        <p class="text-xs text-gray-400 mt-1">支持 mp4 / avi / mov / webm，最大 500MB</p>
                      </template>
                    </div>
                    <input type="file" accept="video/mp4,video/avi,video/mov,video/webm" class="hidden" @change="handleFileSelect" />
                  </label>

                  <!-- Config panel -->
                  <div class="space-y-3">
                    <div>
                      <label class="text-xs text-gray-500 mb-1 block">任务名称（可选）</label>
                      <el-input v-model="taskName" placeholder="输入名称" size="small" />
                    </div>
                    <div>
                      <label class="text-xs text-gray-500 mb-1 block">检测模式</label>
                      <el-select v-model="uploadMode" size="small" class="w-full">
                        <el-option label="YOLO检测" value="yolo_only" />
                        <el-option label="LLM分析" value="llm_only" />
                        <el-option label="协同模式" value="collaborative" />
                      </el-select>
                    </div>
                    <div v-if="uploadMode !== 'llm_only'">
                      <label class="text-xs text-gray-500 mb-1 block">YOLO模型</label>
                      <el-select v-model="selectedModelId" size="small" class="w-full" placeholder="默认模型" clearable>
                        <el-option v-for="m in configStore.yoloModels" :key="m.id" :label="m.name" :value="m.id" />
                      </el-select>
                    </div>
                    <div v-if="uploadMode !== 'yolo_only'">
                      <label class="text-xs text-gray-500 mb-1 block">LLM配置</label>
                      <el-select v-model="selectedLLMConfigId" size="small" class="w-full" placeholder="默认启用" clearable>
                        <el-option v-for="c in configStore.llmConfigs" :key="c.id" :label="c.name" :value="c.id" />
                      </el-select>
                    </div>
                    <el-button type="primary" :loading="uploading" :disabled="!uploadFile" @click="startUpload" class="w-full">
                      开始检测
                    </el-button>
                    <p class="text-xs text-gray-400">视频逐帧检测，每5帧处理1帧</p>
                  </div>
                </div>
              </div>

              <!-- Video task list -->
              <div class="bg-white rounded-lg shadow-sm">
                <div class="p-4 border-b flex items-center justify-between">
                  <h3 class="text-base font-semibold">视频任务列表</h3>
                  <el-button :icon="Refresh" size="small" @click="fetchVideoTasks">刷新</el-button>
                </div>

                <div v-if="videoTasks.length === 0" class="p-12 text-center text-gray-400">
                  <el-icon :size="48"><VideoCamera /></el-icon>
                  <p class="mt-2 text-sm">暂无视频任务，上传视频开始检测</p>
                </div>

                <div class="divide-y">
                  <div
                    v-for="task in videoTasks" :key="task.id"
                    @click="viewDetail(task)"
                    class="p-4 flex items-center gap-4 cursor-pointer hover:bg-gray-50 transition-colors"
                  >
                    <!-- Thumbnail placeholder -->
                    <div class="w-20 h-14 bg-gray-800 rounded flex-shrink-0 flex items-center justify-center">
                      <el-icon :size="20" color="#fff"><VideoPlay /></el-icon>
                    </div>

                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-2 mb-1">
                        <span v-if="task.task_name" class="text-sm font-medium text-gray-700">{{ task.task_name }}</span>
                        <span v-else class="text-sm text-gray-500">任务 #{{ task.id }}</span>
                        <el-tag :type="statusTagType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
                        <el-tag size="small" type="warning">视频</el-tag>
                        <el-tag size="small">{{ formatMode(task.mode) }}</el-tag>
                      </div>
                      <div class="flex items-center gap-3 text-xs text-gray-400">
                        <span>{{ formatTime(task.created_at) }}</span>
                        <template v-if="task.status === 'completed' && task.result_json">
                          <span>处理 {{ task.result_json.frame_count || 0 }} 帧</span>
                          <span>检测到 {{ task.result_json.total_objects || 0 }} 个目标</span>
                        </template>
                      </div>
                    </div>

                    <el-button
                      type="danger" size="small" :icon="Delete" plain
                      @click.stop="deleteTask(task.id)"
                    />
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- ============= CAMERA TAB ============= -->
            <el-tab-pane label="摄像头" name="camera">
              <!-- ===== Webcam Section ===== -->
              <div class="bg-white rounded-lg shadow-sm p-4 mb-6">
                <h3 class="text-base font-semibold mb-3">本机摄像头</h3>
                <div class="grid grid-cols-[1fr_280px] gap-4">
                  <!-- Video preview -->
                  <div class="relative bg-black rounded-lg overflow-hidden min-h-[300px]">
                    <video
                      :ref="(el: any) => camera.videoRef.value = el"
                      class="w-full h-full object-contain absolute inset-0"
                      autoplay playsinline muted
                    />
                    <canvas
                      ref="webcamCanvasRef"
                      class="w-full h-full object-contain absolute inset-0"
                    />
                    <div v-if="!camera.isActive.value" class="absolute inset-0 flex items-center justify-center bg-gray-900">
                      <p class="text-gray-400 text-sm">摄像头未开启</p>
                    </div>
                  </div>

                  <!-- Controls -->
                  <div class="space-y-3">
                    <div>
                      <label class="text-xs text-gray-500 mb-1 block">检测模式</label>
                      <el-select v-model="webcamMode" size="small" class="w-full" :disabled="webcamDetecting">
                        <el-option label="YOLO检测" value="yolo_only" />
                        <el-option label="LLM分析" value="llm_only" />
                        <el-option label="协同模式" value="collaborative" />
                      </el-select>
                    </div>

                    <div v-if="webcamMode !== 'llm_only'">
                      <label class="text-xs text-gray-500 mb-1 block">YOLO模型</label>
                      <el-select v-model="webcamModelId" size="small" class="w-full" placeholder="默认模型" clearable :disabled="webcamDetecting">
                        <el-option v-for="m in configStore.yoloModels" :key="m.id" :label="m.name" :value="m.id" />
                      </el-select>
                    </div>

                    <div v-if="webcamMode !== 'yolo_only'">
                      <label class="text-xs text-gray-500 mb-1 block">LLM配置</label>
                      <el-select v-model="webcamLLMConfigId" size="small" class="w-full" placeholder="默认启用" clearable :disabled="webcamDetecting">
                        <el-option v-for="c in configStore.llmConfigs" :key="c.id" :label="c.name" :value="c.id" />
                      </el-select>
                    </div>

                    <div v-if="!camera.isActive.value">
                      <el-button type="primary" @click="startWebcam" class="w-full">
                        开启摄像头
                      </el-button>
                    </div>
                    <div v-else class="space-y-2">
                      <el-button
                        :type="webcamDetecting ? 'warning' : 'success'"
                        @click="toggleWebcamDetection"
                        class="w-full"
                      >
                        {{ webcamDetecting ? '停止检测' : '开始实时检测' }}
                      </el-button>
                      <el-button @click="stopWebcam" class="w-full">关闭摄像头</el-button>
                    </div>

                    <!-- Results summary -->
                    <div v-if="webcamDetecting && webcamBBoxes.length > 0" class="bg-green-50 rounded p-2 text-xs">
                      <p class="text-green-700 font-medium mb-1">
                        检测到 {{ webcamBBoxes.length }} 个目标
                      </p>
                      <div class="flex flex-wrap gap-1">
                        <span
                          v-for="(box, i) in webcamBBoxes" :key="i"
                          class="bg-green-100 text-green-700 px-1.5 py-0.5 rounded"
                        >
                          {{ box.class_name }} {{ (box.confidence * 100).toFixed(0) }}%
                        </span>
                      </div>
                    </div>

                    <p v-if="camera.error.value" class="text-xs text-red-500">{{ camera.error.value }}</p>
                  </div>
                </div>
              </div>

              <!-- ===== Network Camera Section ===== -->
              <div class="mb-4">
                <el-button type="primary" :icon="Link" @click="showCameraForm = !showCameraForm">
                  {{ showCameraForm ? '取消' : '添加网络摄像头' }}
                </el-button>
              </div>

              <!-- Add camera form -->
              <div v-if="showCameraForm" class="bg-white rounded-lg shadow-sm p-4 mb-4">
                <div class="flex items-end gap-3">
                  <div class="flex-1">
                    <label class="text-xs text-gray-500 mb-1 block">名称</label>
                    <el-input v-model="cameraForm.name" placeholder="例：门口监控" size="small" />
                  </div>
                  <div class="flex-1">
                    <label class="text-xs text-gray-500 mb-1 block">地址 (RTSP/RTMP)</label>
                    <el-input v-model="cameraForm.url" placeholder="rtsp://192.168.1.1:554/stream" size="small" />
                  </div>
                  <el-button type="primary" size="small" @click="addCamera">添加</el-button>
                </div>
              </div>

              <!-- Network camera list -->
              <div v-if="cameras.length === 0 && !showCameraForm" class="text-center text-gray-400 py-6">
                <p class="text-xs">暂无网络摄像头</p>
              </div>

              <div class="grid grid-cols-2 gap-4">
                <div
                  v-for="cam in cameras" :key="cam.id"
                  class="bg-white rounded-lg shadow-sm p-4"
                >
                  <div class="flex items-start justify-between mb-3">
                    <div>
                      <h4 class="text-sm font-semibold">{{ cam.name }}</h4>
                      <p class="text-xs text-gray-400 mt-0.5 truncate max-w-[200px]">{{ cam.url }}</p>
                    </div>
                    <el-switch :model-value="cam.enabled" @change="toggleCamera(cam)" size="small" />
                  </div>
                  <div class="flex items-center gap-2">
                    <el-tag :type="cam.type === 'rtsp' ? '' : 'success'" size="small">
                      {{ cam.type.toUpperCase() }}
                    </el-tag>
                    <span class="text-xs text-gray-400">{{ cam.enabled ? '已启用' : '已停用' }}</span>
                    <div class="flex-1" />
                    <el-button type="danger" size="small" text @click="removeCamera(cam.id)">删除</el-button>
                  </div>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>

    <!-- Detail Dialog -->
    <el-dialog v-model="detailVisible" title="视频任务详情" width="700px" top="3vh">
      <template v-if="detailTask">
        <div class="space-y-4">
          <!-- Video player -->
          <div v-if="detailTask.result_json?.video_path" class="bg-black rounded-lg overflow-hidden">
            <video controls class="w-full max-h-[400px]" :src="'/' + detailTask.result_json.video_path">
              您的浏览器不支持视频播放
            </video>
          </div>

          <div class="flex gap-3 text-sm">
            <el-tag :type="statusTagType(detailTask.status)">{{ statusLabel(detailTask.status) }}</el-tag>
            <el-tag>{{ formatMode(detailTask.mode) }}</el-tag>
            <span class="text-gray-400">{{ formatTime(detailTask.created_at) }}</span>
          </div>

          <!-- Frame count & summary -->
          <div v-if="detailTask.result_json?.source_type === 'video'">
            <div class="bg-gray-50 rounded p-3 flex gap-6 text-sm">
              <div>
                <span class="text-gray-500">处理帧数:</span>
                <span class="ml-1 font-medium">{{ detailTask.result_json.frame_count || 0 }}</span>
              </div>
              <div>
                <span class="text-gray-500">检测目标:</span>
                <span class="ml-1 font-medium">{{ detailTask.result_json.total_objects || 0 }} 个</span>
              </div>
            </div>
          </div>

          <!-- Detection summary -->
          <div v-if="detailTask.result_json?.detection_summary?.length">
            <h4 class="text-sm font-semibold text-gray-500 mb-2">检测汇总</h4>
            <div class="space-y-1">
              <div
                v-for="s in detailTask.result_json.detection_summary" :key="s.class"
                class="flex items-center gap-2 text-sm bg-blue-50 rounded px-3 py-1.5"
              >
                <el-tag size="small" type="success">{{ s.class }}</el-tag>
                <span class="text-gray-500">出现 {{ s.count }} 次</span>
                <span class="text-gray-400">平均置信度 {{ (s.avg_confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- Error -->
          <div v-if="detailTask.result_json?.error" class="text-sm text-red-500 bg-red-50 rounded p-3">
            {{ detailTask.result_json.error }}
          </div>
        </div>
      </template>
    </el-dialog>
  </LayoutShell>
</template>
