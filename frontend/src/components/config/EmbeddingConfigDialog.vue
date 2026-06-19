<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '@/stores/config'
import type { EmbeddingConfigForm, EmbeddingProvider, EmbeddingConfig } from '@/types/config'

const props = defineProps<{ visible: boolean; editConfig?: EmbeddingConfig | null }>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

const configStore = useConfigStore()

const isEditMode = computed(() => !!props.editConfig)
const dialogTitle = computed(() => isEditMode.value ? '编辑嵌入模型' : '添加嵌入模型')

const form = ref<EmbeddingConfigForm>({
  name: '',
  provider: 'local',
  model_name: 'paraphrase-multilingual-MiniLM-L12-v2',
  api_base_url: '',
  api_key: '',
  dimension: 384,
  is_active: false,
  description: '',
})

watch(() => props.visible, (val) => {
  if (val) {
    if (props.editConfig) {
      form.value = {
        name: props.editConfig.name || '',
        provider: props.editConfig.provider as EmbeddingProvider || 'custom',
        model_name: props.editConfig.model_name || '',
        api_base_url: props.editConfig.api_base_url || '',
        api_key: '',
        dimension: props.editConfig.dimension || 384,
        is_active: props.editConfig.is_active || false,
        description: props.editConfig.description || '',
      }
    } else {
      form.value = {
        name: '',
        provider: 'local',
        model_name: 'paraphrase-multilingual-MiniLM-L12-v2',
        api_base_url: '',
        api_key: '',
        dimension: 384,
        is_active: false,
        description: '',
      }
    }
  }
})

const presets: Record<string, { model_name: string; dimension: number; api_base_url?: string }> = {
  'local-multilingual': {
    model_name: 'paraphrase-multilingual-MiniLM-L12-v2',
    dimension: 384,
  },
  'local-chinese': {
    model_name: 'shibing624/text2vec-base-chinese',
    dimension: 768,
  },
  'openai-small': {
    model_name: 'text-embedding-3-small',
    dimension: 1536,
    api_base_url: 'https://api.openai.com/v1',
  },
  'openai-large': {
    model_name: 'text-embedding-3-large',
    dimension: 3072,
    api_base_url: 'https://api.openai.com/v1',
  },
}

function applyPreset(key: string) {
  const preset = presets[key]
  if (!preset) return
  form.value.model_name = preset.model_name
  form.value.dimension = preset.dimension
  if (preset.api_base_url) {
    form.value.api_base_url = preset.api_base_url
  }
}

async function handleSubmit() {
  if (!form.value.name.trim() || !form.value.model_name.trim()) {
    ElMessage.warning('请填写必填项')
    return
  }
  try {
    // Build payload — exclude api_key if empty (keep existing)
    const payload: Partial<EmbeddingConfigForm> = { ...form.value }
    if (!payload.api_key) delete payload.api_key

    if (isEditMode.value && props.editConfig) {
      await configStore.updateEmbeddingConfig(props.editConfig.id, payload)
      ElMessage.success('嵌入模型配置已更新')
    } else {
      await configStore.createEmbeddingConfig(payload as EmbeddingConfigForm)
      ElMessage.success('嵌入模型配置已添加')
    }
    emit('update:visible', false)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || (isEditMode.value ? '更新失败' : '添加失败'))
  }
}

function handleProviderChange(provider: EmbeddingProvider) {
  if (provider === 'local') {
    form.value.api_base_url = ''
    form.value.api_key = ''
    form.value.model_name = 'paraphrase-multilingual-MiniLM-L12-v2'
    form.value.dimension = 384
  } else if (provider === 'openai') {
    form.value.api_base_url = 'https://api.openai.com/v1'
    form.value.model_name = 'text-embedding-3-small'
    form.value.dimension = 1536
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="emit('update:visible', $event)"
    :title="dialogTitle"
    width="520px"
  >
    <el-form :model="form" label-width="100px">
      <el-form-item label="配置名称" required>
        <el-input v-model="form.name" placeholder="如：本地多语言模型" />
      </el-form-item>

      <el-form-item label="提供商" required>
        <el-select v-model="form.provider" @change="handleProviderChange" style="width: 100%">
          <el-option label="本地模型 (sentence-transformers)" value="local" />
          <el-option label="OpenAI 兼容 API" value="openai" />
          <el-option label="自定义" value="custom" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="form.provider === 'local'" label="预设模型">
        <el-select @change="applyPreset" placeholder="选择预设" style="width: 100%" clearable>
          <el-option label="多语言通用 (384维)" value="local-multilingual" />
          <el-option label="中文专用 (768维)" value="local-chinese" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="form.provider === 'openai'" label="预设模型">
        <el-select @change="applyPreset" placeholder="选择预设" style="width: 100%" clearable>
          <el-option label="text-embedding-3-small (1536维)" value="openai-small" />
          <el-option label="text-embedding-3-large (3072维)" value="openai-large" />
        </el-select>
      </el-form-item>

      <el-form-item label="模型名称" required>
        <el-input v-model="form.model_name" placeholder="模型标识" />
      </el-form-item>

      <el-form-item v-if="form.provider !== 'local'" label="API 地址">
        <el-input v-model="form.api_base_url" placeholder="https://api.example.com/v1" />
      </el-form-item>

      <el-form-item v-if="form.provider !== 'local'" label="API 密钥">
        <el-input v-model="form.api_key" type="password" show-password placeholder="sk-..." />
      </el-form-item>

      <el-form-item label="向量维度">
        <el-input-number v-model="form.dimension" :min="64" :max="4096" :step="64" />
      </el-form-item>

      <el-form-item label="启用">
        <el-switch v-model="form.is_active" />
        <span class="text-xs text-gray-400 ml-2">启用后将停用其他嵌入模型</span>
      </el-form-item>

      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选描述" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" @click="handleSubmit">{{ isEditMode ? '保存' : '添加' }}</el-button>
    </template>
  </el-dialog>
</template>
