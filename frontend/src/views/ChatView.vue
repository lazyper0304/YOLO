<script setup lang="ts">
import { ref, watch, nextTick, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Promotion, MagicStick, ChatDotRound, ChatLineSquare, EditPen } from '@element-plus/icons-vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import { LayoutShell } from '@/components'
import { useConfigStore } from '@/stores/config'
import { useKnowledgeBaseStore } from '@/stores/knowledge_base'
import { knowledgeBaseApi } from '@/api/knowledge_base'
import { detectionApi } from '@/api/detection'
import { fetchTasks } from '@/api/tasks'
import type { RAGSessionResponse, HistoryMessage } from '@/types/knowledge_base'

const configStore = useConfigStore()
const kbStore = useKnowledgeBaseStore()

const activeMode = ref<'qa' | 'prompt' | 'rag'>('qa')

interface Message { role: 'user' | 'assistant'; content: string; reasoning?: string; reasoningExpanded?: boolean }
interface TaskOption { id: number; label: string; mode: string }

const selectedLLMId = ref<number | null>(null)
const question = ref('')
const messages = ref<Message[]>([])
const streaming = ref(false)
const currentStream = ref('')
const reasoningStream = ref('')
const reasoningExpanded = ref(true)
const chatRef = ref<HTMLElement | null>(null)

const tasks = ref<TaskOption[]>([])
const selectedTaskId = ref<number | null>(null)
const promptRequirement = ref('')
const promptGenerating = ref(false)
const generatedPrompt = ref('')
const selectedKBIds = ref<number[]>([])
const sessions = ref<RAGSessionResponse[]>([])
const activeSessionId = ref<string | null>(null)
const sessionsLoading = ref(false)

const token = () => localStorage.getItem('access_token') || ''
const canSend = computed(() => { if (streaming.value || !question.value.trim()) return false; if (activeMode.value === 'qa') return true; if (activeMode.value === 'rag') return selectedKBIds.value.length > 0; return false })

onMounted(async () => {
  await Promise.all([configStore.fetchLLMConfigs(), kbStore.fetchKnowledgeBases()])
  try {
    const data = (await fetchTasks({ page_size: 100 })) as any
    tasks.value = (data.items || []).filter((t: any) => t.status === 'completed').map((t: any) => ({
      id: t.id, label: (t.task_name ? t.task_name + ' ' : '') + `#${t.id} ${t.mode==='yolo_only'?'YOLO':t.mode==='llm_only'?'LLM':'协同'}`, mode: t.mode,
    }))
  } catch { /* */ }
})

watch(selectedTaskId, async (id) => { messages.value = []; if (!id) return; try { const r = await fetch(`/api/chat/history?task_id=${id}&token=${token()}`); const d = await r.json(); if (d.code===0&&d.data?.messages) messages.value = d.data.messages } catch { /* */ } })

async function saveQAHistory() { if (!selectedTaskId.value || !messages.value.length) return; try { await fetch(`/api/chat/history?token=${token()}`, { method:'POST',headers:{'Content-Type':'application/json'}, body:JSON.stringify({ task_id:selectedTaskId.value, messages:messages.value.map(m=>({role:m.role,content:m.content,reasoning:m.reasoning||null})) }) }) } catch { /* */ } }

function send() { if (activeMode.value==='qa') sendQA(); else if (activeMode.value==='rag') sendRag() }

function sendQA() { if (!canSend.value) return; const q=question.value.trim(); question.value=''; messages.value.push({role:'user',content:q}); saveQAHistory(); streaming.value=true; currentStream.value=''; reasoningStream.value=''; reasoningExpanded.value=false; const p=new URLSearchParams({ question:q, token:token() }); if (selectedTaskId.value) p.set('task_id',String(selectedTaskId.value)); if (selectedLLMId.value) p.set('llm_config_id',String(selectedLLMId.value)); if (selectedKBIds.value.length) p.set('kb_ids', selectedKBIds.value.join(',')); doStream('/api/chat/stream?'+p.toString()) }

