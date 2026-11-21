<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import { DIRECTION_LABELS } from '@/utils/lights'

/** Кнопка «?» рядом с показателем: определение, направление и база сравнения (глоссарий 0.5.0).
 *  about — { description, direction } из API; unit и deltaBase — для полноты картины. */
const props = defineProps({
  label: { type: String, required: true },
  about: { type: Object, default: null },
  unit: { type: String, default: '' },
  deltaBase: { type: String, default: 'к прошлому периоду' },
})
const open = ref(false)
const direction = () => DIRECTION_LABELS[props.about?.direction] || ''
</script>

<template>
  <template v-if="about && (about.description || direction())">
    <button class="glossary" type="button" :aria-label="`О показателе «${label}»`" :title="`О показателе «${label}»`"
            @click.stop="open = true">
      <AppIcon name="help" :size="13" :stroke="2.2" />
    </button>
    <AppModal v-if="open" :title="label" :width="420" @close="open = false">
      <div class="about">
        <p v-if="about.description">{{ about.description }}</p>
        <dl>
          <div v-if="unit"><dt>Единица</dt><dd>{{ unit }}</dd></div>
          <div v-if="direction()"><dt>Направление</dt><dd>{{ direction() }}</dd></div>
          <div><dt>Динамика</dt><dd>изменение {{ deltaBase }}; стрелка у значения — динамика, значок — статус по порогам светофора</dd></div>
        </dl>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="open = false">Закрыть</button>
      </template>
    </AppModal>
  </template>
</template>

<style scoped>
.glossary { display: inline-grid; place-items: center; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 50%; background: transparent; color: var(--muted); cursor: pointer; flex: 0 0 20px; }
.glossary:hover { background: var(--surface-3); color: var(--text); }
.about p { margin: 0 0 12px; line-height: 1.55; }
.about dl { margin: 0; display: flex; flex-direction: column; gap: 8px; }
.about dl div { display: grid; grid-template-columns: 110px 1fr; gap: 10px; }
.about dt { color: var(--muted); font-size: var(--fs-sm); }
.about dd { margin: 0; font-size: var(--fs-sm); line-height: 1.5; }
</style>
