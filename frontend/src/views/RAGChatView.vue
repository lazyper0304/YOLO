<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, ChatDotRound } from '@element-plus/icons-vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import { LayoutShell } from '@/components'
import { useConfigStore } from '@/stores/config'
import { useKnowledgeBaseStore } from '@/stores/knowledge_base'
import { knowledgeBaseApi } from '@/api/knowledge_base'
import type { RAGSessionResponse, HistoryMessage } from '@/types/knowledge_base'
import { Promotion } from '@element-plus/icons-vue'

const configStore = useConfigStore()
const kbStore = useKnowledgeBaseStore()

interface Message {
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  reasoningExpanded?: boolean
}

const selectedKBIds = ref<number[]>([])
const selectedLLMId = ref<number | null>(null)
const question = ref('')
const messages = ref<Message[]>([])
const streaming = ref(false)
const currentStream = ref('')
const reasoningStream = ref('')
const reasoningExpanded = ref(true)
const chatRef = ref<HTMLElement | null>(null)

// ─── Session state ────────────────────────────────────────────────
const sessions = ref<RAGSessionResponse[]>([])
const activeSessionId = ref<string | null>(null)
const sessionsLoading = ref(false)

const token = () => localStorage.getItem('access_token') || ''

onMounted(async () => {
  await configStore.fetchLLMConfigs()
  await kbStore.fetchKnowledgeBases()
})

// ─── Session management ───────────────────────────────────────────

/** Determine the primary KB ID for session scoping (first selected) */
function primaryKBId(): number | null {
  return selectedKBIds.value.length > 0 ? selectedKBIds.value[0] : null
}

async function loadSessions() {
  const kbId = primaryKBId()
  if (!kbId) return
  sessionsLoading.value = true
  try {
    const res = await knowledgeBaseApi.getRAGSessions(kbId)
    sessions.value = res.data.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '加载会话列表失败')
  } finally {
    sessionsLoading.value = false
  }
}

async function createSession() {
  const kbId = primaryKBId()
  if (!kbId) {
    ElMessage.warning('请先选择知识库')
    return
  }
  try {
    const res = await knowledgeBaseApi.createRAGSession(kbId, '新的对话')
    const session = res.data.data
    sessions.value.unshift(session)
    switchSession(session.session_id)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '创建会话失败')
  }
}

async function switchSession(sessionId: string) {
  activeSessionId.value = sessionId
  messages.value = []
  const kbId = primaryKBId()
  if (!kbId) return

  try {
    const res = await knowledgeBaseApi.getRAGHistory(kbId, sessionId)
    const history: HistoryMessage[] = res.data.data.messages || []
    messages.value = history.map((m) => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
      reasoning: m.reasoning || undefined,
      reasoningExpanded: false,
    }))
    await scrollBottom()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '加载历史消息失败')
  }
}

async function deleteSession(sessionId: string) {
  const kbId = primaryKBId()
  if (!kbId) return
  try {
    await ElMessageBox.confirm('确定删除此会话？对话历史将被永久删除。', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await knowledgeBaseApi.deleteRAGSession(kbId, sessionId)
    sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null
      messages.value = []
    }
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e.response?.data?.message || '删除会话失败')
    }
  }
}

/** Watch selected KBs change → reload sessions */
watch(
  () => selectedKBIds.value,
  async (newIds, oldIds) => {
    const newPrimary = newIds.length > 0 ? newIds[0] : null
    const oldPrimary = oldIds.length > 0 ? oldIds[0] : null
    if (newPrimary !== oldPrimary) {
      activeSessionId.value = null
      messages.value = []
      sessions.value = []
      if (newPrimary) {
        await loadSessions()
      }
    }
  },
  { deep: true }
)

// ─── Chat logic ───────────────────────────────────────────────────

function send() {
  if (!question.value.trim() || selectedKBIds.value.length === 0 || streaming.value) return
  const q = question.value.trim()
  question.value = ''
  messages.value.push({ role: 'user', content: q })
  streaming.value = true
  currentStream.value = ''
  reasoningStream.value = ''
  reasoningExpanded.value = true
  startStream(q)
}