function sendRag() { if (!canSend.value) return; const q=question.value.trim(); question.value=''; messages.value.push({role:'user',content:q}); streaming.value=true; currentStream.value=''; reasoningStream.value=''; reasoningExpanded.value=false; const p=new URLSearchParams({ question:q, token:token(), kb_ids:selectedKBIds.value.join(',') }); if (selectedLLMId.value) p.set('llm_config_id',String(selectedLLMId.value)); if (activeSessionId.value) p.set('session_id',activeSessionId.value); doStream('/api/rag-chat/stream?'+p.toString()) }

function doStream(url: string) {
  const es = new EventSource(url)
  es.addEventListener('reasoning',e=>{try{const d=JSON.parse(e.data);if(d.content)reasoningStream.value+=d.content}catch{/* */}})
  es.addEventListener('message',e=>{try{const d=JSON.parse(e.data);if(d.error){currentStream.value='错误: '+d.content;streaming.value=false;commit();es.close();return}if(d.content)currentStream.value+=d.content;if(d.done){streaming.value=false;commit(d.full_reasoning);es.close()}}catch{streaming.value=false;commit();es.close()}})
  es.onerror=()=>{streaming.value=false;if(!currentStream.value)currentStream.value='连接失败，请重试';commit();es.close()}
}

function commit(reasoning?:string) { reasoningExpanded.value=false; if (currentStream.value||reasoning) { messages.value.push({role:'assistant',content:currentStream.value,reasoning:reasoning||reasoningStream.value||undefined,reasoningExpanded:false}); currentStream.value=''; reasoningStream.value=''; if(activeMode.value==='qa')saveQAHistory();else if(activeMode.value==='rag')saveRAGHistory() } nextTick(()=>{if(chatRef.value)chatRef.value.scrollTop=chatRef.value.scrollHeight}) }

function primaryKBId() { return selectedKBIds.value[0] || null }

