<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useConfigStore } from '@/stores/config'
import type { LLMProvider, LLMConfigForm } from '@/types/config'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const configStore = useConfigStore()

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
    Object.assign(form, {
      name: '',
      api_base_url: '',
      api_key: '',
      model_name: '',
      provider: 'generic' as LLMProvider,
      is_active: false,
    })
    testing.value = false
  }
})

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await configStore.createLLMConfig({ ...form })
    ElMessage.success('LLM配置创建成功')
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
    // Create config first, then test
    const result = await configStore.createLLMConfig({ ...form })
    const testResult = await configStore.testLLMConfig(result.id)
    if (testResult.success) {
      ElMessage.success(`连接成功！响应时间: ${testResult.response_time_ms.toFixed(0)}ms`)
    } else {
      ElMessage.error(`连接失败: ${testResult.message}`)
      // Remove the failed config
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
    title="添加 LLM 配置"
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
          <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>
