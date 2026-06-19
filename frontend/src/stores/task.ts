import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchTasks, getTask, createTask, deleteTask, pauseTask, resumeTask, batchDeleteTasks,
  type TaskItem, type TaskListData,
} from '@/api/tasks'

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<TaskItem[]>([])
  const currentTask = ref<TaskItem | null>(null)
  const total = ref(0)
  const loading = ref(false)

  async function loadTasks(params?: { page?: number; page_size?: number; status?: string }) {
    loading.value = true
    try {
      const data: TaskListData = await fetchTasks(params)
      tasks.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  async function loadTask(id: number) {
    currentTask.value = await getTask(id)
    return currentTask.value
  }

  async function submitTask(form: FormData) {
    const task = await createTask(form)
    return task
  }

  async function removeTask(id: number) {
    await deleteTask(id)
    tasks.value = tasks.value.filter(t => t.id !== id)
    total.value -= 1
  }

  async function removeTasks(ids: number[]) {
    await batchDeleteTasks(ids)
  }

  async function togglePause(id: number) {
    const task = tasks.value.find(t => t.id === id)
    if (!task) return
    if (task.status === 'running') {
      await pauseTask(id)
    } else if (task.status === 'paused') {
      await resumeTask(id)
    }
    await loadTasks()
  }

  function clearCurrent() {
    currentTask.value = null
  }

  return {
    tasks, currentTask, total, loading,
    loadTasks, loadTask, submitTask, removeTask, removeTasks, togglePause, clearCurrent,
  }
})
