<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { ElMessage, ElDialog } from 'element-plus'
import { knowledgeBaseApi } from '@/api/knowledge_base'
import type { GraphData } from '@/types/knowledge_base'
import { Refresh, Aim } from '@element-plus/icons-vue'
import * as d3 from 'd3'

const props = defineProps<{ kbId: number }>()

const loading = ref(false)
const extracting = ref(false)
const graph = ref<GraphData>({ nodes: [], edges: [] })
const containerRef = ref<HTMLDivElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)

// Node click detail
const showChunkDialog = ref(false)
const selectedEntity = ref('')
const chunkLoading = ref(false)
const entityChunks = ref<any[]>([])

const entityColors: Record<string, string> = {
  person: '#EF4444', organization: '#F59E0B', location: '#10B981',
  concept: '#3B82F6', technology: '#8B5CF6', event: '#EC4899',
}
const entityColorsLight: Record<string, string> = {
  person: '#FEE2E2', organization: '#FEF3C7', location: '#D1FAE5',
  concept: '#DBEAFE', technology: '#EDE9FE', event: '#FCE7F3',
}

let simulation: d3.Simulation<d3.SimulationNodeDatum, undefined> | null = null

async function loadGraph() {
  loading.value = true
  try {
    const res = await knowledgeBaseApi.getGraph(props.kbId)
    graph.value = res.data.data
    await nextTick()
    if (graph.value.nodes.length) renderGraph()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '加载图谱失败')
  } finally { loading.value = false }
}

async function extractGraph() {
  extracting.value = true
  try {
    const res = await knowledgeBaseApi.extractGraph(props.kbId)
    const d = res.data.data
    ElMessage.success(`提取完成：${d.entities_added} 个实体，${d.relations_added} 条关系`)
    await loadGraph()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '提取失败')
  } finally { extracting.value = false }
}

function renderGraph() {
  if (!svgRef.value || !containerRef.value) return

  const svg = d3.select(svgRef.value)
  svg.selectAll('*').remove()

  const width = containerRef.value.clientWidth || 700
  const height = 480

  svg.attr('viewBox', `0 0 ${width} ${height}`)

  // Build nodes/links
  const nodeMap = new Map(graph.value.nodes.map(n => [n.id, n]))
  const nodes: any[] = graph.value.nodes.map(n => ({ ...n, x: width / 2 + (Math.random() - 0.5) * 200, y: height / 2 + (Math.random() - 0.5) * 150 }))
  const links = graph.value.edges
    .filter(e => nodeMap.has(e.source) && nodeMap.has(e.target))
    .map(e => ({ source: e.source, target: e.target, type: e.type }))

  // Zoom behavior
  const g = svg.append('g')
  const zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.3, 4])
    .on('zoom', (event) => { g.attr('transform', event.transform) })
  svg.call(zoom)

  // Arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 20).attr('refY', 0)
    .attr('markerWidth', 6).attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-4L8,0L0,4')
    .attr('fill', '#CBD5E1')

  // Links
  const link = g.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', '#CBD5E1')
    .attr('stroke-width', 1.5)
    .attr('marker-end', 'url(#arrowhead)')

  // Link labels
  const linkLabel = g.append('g')
    .selectAll('text')
    .data(links)
    .join('text')
    .text(d => d.type)
    .attr('fill', '#9CA3AF')
    .attr('font-size', '9')
    .attr('text-anchor', 'middle')
    .attr('dy', -4)

  // Nodes
  const node = g.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'cursor-pointer')
    .call(d3.drag<SVGGElement, any>()
      .on('start', (event, d) => {
        if (!event.active) simulation?.alphaTarget(0.3).restart()
        d.fx = d.x; d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x; d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation?.alphaTarget(0)
        d.fx = null; d.fy = null
      }) as any)

  // Node circles
  node.append('circle')
    .attr('r', d => Math.min(Math.max(d.name.length * 1.5 + 6, 11), 28))
    .attr('fill', d => entityColors[d.type] || '#6B7280')
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)
    .attr('filter', 'url(#shadow)')

  // Glow shadow
  svg.select('defs').append('filter')
    .attr('id', 'shadow')
    .append('feDropShadow')
    .attr('dx', 0).attr('dy', 1)
    .attr('stdDeviation', 2)
    .attr('flood-opacity', 0.2)

  // Node labels
  node.append('text')
    .text(d => d.name.length > 10 ? d.name.slice(0, 9) + '…' : d.name)
    .attr('text-anchor', 'middle')
    .attr('dy', d => (d.name.length * 1.5 + 6) + 14)
    .attr('fill', '#374151')
    .attr('font-size', '10')
    .attr('font-weight', '500')

  // Node titles (tooltip)
  node.append('title')
    .text(d => `${d.name}\n类型: ${d.type}\n${d.description || ''}`)

  // Node hover effect
  node.on('mouseenter', function () {
    d3.select(this).select('circle')
      .transition().duration(200)
      .attr('stroke', '#3B82F6').attr('stroke-width', 3)
  })
  node.on('mouseleave', function () {
    d3.select(this).select('circle')
      .transition().duration(200)
      .attr('stroke', '#fff').attr('stroke-width', 2)
  })
  // Node click → show related chunks
  node.on('click', function (event: MouseEvent, d: any) {
    event.stopPropagation()
    showEntityChunks(d.id, d.name)
  })

  // Force simulation
  simulation?.stop()
  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id((d: any) => d.id).distance(120))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(30))
    .on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)

      linkLabel
        .attr('x', (d: any) => (d.source.x + d.target.x) / 2)
        .attr('y', (d: any) => (d.source.y + d.target.y) / 2)

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
    })

  // Initial zoom to fit
  svg.call(zoom.transform as any, d3.zoomIdentity.translate(20, 20).scale(0.9))
}

