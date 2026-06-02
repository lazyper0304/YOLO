<script setup lang="ts">
import { ref } from 'vue'
import { useDetectionStore } from '@/stores/detection'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = withDefaults(defineProps<{
  compact?: boolean
}>(), {
  compact: false,
})

const detectionStore = useDetectionStore()
const isDragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp']
const allowedExtensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

function validateFile(file: File): boolean {
  if (!allowedTypes.includes(file.type) && !allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) {
    ElMessage.error('不支持的图片格式，请选择 jpg/png/webp/bmp 格式')
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error('图片大小不能超过 20MB')
    return false
  }
  return true
}

function handleFileSelect(file: File) {
  if (!validateFile(file)) return
  const url = URL.createObjectURL(file)
  detectionStore.setFile(file, url)
  detectionStore.reset()
}

function handleInputChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    handleFileSelect(file)
  }
  input.value = ''
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  isDragOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) {
    handleFileSelect(file)
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
  isDragOver.value = true
}

function handleDragLeave() {
  isDragOver.value = false
}
</script>

<template>
  <div
    class="border-2 border-dashed rounded-lg transition-colors cursor-pointer flex flex-col items-center justify-center"
    :class="[
      compact ? 'p-4 text-sm' : 'p-8',
      isDragOver ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50',
    ]"
    @drop="handleDrop"
    @dragover="handleDragOver"
    @dragleave="handleDragLeave"
    @click="fileInput?.click()"
  >
    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/bmp"
      class="hidden"
      @change="handleInputChange"
    />

    <el-icon :size="compact ? 28 : 48" class="text-gray-300 mb-2"><UploadFilled /></el-icon>
    <p v-if="!compact" class="text-gray-500">点击或拖拽图片到此区域上传</p>
    <p :class="compact ? 'text-xs' : 'text-xs'" class="text-gray-400 mt-1">支持 JPG / PNG / WebP / BMP，最大 20MB</p>

    <div v-if="detectionStore.uploadedFile" class="mt-3 text-center">
      <el-tag size="small" type="success" closable @close="detectionStore.setFile(null, null)">
        {{ detectionStore.uploadedFile.name }}
      </el-tag>
    </div>
  </div>
</template>
