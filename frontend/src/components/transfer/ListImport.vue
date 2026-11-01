<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ImportPlanView from './ImportPlanView.vue'
import TransferBanner from './TransferBanner.vue'
import TransferFile from './TransferFile.vue'
import { orgApi } from '@/api/org'
import { LIST_SAMPLE } from '@/domain/org'

/**
 * Быстрая загрузка списком: таблица «email; ФИО; Подразделение (путь через /); Должность;
 * Руководитель (email); Руководит» — файлом CSV/Excel или вставленным текстом.
 */
const emit = defineEmits(['applied'])
const COLUMNS = [
  { name: 'email', note: 'обязательно (или логин)' }, { name: 'ФИО', note: 'для новых' },
  { name: 'Подразделение', note: 'путь через «/»' }, { name: 'Должность' }, { name: 'Руководитель', note: 'email' },
  { name: 'Руководит', note: '«да» — руководит своим' }, { name: 'Логин' }, { name: 'Внешний ID' },
]

const file = ref(null)
const text = ref('')
const createMissing = ref(false)
const plan = ref(null)
const result = ref(null)
const busy = ref('')
const error = ref('')

const ready = computed(() => !!file.value || !!text.value.trim())
watch([file, text, createMissing], () => {
  plan.value = null
  result.value = null
  error.value = ''
})

async function run(apply) {
  busy.value = apply ? 'apply' : 'check'
  error.value = ''
  try {
    return await orgApi.importList({ file: file.value, content: text.value, createMissing: createMissing.value, apply })
  } catch (e) {
    error.value = e.message
    return null
  } finally {
    busy.value = ''
  }
}
async function check() {
  result.value = null
  const next = await run(false)
  if (next) plan.value = next
}
async function apply() {
  const applied = await run(true)
  if (!applied) return
  plan.value = applied
  if (applied.rejected) return
  const s = applied.summary
  result.value = `Новых подразделений: ${s.create_departments} · новых сотрудников: ${s.create_users} · изменено: ${s.update_users}`
  emit('applied')
  const fresh = await run(false)
  if (fresh) plan.value = fresh
}
function sample() {
  file.value = null
  text.value = LIST_SAMPLE
}
const source = computed(() => (file.value ? file.value.name : 'Вставленный текст'))
</script>

<template>
  <div class="transfer">
    <section class="card block">
      <div class="block-head">
        <span class="b-icon"><AppIcon name="list" :size="18" /></span>
        <div class="b-text">
          <h2>Быстрая загрузка списком</h2>
          <p>Подразделения и сотрудники одной таблицей: недостающие подразделения создаются по пути, сотрудники сопоставляются по email или логину. Руководитель из файла записывается явно, только если он отличается от руководителя по структуре. Первая строка — заголовки, разделитель «;» или «,».</p>
        </div>
      </div>
      <div class="block-body">
        <ul class="columns" aria-label="Столбцы">
          <li v-for="c in COLUMNS" :key="c.name"><code>{{ c.name }}</code><small v-if="c.note">{{ c.note }}</small></li>
        </ul>
        <TransferFile v-model="file" accept=".csv,.xlsx" hint="CSV (UTF-8) или Excel" testid="list-file" />
        <div v-if="!file" class="paste">
          <div class="paste-head">
            <span class="paste-label">или вставьте строки таблицы</span>
            <button type="button" class="link-btn" data-testid="list-sample" @click="sample"><AppIcon name="copy" :size="13" />Вставить пример</button>
          </div>
          <textarea v-model="text" class="textarea mono" rows="7" spellcheck="false" aria-label="Строки для загрузки" data-testid="list-text"
                    placeholder="email;ФИО;Подразделение;Должность;Руководитель;Руководит" />
        </div>
        <label class="check"><input v-model="createMissing" type="checkbox" data-testid="list-create" />
          <span>Создавать новых сотрудников<small>Без пароля и доступа — доступ выдаётся в разделе «Пользователи». Без отметки строки с новыми сотрудниками — ошибки.</small></span>
        </label>
        <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>
        <div class="actions">
          <button type="button" class="btn btn-primary" :disabled="!ready || !!busy" data-testid="list-check" @click="check">
            <AppIcon name="search" :size="15" />{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}
          </button>
          <span class="muted">Проверка ничего не записывает.</span>
        </div>
      </div>
    </section>

    <TransferBanner v-if="result" title="Список загружен" :text="result" data-testid="list-applied" />

    <ImportPlanView v-if="plan" :key="plan.applied ? 'a' : 'p'" :plan="plan" :title="result ? 'После загрузки' : 'Что изменится'" :source="source">
      <template #footer>
        <button type="button" class="btn btn-primary" :disabled="!plan.can_apply || !!busy || !!result" data-testid="list-apply" @click="apply">
          <AppIcon name="check" :size="15" />{{ busy === 'apply' ? 'Применяю…' : 'Применить' }}
        </button>
        <span class="muted">{{ result ? 'Изменения применены.' : plan.can_apply ? 'Всё будет записано одной операцией.' : 'Исправьте ошибки и проверьте снова.' }}</span>
      </template>
    </ImportPlanView>
  </div>
</template>

<style scoped src="./transfer.css"></style>
<style scoped>
.columns { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.columns li { display: inline-flex; align-items: baseline; gap: 6px; padding: 4px 10px; border-radius: var(--radius-pill); background: var(--surface-2); border: 1px solid var(--border); }
.columns code { font-family: var(--font-sans); font-size: var(--fs-sm); font-weight: 600; color: var(--text); }
.columns small { font-size: var(--fs-xs); color: var(--muted); }
.paste { display: flex; flex-direction: column; gap: 6px; }
.paste-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.paste-head .paste-label { font-size: var(--fs-sm); color: var(--muted); }
.link-btn { display: inline-flex; align-items: center; gap: 5px; padding: 0; border: 0; background: transparent; color: var(--accent); font-size: var(--fs-sm); cursor: pointer; }
.link-btn:hover { text-decoration: underline; }
.mono { font-family: var(--font-mono); font-size: var(--fs-sm); line-height: 1.55; }
</style>
