<script setup>
import { computed, useId } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import {
  INTERVAL_PRESETS, MAX_INTERVAL, MAX_SCHEDULES, MIN_INTERVAL, SCHEDULE_MODES, WEEKDAYS, canAddSchedule, entryLabel, intervalText,
  newScheduleEntry, schedulableActions, scheduleLabel, schedulePayload, toggleWeekday,
} from '@/domain/integrations'

/**
 * Расписание подключения — до MAX_SCHEDULES записей, у каждой свои вид и действия: через интервал (минуты) или
 * в заданное время (ЧЧ:ММ по часовому поясу компании и дни недели; без дней — каждый день). Так «По Делу» одним
 * подключением синхронизирует структуру раз в день и забирает файлы задач каждые 30 минут. Нет записей —
 * подключение запускается только вручную. Запуски выполняет планировщик (python -m app.cli worker).
 * v-model — список черновиков записей (domain/integrations: scheduleDraft, schedulePayload).
 */
const props = defineProps({
  modelValue: { type: Array, required: true },
  kind: { type: Object, required: true },
  errors: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])
const uid = useId()

const actions = computed(() => schedulableActions(props.kind))
const entries = computed(() => props.modelValue || [])
const preview = computed(() => scheduleLabel(schedulePayload(entries.value), props.kind))
const canAdd = computed(() => canAddSchedule(entries.value, props.kind))

function update(index, patch) {
  emit('update:modelValue', entries.value.map((e, n) => (n === index ? { ...e, ...patch } : e)))
}
function add() {
  if (canAdd.value) emit('update:modelValue', [...entries.value, newScheduleEntry(props.kind, entries.value)])
}
function remove(index) {
  emit('update:modelValue', entries.value.filter((_, n) => n !== index))
}
function toggleAction(index, key) {
  const list = entries.value[index].actions || []
  update(index, { actions: list.includes(key) ? list.filter((a) => a !== key) : [...list, key] })
}
const err = (index, field) => props.errors[`schedule.${index}.${field}`] || ''
</script>