function resetZoom() {
  if (!svgRef.value) return
  d3.select(svgRef.value).transition().duration(400)
    .call((d3.zoom() as any).transform, d3.zoomIdentity.translate(20, 20).scale(0.9))
}

async function showEntityChunks(entityId: number, entityName: string) {
  selectedEntity.value = entityName
  showChunkDialog.value = true
  chunkLoading.value = true
  entityChunks.value = []
  try {
    const res = await knowledgeBaseApi.getEntityChunks(props.kbId, entityId)
    entityChunks.value = res.data.data.chunks || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message || '加载相关片段失败')
  } finally { chunkLoading.value = false }
}

watch(() => props.kbId, async (id) => { if (id) await loadGraph() })
onMounted(async () => { if (props.kbId) await loadGraph() })
</script>

<template>
  <div class="bg-white rounded-lg shadow-sm border border-gray-100 mt-4">
    <div class="px-4 py-3 border-b flex items-center justify-between">
      <h3 class="text-sm font-semibold text-gray-700">知识图谱</h3>
      <div class="flex items-center gap-2">
        <el-button size="small" text :icon="ZoomIn" @click="resetZoom" />
        <el-button size="small" :icon="Refresh" :loading="loading" @click="loadGraph">刷新</el-button>
        <el-button size="small" type="primary" :icon="Aim" :loading="extracting" @click="extractGraph">提取图谱</el-button>
      </div>
    </div>

    <div ref="containerRef" class="relative">
      <div v-if="!graph.nodes.length && !loading" class="text-center py-16 text-gray-400 text-sm">
        暂无知识图谱数据，点击「提取图谱」从文档中自动构建
      </div>
      <div v-else-if="loading" class="text-center py-16 text-gray-400 text-sm">加载中...</div>
      <svg ref="svgRef" class="w-full cursor-grab active:cursor-grabbing" style="height: 480px"></svg>
    </div>

    <!-- Legend -->
    <div v-if="graph.nodes.length" class="px-4 py-2 border-t bg-gray-50 flex items-center gap-4 text-xs">
      <span class="text-gray-500 font-medium">图例:</span>
      <span v-for="(color, type) in entityColors" :key="type" class="flex items-center gap-1">
        <span class="inline-block w-2.5 h-2.5 rounded-full" :style="{ background: color }"></span>
        {{ { person: '人物', organization: '组织', location: '地点', concept: '概念', technology: '技术', event: '事件' }[type] }}
      </span>
      <span class="text-gray-300 mx-1">|</span>
      <span class="text-gray-400">点击节点查看相关文档片段</span>
    </div>

    <!-- Entity Chunks Dialog -->
    <el-dialog v-model="showChunkDialog" :title="`相关段落 - ${selectedEntity}`" width="640px" top="8vh">
      <div v-if="chunkLoading" class="text-center py-8 text-gray-400">加载中...</div>
      <div v-else-if="!entityChunks.length" class="text-center py-8 text-gray-400">暂无相关文本段落</div>
      <div v-else class="space-y-3 max-h-96 overflow-y-auto pr-1">
        <div v-for="(chunk, i) in entityChunks" :key="i" class="bg-gray-50 rounded-lg p-3 text-sm text-gray-700 leading-relaxed border border-gray-100">
          <div class="text-xs text-gray-400 mb-1 flex items-center gap-2">
            <span class="font-medium text-blue-500">#{{ i + 1 }}</span>
            <span v-if="chunk.metadata?.filename" class="truncate">{{ chunk.metadata.filename }}</span>
            <span v-if="chunk.distance" class="ml-auto">相似度: {{ (1 - chunk.distance).toFixed(2) }}</span>
          </div>
          <div class="whitespace-pre-wrap">{{ chunk.content }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showChunkDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>
