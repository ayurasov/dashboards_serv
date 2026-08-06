<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="mh">
        <span class="mt">{{ isNew ? 'Новое партнёрство' : 'Редактировать партнёрство' }}</span>
        <button class="mc" @click="$emit('close')">✕</button>
      </div>

      <div class="fg">
        <div class="fgi full">
          <label class="fl">Партнёр</label>
          <input class="fi" v-model="form.partner" placeholder="ООО …">
        </div>
        <div class="fgi full">
          <label class="fl">Продукт</label>
          <input class="fi" v-model="form.product">
        </div>
        <div class="fgi">
          <label class="fl">Направление</label>
          <input class="fi" v-model="form.direction" list="pm-directions">
          <datalist id="pm-directions">
            <option v-for="d in directions" :key="d" :value="d"></option>
          </datalist>
        </div>
        <div class="fgi">
          <label class="fl">Тип</label>
          <select class="fs" v-model="form.type">
            <option value="ПО">ПО</option>
            <option value="Железо">Железо</option>
          </select>
        </div>
        <div class="fgi">
          <label class="fl">Продукт АЛМИ</label>
          <input class="fi" v-model="form.almi_product" list="pm-products">
          <datalist id="pm-products">
            <option v-for="p in almiProducts" :key="p" :value="p"></option>
          </datalist>
        </div>
        <div class="fgi">
          <label class="fl">Версия АЛМИ</label>
          <input class="fi" v-model="form.almi_version">
        </div>
        <div class="fgi">
          <label class="fl">Статус</label>
          <select class="fs" v-model="form.status">
            <option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="fgi">
          <label class="fl">Дата сертификата</label>
          <input class="fi" type="date" v-model="form.cert_date">
        </div>
        <div class="fgi">
          <label class="fl">Bitrix</label>
          <input class="fi" v-model="form.bitrix">
        </div>
        <div class="fgi">
          <label class="fl">Сайт</label>
          <input class="fi" v-model="form.website">
        </div>
        <div class="fgi">
          <label class="fl">NDA</label>
          <label style="display:flex;align-items:center;gap:8px;font-size:.8125rem">
            <input type="checkbox" v-model="form.nda"> подписано
          </label>
        </div>
        <div class="fgi">
          <label class="fl">Соглашение</label>
          <label style="display:flex;align-items:center;gap:8px;font-size:.8125rem">
            <input type="checkbox" v-model="form.agreement"> подписано
          </label>
        </div>
        <div class="fgi full">
          <label class="fl">Комментарий</label>
          <textarea class="fta" v-model="form.comment"></textarea>
        </div>
      </div>

      <div class="err-msg">{{ err }}</div>
      <div class="fac">
        <button v-if="!isNew" class="btn btn-d" @click="remove">Удалить</button>
        <span v-else></span>
        <div class="right">
          <button class="btn btn-g" @click="$emit('close')">Отмена</button>
          <button class="btn btn-p" :disabled="saving" @click="save">{{ saving ? '…' : 'Сохранить' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { api } from '../api/client.js'

const STATUSES = ['Завершено', 'В работе', 'Отложено', 'Не подписывают']

const props = defineProps({
  modelValue: { type: Object, required: true },
  directions: { type: Array, default: () => [] },
  almiProducts: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved'])

const isNew = computed(() => !props.modelValue?.id)
const saving = ref(false)
const err = ref('')

const form = ref({
  partner: '', product: '', direction: '', almi_product: '', almi_version: '',
  status: 'В работе', type: 'ПО', nda: false, agreement: false,
  bitrix: '', website: '', comment: '',
  ...props.modelValue,
  cert_date: props.modelValue?.cert_date || '',
})

function payload() {
  return {
    partner: form.value.partner?.trim() || '',
    product: form.value.product || '',
    direction: form.value.direction || '',
    almi_product: form.value.almi_product || '',
    almi_version: form.value.almi_version || '',
    status: form.value.status,
    cert_date: form.value.cert_date || null,
    type: form.value.type,
    nda: !!form.value.nda,
    agreement: !!form.value.agreement,
    bitrix: form.value.bitrix || null,
    website: form.value.website || null,
    comment: form.value.comment || null,
    last_modified: new Date().toISOString().slice(0, 10),
  }
}

async function save() {
  if (!form.value.partner?.trim()) { err.value = 'Укажите партнёра'; return }
  saving.value = true
  err.value = ''
  try {
    if (isNew.value) await api.post('/partnerships', payload())
    else await api.put(`/partnerships/${props.modelValue.id}`, payload())
    emit('saved')
  } catch (e) {
    err.value = e.message
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!confirm('Удалить запись о партнёрстве?')) return
  saving.value = true
  err.value = ''
  try {
    await api.del(`/partnerships/${props.modelValue.id}`)
    emit('saved')
  } catch (e) {
    err.value = e.message
  } finally {
    saving.value = false
  }
}
</script>
