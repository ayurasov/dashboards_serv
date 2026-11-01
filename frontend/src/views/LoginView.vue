<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { api } from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const show = ref(false)
const busy = ref(false)
const error = ref(route.query.expired ? 'Сессия завершена. Войдите снова' : '')
const version = ref('')

onMounted(async () => {
  try { version.value = (await api.get('/version', null, { silent: true })).version } catch {}
})

async function submit() {
  if (!username.value || !password.value) return
  busy.value = true
  error.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    const target = auth.mustChangePassword ? { name: 'profile', query: { password: 'required' } } : String(route.query.redirect || '/')
    router.replace(target)
  } catch (e) {
    error.value = e.message
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <section class="panel">
      <div class="brand">
        <img src="/logo.png" width="40" height="40" alt="" />
        <div>
          <strong>Дашборды компании</strong>
          <span>АЛМИ Партнер</span>
        </div>
      </div>
      <h1>Вход</h1>
      <p class="lead">Показатели служб компании в одном месте: персонал, техническая поддержка, технологические партнёрства.</p>
      <form class="form" @submit.prevent="submit">
        <label class="field">
          <span>Логин</span>
          <input v-model="username" class="input" name="username" autocomplete="username" autofocus required />
        </label>
        <label class="field">
          <span>Пароль</span>
          <span class="pwd">
            <input v-model="password" class="input" name="password" :type="show ? 'text' : 'password'" autocomplete="current-password" required />
            <button class="eye" type="button" :title="show ? 'Скрыть пароль' : 'Показать пароль'" @click="show = !show">
              <AppIcon :name="show ? 'eye-off' : 'eye'" :size="16" />
            </button>
          </span>
        </label>
        <p v-if="error" class="error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>
        <button class="btn btn-primary submit" type="submit" :disabled="busy || !username || !password">
          {{ busy ? 'Вход…' : 'Войти' }}
        </button>
      </form>
      <p class="foot">Нет доступа или забыли пароль — обратитесь к администратору системы.</p>
    </section>
    <aside class="art" aria-hidden="true">
      <div class="art-inner">
        <div class="art-card a1"><span class="dot g" />Текучесть кадров <b>2,0%</b></div>
        <div class="art-card a2"><span class="dot y" />Заявок в работе <b>274</b></div>
        <div class="art-card a3"><span class="dot g" />Партнёрств завершено <b>141</b></div>
        <svg class="art-chart" viewBox="0 0 400 160" fill="none">
          <path d="M0 130 C 50 120, 80 70, 130 80 S 210 40, 250 55 S 330 20, 400 30" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
          <path d="M0 130 C 50 120, 80 70, 130 80 S 210 40, 250 55 S 330 20, 400 30 L 400 160 L 0 160 Z" fill="currentColor" opacity=".08" />
        </svg>
        <p class="version">Версия {{ version }}</p>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.login { min-height: 100vh; display: grid; grid-template-columns: minmax(380px, 520px) 1fr; background: var(--bg-elevated); }
.panel { display: flex; flex-direction: column; justify-content: center; padding: 48px 56px; }
.brand { display: flex; align-items: center; gap: 12px; margin-bottom: 44px; }
.brand img { border-radius: 10px; }
.brand div { display: flex; flex-direction: column; line-height: 1.2; }
.brand strong { font-size: 16px; }
.brand span { font-size: var(--fs-sm); color: var(--muted); }
h1 { font-size: 28px; letter-spacing: -0.02em; }
.lead { margin: 8px 0 28px; color: var(--muted); max-width: 380px; }
.form { display: flex; flex-direction: column; gap: 16px; max-width: 380px; }
.form .input { height: 42px; font-size: 15px; }
.pwd { position: relative; display: block; }
.pwd .input { padding-right: 42px; }
.eye { position: absolute; right: 6px; top: 6px; width: 30px; height: 30px; display: grid; place-items: center; border: 0; border-radius: 7px; background: transparent; color: var(--muted); cursor: pointer; }
.eye:hover { color: var(--text); background: var(--surface-3); }
.error { display: flex; align-items: center; gap: 7px; padding: 9px 12px; border-radius: 10px; background: color-mix(in srgb, var(--light-red) 10%, transparent); color: var(--light-red); font-size: var(--fs-sm); }
.submit { height: 42px; font-size: 15px; margin-top: 4px; }
.foot { margin-top: 28px; font-size: var(--fs-sm); color: var(--muted); }
.art { position: relative; overflow: hidden; background: radial-gradient(1200px 600px at 80% 10%, color-mix(in srgb, var(--brand) 18%, transparent), transparent 60%), linear-gradient(160deg, var(--surface-2), var(--surface-3)); border-left: 1px solid var(--border); }
.art-inner { position: absolute; inset: 0; display: grid; place-items: center; color: var(--brand); }
.art-chart { position: absolute; left: 8%; right: 8%; bottom: 18%; width: 84%; }
.art-card { position: absolute; display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 14px; background: var(--bg-elevated); border: 1px solid var(--border); box-shadow: var(--shadow); color: var(--text-2); font-size: var(--fs-sm); }
.art-card b { color: var(--text); font-size: 16px; margin-left: 6px; font-variant-numeric: tabular-nums; }
.a1 { top: 20%; left: 16%; } .a2 { top: 34%; right: 14%; } .a3 { top: 50%; left: 26%; }
.dot { width: 9px; height: 9px; border-radius: 50%; }
.dot.g { background: var(--light-green); } .dot.y { background: var(--light-yellow); }
.version { position: absolute; bottom: 24px; right: 28px; color: var(--muted); font-size: var(--fs-xs); }
@media (max-width: 900px) { .login { grid-template-columns: 1fr; } .art { display: none; } .panel { padding: 32px 24px; } }
</style>
