<script setup lang="ts">
import { ref, watch } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '@/stores/config'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const configStore = useConfigStore()

const modelName = ref('')
const file = ref<File | null>(null)
const uploading = ref(false)

watch(() => props.visible, (val) => {
  if (val) {
    modelName.value = ''
    file.value = null
  }
})

function handleFileChange(f: File) {
  if (!f.name.endsWith('.pt')) {
    ElMessage.error('仅支持 .pt 格式的模型文件')
    return
  }
  file.value = f
  if (!modelName.value) {
    modelName.value = f.name.replace('.pt', '')
  }
}

async function handleUpload() {
  if (!file.value) {
    ElMessage.warning('请选择模型文件')
    return
  }
  if (!modelName.value.trim()) {
    ElMessage.warning('请输入模型名称')
    return
  }

  uploading.value = true
  try {
    await configStore.uploadYOLOModel(modelName.value.trim(), file.value)
    ElMessage.success('模型上传成功')
    emit('update:visible', false)
  } catch {
    // Error handled by interceptor
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="上传 YOLO 模型"
    width="460px"
    :close-on-click-modal="false"
    @update:model-value="(val: boolean) => emit('update:visible', val)"
  >
    <el-form label-width="80px">
      <el-form-item label="模型名称">
        <el-input v-model="modelName" placeholder="输入模型名称" />
      </el-form-item>
      <el-form-item label="模型文件">
        <el-upload
          :auto-upload="false"
          :limit="1"
          accept=".pt"
          drag
          :on-change="(uploadFile: any) => handleFileChange(uploadFile.raw as File)"
        >
          <div class="text-center py-4">
            <el-icon :size="40" class="text-gray-300 mb-2"><UploadFilled /></el-icon>
            <p class="text-sm text-gray-500">拖拽或点击上传 .pt 模型文件</p>
            <p class="text-xs text-gray-400 mt-1">最大 200MB</p>
          </div>
        </el-upload>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="uploading" :disabled="!file" @click="handleUpload">
        上传
      </el-button>
    </template>
  </el-dialog>
</template>
