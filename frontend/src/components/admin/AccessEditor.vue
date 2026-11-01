<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import DimensionControl from './DimensionControl.vue'
import EffectiveAccessCard from './EffectiveAccessCard.vue'
import UnitPicker from './UnitPicker.vue'
import {
  clearOverride, computeEffective, DIMENSIONS, dimensionView, grantViewAll, headedUnits, INDIVIDUAL_LABEL, LEVEL_HINTS,
  LEVEL_LABELS, LEVELS, MAX_DRILL_DEPTH, ORG_SCOPE_HINTS, ORG_SCOPE_SHORT, ORG_SCOPES, scopeUnits, scopeWarning, serviceView,
  setOverride, setServiceLevel, setServiceScope, startOverride,
} from '@/domain/access'
import { plural } from '@/utils/format'

/**
 * Доступ пользователя (ADR-0009): профиль доступа, личные значения измерений поверх профиля,
 * уровни служб, дополнительные подразделения — и живая сводка «Действующий доступ».
 * modelValue — черновик из policyDraft(); изменения приходят новым объектом.
 */
const props = defineProps({
  modelValue: { type: Object, required: true },
  profiles: { type: Array, default: () => [] },
  services: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
  userId: { type: Number, default: null },
  homeId: { type: Number, default: null },
  isAdmin: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  maxDepth: { type: Number, default: MAX_DRILL_DEPTH },
})
const emit = defineEmits(['update:modelValue'])

const draft = computed(() => props.modelValue)
const profile = computed(() => props.profiles.find((p) => p.id === draft.value.profileId) || null)
const inheritWord = computed(() => (profile.value ? 'Как в профиле' : 'По умолчанию'))
const locked = computed(() => props.disabled || props.isAdmin)

function update(patch) {
  if (!locked.value) emit('update:modelValue', { ...draft.value, ...patch })
}

// ---------- профиль ----------
function pickProfile(event) {
  const value = event.target.value
  update({ profileId: value === '' ? null : Number(value) })
}

// ---------- измерения ----------
const dimensions = computed(() => DIMENSIONS.map((d) => ({ ...d, view: dimensionView(d.key, draft.value.overrides, profile.value) })))
const personalCount = computed(() => dimensions.value.filter((d) => d.view.personal).length)
const startDim = (key) => update({ overrides: startOverride(draft.value.overrides, key, profile.value) })
const clearDim = (key) => update({ overrides: clearOverride(draft.value.overrides, key) })
const setDim = (key, value) => update({ overrides: setOverride(draft.value.overrides, key, value) })

// ---------- службы ----------
const showLater = ref(false)
const serviceRows = computed(() => props.services.map((s) => serviceView(s, draft.value, profile.value)))
const laterRows = computed(() => serviceRows.value.filter((r) => !r.has_dashboard))
const visibleRows = computed(() => serviceRows.value.filter((r) => r.has_dashboard || showLater.value || r.personal || r.level))
const hiddenLater = computed(() => laterRows.value.filter((r) => !r.personal && !r.level).length)
const personalServices = computed(() => serviceRows.value.filter((r) => r.personal).length)

function inheritedLevelText(row) {
  if (!profile.value) return 'Нет доступа'
  return `Как в профиле: ${row.profileLevel ? LEVEL_LABELS[row.profileLevel].toLowerCase() : 'нет'}`
}
const setLevel = (row, level) => update({ services: setServiceLevel(draft.value.services, row.key, level) })
const setScope = (row, scope) => update({ services: setServiceScope(draft.value.services, row.key, scope, profile.value) })
const viewAll = () => update({ services: grantViewAll(draft.value.services, props.services, profile.value) })
const resetServices = () => update({ services: {} })
const resetAll = () => update({ overrides: {}, services: {} })

// ---------- действующий доступ ----------
const serviceKeys = computed(() => props.services.map((s) => s.key))
const effective = computed(() => computeEffective({
  isAdmin: props.isAdmin, profile: profile.value, overrides: draft.value.overrides, services: draft.value.services, serviceKeys: serviceKeys.value,
}))
const effectiveScope = computed(() => effective.value.org_scope)
const units = computed(() => scopeUnits(props.departments, {
  userId: props.userId, homeId: props.homeId, extraIds: draft.value.extraUnitIds, scope: effectiveScope.value,
}))
const headed = computed(() => headedUnits(props.departments, props.userId))
const unitsNote = computed(() => {
  const own = Object.entries(effective.value.service_scopes || {})
  if (!own.length) return ''
  const titles = Object.fromEntries(props.services.map((s) => [s.key, s.short_title || s.title]))
  return `Своя область у служб: ${own.map(([k, v]) => `${titles[k] || k} — ${ORG_SCOPE_SHORT[v].toLowerCase()}`).join(', ')}`
})
const warning = computed(() => (props.isAdmin ? '' : scopeWarning({
  scopes: [effective.value.org_scope, ...Object.values(effective.value.service_scopes || {})],
  homeId: props.homeId, extraIds: draft.value.extraUnitIds, headedCount: headed.value.length,
})))
const home = computed(() => props.departments.find((d) => d.id === props.homeId) || null)
const servicesWord = (n) => plural(n, ['служба', 'службы', 'служб'])
</script>