function startStream(q: string) {
  const params = new URLSearchParams({
    question: q,
    token: token(),
    kb_ids: selectedKBIds.value.join(','),
  })
  if (selectedLLMId.value) params.set('llm_config_id', String(selectedLLMId.value))

  const url = '/api/knowledge-bases/ask?' + params.toString()
  const evtSource = new EventSource(url)

  evtSource.addEventListener('reasoning', (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.content) {
        reasoningStream.value += data.content
      }
    } catch { /* ignore */ }
  })

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
    // Save to backend
    saveHistoryToBackend()
  }
  scrollBottom()
}

async function saveHistoryToBackend() {
  const kbId = primaryKBId()
  const sessionId = activeSessionId.value
  if (!kbId || !sessionId) return

  // Collect the last user-assistant pair
  const allMsgs = messages.value
  const toSave: HistoryMessage[] = []
  for (const msg of allMsgs) {
    toSave.push({
      role: msg.role,
      content: msg.content,
      reasoning: msg.reasoning || null,
    })
  }

  // Only save the last 2 messages (user + assistant) if they exist
  const lastTwo = toSave.slice(-2)
  if (lastTwo.length === 0) return

  try {
    await knowledgeBaseApi.saveRAGHistory(kbId, sessionId, lastTwo)
    // Update session message count in local list
    const sess = sessions.value.find((s) => s.session_id === sessionId)
    if (sess) {
      sess.message_count += lastTwo.length
    }
  } catch (e: any) {
    // Silently fail — history save is non-critical
    console.warn('Failed to save RAG history:', e)
  }
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

async function clearChat() {
  const kbId = primaryKBId()
  const sessionId = activeSessionId.value
  if (kbId && sessionId) {
    try {
      await knowledgeBaseApi.clearRAGHistory(kbId, sessionId)
      const sess = sessions.value.find((s) => s.session_id === sessionId)
      if (sess) sess.message_count = 0
    } catch { /* ignore */ }
  }
  messages.value = []
}
</script>

<template>
  <LayoutShell>
    <div class="flex h-[calc(100vh-64px)]">
      <!-- Session Sidebar -->
      <div class="w-64 bg-white border-r flex flex-col shrink-0">
        <div class="p-3 border-b">
          <el-button type="primary" size="small" :icon="Plus" class="w-full" @click="createSession">
            新对话
          </el-button>
        </div>
        <div class="flex-1 overflow-auto">
          <div v-if="!primaryKBId()" class="p-4 text-center text-gray-400 text-sm">
            请先在上方选择知识库
          </div>
          <div v-else-if="sessionsLoading" class="p-4 text-center text-gray-400 text-sm">
            加载中...
          </div>
          <div v-else-if="sessions.length === 0" class="p-4 text-center text-gray-400 text-sm">
            暂无会话，点击"新对话"开始
          </div>
          <div v-else class="divide-y">
            <div
              v-for="session in sessions"
              :key="session.session_id"
              class="p-3 cursor-pointer hover:bg-gray-50 transition-colors group"
              :class="{ 'bg-blue-50 border-l-2 border-blue-500': activeSessionId === session.session_id }"
              @click="switchSession(session.session_id)"
            >
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2 min-w-0">
                  <ChatDotRound class="text-blue-400 shrink-0" :size="16" />
                  <span class="text-sm truncate">{{ session.title }}</span>
                </div>
                <el-button
                  link
                  size="small"
                  class="opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                  @click.stop="deleteSession(session.session_id)"
                >
                  <el-icon :size="14"><Delete /></el-icon>
                </el-button>
              </div>
              <div class="text-xs text-gray-400 mt-1">
                {{ session.message_count }} 条消息
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col min-w-0">
        <!-- Header -->
        <div class="bg-white border-b p-4">
          <div class="flex items-center gap-4 flex-wrap">
            <h2 class="text-lg font-semibold shrink-0">知识库问答</h2>
            <el-select
              v-model="selectedKBIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              placeholder="选择知识库"
              style="min-width: 240px"
            >
              <el-option
                v-for="kb in kbStore.knowledgeBases"
                :key="kb.id"
                :label="kb.name"
                :value="kb.id"
              />
            </el-select>
            <el-select
              v-model="selectedLLMId"
              placeholder="选择LLM"
              clearable
              style="width: 180px"
            >
              <el-option
                v-for="c in configStore.llmConfigs"
                :key="c.id"
                :label="c.name"
                :value="c.id"
              />
            </el-select>
            <el-button size="small" @click="clearChat">清空对话</el-button>
          </div>
        </div>

        <!-- Chat Area -->
        <div ref="chatRef" class="flex-1 overflow-auto p-4 bg-gray-50">
          <div class="max-w-4xl mx-auto space-y-4">
            <!-- Empty State -->
            <div v-if="messages.length === 0 && !streaming" class="text-center py-20">
              <div class="text-gray-400 mb-4">
                <svg class="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
              </div>
              <p class="text-gray-500 text-lg">基于知识库的智能问答</p>
              <p class="text-gray-400 text-sm mt-2">选择知识库后输入问题，AI 将参考知识库内容回答</p>
            </div>

            <!-- Messages -->
            <div v-for="(msg, i) in messages" :key="i">
              <!-- User Message -->
              <div v-if="msg.role === 'user'" class="flex justify-end mb-4">
                <div class="bg-blue-500 text-white rounded-2xl rounded-br-sm px-4 py-3 max-w-[80%] shadow-sm">
                  <div class="whitespace-pre-wrap">{{ msg.content }}</div>
                </div>
              </div>

              <!-- Assistant Message -->
              <div v-else class="flex justify-start mb-4">
                <div class="bg-white rounded-2xl rounded-bl-sm shadow-sm max-w-[85%] overflow-hidden">
                  <!-- Reasoning -->
                  <div v-if="msg.reasoning" class="border-b bg-gray-50">
                    <button
                      class="w-full px-4 py-2 text-left text-sm text-gray-500 hover:bg-gray-100 flex items-center justify-between"
                      @click="msg.reasoningExpanded = !msg.reasoningExpanded"
                    >
                      <span>思考过程</span>
                      <span>{{ msg.reasoningExpanded ? '▲' : '▼' }}</span>
                    </button>
                    <div v-if="msg.reasoningExpanded" class="px-4 pb-3 text-sm text-gray-600 whitespace-pre-wrap max-h-60 overflow-auto">
                      {{ msg.reasoning }}
                    </div>
                  </div>
                  <!-- Content -->
                  <div class="px-4 py-3">
                    <MarkdownRenderer :content="msg.content" />
                  </div>
                </div>
              </div>
            </div>

            <!-- Streaming -->
            <div v-if="streaming" class="flex justify-start mb-4">
              <div class="bg-white rounded-2xl rounded-bl-sm shadow-sm max-w-[85%] overflow-hidden">
                <div v-if="reasoningStream" class="border-b bg-gray-50">
                  <button
                    class="w-full px-4 py-2 text-left text-sm text-gray-500 flex items-center justify-between"
                    @click="reasoningExpanded = !reasoningExpanded"
                  >
                    <span>思考中...</span>
                    <span>{{ reasoningExpanded ? '▲' : '▼' }}</span>
                  </button>
                  <div v-if="reasoningExpanded" class="px-4 pb-3 text-sm text-gray-600 whitespace-pre-wrap max-h-60 overflow-auto">
                    {{ reasoningStream }}
                  </div>
                </div>
                <div class="px-4 py-3">
                  <div v-if="currentStream">
                    <MarkdownRenderer :content="currentStream" />
                  </div>
                  <span v-else class="inline-block w-2 h-4 bg-gray-400 animate-pulse rounded-sm"></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Input Bar -->
        <div class="bg-white border-t p-4">
          <div class="max-w-4xl mx-auto flex gap-3">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              placeholder="输入问题..."
              resize="none"
              @keydown="handleKeydown"
            />
            <el-button
              type="primary"
              :icon="Promotion"
              :loading="streaming"
              :disabled="!question.trim() || selectedKBIds.length === 0"
              @click="send"
            >
              发送
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </LayoutShell>
</template>
