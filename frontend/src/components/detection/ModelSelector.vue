<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDetectionStore } from '@/stores/detection'
import { useConfigStore } from '@/stores/config'
import LLMConfigDialog from '@/components/config/LLMConfigDialog.vue'
import YOLOModelUpload from '@/components/config/YOLOModelUpload.vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'

const props = defineProps<{
  type: 'yolo' | 'llm'
}>()

const detectionStore = useDetectionStore()
const configStore = useConfigStore()

const showLLMDialog = ref(false)
const showYOLOUpload = ref(false)
const deleting = ref(false)

const options = computed(() => {
  if (props.type === 'yolo') {
    return configStore.yoloModels.map(m => ({ id: m.id, name: m.name }))
  }
  return configStore.llmConfigs.map(c => ({ id: c.id, name: c.name }))
})

const selectedId = computed({
  get: () => props.type === 'yolo' ? detectionStore.selectedModelId : detectionStore.selectedLLMConfigId,
  set: (val) => {
    if (props.type === 'yolo') {
      detectionStore.selectedModelId = val
    } else {
      detectionStore.selectedLLMConfigId = val
    }
  },
})

const canDelete = computed(() => {
  if (props.type === 'yolo') {
    return detectionStore.selectedModelId && detectionStore.selectedModelId !== 0
  }
  return detectionStore.selectedLLMConfigId != null
})

async function handleDelete() {
  const id = props.type === 'yolo'
    ? detectionStore.selectedModelId
    : detectionStore.selectedLLMConfigId
  if (id == null) return

  const label = props.type === 'yolo' ? 'YOLO模型' : 'LLM配置'
  try {
    await ElMessageBox.confirm(`确定要删除这个${label}吗？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  deleting.value = true
  try {
    if (props.type === 'yolo') {
      await configStore.deleteYOLOModel(id)
      detectionStore.selectedModelId = null
    } else {
      await configStore.deleteLLMConfig(id)
      detectionStore.selectedLLMConfigId = null
    }
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="flex items-center gap-2">
    <el-select
      v-model="selectedId"
      :placeholder="type === 'yolo' ? '选择YOLO模型' : '选择LLM配置'"
      size="small"
      class="flex-1"
      clearable
    >
      <el-option
        v-for="opt in options"
        :key="opt.id ?? 'default'"
        :label="opt.name"
        :value="opt.id"
      />
    </el-select>
    <el-button v-if="type === 'llm'" size="small" @click="showLLMDialog = true">+</el-button>
    <el-button v-if="type === 'yolo'" size="small" @click="showYOLOUpload = true">+</el-button>
    <el-button
      v-if="canDelete"
      size="small"
      type="danger"
      :icon="Delete"
      :loading="deleting"
      @click="handleDelete"
    />
  </div>

  <LLMConfigDialog v-model:visible="showLLMDialog" />
  <YOLOModelUpload v-model:visible="showYOLOUpload" />
</template>
