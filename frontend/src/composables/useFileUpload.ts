import { ref } from 'vue'

export function useFileUpload() {
  const file = ref<File | null>(null)
  const previewUrl = ref<string | null>(null)
  const isUploading = ref(false)
  const progress = ref(0)
  const error = ref<string | null>(null)

  function setFile(f: File) {
    file.value = f
    error.value = null

    // Revoke previous URL
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
    }
    previewUrl.value = URL.createObjectURL(f)
  }

  function clearFile() {
    file.value = null
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
      previewUrl.value = null
    }
    progress.value = 0
    error.value = null
  }

  function setProgress(p: number) {
    progress.value = p
  }

  function setError(msg: string) {
    error.value = msg
  }

  function startUpload() {
    isUploading.value = true
    progress.value = 0
  }

  function finishUpload() {
    isUploading.value = false
    progress.value = 100
  }

  return {
    file,
    previewUrl,
    isUploading,
    progress,
    error,
    setFile,
    clearFile,
    setProgress,
    setError,
    startUpload,
    finishUpload,
  }
}
