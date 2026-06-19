<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { LayoutShell } from '@/components'
import { useConfigStore } from '@/stores/config'
import LLMConfigDialog from '@/components/config/LLMConfigDialog.vue'
import YOLOModelUpload from '@/components/config/YOLOModelUpload.vue'
import EmbeddingConfigDialog from '@/components/config/EmbeddingConfigDialog.vue'
import type { LLMConfig, LLMConfigForm, EmbeddingConfig } from '@/types/config'

const configStore = useConfigStore()
const showLLMDialog = ref(false)
const editingLLMConfig = ref<LLMConfig | null>(null)
const showYOLOUpload = ref(false)
const showEmbeddingDialog = ref(false)
const editingEmbeddingConfig = ref<EmbeddingConfig | null>(null)

onMounted(async () => {
  await Promise.all([
    configStore.fetchYOLOModels(),
    configStore.fetchLLMConfigs(),
    configStore.fetchEmbeddingConfigs(),
  ])
})

async function deleteYOLO(id: number) {
  try { await ElMessageBox.confirm('确定删除此模型吗？', '确认', { type: 'warning' }) } catch { return }
  await configStore.deleteYOLOModel(id)
  ElMessage.success('已删除')
}

async function deleteLLM(id: number) {
  try { await ElMessageBox.confirm('确定删除此配置吗？', '确认', { type: 'warning' }) } catch { return }
  await configStore.deleteLLMConfig(id)
  ElMessage.success('已删除')
}

async function toggleLLM(row: { id: number; is_active: boolean }) {
  const newActive = !row.is_active
  const action = newActive ? '启用' : '停用'
  try {
    await configStore.updateLLMConfig(row.id, { is_active: newActive })
    ElMessage.success(`已${action}`)
  } catch {
    ElMessage.error(`${action}失败`)
  }
}

function openEditLLM(config: LLMConfig | null) {
  editingLLMConfig.value = config
  showLLMDialog.value = true
}

function closeLLMDialog() {
  showLLMDialog.value = false
  editingLLMConfig.value = null
}

async function deleteEmbedding(id: number) {
  try { await ElMessageBox.confirm('确定删除此嵌入模型配置吗？', '确认', { type: 'warning' }) } catch { return }
  await configStore.deleteEmbeddingConfig(id)
  ElMessage.success('已删除')
}

async function toggleEmbedding(row: { id: number; is_active: boolean }) {
  const newActive = !row.is_active
  const action = newActive ? '启用' : '停用'
  try {
    await configStore.updateEmbeddingConfig(row.id, { is_active: newActive })
    ElMessage.success(`已${action}`)
  } catch {
    ElMessage.error(`${action}失败`)
  }
}

function openEditEmbedding(config: EmbeddingConfig) {
  editingEmbeddingConfig.value = config
  showEmbeddingDialog.value = true
}

function closeEmbeddingDialog() {
  showEmbeddingDialog.value = false
  editingEmbeddingConfig.value = null
}

function providerLabel(provider: string) {
  const map: Record<string, string> = {
    local: '本地',
    openai: 'OpenAI',
    custom: '自定义',
  }
  return map[provider] || provider
}
</script>

