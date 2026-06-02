<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

defineProps<{
  visible: boolean
}>()
</script>

<template>
  <Transition name="fade">
    <div
      v-if="visible"
      class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    >
      <div class="bg-white rounded-lg shadow-xl p-8 flex flex-col items-center gap-4">
        <el-icon class="is-loading" :size="48" color="#409EFF">
          <Loading />
        </el-icon>
        <p class="text-gray-700 text-base font-medium mt-2">正在检测中...</p>
        <div class="text-xs text-gray-400 space-y-1 mt-1">
          <p>YOLO 目标检测</p>
          <p>LLM 智能分析</p>
          <p>结果生成中</p>
        </div>
        <p class="text-xs text-gray-300 mt-2">请勿关闭页面或重复操作</p>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
