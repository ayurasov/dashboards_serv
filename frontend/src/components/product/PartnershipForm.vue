<script setup>
import { computed, reactive, ref } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { partnershipsApi } from '@/api/services'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { PARTNERSHIP_STATUSES, PARTNERSHIP_TYPES, mergeOptions } from '@/domain/partnerships'

/**
 * Добавление и изменение партнёрства. record — запись реестра (пусто — новая),
 * options — значения из /partnerships/options для подсказок, defaults — начальные значения новой записи.
 */
const props = defineProps({
  record: { type: Object, default: null },
  options: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  removable: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved', 'deleted'])

const FIELDS = ['partner', 'product', 'direction', 'almi_product', 'almi_version', 'status', 'cert_date', 'nda',
  'agreement', 'bitrix', 'website', 'comment', 'type', 'last_modified']
const EMPTY = { partner: '', product: '', direction: '', almi_product: '', almi_version: '', status: 'В работе',
  cert_date: '', nda: false, agreement: false, bitrix: '', website: '', comment: '', type: 'ПО', last_modified: '' }

const isNew = computed(() => !props.record?.id)
const source = props.record?.id ? props.record : { ...EMPTY, ...props.defaults }
const form = reactive(Object.fromEntries(FIELDS.map((k) => [k, source[k] ?? EMPTY[k]])))

const statuses = computed(() => mergeOptions(PARTNERSHIP_STATUSES, [...(props.options.statuses || []), form.status]))
const types = computed(() => mergeOptions(PARTNERSHIP_TYPES, [...(props.options.types || []), form.type]))

const saving = ref(false)
const error = ref('')
const fields = ref({})
const uid = Math.random().toString(36).slice(2, 8)

function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function body() {
  const out = {}
  for (const k of FIELDS) {
    const v = form[k]
    if (k === 'cert_date' || k === 'last_modified') out[k] = v || null
    else if (k === 'nda' || k === 'agreement') out[k] = !!v
    else out[k] = typeof v === 'string' ? v.trim() : v ?? ''
  }
  return out
}

async function save() {
  error.value = ''
  fields.value = {}
  if (!form.partner.trim()) {
    fields.value = { partner: 'Укажите партнёра' }
    error.value = 'Заполните обязательные поля'
    return
  }
  saving.value = true
  try {
    const saved = isNew.value
      ? await partnershipsApi.create(body())
      : await partnershipsApi.update(props.record.id, body())
    toastOk(isNew.value ? 'Партнёрство добавлено' : 'Изменения сохранены')
    emit('saved', saved)
  } catch (e) {
    error.value = e.message
    fields.value = e.fields || {}
  } finally {
    saving.value = false
  }
}

async function remove() {
  const ok = await confirm({ title: 'Удалить партнёрство?', message: `${props.record.partner}${props.record.product ? ` — ${props.record.product}` : ''}\nДействие попадёт в журнал изменений.`, confirmText: 'Удалить', danger: true })
  if (!ok) return
  saving.value = true
  try {
    await partnershipsApi.remove(props.record.id)
    toastOk('Партнёрство удалено')
    emit('deleted', props.record)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

const invalid = (k) => ({ invalid: !!fields.value[k] })
</script>

<template>
  <AppModal :title="isNew ? 'Новое партнёрство' : 'Изменить партнёрство'" :subtitle="isNew ? 'Сертификация продукта партнёра с продуктом АЛМИ' : record.partner" :width="680" @close="emit('close')">
    <form :id="`partnership-form-${uid}`" class="form" novalidate @submit.prevent="save">
      <fieldset>
        <legend>Партнёр и продукт</legend>
        <div class="form-grid">
          <label class="field full"><span>Партнёр <em class="req">обязательно</em></span>
            <input v-model="form.partner" class="input" :class="invalid('partner')" maxlength="300" placeholder="ООО «Название»" autocomplete="off" />
            <span v-if="fields.partner" class="error">{{ fields.partner }}</span>
          </label>
          <label class="field full"><span>Продукт партнёра</span>
            <input v-model="form.product" class="input" :class="invalid('product')" maxlength="300" />
            <span v-if="fields.product" class="error">{{ fields.product }}</span>
          </label>
          <label class="field"><span>Направление</span>
            <input v-model="form.direction" class="input" :class="invalid('direction')" :list="`pf-directions-${uid}`" maxlength="300" placeholder="Например, СУБД" />
            <span v-if="fields.direction" class="error">{{ fields.direction }}</span>
          </label>
          <label class="field"><span>Тип</span>
            <select v-model="form.type" class="select" :class="invalid('type')">
              <option v-for="t in types" :key="t" :value="t">{{ t }}</option>
            </select>
            <span v-if="fields.type" class="error">{{ fields.type }}</span>
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Сертификация</legend>
        <div class="form-grid">
          <label class="field"><span>Продукт АЛМИ</span>
            <input v-model="form.almi_product" class="input" :class="invalid('almi_product')" :list="`pf-products-${uid}`" maxlength="200" placeholder="Например, АльтерОС" />
            <span v-if="fields.almi_product" class="error">{{ fields.almi_product }}</span>
          </label>
          <label class="field"><span>Версия продукта АЛМИ</span>
            <input v-model="form.almi_version" class="input" :class="invalid('almi_version')" maxlength="200" />
            <span v-if="fields.almi_version" class="error">{{ fields.almi_version }}</span>
          </label>
          <label class="field"><span>Статус</span>
            <select v-model="form.status" class="select" :class="invalid('status')">
              <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
            </select>
            <span v-if="fields.status" class="error">{{ fields.status }}</span>
          </label>
          <label class="field"><span>Дата сертификата</span>
            <input v-model="form.cert_date" class="input" :class="invalid('cert_date')" type="date" />
            <span v-if="fields.cert_date" class="error">{{ fields.cert_date }}</span>
            <span v-else class="help">По ней считается срок сертификата</span>
          </label>
          <div class="field">
            <span>Документы</span>
            <div class="checks">
              <label class="check"><input v-model="form.nda" type="checkbox" />NDA подписан</label>
              <label class="check"><input v-model="form.agreement" type="checkbox" />Соглашение подписано</label>
            </div>
          </div>
          <div class="field"><span>Дата изменения</span>
            <div class="with-action">
              <input v-model="form.last_modified" class="input" :class="invalid('last_modified')" type="date" aria-label="Дата изменения" />
              <button class="btn btn-sm btn-ghost" type="button" title="Поставить сегодняшнюю дату" @click="form.last_modified = today()">Сегодня</button>
            </div>
            <span v-if="fields.last_modified" class="error">{{ fields.last_modified }}</span>
            <span v-else class="help">Для хронологии изменений</span>
          </div>
        </div>
      </fieldset>

      <fieldset>
        <legend>Ссылки и комментарий</legend>
        <div class="form-grid">
          <label class="field"><span>Задача в Битрикс24</span>
            <input v-model="form.bitrix" class="input" :class="invalid('bitrix')" type="url" maxlength="500" placeholder="https://" />
            <span v-if="fields.bitrix" class="error">{{ fields.bitrix }}</span>
          </label>
          <label class="field"><span>Сайт партнёра</span>
            <input v-model="form.website" class="input" :class="invalid('website')" type="url" maxlength="500" placeholder="https://" />
            <span v-if="fields.website" class="error">{{ fields.website }}</span>
          </label>
          <label class="field full"><span>Комментарий</span>
            <textarea v-model="form.comment" class="textarea" :class="invalid('comment')" rows="3" maxlength="5000" />
            <span v-if="fields.comment" class="error">{{ fields.comment }}</span>
          </label>
        </div>
      </fieldset>

      <datalist :id="`pf-directions-${uid}`"><option v-for="d in options.directions || []" :key="d" :value="d" /></datalist>
      <datalist :id="`pf-products-${uid}`"><option v-for="p in options.almi_products || []" :key="p" :value="p" /></datalist>
    </form>
    <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>

    <template #footer>
      <button v-if="!isNew && removable" class="btn btn-ghost btn-danger" type="button" :disabled="saving" @click="remove"><AppIcon name="trash" :size="14" />Удалить</button>
      <span class="spacer" />
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" :form="`partnership-form-${uid}`" :disabled="saving">{{ saving ? 'Сохранение…' : isNew ? 'Добавить' : 'Сохранить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: var(--sp-5); }
fieldset { margin: 0; padding: 0; border: 0; min-width: 0; }
legend { padding: 0; margin-bottom: var(--sp-3); font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.req { font-style: normal; font-weight: 500; font-size: var(--fs-xs); color: var(--muted); margin-left: 4px; }
.checks { display: flex; flex-direction: column; gap: 8px; padding-top: 4px; }
.with-action { display: flex; gap: 6px; align-items: center; }
.with-action .input { flex: 1; }
.textarea.invalid, .select.invalid { border-color: var(--light-red); }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: var(--sp-4); color: var(--light-red); font-size: var(--fs-sm); }
</style>
