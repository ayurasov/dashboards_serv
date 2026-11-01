<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { deniedServices, effectiveRows, INDIVIDUAL_LABEL } from '@/domain/access'
import { plural } from '@/utils/format'

/**
 * «Действующий доступ»: что получается из профиля и личных настроек — службы и уровни, область,
 * классы данных, глубина, записи, выгрузка; у каждого значения — источник («из профиля «…»»,
 * «задано лично», «по умолчанию»). units — подразделения области (null — вся компания).
 */
const props = defineProps({
  effective: { type: Object, default: null },
  services: { type: Array, default: () => [] },
  units: { type: Array, default: undefined },
  unitsNote: { type: String, default: '' },
  warning: { type: String, default: '' },
  title: { type: String, default: 'Действующий доступ' },
  subtitle: { type: String, default: 'Так система работает для пользователя' },
})

const rows = computed(() => effectiveRows(props.effective, props.services))
const denied = computed(() => deniedServices(props.effective, props.services))
const profile = computed(() => (props.effective?.is_admin ? 'Администратор' : props.effective?.profile_name || INDIVIDUAL_LABEL))
const UNITS_SHOWN = 4
const allUnits = ref(false)
const shownUnits = computed(() => (allUnits.value ? props.units : (props.units || []).slice(0, UNITS_SHOWN)) || [])
const parentOf = (u) => String(u.path).split(' / ').slice(0, -1).join(' / ')
const unitsWord = (n) => plural(n, ['подразделение', 'подразделения', 'подразделений'])
</script>

<template>
  <section class="effective" data-testid="effective-access" aria-live="polite">
    <header class="eff-head">
      <span class="eff-icon"><AppIcon name="shield" :size="16" /></span>
      <div>
        <h3>{{ title }}</h3>
        <p>{{ subtitle }}</p>
      </div>
    </header>

    <div v-if="effective?.is_admin" class="admin-note">
      <AppIcon name="shield" :size="15" />Администратор: полный доступ ко всем службам, данным и настройкам
    </div>

    <template v-else-if="effective">
      <div class="block">
        <span class="k">Профиль</span>
        <span class="v">{{ profile }}</span>
      </div>

      <div class="block">
        <span class="k">Службы</span>
        <ul v-if="rows.services.length || denied.length" class="svc">
          <li v-for="s in rows.services" :key="s.key" :class="`src-${s.source}`">
            <span class="svc-name">{{ s.short_title }}</span>
            <span class="svc-level">{{ s.levelText }}<small v-if="s.scopeText"> · {{ s.scopeText.toLowerCase() }}</small></span>
            <span class="src" :title="s.sourceText"><i />{{ s.sourceText }}</span>
          </li>
          <li v-for="s in denied" :key="`deny-${s.key}`" class="denied src-personal">
            <span class="svc-name">{{ s.title }}</span>
            <span class="svc-level">Нет доступа</span>
            <span class="src"><i />задано лично</span>
          </li>
        </ul>
        <p v-else class="none"><AppIcon name="alert" :size="13" />Нет доступа ни к одной службе</p>
      </div>

      <div v-for="d in rows.dimensions" :key="d.key" class="block" :class="`src-${d.source}`" :data-dimension="d.key">
        <span class="k">{{ d.label }}</span>
        <span class="v">{{ d.valueText }}</span>
        <span class="src"><i />{{ d.sourceText }}</span>
        <template v-if="d.key === 'org_scope'">
          <div v-if="units === null" class="units-line muted">Все подразделения компании</div>
          <div v-else-if="units" class="units">
            <span class="units-count">{{ units.length ? `${units.length} ${unitsWord(units.length)}` : 'Подразделений нет' }}</span>
            <ul v-if="units.length">
              <li v-for="u in shownUnits" :key="u.id" :title="u.path"><b>{{ u.name }}</b><small v-if="parentOf(u)">{{ parentOf(u) }}</small></li>
            </ul>
            <button v-if="units.length > UNITS_SHOWN" type="button" class="more" @click="allUnits = !allUnits">
              {{ allUnits ? 'Свернуть' : `Ещё ${units.length - UNITS_SHOWN}` }}
            </button>
          </div>
          <p v-if="unitsNote" class="units-line muted">{{ unitsNote }}</p>
        </template>
      </div>
    </template>

    <p v-if="warning" class="warn" role="note"><AppIcon name="alert" :size="14" /><span>{{ warning }}</span></p>
  </section>
</template>

<style scoped>
.effective { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px 16px; border-radius: var(--radius-lg); background: var(--surface-2); border: 1px solid var(--border); }
.eff-head { display: flex; align-items: flex-start; gap: 10px; padding-bottom: 10px; margin-bottom: 4px; border-bottom: 1px solid var(--border); }
.eff-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 8px; background: var(--brand-soft); color: var(--brand); }
.eff-head h3 { font-size: var(--fs-base); font-weight: 650; }
.eff-head p { font-size: var(--fs-xs); color: var(--muted); }
.admin-note { display: flex; gap: 8px; align-items: flex-start; padding: 8px 0; font-size: var(--fs-sm); color: var(--text-2); }
.admin-note :deep(svg) { flex: 0 0 auto; margin-top: 2px; color: var(--brand); }
.block { display: flex; flex-direction: column; gap: 1px; padding: 8px 0; border-bottom: 1px dashed var(--border); }
.block:last-of-type { border-bottom: 0; }
.k { font-size: 10.5px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; color: var(--faint); }
.v { font-size: var(--fs-sm); font-weight: 600; color: var(--text); line-height: 1.35; }
.src { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--muted); line-height: 1.3; }
.src i { width: 6px; height: 6px; flex: 0 0 6px; border-radius: 50%; background: var(--border-strong); }
.src-personal .src { color: var(--accent); }
.src-personal .src i { background: var(--accent); }
.src-profile .src i { background: var(--faint); }
.src-admin .src i { background: var(--brand); }
.svc { list-style: none; margin: 3px 0 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.svc li { display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 8px; font-size: var(--fs-sm); }
.svc-name { color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.svc-level { font-weight: 600; color: var(--text); text-align: right; white-space: nowrap; }
.svc-level small { font-weight: 500; color: var(--muted); }
.svc .src { grid-column: 1 / -1; }
.svc li.denied .svc-name { text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--light-red) 60%, transparent); }
.svc li.denied .svc-level { color: var(--light-red); }
.none { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.units { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.units-count { font-size: var(--fs-xs); font-weight: 600; color: var(--text-2); }
.units ul { list-style: none; margin: 0; padding: 0 0 0 10px; border-left: 2px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.units li { display: flex; flex-direction: column; line-height: 1.25; min-width: 0; }
.units li b { font-size: var(--fs-sm); font-weight: 560; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.units li small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.units-line { margin-top: 4px; font-size: var(--fs-xs); }
.more { align-self: flex-start; padding: 0; border: 0; background: none; color: var(--accent); font-size: var(--fs-xs); cursor: pointer; }
.more:hover { text-decoration: underline; }
.warn { display: flex; gap: 8px; align-items: flex-start; margin-top: 8px; padding: 9px 11px; border-radius: var(--radius); font-size: var(--fs-xs); line-height: 1.45;
  background: color-mix(in srgb, var(--light-yellow) 12%, var(--surface)); border: 1px solid color-mix(in srgb, var(--light-yellow) 35%, var(--border)); color: var(--text-2); }
.warn :deep(svg) { flex: 0 0 auto; margin-top: 1px; color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
</style>