<template>
  <LayoutShell>
    <div class="p-8 space-y-8">
          <h2 class="text-2xl font-bold mb-6">模型算法管理</h2>

          <!-- YOLO Models -->
          <div class="bg-white rounded-lg shadow-sm">
            <div class="flex items-center justify-between p-5 border-b">
              <h3 class="text-base font-semibold">YOLO 模型管理</h3>
              <el-button type="primary" size="small" :disabled="configStore.isLoadingYOLO" :loading="configStore.isLoadingYOLO" @click="showYOLOUpload = true">{{ configStore.isLoadingYOLO ? '加载中...' : '上传模型' }}</el-button>
            </div>
            <el-table :data="configStore.yoloModels" size="small" stripe>
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="name" label="模型" min-width="140" />
              <el-table-column prop="model_type" label="类型" width="100" />
              <el-table-column label="内置" width="60">
                <template #default="{ row }"><el-tag size="small" :type="row.is_builtin ? 'info' : ''">{{ row.is_builtin ? '是' : '否' }}</el-tag></template>
              </el-table-column>
              <el-table-column label="可检测类别" min-width="260">
                <template #default="{ row }">
                  <div class="text-xs text-gray-600 max-w-60 truncate" :title="row.classes">
                    {{ row.classes || '尚未加载' }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button v-if="!row.is_builtin" type="danger" size="small" plain @click="deleteYOLO(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- LLM Configs -->
          <div class="bg-white rounded-lg shadow-sm">
            <div class="flex items-center justify-between p-5 border-b">
              <h3 class="text-base font-semibold">LLM 配置管理</h3>
              <el-button type="primary" size="small" :disabled="configStore.isLoadingLLM" :loading="configStore.isLoadingLLM" @click="openEditLLM(null)">{{ configStore.isLoadingLLM ? '加载中...' : '添加配置' }}</el-button>
            </div>
            <el-table :data="configStore.llmConfigs" size="small" stripe>
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="name" label="配置名称" />
              <el-table-column prop="provider" label="服务商" width="80">
                <template #default="{ row }"><el-tag size="small">{{ row.provider }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="api_base_url" label="API地址" min-width="200" />
              <el-table-column prop="model_name" label="模型名" width="120" />
              <el-table-column label="状态" width="70">
                <template #default="{ row }"><el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="210">
                <template #default="{ row }">
                  <el-button size="small" @click="openEditLLM(row)">编辑</el-button>
                  <el-button
                    v-if="!row.is_active"
                    size="small"
                    type="success"
                    plain
                    @click="toggleLLM(row)"
                  >启用</el-button>
                  <el-button
                    v-else
                    size="small"
                    type="warning"
                    plain
                    @click="toggleLLM(row)"
                  >停用</el-button>
                  <el-button size="small" type="danger" plain @click="deleteLLM(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- Embedding Model Configs -->
          <div class="bg-white rounded-lg shadow-sm">
            <div class="flex items-center justify-between p-5 border-b">
              <h3 class="text-base font-semibold">知识库嵌入模型管理</h3>
              <el-button type="primary" size="small" :disabled="configStore.isLoadingEmbedding" :loading="configStore.isLoadingEmbedding" @click="openEditEmbedding(null!)">{{ configStore.isLoadingEmbedding ? '加载中...' : '添加模型' }}</el-button>
            </div>
            <div v-if="configStore.embeddingConfigs.length === 0" class="p-8 text-center text-gray-400">
              暂无嵌入模型配置，点击上方按钮添加
            </div>
            <el-table v-else :data="configStore.embeddingConfigs" size="small" stripe>
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="name" label="配置名称" />
              <el-table-column label="提供商" width="80">
                <template #default="{ row }"><el-tag size="small">{{ providerLabel(row.provider) }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="model_name" label="模型名" min-width="180" />
              <el-table-column label="维度" width="80" prop="dimension" />
              <el-table-column label="状态" width="70">
                <template #default="{ row }"><el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="210">
                <template #default="{ row }">
                  <el-button size="small" @click="openEditEmbedding(row)">编辑</el-button>
                  <el-button
                    v-if="!row.is_active"
                    size="small"
                    type="success"
                    plain
                    @click="toggleEmbedding(row)"
                  >启用</el-button>
                  <el-button
                    v-else
                    size="small"
                    type="warning"
                    plain
                    @click="toggleEmbedding(row)"
                  >停用</el-button>
                  <el-button v-if="!row.is_default" size="small" type="danger" plain @click="deleteEmbedding(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
    <LLMConfigDialog v-model:visible="showLLMDialog" :edit-config="editingLLMConfig" @update:visible="closeLLMDialog" />
    <YOLOModelUpload v-model:visible="showYOLOUpload" />
    <EmbeddingConfigDialog v-model:visible="showEmbeddingDialog" :edit-config="editingEmbeddingConfig" @update:visible="closeEmbeddingDialog" />
  </LayoutShell>
</template>
