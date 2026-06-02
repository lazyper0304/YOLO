<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftSidebar from '@/components/layout/LeftSidebar.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import { useConfigStore } from '@/stores/config'
import client from '@/api/client'
import { Promotion } from '@element-plus/icons-vue'

const configStore = useConfigStore()

interface Message {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
}

interface TaskOption {
  id: number; label: string; mode: string
}

const tasks = ref<TaskOption[]>([])
const selectedTaskId = ref<number | null>(null)
const selectedLLMId = ref<number | null>(null)
const question = ref('')
const messages = ref<Message[]>([])
const streaming = ref(false)
const currentStream = ref('')
const reasoningStream = ref('')
const reasoningExpanded = ref(true)
const chatRef = ref<HTMLElement | null>(null)

const token = () => localStorage.getItem('access_token') || ''

onMounted(async () => {
  await configStore.fetchLLMConfigs()
  try {
    const res = await client.get('/api/tasks', { params: { page_size: 100 } })
    tasks.value = (res.data.data?.items || [])
      .filter((t: any) => t.status === 'completed')
      .map((t: any) => ({
        id: t.id,
        label: (t.task_name ? t.task_name + ' ' : '') + `#${t.id} ${t.mode === 'yolo_only' ? 'YOLO' : t.mode === 'llm_only' ? 'LLM' : '协同'}`,
        mode: t.mode,
      }))
  } catch { /* ignore */ }
})

// Load history from Redis when task selection changes
watch(selectedTaskId, async (newId) => {
  messages.value = []
  if (!newId) return
  try {
    const res = await fetch(`/api/chat/history?task_id=${newId}&token=${token()}`)
    const data = await res.json()
    if (data.code === 200 && data.data?.messages) {
      messages.value = data.data.messages
    }
  } catch { /* ignore */ }
})

