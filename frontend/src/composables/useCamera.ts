import { ref, onUnmounted } from 'vue'

export function useCamera() {
  const stream = ref<MediaStream | null>(null)
  const videoRef = ref<HTMLVideoElement | null>(null)
  const isActive = ref(false)
  const error = ref<string | null>(null)

  async function startCamera(videoElement?: HTMLVideoElement) {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
      })
      stream.value = mediaStream
      isActive.value = true
      error.value = null

      const el = videoElement || videoRef.value
      if (el) {
        el.srcObject = mediaStream
        await el.play()
      }
    } catch (err: any) {
      error.value = `摄像头访问失败: ${err.message || '未知错误'}`
      isActive.value = false
    }
  }

  function stopCamera() {
    if (stream.value) {
      stream.value.getTracks().forEach(track => track.stop())
      stream.value = null
    }
    isActive.value = false
  }

  function captureFrame(): string | null {
    const el = videoRef.value
    if (!el) return null

    const canvas = document.createElement('canvas')
    canvas.width = el.videoWidth
    canvas.height = el.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return null

    ctx.drawImage(el, 0, 0)
    return canvas.toDataURL('image/jpeg', 0.85)
  }

  onUnmounted(() => {
    stopCamera()
  })

  return {
    stream,
    videoRef,
    isActive,
    error,
    startCamera,
    stopCamera,
    captureFrame,
  }
}
