<script setup>
import { computed, useId } from 'vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import { INTERVAL_PRESETS, MAX_INTERVAL, MIN_INTERVAL, SCHEDULE_MODES, WEEKDAYS, intervalText, schedulableActions, schedulePayload, scheduleLabel, toggleWeekday } from '@/domain/integrations'

/**
 * Расписание подключения: вручную · через интервал (минуты) · в заданное время (ЧЧ:ММ по часовому
 * поясу компании и дни недели; без дней — каждый день) и какие действия выполнять по расписанию
 * (только schedulable). Запуски выполняет планировщик (python -m app.cli worker).
 */
const props = defineProps({
  modelValue: { type: Object, required: true },
  kind: { type: Object, required: true },
  errors: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])
const uid = useId()

const actions = computed(() => schedulableActions(props.kind))
const draft = computed(() => props.modelValue)
const preview = computed(() => scheduleLabel(schedulePayload(draft.value)))
function set(patch) {
  emit('update:modelValue', { ...draft.value, ...patch })
}
function toggleAction(key) {
  const list = draft.value.actions || []
  set({ actions: list.includes(key) ? list.filter((a) => a !== key) : [...list, key] })
}
</script>

<template>
  <div class="schedule" data-testid="schedule-editor">
    <p v-if="!actions.length" class="muted">У этого подключения нет действий по расписанию — оно запускается только вручную.</p>
    <template v-else>
      <SegmentedControl :model-value="draft.mode" :options="SCHEDULE_MODES" aria-label="Расписание" @update:model-value="set({ mode: $event })" />

      <div v-if="draft.mode === 'interval'" class="row-block">
        <label class="field" :for="`${uid}-min`">
          <span>Интервал, минут</span>
          <input :id="`${uid}-min`" class="input num minutes" type="number" inputmode="numeric" :min="MIN_INTERVAL" :max="MAX_INTERVAL" step="1"
                 :class="{ invalid: errors['schedule.minutes'] }" :value="draft.minutes" data-testid="schedule-minutes" @input="set({ minutes: $event.target.value })" />
        </label>
        <div class="presets" role="group" aria-label="Готовые интервалы">
          <button v-for="m in INTERVAL_PRESETS" :key="m" type="button" class="chip" :class="{ active: Number(draft.minutes) === m }" @click="set({ minutes: String(m) })">{{ intervalText(m) }}</button>
        </div>
        <small v-if="errors['schedule.minutes']" class="error">{{ errors['schedule.minutes'] }}</small>
      </div>

      <div v-if="draft.mode === 'daily'" class="row-block">
        <label class="field" :for="`${uid}-time`">
          <span>Время запуска</span>
          <input :id="`${uid}-time`" class="input time" type="time" :class="{ invalid: errors['schedule.time'] }" :value="draft.time" data-testid="schedule-time" @input="set({ time: $event.target.value })" />
        </label>
        <div class="field">
          <span>Дни недели <small class="muted">— не выбраны: каждый день</small></span>
          <div class="days" role="group" aria-label="Дни недели">
            <button v-for="d in WEEKDAYS" :key="d.value" type="button" class="day" :class="{ on: draft.weekdays.includes(d.value) }" :aria-pressed="draft.weekdays.includes(d.value)"
                    :title="d.full" @click="set({ weekdays: toggleWeekday(draft.weekdays, d.value) })">{{ d.label }}</button>
          </div>
        </div>
        <small v-if="errors['schedule.time']" class="error">{{ errors['schedule.time'] }}</small>
      </div>

      <fieldset v-if="draft.mode !== 'off'" class="acts">
        <legend>Что выполнять по расписанию</legend>
        <label v-for="a in actions" :key="a.key" class="check">
          <input type="checkbox" :checked="draft.actions.includes(a.key)" @change="toggleAction(a.key)" />
          <span>{{ a.label }}<small v-if="a.description">{{ a.description }}</small></span>
        </label>
        <small v-if="errors['schedule.actions']" class="error">{{ errors['schedule.actions'] }}</small>
      </fieldset>
      <small v-if="errors.schedule" class="error">{{ errors.schedule }}</small>

      <p class="preview" data-testid="schedule-preview">
        <b>{{ preview }}</b>
        <template v-if="draft.mode !== 'off'"> — запуски выполняет планировщик (сервис worker) по часовому поясу компании; включённое подключение запускается и вручную.</template>
        <template v-else> — подключение запускается только кнопками действий.</template>
      </p>
    </template>
  </div>
</template>

<style scoped>
.schedule { display: flex; flex-direction: column; gap: 14px; }
.row-block { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 16px; }
.minutes { width: 120px; }
.time { width: 130px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; }
.days { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.day { min-width: 38px; height: 32px; padding: 0 8px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--surface); color: var(--text-2); font-size: var(--fs-sm); font-weight: 560; cursor: pointer; }
.day:hover { border-color: var(--faint); color: var(--text); }
.day.on { background: var(--text); border-color: var(--text); color: var(--bg-elevated); }
.acts { margin: 0; padding: 0; border: 0; display: flex; flex-direction: column; gap: 8px; }
.acts legend { margin-bottom: 6px; font-size: var(--fs-sm); font-weight: 560; color: var(--text-2); }
.check { align-items: flex-start; }
.check input { margin-top: 2px; flex: 0 0 auto; }
.check span { display: flex; flex-direction: column; font-size: var(--fs-sm); }
.check small { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); flex-basis: 100%; }
.preview { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.muted { color: var(--muted); font-size: var(--fs-sm); }
.field small.muted { font-size: var(--fs-xs); font-weight: 400; }
</style>
