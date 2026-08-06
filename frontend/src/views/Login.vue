<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="login-brand">
        <img src="/assets/logo-sidebar.png" width="34" height="34" alt="АЛМИ Партнер">
        <span class="login-brand-name">АЛМИ Партнер</span>
      </div>
      <h1 class="login-title">Служба персонала</h1>
      <p class="login-sub">Вход в систему</p>
      <form @submit.prevent="doLogin">
        <div class="fgi" style="margin-bottom:12px">
          <label class="fl">Имя пользователя</label>
          <input class="fi" v-model="form.username" placeholder="Введите логин" required style="width:100%" autofocus>
        </div>
        <div class="fgi" style="margin-bottom:12px">
          <label class="fl">Пароль</label>
          <input class="fi" type="password" v-model="form.password" placeholder="••••••" required style="width:100%">
        </div>
        <div class="err-msg">{{ err }}</div>
        <button type="submit" class="btn btn-p" style="width:100%;justify-content:center;padding:10px;margin-top:8px">Войти</button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const router = useRouter()
const form = ref({ username: '', password: '' })
const err = ref('')

async function doLogin() {
  err.value = ''
  try {
    await auth.login(form.value.username, form.value.password)
    router.push('/')
  } catch (e) {
    err.value = e.message
  }
}
</script>
