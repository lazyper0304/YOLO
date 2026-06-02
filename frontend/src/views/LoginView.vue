<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref()
const form = reactive({
  username: '',
  password: '',
})
const loading = ref(false)

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch {
    // Error handled by interceptor
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-50">
    <div class="w-full max-w-md bg-white rounded-lg shadow-lg p-8">
      <h1 class="text-2xl font-bold text-center mb-8">YOLO 目标检测平台</h1>
      <h2 class="text-lg text-gray-600 text-center mb-6">用户登录</h2>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" class="w-full" :loading="loading" @click="handleLogin">
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="text-center mt-4">
        <span class="text-gray-500">还没有账号？</span>
        <router-link to="/register" class="text-blue-500 hover:text-blue-600 ml-1">立即注册</router-link>
      </div>
    </div>
  </div>
</template>
