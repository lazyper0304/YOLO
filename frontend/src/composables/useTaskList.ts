import { computed } from 'vue'
import { useTaskStore } from '@/stores/task'
import { storeToRefs } from 'pinia'

export function useTaskList() {
  const store = useTaskStore()
  const { tasks, total, loading, currentTask } = storeToRefs(store)

  const runningTasks = computed(() => tasks.value.filter(t => t.status === 'running'))
  const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending'))
  const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed'))
  const failedTasks = computed(() => tasks.value.filter(t => t.status === 'failed'))

  return {
    tasks,
    total,
    loading,
    currentTask,
    runningTasks,
    pendingTasks,
    completedTasks,
    failedTasks,
    loadTasks: store.loadTasks,
    loadTask: store.loadTask,
    submitTask: store.submitTask,
    removeTask: store.removeTask,
    removeTasks: store.removeTasks,
    togglePause: store.togglePause,
    clearCurrent: store.clearCurrent,
  }
}
