<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useDetectionStore } from '@/stores/detection'
import type { BBox } from '@/types/api'

const detectionStore = useDetectionStore()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)

const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const imageLoaded = ref(false)
const image = ref<HTMLImageElement | null>(null)
const canvasWidth = ref(800)
const canvasHeight = ref(600)

let resizeObserver: ResizeObserver | null = null

const displayImageSrc = computed(() => {
  if (detectionStore.uploadedFileUrl) {
    return detectionStore.uploadedFileUrl
  }
  return null
})

watch(displayImageSrc, (src) => {
  if (src) {
    loadImage(src)
  }
}, { immediate: true })

function loadImage(src: string) {
  const img = new Image()
  img.onload = () => {
    image.value = img
    imageLoaded.value = true
    fitToCanvas()
    drawCanvas()
  }
  img.src = src
}

function fitToCanvas() {
  if (!image.value || !containerRef.value) return
  const container = containerRef.value
  const cw = container.clientWidth
  const ch = container.clientHeight
  const iw = image.value.naturalWidth
  const ih = image.value.naturalHeight

  const fitScale = Math.min(cw / iw, ch / ih, 1)
  scale.value = fitScale
  canvasWidth.value = iw * fitScale
  canvasHeight.value = ih * fitScale
  offsetX.value = (cw - canvasWidth.value) / 2
  offsetY.value = (ch - canvasHeight.value) / 2
}

function drawCanvas() {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !image.value || !container) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const cw = container.clientWidth
  const ch = container.clientHeight
  const dpr = window.devicePixelRatio || 1
  canvas.width = cw * dpr
  canvas.height = ch * dpr
  canvasWidth.value = cw
  canvasHeight.value = ch

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  ctx.fillStyle = '#e5e7eb'
  ctx.fillRect(0, 0, cw, ch)

  ctx.save()
  ctx.translate(offsetX.value, offsetY.value)
  ctx.scale(scale.value, scale.value)
  ctx.drawImage(image.value, 0, 0)
  ctx.restore()

  if (detectionStore.bboxes.length > 0) {
    for (let i = 0; i < detectionStore.bboxes.length; i++) {
      drawBBox(ctx, detectionStore.bboxes[i], i)
    }
  }
}

function drawBBox(ctx: CanvasRenderingContext2D, bbox: BBox, index: number) {
  const s = scale.value
  const ox = offsetX.value
  const oy = offsetY.value

  const x1 = bbox.x1 * s + ox
  const y1 = bbox.y1 * s + oy
  const x2 = bbox.x2 * s + ox
  const y2 = bbox.y2 * s + oy
  const w = x2 - x1
  const h = y2 - y1

  const isHighlighted = detectionStore.highlightedBBoxIndex === index
  const colors = ['#FF0000', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF']
  const color = colors[index % colors.length]

  ctx.strokeStyle = color
  ctx.lineWidth = isHighlighted ? 3 : 2
  ctx.strokeRect(x1, y1, w, h)

  const label = `${bbox.class_name} ${(bbox.confidence * 100).toFixed(0)}%`
  ctx.fillStyle = color
  const textWidth = ctx.measureText(label).width + 8
  ctx.fillRect(x1, y1 - 20, textWidth, 20)
  ctx.fillStyle = '#FFFFFF'
  ctx.font = '12px sans-serif'
  ctx.fillText(label, x1 + 4, y1 - 6)

  if (isHighlighted) {
    ctx.strokeStyle = '#FFD700'
    ctx.lineWidth = 3
    ctx.strokeRect(x1 - 2, y1 - 2, w + 4, h + 4)
  }
}

function handleWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newScale = Math.max(0.1, Math.min(10, scale.value * delta))

  const rect = containerRef.value?.getBoundingClientRect()
  if (rect) {
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    offsetX.value = mouseX - (mouseX - offsetX.value) * (newScale / scale.value)
    offsetY.value = mouseY - (mouseY - offsetY.value) * (newScale / scale.value)
  }

  scale.value = newScale
  drawCanvas()
}

function handleMouseDown(e: MouseEvent) {
  if (e.button === 0) {
    isDragging.value = true
    dragStartX.value = e.clientX - offsetX.value
    dragStartY.value = e.clientY - offsetY.value
  }
}

function handleMouseMove(e: MouseEvent) {
  if (isDragging.value) {
    offsetX.value = e.clientX - dragStartX.value
    offsetY.value = e.clientY - dragStartY.value
    drawCanvas()
  }
}

function handleMouseUp() {
  isDragging.value = false
}

onMounted(() => {
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (image.value) {
        fitToCanvas()
        drawCanvas()
      }
    })
    resizeObserver.observe(containerRef.value)
  }

  if (displayImageSrc.value) {
    loadImage(displayImageSrc.value)
  }
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

watch([() => detectionStore.bboxes, () => detectionStore.highlightedBBoxIndex], () => {
  if (imageLoaded.value) {
    drawCanvas()
  }
}, { deep: true })
</script>

<template>
  <div
    ref="containerRef"
    class="w-full h-full bg-gray-200 overflow-hidden relative"
    @wheel="handleWheel"
    @mousedown="handleMouseDown"
    @mousemove="handleMouseMove"
    @mouseup="handleMouseUp"
    @mouseleave="handleMouseUp"
  >
    <canvas
      v-show="imageLoaded"
      ref="canvasRef"
      class="absolute inset-0 w-full h-full cursor-grab"
    />
    <div v-if="!imageLoaded" class="flex items-center justify-center h-full text-gray-400 text-sm">
      请上传图片开始检测
    </div>
  </div>
</template>
