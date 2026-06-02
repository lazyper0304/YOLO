import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { HistoryItem, HistoryDetail } from '@/types/detection'
import { historyApi } from '@/api/history'

export const useHistoryStore = defineStore('history', () => {
  const records = ref<HistoryItem[]>([])
  const total = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(20)
  const isLoading = ref(false)
  const selectedRecord = ref<HistoryDetail | null>(null)
  const filterMode = ref<string | null>(null)
  const filterSourceType = ref<string | null>(null)

  async function fetchHistory(page: number = 1) {
    isLoading.value = true
    currentPage.value = page
    try {
      const res = await historyApi.list({
        page,
        page_size: pageSize.value,
        mode: filterMode.value || undefined,
        source_type: filterSourceType.value || undefined,
      })
      const data = res.data.data
      total.value = data.total
      records.value = data.items
    } finally {
      isLoading.value = false
    }
  }

  async function fetchDetail(id: number) {
    const res = await historyApi.getDetail(id)
    selectedRecord.value = res.data.data as HistoryDetail
    return selectedRecord.value
  }

  function setFilter(mode: string | null, sourceType: string | null) {
    filterMode.value = mode
    filterSourceType.value = sourceType
  }

  function clearFilters() {
    filterMode.value = null
    filterSourceType.value = null
  }

  return {
    records,
    total,
    currentPage,
    pageSize,
    isLoading,
    selectedRecord,
    filterMode,
    filterSourceType,
    fetchHistory,
    fetchDetail,
    setFilter,
    clearFilters,
  }
})
