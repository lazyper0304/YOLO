<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftSidebar from '@/components/layout/LeftSidebar.vue'
import { useConfigStore } from '@/stores/config'
import LLMConfigDialog from '@/components/config/LLMConfigDialog.vue'
import YOLOModelUpload from '@/components/config/YOLOModelUpload.vue'
import type { LLMConfig, LLMConfigForm } from '@/types/config'

const configStore = useConfigStore()
const showLLMDialog = ref(false)
const showYOLOUpload = ref(false)

onMounted(async () => {
  await Promise.all([configStore.fetchYOLOModels(), configStore.fetchLLMConfigs()])
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

async function testLLM(id: number) {
  const result = await configStore.testLLMConfig(id)
  if (result.success) ElMessage.success('连接成功 ' + result.response_time_ms.toFixed(0) + 'ms')
  else ElMessage.error(result.message)
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 overflow-auto bg-gray-50">
        <div class="max-w-5xl mx-auto p-8 space-y-8">
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
              <el-button type="primary" size="small" :disabled="configStore.isLoadingLLM" :loading="configStore.isLoadingLLM" @click="showLLMDialog = true">{{ configStore.isLoadingLLM ? '加载中...' : '添加配置' }}</el-button>
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
              <el-table-column label="操作" width="160">
                <template #default="{ row }">
                  <el-button size="small" @click="testLLM(row.id)">测试</el-button>
                  <el-button size="small" type="danger" plain @click="deleteLLM(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </main>
    </div>
    <LLMConfigDialog v-model:visible="showLLMDialog" />
    <YOLOModelUpload v-model:visible="showYOLOUpload" />
  </div>
</template>
