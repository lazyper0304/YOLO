<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useHistoryStore } from '@/stores/history'
import { Loading, Picture, ArrowRight } from '@element-plus/icons-vue'
import { LayoutShell } from '@/components'
import type { DetectionMode, SourceType } from '@/types/detection'

const router = useRouter()
const authStore = useAuthStore()
const historyStore = useHistoryStore()

const modeFilter = ref<DetectionMode | ''>('')
const sourceTypeFilter = ref<SourceType | ''>('')

onMounted(async () => {
  if (!authStore.user) {
    await authStore.fetchUser()
  }
  await historyStore.fetchRecords(1)
})

async function handlePageChange(page: number) {
  await historyStore.fetchRecords(page, modeFilter.value || undefined, sourceTypeFilter.value || undefined)
}

async function handleFilterChange() {
  await historyStore.fetchRecords(1, modeFilter.value || undefined, sourceTypeFilter.value || undefined)
}

function viewDetail(id: number) {
  router.push(`/history/${id}`)
}

function modeTagType(mode: string) {
  if (mode === 'yolo_only') return ''
  if (mode === 'llm_only') return 'success'
  return 'warning'
}

function modeLabel(mode: string) {
  if (mode === 'yolo_only') return 'YOLO'
  if (mode === 'llm_only') return 'LLM'
  return '协同'
}
</script>

<template>
  <LayoutShell>
    <div class="p-8">
          <h2 class="text-2xl font-bold mb-6">历史记录</h2>

          <!-- Filters -->
          <div class="bg-white rounded-lg shadow p-4 mb-6 flex items-center gap-4">
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-600">检测模式：</span>
              <el-select v-model="modeFilter" placeholder="全部" clearable size="small" style="width: 140px" @change="handleFilterChange">
                <el-option label="YOLO" value="yolo_only" />
                <el-option label="LLM" value="llm_only" />
                <el-option label="协同" value="collaborative" />
              </el-select>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-600">来源类型：</span>
              <el-select v-model="sourceTypeFilter" placeholder="全部" clearable size="small" style="width: 140px" @change="handleFilterChange">
                <el-option label="图片" value="image" />
                <el-option label="视频" value="video" />
                <el-option label="摄像头" value="camera" />
              </el-select>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="historyStore.isLoading" class="flex justify-center py-12">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          </div>

          <!-- Empty -->
          <div v-else-if="historyStore.records.length === 0" class="bg-white rounded-lg shadow p-12 text-center">
            <el-empty description="暂无检测记录" />
          </div>

          <!-- Records -->
          <div v-else class="space-y-4">
            <div
              v-for="record in historyStore.records" :key="record.id"
              class="bg-white rounded-lg shadow p-4 cursor-pointer hover:shadow-md transition-shadow"
              @click="viewDetail(record.id)"
            >
              <div class="flex items-start gap-4">
                <div class="w-24 h-24 bg-gray-100 rounded flex-shrink-0 flex items-center justify-center overflow-hidden">
                  <img v-if="record.thumbnail_path" :src="record.thumbnail_path" class="w-full h-full object-cover" />
                  <el-icon v-else :size="32" class="text-gray-400"><Picture /></el-icon>
                </div>

                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-2">
                    <el-tag :type="modeTagType(record.mode)" size="small">{{ modeLabel(record.mode) }}</el-tag>
                    <el-tag type="info" size="small">{{ record.source_type }}</el-tag>
                    <span class="text-xs text-gray-400">{{ record.created_at }}</span>
                  </div>
                  <p class="text-sm text-gray-600 truncate">{{ record.source_path }}</p>
                  <div v-if="record.result_json?.bboxes?.length" class="mt-2 flex flex-wrap gap-1">
                    <el-tag v-for="(bbox, idx) in record.result_json.bboxes.slice(0, 5)" :key="idx" size="small" type="success">
                      {{ bbox.class_name }} {{ (bbox.confidence * 100).toFixed(0) }}%
                    </el-tag>
                    <span v-if="record.result_json.bboxes.length > 5" class="text-xs text-gray-400">
                      +{{ record.result_json.bboxes.length - 5 }} 更多
                    </span>
                  </div>
                </div>

                <div class="flex items-center text-gray-300">
                  <el-icon><ArrowRight /></el-icon>
                </div>
              </div>
            </div>
          </div>

          <!-- Pagination -->
          <div v-if="historyStore.total > historyStore.pageSize" class="flex justify-center mt-6">
            <el-pagination
              :current-page="historyStore.currentPage"
              :page-size="historyStore.pageSize"
              :total="historyStore.total"
              layout="prev, pager, next"
              @current-change="handlePageChange"
            />
          </div>
        </div>
  </LayoutShell>
</template>