async function loadSessions() { const kbId=primaryKBId(); if(!kbId)return; sessionsLoading.value=true; try{const r=await knowledgeBaseApi.getRAGSessions(kbId);sessions.value=r.data.data}catch{/* */}finally{sessionsLoading.value=false} }
async function createSession() { const kbId=primaryKBId(); if(!kbId){ElMessage.warning('请先选择知识库');return} try{const r=await knowledgeBaseApi.createRAGSession(kbId,'新的对话');sessions.value.unshift(r.data.data);switchSession(r.data.data.session_id)}catch(e:any){ElMessage.error(e.response?.data?.message||'创建失败')} }
async function switchSession(sid:string) { activeSessionId.value=sid;messages.value=[];await loadRAGHistory(sid);nextTick(()=>{if(chatRef.value)chatRef.value.scrollTop=chatRef.value.scrollHeight}) }
async function deleteSession(sid:string) { const kbId=primaryKBId();if(!kbId)return;try{await ElMessageBox.confirm('确定删除此会话？','确认',{confirmButtonText:'删除',cancelButtonText:'取消',type:'warning'});await knowledgeBaseApi.deleteRAGSession(kbId,sid);sessions.value=sessions.value.filter(s=>s.session_id!==sid);if(activeSessionId.value===sid){activeSessionId.value=null;messages.value=[]}}catch(e:any){if(e!=='cancel'&&e!=='close')ElMessage.error(e.response?.data?.message||'删除失败')} }
async function loadRAGHistory(sid:string) { const kbId=primaryKBId();if(!kbId)return;try{const r=await fetch(`/api/rag-chat/history?kb_id=${kbId}&session_id=${sid}&token=${token()}`);const d=await r.json();if(d.code===0&&d.data?.messages)messages.value=d.data.messages.map((m:HistoryMessage)=>({role:m.role as'user'|'assistant',content:m.content,reasoning:m.reasoning||undefined,reasoningExpanded:false}))}catch{/* */} }
async function saveRAGHistory() { const kbId=primaryKBId();const sid=activeSessionId.value;if(!kbId||!sid)return;try{await fetch(`/api/rag-chat/history?token=${token()}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kb_id:kbId,session_id:sid,messages:messages.value.map(m=>({role:m.role,content:m.content,reasoning:m.reasoning||null}))})});const s=sessions.value.find(x=>x.session_id===sid);if(s)s.message_count=messages.value.length}catch{/* */} }
async function clearRAGChat() { const kbId=primaryKBId();const sid=activeSessionId.value;if(kbId&&sid){try{await knowledgeBaseApi.clearRAGHistory(kbId,sid);const s=sessions.value.find(x=>x.session_id===sid);if(s)s.message_count=0}catch{/* */}}messages.value=[] }
watch(()=>selectedKBIds.value,async(n,o)=>{const np=n[0]||null;const op=o[0]||null;if(np!==op){activeSessionId.value=null;messages.value=[];sessions.value=[];if(np)await loadSessions()}},{deep:true})
function switchMode(m:'qa'|'prompt'|'rag') { activeMode.value=m; if(m==='prompt'){messages.value=[];promptRequirement.value='';generatedPrompt.value=''} }
async function generatePrompt() { if(!promptRequirement.value.trim()){ElMessage.warning('请描述分析需求');return} promptGenerating.value=true;generatedPrompt.value='';try{const r=await detectionApi.generatePrompt(promptRequirement.value,selectedLLMId.value,selectedKBIds.value);generatedPrompt.value=r.data.data?.prompt||'';ElMessage.success('已生成')}catch(e:any){ElMessage.error(e?.message||'生成失败')}finally{promptGenerating.value=false} }
function copyPrompt() { if(generatedPrompt.value) navigator.clipboard.writeText(generatedPrompt.value).then(()=>ElMessage.success('已复制')).catch(()=>ElMessage.warning('复制失败')) }
function modeTitle() { return ({qa:'智能问答',prompt:'生成分析提示词',rag:'知识库问答'})[activeMode.value] }
function toggleReasoning(msg:Message) { msg.reasoningExpanded = msg.reasoningExpanded===false ? true : false }
</script>

<template>
  <LayoutShell>
    <div class="h-full flex flex-col overflow-hidden">
      <!-- Compact Header -->
      <div class="px-5 py-2.5 bg-white border-b flex-shrink-0 flex items-center justify-between gap-3">
        <div class="flex items-center gap-2.5">
          <h2 class="text-sm font-bold text-gray-700">{{ modeTitle() }}</h2>
          <div class="flex bg-gray-100 rounded-lg p-0.5">
            <button v-for="m in (['qa','rag','prompt'] as const)" :key="m" @click="switchMode(m)"
              :class="activeMode===m?'bg-white shadow-sm text-blue-600 font-medium':'text-gray-500 hover:text-gray-700'"
              class="flex items-center gap-1 px-2.5 py-1 text-xs rounded-md transition-all">
              <el-icon :size="12"><component :is="m==='qa'?ChatDotRound:m==='rag'?ChatLineSquare:EditPen"/></el-icon>
              {{ m==='qa'?'问答':m==='rag'?'知识库':'提示词' }}
            </button>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <template v-if="activeMode==='qa'">
            <el-select v-model="selectedTaskId" placeholder="选择任务(可选)" size="small" style="width:170px" filterable clearable><el-option v-for="t in tasks" :key="t.id" :label="t.label" :value="t.id"/></el-select>
            <el-select v-model="selectedLLMId" placeholder="LLM" size="small" style="width:150px" clearable filterable><el-option v-for="c in configStore.llmConfigs" :key="c.id" :label="c.name" :value="c.id"/></el-select>
            <el-select v-model="selectedKBIds" multiple collapse-tags collapse-tags-tooltip placeholder="关联知识库(可选)" size="small" style="min-width:170px"><el-option v-for="kb in kbStore.knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id"/></el-select>
          </template>
          <template v-if="activeMode==='rag'">
            <el-select v-model="selectedKBIds" multiple collapse-tags collapse-tags-tooltip placeholder="知识库" size="small" style="min-width:170px"><el-option v-for="kb in kbStore.knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id"/></el-select>
            <el-select v-model="selectedLLMId" placeholder="LLM" size="small" style="width:150px" clearable filterable><el-option v-for="c in configStore.llmConfigs" :key="c.id" :label="c.name" :value="c.id"/></el-select>
            <el-button size="small" text type="danger" @click="clearRAGChat">清空</el-button>
          </template>
        </div>
      </div>

      <!-- RAG mode with session sidebar -->
      <template v-if="activeMode==='rag'">
        <div class="flex flex-1 overflow-hidden">
          <div class="w-48 bg-white border-r flex-shrink-0 flex flex-col">
            <div class="p-2 border-b"><el-button type="primary" size="small" :icon="Plus" class="w-full" @click="createSession">新对话</el-button></div>
            <div class="flex-1 overflow-auto">
              <div v-if="!primaryKBId()" class="p-4 text-center text-xs text-gray-400">请先在上方选择知识库</div>
              <div v-else-if="sessionsLoading" class="p-4 text-center text-xs text-gray-400">加载中...</div>
              <div v-else-if="!sessions.length" class="p-4 text-center text-xs text-gray-400">暂无会话</div>
              <div v-else class="py-1">
                <div v-for="s in sessions" :key="s.session_id" class="mx-1 px-2.5 py-1.5 rounded cursor-pointer hover:bg-gray-50 transition-colors group text-xs" :class="{'bg-blue-50 text-blue-700':activeSessionId===s.session_id}" @click="switchSession(s.session_id)">
                  <div class="flex items-center justify-between"><span class="truncate">{{ s.title }}</span><el-button link size="small" class="opacity-0 group-hover:opacity-100" @click.stop="deleteSession(s.session_id)"><el-icon :size="11"><Delete/></el-icon></el-button></div>
                  <div class="text-[10px] mt-0.5" :class="activeSessionId===s.session_id?'text-blue-400':'text-gray-400'">{{ s.message_count }} 条消息</div>
                </div>
              </div>
            </div>
          </div>
          <div class="flex-1 flex flex-col min-w-0 bg-gray-50">
            <!-- Chat messages -->
            <div ref="chatRef" class="flex-1 overflow-y-auto p-4">
              <div v-if="messages.length===0 && !streaming" class="flex flex-col items-center justify-center h-full text-gray-400">
                <div class="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center mb-3"><el-icon :size="28" color="#60A5FA"><ChatLineSquare/></el-icon></div>
                <p class="text-sm font-medium text-gray-500 mb-1">知识库问答</p><p class="text-xs">选择知识库后输入问题</p>
              </div>
              <div class=" space-y-4">
                <div v-for="(msg,i) in messages" :key="i" :class="msg.role==='user'?'flex justify-end':'flex justify-start'">
                  <div :class="msg.role==='user'?'bg-blue-500 text-white rounded-2xl rounded-tr-md px-4 py-2.5 max-w-[75%] shadow-sm':'bg-white rounded-2xl rounded-tl-md px-4 py-3 max-w-[75%] shadow-sm border border-gray-100'">
                    <div class="text-[11px] font-medium mb-1.5 opacity-75" :class="msg.role==='user'?'text-blue-100':'text-gray-400'">{{ msg.role==='user'?'我':'AI 助手' }}</div>
                    <div v-if="msg.reasoning" class="mb-3 border border-gray-200 rounded-lg overflow-hidden">
                      <button class="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 bg-gray-50 hover:bg-gray-100 transition-colors" @click="toggleReasoning(msg)"><span class="transform transition-transform duration-200 text-[10px]" :class="msg.reasoningExpanded!==false?'rotate-90':''">&#9654;</span>思考过程</button>
                      <div v-show="msg.reasoningExpanded!==false" class="px-3 py-2 text-xs text-gray-500 whitespace-pre-wrap border-t border-gray-100 bg-gray-50/50 leading-relaxed">{{ msg.reasoning }}</div>
                    </div>
                    <div class="text-[15px] leading-relaxed"><MarkdownRenderer :content="msg.content" v-if="msg.role==='assistant'"/><div class="whitespace-pre-wrap" v-else>{{ msg.content }}</div></div>
                  </div>
                </div>
                <!-- Streaming -->
                <div v-if="streaming" class="flex justify-start">
                  <div class="bg-white rounded-2xl rounded-tl-md px-4 py-3 max-w-[75%] shadow-sm border border-gray-100">
                    <div class="text-[11px] font-medium text-gray-400 mb-1.5 opacity-75">AI 助手</div>
                    <div v-if="reasoningStream" class="mb-3 border border-orange-200 rounded-lg overflow-hidden">
                      <button class="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-orange-600 bg-orange-50 font-medium" @click="reasoningExpanded=!reasoningExpanded"><span class="transform transition-transform duration-200 text-[10px]" :class="reasoningExpanded?'rotate-90':''">&#9654;</span>{{ currentStream?'思考过程':'思考中...' }}</button>
                      <div v-show="reasoningExpanded" class="px-3 py-2 text-xs text-gray-500 whitespace-pre-wrap border-t border-orange-100 bg-orange-50/30 leading-relaxed">{{ reasoningStream }}<span v-if="!currentStream" class="inline-block w-1.5 h-3.5 bg-orange-400 ml-0.5 animate-pulse align-middle rounded-sm"/></div>
                    </div>
                    <div class="text-[15px] leading-relaxed"><MarkdownRenderer v-if="currentStream" :content="currentStream" :is-streaming="true"/><span v-else class="text-gray-400">思考中...<span class="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 animate-pulse align-middle rounded-sm"/></span></div>
                  </div>
                </div>
              </div>
            </div>
            <!-- Input -->
            <div class="px-4 py-3 bg-white border-t flex-shrink-0"><div class="flex gap-2"><el-input v-model="question" type="textarea" :rows="2" placeholder="输入问题..." resize="none" :disabled="streaming" @keydown="(e:KeyboardEvent)=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}" class="flex-1"/><el-button type="primary" :icon="Promotion" :loading="streaming" :disabled="!canSend" @click="send" class="self-end px-5">发送</el-button></div></div>
          </div>
        </div>
      </template>

      <!-- QA mode -->
      <template v-if="activeMode==='qa'">
        <div class="flex-1 flex flex-col overflow-hidden">
          <div ref="chatRef" class="flex-1 overflow-y-auto p-5">
            <div v-if="messages.length===0 && !streaming" class="flex flex-col items-center justify-center h-full text-gray-400 -mt-8">
              <div class="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center mb-3"><el-icon :size="28" color="#60A5FA"><ChatDotRound/></el-icon></div>
              <p class="text-sm font-medium text-gray-500 mb-1">智能助手</p><p class="text-xs">选择任务可分析检测结果，不选任务可直接对话</p>
            </div>
            <div class=" space-y-4">
              <div v-for="(msg,i) in messages" :key="i" :class="msg.role==='user'?'flex justify-end':'flex justify-start'">
                <div :class="msg.role==='user'?'bg-blue-500 text-white rounded-2xl rounded-tr-md px-4 py-2.5 max-w-[75%] shadow-sm':'bg-white rounded-2xl rounded-tl-md px-4 py-3 max-w-[75%] shadow-sm border border-gray-100'">
                  <div class="text-[11px] font-medium mb-1.5 opacity-75" :class="msg.role==='user'?'text-blue-100':'text-gray-400'">{{ msg.role==='user'?'我':'AI 助手' }}</div>
                  <div v-if="msg.reasoning" class="mb-3 border border-gray-200 rounded-lg overflow-hidden">
                    <button class="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 bg-gray-50 hover:bg-gray-100 transition-colors" @click="toggleReasoning(msg)"><span class="transform transition-transform duration-200 text-[10px]" :class="msg.reasoningExpanded!==false?'rotate-90':''">&#9654;</span>思考过程</button>
                    <div v-show="msg.reasoningExpanded!==false" class="px-3 py-2 text-xs text-gray-500 whitespace-pre-wrap border-t border-gray-100 bg-gray-50/50 leading-relaxed">{{ msg.reasoning }}</div>
                  </div>
                  <div class="text-[15px] leading-relaxed"><MarkdownRenderer :content="msg.content" v-if="msg.role==='assistant'"/><div class="whitespace-pre-wrap" v-else>{{ msg.content }}</div></div>
                </div>
              </div>
              <div v-if="streaming" class="flex justify-start">
                <div class="bg-white rounded-2xl rounded-tl-md px-4 py-3 max-w-[75%] shadow-sm border border-gray-100">
                  <div class="text-[11px] font-medium text-gray-400 mb-1.5 opacity-75">AI 助手</div>
                  <div v-if="reasoningStream" class="mb-3 border border-orange-200 rounded-lg overflow-hidden">
                    <button class="w-full flex items-center gap-1.5 px-3 py-1.5 text-xs text-orange-600 bg-orange-50 font-medium" @click="reasoningExpanded=!reasoningExpanded"><span class="transform transition-transform duration-200 text-[10px]" :class="reasoningExpanded?'rotate-90':''">&#9654;</span>{{ currentStream?'思考过程':'思考中...' }}</button>
                    <div v-show="reasoningExpanded" class="px-3 py-2 text-xs text-gray-500 whitespace-pre-wrap border-t border-orange-100 bg-orange-50/30 leading-relaxed">{{ reasoningStream }}<span v-if="!currentStream" class="inline-block w-1.5 h-3.5 bg-orange-400 ml-0.5 animate-pulse align-middle rounded-sm"/></div>
                  </div>
                  <div class="text-[15px] leading-relaxed"><MarkdownRenderer v-if="currentStream" :content="currentStream" :is-streaming="true"/><span v-else class="text-gray-400">思考中...<span class="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 animate-pulse align-middle rounded-sm"/></span></div>
                </div>
              </div>
            </div>
          </div>
          <div class="px-5 py-3 bg-white border-t"><div class="flex gap-2"><el-input v-model="question" placeholder="输入问题，Enter 发送..." :disabled="streaming" @keydown="(e:KeyboardEvent)=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}" size="large" class="flex-1"/><el-button type="primary" :disabled="!canSend" @click="send" size="large" class="px-6">发送</el-button></div></div>
        </div>
      </template>

      <!-- Prompt mode -->
      <template v-if="activeMode==='prompt'">
        <div class="flex-1 overflow-y-auto p-6 bg-gray-50">
          <div class="max-w-2xl mx-auto space-y-4">
            <div class="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 rounded-xl p-4 text-sm">
              <div class="flex items-start gap-2.5">
                <div class="w-7 h-7 bg-blue-100 rounded-lg flex items-center justify-center shrink-0"><el-icon :size="14" class="text-blue-500"><Promotion/></el-icon></div>
                <div><p class="font-medium text-blue-800 mb-0.5">提示词生成器</p><p class="text-blue-600/70 text-xs">描述分析需求，AI 生成结构化提示词。粘贴到任务创建对话框用于视频逐帧 LLM 分析。</p></div>
              </div>
            </div>
            <div class="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
              <label class="text-sm font-semibold text-gray-700">分析需求描述</label>
              <el-input v-model="promptRequirement" type="textarea" :rows="4" placeholder="例如：分析停车场监控视频，统计每帧中出现的车辆数量和颜色，识别车牌颜色..." size="large"/>
              <div class="flex items-center gap-2">
                <el-button type="primary" :icon="MagicStick" :loading="promptGenerating" @click="generatePrompt" :disabled="!promptRequirement.trim()">{{ promptGenerating?'生成中...':'生成提示词' }}</el-button>
                <el-select v-model="selectedLLMId" placeholder="LLM（可选）" size="small" style="width:150px" clearable><el-option v-for="c in configStore.llmConfigs" :key="c.id" :label="c.name" :value="c.id"/></el-select>
                <el-select v-model="selectedKBIds" multiple collapse-tags collapse-tags-tooltip placeholder="参考知识库" size="small" style="width:150px" clearable><el-option v-for="kb in kbStore.knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id"/></el-select>
              </div>
            </div>
            <div v-if="generatedPrompt" class="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
              <div class="flex items-center justify-between"><label class="text-sm font-semibold text-gray-700">生成的提示词</label><el-button type="primary" size="small" plain @click="copyPrompt">复制</el-button></div>
              <div class="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap leading-relaxed border">{{ generatedPrompt }}</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </LayoutShell>
</template>