// Save full message list to Redis
async function saveHistory() {
  if (!selectedTaskId.value || messages.value.length === 0) return
  try {
    await fetch(`/api/chat/history?token=${token()}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: selectedTaskId.value,
        messages: messages.value.map(m => ({
          role: m.role,
          content: m.content,
          reasoning: m.reasoning || null,
        })),
      }),
    })
  } catch { /* ignore - non-critical */ }
}

function send() {
  if (!question.value.trim() || !selectedTaskId.value || streaming.value) return
  const q = question.value.trim()
  question.value = ''
  messages.value.push({ role: 'user', content: q })
  saveHistory()
  streaming.value = true
  currentStream.value = ''
  reasoningStream.value = ''
  reasoningExpanded.value = true
  startStream(q)
}

function startStream(q: string) {
  const params = new URLSearchParams({
    task_id: String(selectedTaskId.value),
    question: q,
    token: token(),
  })
  if (selectedLLMId.value) params.set('llm_config_id', String(selectedLLMId.value))

  const url = '/api/chat/stream?' + params.toString()
  const evtSource = new EventSource(url)

  // Reasoning event: thinking process stream
  evtSource.addEventListener('reasoning', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.content) {
        reasoningStream.value += data.content
      }
      if (data.done) {
        // reasoning phase complete
      }
    } catch { /* ignore malformed */ }
  })

  // Message event: final answer stream
  evtSource.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.error) {
        currentStream.value = '错误: ' + data.content
        streaming.value = false
        finalizeMessage()
        evtSource.close()
        return
      }
      if (data.content) {
        currentStream.value += data.content
      }
      if (data.done) {
        streaming.value = false
        finalizeMessage(data.full_reasoning)
        evtSource.close()
      }
    } catch {
      streaming.value = false
      finalizeMessage()
      evtSource.close()
    }
  })

  evtSource.onerror = () => {
    streaming.value = false
    if (!currentStream.value) currentStream.value = '连接失败，请重试'
    finalizeMessage()
    evtSource.close()
  }
}

function finalizeMessage(reasoning?: string) {
  if (currentStream.value || reasoning) {
    messages.value.push({
      role: 'assistant',
      content: currentStream.value,
      reasoning: reasoning || reasoningStream.value || undefined,
    })
    currentStream.value = ''
    reasoningStream.value = ''
    saveHistory()
  }
  scrollBottom()
}

async function scrollBottom() {
  await nextTick()
  if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 flex flex-col overflow-hidden bg-gray-50">
        <div class="p-4 border-b bg-white flex items-center gap-3 flex-shrink-0">
          <h2 class="text-lg font-bold">智能问答</h2>
          <el-select v-model="selectedTaskId" placeholder="选择已完成的任务" size="small" style="width: 280px" filterable>
            <el-option v-for="t in tasks" :key="t.id" :label="t.label" :value="t.id" />
          </el-select>
          <el-select v-model="selectedLLMId" placeholder="对话模型(默认启用)" size="small" style="width: 180px" clearable filterable>
            <el-option v-for="c in configStore.llmConfigs" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </div>

        <div ref="chatRef" class="flex-1 overflow-y-auto p-6">
          <div v-if="messages.length === 0 && !streaming" class="text-center text-gray-400 mt-20">
            <el-icon :size="48"><Promotion /></el-icon>
            <p class="mt-2 text-sm">选择一个任务，开始提问</p>
          </div>

          <div class="max-w-3xl mx-auto space-y-4">
            <div v-for="(msg, i) in messages" :key="i" :class="msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'">
              <div :class="msg.role === 'user'
                ? 'bg-blue-500 text-white rounded-lg rounded-tr-none px-4 py-2 max-w-[80%]'
                : 'bg-white shadow rounded-lg rounded-tl-none px-4 py-2 max-w-[80%]'">
                <div class="text-xs mb-1" :class="msg.role === 'user' ? 'text-blue-100' : 'text-gray-400'">
                  {{ msg.role === 'user' ? '我' : 'AI助手' }}
                </div>
                <!-- Reasoning (collapsible) -->
                <div v-if="msg.reasoning" class="mb-2 border border-gray-200 rounded-md overflow-hidden">
                  <button
                    class="w-full flex items-center gap-1 px-2 py-1 text-xs text-gray-500 bg-gray-50 hover:bg-gray-100 transition-colors"
                    @click="msg.reasoningExpanded = !msg.reasoningExpanded"
                  >
                    <span class="transform transition-transform duration-200" :class="msg.reasoningExpanded !== false ? 'rotate-90' : ''">&#9654;</span>
                    思考过程
                  </button>
                  <div v-show="msg.reasoningExpanded !== false" class="px-3 py-2 text-xs text-gray-500 whitespace-pre-wrap border-t border-gray-100 bg-gray-50/50">
                    {{ msg.reasoning }}
                  </div>
                </div>
                <div class="text-sm">
                  <MarkdownRenderer :content="msg.content" v-if="msg.role === 'assistant'" />
                  <div class="whitespace-pre-wrap" v-else>{{ msg.content }}</div>
                </div>
              </div>
            </div>

            <!-- Streaming bubble -->
            <div v-if="streaming" class="flex justify-start">
              <div class="bg-white shadow rounded-lg rounded-tl-none px-4 py-2 max-w-[80%]">
                <div class="text-xs text-gray-400 mb-1">AI助手</div>
                <!-- Streaming reasoning -->
                <div v-if="reasoningStream" class="mb-2 border border-orange-200 rounded-md overflow-hidden">
                  <button
                    class="w-full flex items-center gap-1 px-2 py-1 text-xs text-orange-600 bg-orange-50"
                    @click="reasoningExpanded = !reasoningExpanded"
                  >
                    <span class="transform transition-transform duration-200" :class="reasoningExpanded ? 'rotate-90' : ''">&#9654;</span>
                    思考中...
                  </button>
                  <div v-show="reasoningExpanded" class="px-3 py-2 text-xs text-gray-500 whitespace-pre-wrap border-t border-orange-100 bg-orange-50/30">
                    {{ reasoningStream }}<span class="inline-block w-1 h-3 bg-orange-400 ml-0.5 animate-pulse align-middle" />
                  </div>
                </div>
                <!-- Streaming answer -->
                <div v-if="!reasoningStream || currentStream" class="text-sm">
                  <MarkdownRenderer v-if="currentStream" :content="currentStream" :is-streaming="true" />
                  <span v-else>思考中...<span class="inline-block w-1 h-4 bg-gray-400 ml-0.5 animate-pulse" /></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="p-4 bg-white border-t flex-shrink-0">
          <div class="max-w-3xl mx-auto flex gap-2">
            <el-input
              v-model="question"
              placeholder="输入问题，回车发送..."
              :disabled="!selectedTaskId || streaming"
              @keydown="handleKeydown"
              size="large"
            />
            <el-button type="primary" :disabled="!selectedTaskId || !question.trim() || streaming" @click="send" size="large">
              发送
            </el-button>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
