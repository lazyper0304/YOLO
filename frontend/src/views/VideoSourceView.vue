<script setup lang="ts">
import { useRouter } from 'vue-router'
import { VideoCamera, Camera } from '@element-plus/icons-vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import LeftSidebar from '@/components/layout/LeftSidebar.vue'

const router = useRouter()

function goDetection() {
  router.push('/detection')
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <AppHeader />
    <div class="flex-1 grid grid-cols-[180px_1fr] overflow-hidden">
      <LeftSidebar />
      <main class="flex-1 overflow-auto bg-gray-50">
        <div class="max-w-4xl mx-auto p-8">
          <h2 class="text-2xl font-bold mb-6">视频源管理</h2>

          <div class="bg-white rounded-lg shadow-sm p-8 text-center">
            <div class="mb-4">
              <el-icon :size="64" color="#409EFF"><Camera /></el-icon>
            </div>
            <p class="text-gray-500 mb-2">实时摄像头视频流目标检测</p>
            <p class="text-sm text-gray-400 mb-4">支持本地摄像头和 RTSP/RTMP 网络摄像头</p>
            <div class="flex justify-center gap-3">
              <el-button type="primary" :icon="Camera" @click="goDetection">本地摄像头</el-button>
              <el-button :icon="VideoCamera" disabled>RTSP 网络摄像头（即将推出）</el-button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