<template>
  <div class="ae-wrap">
  <div class="access-editor" :class="{ locked }">
    <div class="main">
      <div v-if="isAdmin" class="admin-note">
        <AppIcon name="shield" :size="18" />
        <div><strong>Администратор имеет полный доступ</strong><p>Профиль и личные настройки начнут действовать, если снять роль «Администратор».</p></div>
      </div>

      <!-- Профиль доступа -->
      <section class="sect">
        <header class="sect-head">
          <h3>Профиль доступа</h3>
          <router-link to="/admin/access-profiles" class="link small">Все профили</router-link>
        </header>
        <select class="select profile-select" :value="draft.profileId ?? ''" :disabled="locked" aria-label="Профиль доступа" data-testid="access-profile" @change="pickProfile">
          <option value="">{{ INDIVIDUAL_LABEL }}</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <p class="sect-hint">{{ profile ? profile.description || 'Шаблон прав без описания' : 'Без профиля: как в версии 0.1.0 — вся компания, все данные, реестры и выгрузка; службы выдаются ниже.' }}</p>
      </section>

      <!-- Измерения -->
      <section class="sect">
        <header class="sect-head">
          <h3>Что видит</h3>
          <span class="sect-sub">{{ personalCount ? `Задано лично: ${personalCount} из ${DIMENSIONS.length}` : `Всё ${profile ? 'как в профиле' : 'по умолчанию'}` }}</span>
          <span class="spacer" />
          <button v-if="personalCount || personalServices" class="btn btn-ghost btn-sm" type="button" :disabled="locked" @click="resetAll">
            <AppIcon name="refresh" :size="13" />Вернуть всё {{ profile ? 'как в профиле' : 'по умолчанию' }}
          </button>
        </header>
        <ul class="dims">
          <li v-for="d in dimensions" :key="d.key" class="dim-row" :class="{ personal: d.view.personal }" :data-dimension="d.key">
            <div class="dim-title">
              <span class="dim-label">{{ d.label }}<span v-if="d.view.personal" class="personal-tag">лично</span></span>
              <span class="dim-hint">{{ d.hint }}</span>
            </div>
            <p v-if="!d.view.personal" class="inherited"><i />{{ inheritWord }}: <b>{{ d.view.inheritedText }}</b></p>
            <template v-else>
              <p class="was" :class="{ same: !d.view.differs }">
                {{ d.view.differs ? `${inheritWord}: ${d.view.inheritedText.toLowerCase()}` : `${profile ? 'Совпадает с профилем' : 'Совпадает со значением по умолчанию'} — измените` }}
              </p>
              <div class="dim-control">
                <DimensionControl :dimension="d.key" :model-value="d.view.value" :disabled="locked" :max-depth="maxDepth" :name="d.label"
                                  @update:model-value="(v) => setDim(d.key, v)" />
              </div>
            </template>
            <div class="dim-action">
              <button v-if="!d.view.personal" class="btn btn-sm" type="button" :disabled="locked" data-action="override" @click="startDim(d.key)"><AppIcon name="edit" :size="13" />Задать лично</button>
              <button v-else class="btn btn-sm btn-ghost" type="button" :disabled="locked" data-action="inherit"
                      :title="`Вернуть ${profile ? 'как в профиле' : 'по умолчанию'}: ${d.view.inheritedText.toLowerCase()}`" @click="clearDim(d.key)">
                <AppIcon name="refresh" :size="13" />Вернуть
              </button>
            </div>
          </li>
        </ul>
      </section>

      <!-- Службы -->
      <section class="sect">
        <header class="sect-head">
          <h3>Службы</h3>
          <span class="sect-sub">{{ Object.keys(effective.services).length ? `Доступ к ${Object.keys(effective.services).length} ${servicesWord(Object.keys(effective.services).length)}` : 'Доступ к службам не выдан' }}</span>
          <span class="spacer" />
          <button class="btn btn-ghost btn-sm" type="button" :disabled="locked" title="Службам с дашбордом без доступа — просмотр" @click="viewAll">Просмотр всех дашбордов</button>
          <button v-if="personalServices" class="btn btn-ghost btn-sm" type="button" :disabled="locked" @click="resetServices">{{ profile ? 'Как в профиле' : 'Снять все' }}</button>
        </header>
        <div class="svc-grid" role="table" aria-label="Уровни доступа к службам">
          <div class="svc-row svc-headrow" role="row">
            <span role="columnheader">Служба</span><span role="columnheader">Уровень</span><span role="columnheader" title="Область структуры для данных службы">Область</span>
          </div>
          <div v-for="r in visibleRows" :key="r.key" class="svc-row" role="row" :class="{ personal: r.personal, granted: r.level, later: !r.has_dashboard }" :data-service="r.key">
            <span class="svc-name" role="cell">
              <span class="svc-icon"><AppIcon :name="r.icon" :size="14" /></span>
              <span class="svc-text">
                <b :title="r.title">{{ r.has_dashboard ? r.short_title : r.title }}</b>
                <small v-if="r.personal && profile">лично · в профиле: {{ r.profileLevel ? LEVEL_LABELS[r.profileLevel].toLowerCase() : 'нет' }}</small>
                <small v-else-if="r.personal">задано лично</small>
                <small v-else-if="!r.has_dashboard">дашборд появится позже</small>
              </span>
            </span>
            <span role="cell">
              <select class="select select-sm" :class="{ chosen: r.personal }" :value="r.personalLevel" :disabled="locked" :aria-label="`${r.title}: уровень доступа`" @change="setLevel(r, $event.target.value)">
                <option value="">{{ inheritedLevelText(r) }}</option>
                <option v-if="profile" value="none" :title="LEVEL_HINTS.none">Нет доступа</option>
                <option v-for="l in LEVELS" :key="l" :value="l" :title="LEVEL_HINTS[l]">{{ LEVEL_LABELS[l] }}</option>
              </select>
            </span>
            <span role="cell">
              <select v-if="r.has_dashboard" class="select select-sm" :class="{ chosen: r.scope }" :value="r.scope" :disabled="locked || !r.level"
                      :title="r.level ? `Своя область структуры для данных службы; общая — ${ORG_SCOPE_SHORT[effectiveScope].toLowerCase()}` : 'Сначала выдайте доступ к службе'" :aria-label="`${r.title}: область`" @change="setScope(r, $event.target.value)">
                <option value="">Общая область</option>
                <option v-for="s in ORG_SCOPES" :key="s" :value="s" :title="ORG_SCOPE_HINTS[s]">{{ ORG_SCOPE_SHORT[s] }}</option>
              </select>
              <span v-else class="faint na">—</span>
            </span>
          </div>
        </div>
        <button v-if="hiddenLater" class="link-btn later-toggle" type="button" @click="showLater = !showLater">
          <AppIcon :name="showLater ? 'chevron-up' : 'chevron-down'" :size="13" />{{ showLater ? 'Скрыть службы без дашборда' : `Службы без дашборда (${hiddenLater})` }}
        </button>
      </section>

      <!-- Дополнительные подразделения -->
      <section class="sect">
        <header class="sect-head"><h3>Дополнительные подразделения</h3></header>
        <p class="sect-hint">
          Расширяют область: куратор, заместитель, проектный руководитель. Основное подразделение —
          <b v-if="home">{{ home.name }}</b><span v-else>не указано</span><template v-if="headed.length">; руководит: {{ headed.map((d) => d.name).join(', ') }}</template>.
        </p>
        <UnitPicker :model-value="draft.extraUnitIds" multiple :departments="departments" :exclude="homeId ? [homeId] : []" :disabled="locked"
                    placeholder="Добавить подразделение" label="Дополнительные подразделения" @update:model-value="(ids) => update({ extraUnitIds: ids })" />
      </section>
    </div>

    <aside class="side">
      <EffectiveAccessCard :effective="effective" :services="services" :units="units" :units-note="unitsNote" :warning="warning" />
    </aside>
  </div>
  </div>