<template>
  <div class="schedule" data-testid="schedule-editor">
    <p v-if="!actions.length" class="muted">У этого подключения нет действий по расписанию — оно запускается только вручную.</p>
    <template v-else>
      <p v-if="!entries.length" class="muted empty" data-testid="schedule-empty">Расписания нет — подключение запускается только кнопками действий на карточке.</p>

      <section v-for="(entry, n) in entries" :key="n" class="entry" data-testid="schedule-entry" :aria-label="`Расписание ${n + 1}`">
        <header class="entry-head">
          <h4>Расписание {{ n + 1 }}<span class="entry-label">{{ entryLabel(schedulePayload([entry])[0]) }}</span></h4>
          <button type="button" class="btn btn-sm btn-ghost btn-icon btn-danger" :aria-label="`Удалить расписание ${n + 1}`" :title="`Удалить расписание ${n + 1}`"
                  data-testid="schedule-remove" @click="remove(n)"><AppIcon name="trash" :size="14" /></button>
        </header>

        <SegmentedControl :model-value="entry.mode" :options="SCHEDULE_MODES" :aria-label="`Расписание ${n + 1}: как запускать`" @update:model-value="update(n, { mode: $event })" />

        <div v-if="entry.mode === 'interval'" class="row-block">
          <label class="field" :for="`${uid}-${n}-min`">
            <span>Интервал, минут</span>
            <input :id="`${uid}-${n}-min`" class="input num minutes" type="number" inputmode="numeric" :min="MIN_INTERVAL" :max="MAX_INTERVAL" step="1"
                   :class="{ invalid: err(n, 'minutes') }" :value="entry.minutes" data-testid="schedule-minutes" @input="update(n, { minutes: $event.target.value })" />
          </label>
          <div class="presets" role="group" aria-label="Готовые интервалы">
            <button v-for="m in INTERVAL_PRESETS" :key="m" type="button" class="chip" :class="{ active: Number(entry.minutes) === m }" @click="update(n, { minutes: String(m) })">{{ intervalText(m) }}</button>
          </div>
          <small v-if="err(n, 'minutes')" class="error">{{ err(n, 'minutes') }}</small>
        </div>

        <div v-else class="row-block">
          <label class="field" :for="`${uid}-${n}-time`">
            <span>Время запуска</span>
            <input :id="`${uid}-${n}-time`" class="input time" type="time" :class="{ invalid: err(n, 'time') }" :value="entry.time" data-testid="schedule-time" @input="update(n, { time: $event.target.value })" />
          </label>
          <div class="field">
            <span>Дни недели <small class="muted">— не выбраны: каждый день</small></span>
            <div class="days" role="group" aria-label="Дни недели">
              <button v-for="d in WEEKDAYS" :key="d.value" type="button" class="day" :class="{ on: entry.weekdays.includes(d.value) }" :aria-pressed="entry.weekdays.includes(d.value)"
                      :title="d.full" @click="update(n, { weekdays: toggleWeekday(entry.weekdays, d.value) })">{{ d.label }}</button>
            </div>
          </div>
          <small v-if="err(n, 'time')" class="error">{{ err(n, 'time') }}</small>
        </div>

        <fieldset class="acts">
          <legend>Что выполнять</legend>
          <label v-for="a in actions" :key="a.key" class="check" :data-action="a.key">
            <input type="checkbox" :checked="entry.actions.includes(a.key)" @change="toggleAction(n, a.key)" />
            <span>{{ a.label }}<small v-if="a.description">{{ a.description }}</small></span>
          </label>
          <small v-if="err(n, 'actions')" class="error">{{ err(n, 'actions') }}</small>
        </fieldset>
      </section>

      <div class="add-row">
        <button type="button" class="btn btn-sm" :disabled="!canAdd" data-testid="schedule-add" @click="add">
          <AppIcon name="plus" :size="14" />Добавить расписание
        </button>
        <small class="muted">{{ entries.length >= MAX_SCHEDULES ? `Не больше ${MAX_SCHEDULES} расписаний у подключения` : 'У каждого расписания — свои время и действия' }}</small>
      </div>
      <small v-if="errors.schedule" class="error">{{ errors.schedule }}</small>

      <p class="preview" data-testid="schedule-preview">
        <b>{{ preview }}</b>
        <template v-if="entries.length"> — запуски выполняет планировщик (сервис worker) по часовому поясу компании; включённое подключение запускается и вручную.</template>
        <template v-else> — подключение запускается только кнопками действий.</template>
      </p>
    </template>
  </div>
</template>

<style scoped>
.schedule { display: flex; flex-direction: column; gap: 12px; }
.empty { padding: 12px 14px; border: 1px dashed var(--border-strong); border-radius: 12px; }
.entry { display: flex; flex-direction: column; gap: 12px; padding: 12px 14px 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); min-width: 0; }
.entry-head { display: flex; align-items: center; gap: 8px; margin: -2px -4px -4px 0; }
.entry-head h4 { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; font-size: var(--fs-sm); font-weight: 650; }
.entry-label { font-weight: 500; color: var(--muted); font-size: var(--fs-xs); }
.row-block { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 16px; }
.minutes { width: 120px; }
.time { width: 130px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; }
.days { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.day { min-width: 38px; height: 32px; padding: 0 8px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--surface); color: var(--text-2); font-size: var(--fs-sm); font-weight: 560; cursor: pointer; }
.day:hover { border-color: var(--faint); color: var(--text); }
.day.on { background: var(--text); border-color: var(--text); color: var(--bg-elevated); }
.acts { margin: 0; padding: 0; border: 0; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.acts legend { margin-bottom: 6px; font-size: var(--fs-sm); font-weight: 560; color: var(--text-2); }
.check { align-items: flex-start; }
.check input { margin-top: 2px; flex: 0 0 auto; }
.check span { display: flex; flex-direction: column; font-size: var(--fs-sm); min-width: 0; }
.check small { font-size: var(--fs-xs); color: var(--muted); overflow-wrap: anywhere; }
.add-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; }
.add-row .btn { white-space: nowrap; }
.error { font-size: var(--fs-xs); color: var(--light-red); flex-basis: 100%; }
.preview { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; overflow-wrap: anywhere; }
.muted { color: var(--muted); font-size: var(--fs-sm); }
.add-row small.muted { font-size: var(--fs-xs); }
.field small.muted { font-size: var(--fs-xs); font-weight: 400; }
</style>
