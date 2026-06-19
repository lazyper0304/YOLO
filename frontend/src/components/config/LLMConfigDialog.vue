<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '@/stores/config'
import type { LLMProvider, LLMConfigForm, LLMConfig } from '@/types/config'

const props = defineProps<{
  visible: boolean
  editConfig?: LLMConfig | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const configStore = useConfigStore()

const isEditMode = computed(() => !!props.editConfig)
const dialogTitle = computed(() => isEditMode.value ? '编辑 LLM 配置' : '添加 LLM 配置')

const formRef = ref()
const loading = ref(false)
const testing = ref(false)

const form = reactive<LLMConfigForm>({
  name: '',
  api_base_url: '',
  api_key: '',
  model_name: '',
  provider: 'generic',
  is_active: false,
})

const rules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  api_base_url: [{ required: true, message: '请输入API地址', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入API密钥', trigger: 'blur' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
}

const providers: { value: LLMProvider; label: string }[] = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'claude', label: 'Claude' },
  { value: 'generic', label: '通用OpenAI兼容' },
  { value: 'ollama', label: 'Ollama' },
]

watch(() => props.visible, (val) => {
  if (val) {
    if (props.editConfig) {
      Object.assign(form, {
        name: props.editConfig.name || '',
        api_base_url: props.editConfig.api_base_url || '',
        api_key: '',
        model_name: props.editConfig.model_name || '',
        provider: (props.editConfig.provider as LLMProvider) || 'generic',
        is_active: props.editConfig.is_active || false,
      })
    } else {
      Object.assign(form, {
        name: '',
        api_base_url: '',
        api_key: '',
        model_name: '',
        provider: 'generic' as LLMProvider,
        is_active: false,
      })
    }
    testing.value = false
  }
})

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const payload: Partial<LLMConfigForm> = { ...form }
    if (!payload.api_key) delete payload.api_key
    if (payload.api_key) payload.api_key = payload.api_key

    if (isEditMode.value && props.editConfig) {
      await configStore.updateLLMConfig(props.editConfig.id, payload)
      ElMessage.success('LLM配置已更新')
    } else {
      await configStore.createLLMConfig(payload as LLMConfigForm)
      ElMessage.success('LLM配置创建成功')
    }
    emit('update:visible', false)
  } catch {
    // Error handled by interceptor
  } finally {
    loading.value = false
  }
}

async function handleTest() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  testing.value = true
  try {
    const result = await configStore.createLLMConfig({ ...form })
    const testResult = await configStore.testLLMConfig(result.id)
    if (testResult.success) {
      ElMessage.success(`连接成功！响应时间: ${testResult.response_time_ms.toFixed(0)}ms`)
    } else {
      ElMessage.error(`连接失败: ${testResult.message}`)
    }
    // Clean up test config if not in edit mode
    if (!isEditMode.value) {
      await configStore.deleteLLMConfig(result.id)
    }
  } catch {
    // Error handled by interceptor
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="dialogTitle"
    width="520px"
    :close-on-click-modal="false"
    @update:model-value="(val: boolean) => emit('update:visible', val)"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="配置名称" prop="name">
        <el-input v-model="form.name" placeholder="例如：我的OpenAI" />
      </el-form-item>

      <el-form-item label="服务商" prop="provider">
        <el-select v-model="form.provider" class="w-full">
          <el-option
            v-for="p in providers"
            :key="p.value"
            :label="p.label"
            :value="p.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="API地址" prop="api_base_url">
        <el-input v-model="form.api_base_url" placeholder="https://api.openai.com/v1" />
      </el-form-item>

      <el-form-item label="API密钥" prop="api_key">
        <el-input
          v-model="form.api_key"
          type="password"
          placeholder="sk-..."
          show-password
        />
      </el-form-item>

      <el-form-item label="模型名称" prop="model_name">
        <el-input v-model="form.model_name" placeholder="gpt-4o" />
      </el-form-item>

      <el-form-item label="设为活跃">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="flex justify-between">
        <el-button :loading="testing" @click="handleTest">测试连接</el-button>
        <div class="flex gap-2">
          <el-button @click="emit('update:visible', false)">取消</el-button>
          <el-button type="primary" :loading="loading" @click="handleSave">{{ isEditMode ? '保存' : '添加' }}</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>