</template>

<style scoped>
.ae-wrap { container-type: inline-size; }
.access-editor { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 22px; align-items: start; }
.main { display: flex; flex-direction: column; gap: 22px; min-width: 0; }
.side { position: sticky; top: 0; }
.admin-note { display: flex; gap: 12px; padding: 14px 16px; border-radius: 12px; background: var(--brand-soft); color: var(--brand); }
.admin-note strong { color: var(--text); }
.admin-note p { margin-top: 2px; font-size: var(--fs-sm); color: var(--text-2); }
.locked .sect { opacity: .62; }
.sect { display: flex; flex-direction: column; gap: 8px; }
.sect-head { display: flex; align-items: center; gap: 4px 10px; flex-wrap: wrap; min-height: 28px; }
.sect-head h3 { font-size: var(--fs-base); font-weight: 650; }
.sect-sub { font-size: var(--fs-xs); color: var(--muted); }
.sect-hint { font-size: var(--fs-sm); color: var(--muted); line-height: 1.45; }
.sect-hint b { color: var(--text-2); font-weight: 600; }
.small { font-size: var(--fs-sm); margin-left: auto; }
.profile-select { max-width: 420px; }

.dims { list-style: none; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.dim-row {
  display: grid; grid-template-columns: minmax(150px, 190px) minmax(0, 1fr) auto; grid-template-areas: 'title value action';
  gap: 8px 14px; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border); transition: background var(--t-fast);
}
.dim-row.personal { grid-template-areas: 'title value action' 'title control control'; }
.dim-title { grid-area: title; align-self: start; padding-top: 3px; }
.inherited, .was { grid-area: value; }
.dim-control { grid-area: control; min-width: 0; }
.dim-action { grid-area: action; justify-self: end; }
.dim-row:last-child { border-bottom: 0; }
.dim-row.personal { background: color-mix(in srgb, var(--accent) 4%, var(--surface)); box-shadow: inset 3px 0 0 var(--accent); }
.dim-title { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.dim-label { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: var(--fs-sm); color: var(--text); }
.dim-hint { font-size: var(--fs-xs); color: var(--muted); }
.personal-tag { padding: 0 6px; border-radius: 99px; background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--accent); font-size: 10.5px; font-weight: 650; line-height: 17px; }
.inherited { min-width: 0; font-size: var(--fs-sm); color: var(--muted); line-height: 1.4; }
.inherited i { display: inline-block; width: 6px; height: 6px; margin-right: 7px; border-radius: 50%; background: var(--faint); vertical-align: 1px; }
.inherited b { color: var(--text); font-weight: 560; }
.was { font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.was.same { color: var(--faint); }
.link-btn { display: inline-flex; align-items: center; gap: 4px; padding: 0; border: 0; background: none; color: var(--accent); font-size: var(--fs-xs); font-weight: 540; cursor: pointer; }
.link-btn:hover:not(:disabled) { text-decoration: underline; }
.link-btn:disabled { color: var(--faint); cursor: not-allowed; }

.svc-grid { border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.svc-row { display: grid; grid-template-columns: minmax(0, 1fr) 196px 176px; gap: 10px; align-items: center; padding: 7px 12px; border-bottom: 1px solid var(--border); }
.svc-row:last-child { border-bottom: 0; }
.svc-headrow { padding-top: 8px; padding-bottom: 8px; background: var(--surface-2); font-size: var(--fs-xs); font-weight: 620; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.svc-row.granted:not(.svc-headrow) { background: color-mix(in srgb, var(--brand) 2.5%, transparent); }
.svc-name { display: flex; align-items: center; gap: 10px; min-width: 0; }
.svc-icon { width: 26px; height: 26px; flex: 0 0 26px; display: grid; place-items: center; border-radius: 8px; background: var(--surface-3); color: var(--muted); }
.granted .svc-icon { background: var(--brand-soft); color: var(--brand); }
.svc-text { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.svc-text b { font-weight: 560; font-size: var(--fs-sm); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.later .svc-text b { color: var(--text-2); font-weight: 520; }
.svc-text small { font-size: var(--fs-xs); color: var(--muted); }
.personal .svc-text small { color: var(--accent); }
.select.chosen { border-color: color-mix(in srgb, var(--accent) 55%, var(--border-strong)); background-color: color-mix(in srgb, var(--accent) 5%, var(--surface)); font-weight: 560; }
.na { padding-left: 12px; }
.later-toggle { align-self: flex-start; font-size: var(--fs-sm); }

@container (max-width: 820px) {
  .access-editor { grid-template-columns: minmax(0, 1fr); }
  .side { position: static; }
}
@container (max-width: 560px) {
  .dim-row { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: 'title action' 'value value'; }
  .dim-row.personal { grid-template-areas: 'title action' 'value value' 'control control'; }
  .svc-row { grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 10px 12px; }
  .svc-row .svc-name { grid-column: 1 / -1; }
  .svc-headrow { display: none; }
}
</style>
