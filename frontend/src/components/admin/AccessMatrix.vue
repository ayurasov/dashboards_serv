<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { ACCESS_COLUMNS, setRowLevel, setRowScope } from '@/domain/admin'

/**
 * Матрица доступа: строки — службы (сначала с дашбордом), столбцы — «Нет» и уровни.
 * modelValue — строки из buildAccessRows(); изменения приходят новым массивом.
 */
const props = defineProps({
  modelValue: { type: Array, required: true },
  disabled: { type: Boolean, default: false },
  name: { type: String, default: 'access' },
})
const emit = defineEmits(['update:modelValue'])

const granted = computed(() => props.modelValue.filter((r) => r.level).length)

function pick(row, level) {
  if (props.disabled) return
  emit('update:modelValue', setRowLevel(props.modelValue, row.key, level))
}
function scope(row, value) {
  emit('update:modelValue', setRowScope(props.modelValue, row.key, value))
}
function fill(level) {
  emit('update:modelValue', props.modelValue.reduce((rows, r) => (r.has_dashboard ? setRowLevel(rows, r.key, level) : rows), props.modelValue))
}
</script>

<template>
  <div class="matrix" :class="{ disabled }">
    <div v-if="!disabled" class="tools">
      <span class="muted">{{ granted ? `Доступ к службам: ${granted}` : 'Доступ не выдан' }}</span>
      <span class="spacer" />
      <button class="btn btn-ghost btn-sm" type="button" @click="fill('viewer')">Просмотр всех дашбордов</button>
      <button class="btn btn-ghost btn-sm" type="button" :disabled="!granted" @click="fill('')">Снять доступ к дашбордам</button>
    </div>
    <div class="table-wrap frame">
      <table class="table table-compact">
        <thead>
          <tr>
            <th>Служба</th>
            <th v-for="c in ACCESS_COLUMNS" :key="c.value" class="lvl" :title="c.hint">{{ c.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in modelValue" :key="r.key" :class="{ granted: r.level, later: !r.has_dashboard }">
            <td>
              <div class="svc">
                <span class="svc-icon"><AppIcon :name="r.icon" :size="15" /></span>
                <div class="svc-text">
                  <span class="svc-title">{{ r.title }}</span>
                  <span v-if="!r.has_dashboard" class="svc-note">дашборд появится позже</span>
                  <label v-if="r.scopeAvailable" class="scope" :class="{ off: r.level !== 'viewer' || disabled }"
                         :title="r.level === 'viewer' ? 'Видны только данные подразделений пользователя' : 'Доступно для уровня «Просмотр»'">
                    <input type="checkbox" :checked="r.department_scope" :disabled="disabled || r.level !== 'viewer'" @change="scope(r, $event.target.checked)" />
                    <span>только свои подразделения</span>
                  </label>
                </div>
              </div>
            </td>
            <td v-for="c in ACCESS_COLUMNS" :key="c.value" class="lvl">
              <label class="radio" :title="`${c.label}: ${c.hint.toLowerCase()}`">
                <input type="radio" :class="{ none: !c.value }" :name="`${name}-${r.key}`" :value="c.value" :checked="r.level === c.value"
                       :disabled="disabled" :aria-label="`${r.title}: ${c.label}`" @change="pick(r, c.value)" />
              </label>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.matrix { display: flex; flex-direction: column; gap: 8px; }
.tools { display: flex; align-items: center; gap: 4px; min-height: 28px; font-size: var(--fs-sm); }
.frame { border: 1px solid var(--border); border-radius: var(--radius-lg); }
.table th.lvl, .table td.lvl { width: 86px; padding-left: 4px; padding-right: 4px; text-align: center; }
.table tbody tr:hover { background: var(--row-hover); }
.table tbody tr.granted { background: color-mix(in srgb, var(--brand) 3%, transparent); }
.svc { display: flex; align-items: flex-start; gap: 10px; min-width: 200px; }
.svc-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 8px; background: var(--surface-3); color: var(--muted); }
.granted .svc-icon { background: var(--brand-soft); color: var(--brand); }
.svc-text { display: flex; flex-direction: column; justify-content: center; min-height: 28px; line-height: 1.25; min-width: 0; }
.svc-title { font-weight: 560; }
.later .svc-title { color: var(--text-2); font-weight: 520; }
.svc-note { font-size: var(--fs-xs); color: var(--muted); }
.scope { display: inline-flex; align-items: center; gap: 6px; margin-top: 4px; font-size: var(--fs-xs); color: var(--text-2); cursor: pointer; }
.scope input { width: 14px; height: 14px; margin: 0; accent-color: var(--brand); }
.scope.off { color: var(--faint); cursor: default; }
.radio { display: flex; justify-content: center; align-items: center; height: 28px; cursor: pointer; }
.radio input {
  appearance: none; width: 17px; height: 17px; margin: 0; border-radius: 50%; cursor: pointer;
  border: 1.5px solid var(--border-strong); background: var(--surface); transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.radio input:hover:not(:disabled) { border-color: var(--faint); }
.radio input:checked { border-color: var(--brand); box-shadow: inset 0 0 0 3.5px var(--surface), inset 0 0 0 9px var(--brand); }
.radio input.none:checked { border-color: var(--faint); box-shadow: inset 0 0 0 3.5px var(--surface), inset 0 0 0 9px var(--faint); }
.radio input:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.disabled .frame { opacity: .5; }
.disabled .radio, .disabled .radio input { cursor: not-allowed; }
</style>
