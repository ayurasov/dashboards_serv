<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ProfileEditor from '@/components/admin/ProfileEditor.vue'
import ProfileComparison from '@/components/admin/ProfileComparison.vue'
import { accessApi } from '@/api/access'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { profileFacts } from '@/domain/access'
import { plural } from '@/utils/format'

/** Профили доступа (ADR-0009): шаблоны прав, их сравнение, создание, изменение и удаление. */
const meta = useAsync(() => accessApi.meta())
const { data, loading, reload } = useAsync(() => accessApi.profiles())
const profiles = computed(() => data.value || [])
const services = computed(() => meta.data.value?.services || [])
const usersWord = (n) => plural(n, ['пользователь', 'пользователя', 'пользователей'])

const editing = ref(null) // null — закрыто, {} — новый, профиль — изменение
function edit(profile) {
  editing.value = profile ? { profile } : { profile: null }
}
function editById(id) {
  const profile = profiles.value.find((p) => p.id === id)
  if (profile) edit(profile)
}
function afterSave(saved) {
  toastOk(editing.value?.profile ? `Профиль «${saved.name}» сохранён` : `Профиль «${saved.name}» создан`)
  editing.value = null
  reload()
}

async function remove(profile) {
  const ok = await confirm({
    title: `Удалить профиль «${profile.name}»?`,
    message: profile.users_count
      ? `Профиль назначен: ${profile.users_count} ${usersWord(profile.users_count)}. Сервер не удалит его, пока им не назначен другой профиль.`
      : 'Профиль никому не назначен. Удалить его можно без последствий.',
    confirmText: 'Удалить', danger: true,
  })
  if (!ok) return
  try {
    const result = await accessApi.deleteProfile(profile.id)
    toastOk(result?.message || 'Профиль удалён')
    reload()
  } catch {
    // Сообщение сервера (встроенный или назначен пользователям) уже показано
  }
}
</script>

<template>
  <div class="page">
    <PageHeader title="Профили доступа" description="Шаблоны прав для уровней сотрудников — от первого лица до рядового сотрудника">
      <router-link to="/admin/users" class="btn"><AppIcon name="users" :size="15" />Пользователи</router-link>
      <button class="btn btn-primary" type="button" :disabled="!meta.data.value" data-testid="profile-add" @click="edit(null)"><AppIcon name="plus" :size="15" />Создать профиль</button>
    </PageHeader>

    <div class="explain card">
      <span class="ex-icon"><AppIcon name="layers" :size="18" /></span>
      <p>
        <b>Доступ пользователя = профиль + личные настройки.</b>
        Профиль задаёт область структуры, классы данных, глубину детализации, исходные записи, выгрузку и уровни служб;
        в карточке пользователя любое из этих значений можно задать лично — личное значение перекрывает профиль, остальное берётся из него.
      </p>
    </div>

    <div v-if="loading && !data" class="cards"><div v-for="i in 5" :key="i" class="card skeleton" style="height: 300px" /></div>
    <EmptyState v-else-if="data && !profiles.length" icon="shield" title="Профилей нет" text="Создайте первый профиль доступа." />
    <div v-else class="cards">
      <article v-for="p in profiles" :key="p.id" class="card pcard" :data-profile="p.key">
        <header class="p-head">
          <div class="p-titles">
            <h2>{{ p.name }}</h2>
            <span class="p-key">{{ p.key }}</span>
          </div>
          <span v-if="p.is_system" class="badge" title="Встроенный профиль: изменяется, но не удаляется">встроенный</span>
        </header>
        <p class="p-desc" :title="p.description">{{ p.description || 'Без описания' }}</p>
        <dl class="facts">
          <div v-for="fact in profileFacts(p, services)" :key="fact.key" :class="{ off: fact.off }">
            <dt>{{ fact.label }}</dt><dd>{{ fact.text }}</dd>
          </div>
        </dl>
        <footer class="p-foot">
          <router-link :to="{ path: '/admin/users', query: { profile: String(p.id) } }" class="users-link" :class="{ zero: !p.users_count }" :title="`Пользователи с профилем «${p.name}»`">
            <AppIcon name="users" :size="14" />{{ p.users_count }} {{ usersWord(p.users_count) }}
          </router-link>
          <span class="spacer" />
          <button class="btn btn-sm" type="button" :disabled="!meta.data.value" @click="edit(p)"><AppIcon name="edit" :size="13" />Изменить</button>
          <button class="btn btn-sm btn-ghost btn-danger btn-icon" type="button" :disabled="p.is_system"
                  :title="p.is_system ? 'Встроенный профиль удалить нельзя — его можно изменить' : 'Удалить профиль'" :aria-label="`Удалить профиль «${p.name}»`" @click="remove(p)">
            <AppIcon name="trash" :size="14" />
          </button>
        </footer>
      </article>
    </div>

    <section v-if="profiles.length && services.length" class="card">
      <header class="card-head">
        <h3>Сравнение профилей</h3>
        <span class="hint">Кто что видит; последний столбец — пользователи без профиля</span>
      </header>
      <div class="card-body flush"><ProfileComparison :profiles="profiles" :services="services" @edit="editById" /></div>
    </section>

    <ProfileEditor v-if="editing" :profile="editing.profile" :services="services" :max-depth="meta.data.value?.max_drill_depth ?? 9"
                   @close="editing = null" @saved="afterSave" />
  </div>
</template>

<style scoped>
.explain { display: flex; gap: 14px; align-items: flex-start; padding: 14px 18px; background: color-mix(in srgb, var(--accent) 5%, var(--surface)); border-color: color-mix(in srgb, var(--accent) 22%, var(--border)); }
.ex-icon { width: 34px; height: 34px; flex: 0 0 34px; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }
.explain p { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.55; max-width: 980px; }
.explain b { color: var(--text); font-weight: 650; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: var(--sp-4); }
.pcard { display: flex; flex-direction: column; gap: 10px; padding: 18px 18px 14px; transition: box-shadow var(--t), border-color var(--t); }
.pcard:hover { box-shadow: var(--shadow); border-color: var(--border-strong); }
.p-head { display: flex; align-items: flex-start; gap: 10px; }
.p-titles { flex: 1; min-width: 0; }
.p-head h2 { font-size: var(--fs-md); line-height: 1.3; }
.p-key { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--faint); }
.p-desc { font-size: var(--fs-sm); color: var(--muted); line-height: 1.45; min-height: 4.35em; display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.p-foot .btn-danger:disabled { color: var(--faint); opacity: .45; }
.facts { margin: 0; display: flex; flex-direction: column; border-top: 1px dashed var(--border); padding-top: 6px; }
.facts div { display: grid; grid-template-columns: 76px minmax(0, 1fr); gap: 10px; padding: 4px 0; font-size: var(--fs-sm); }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; color: var(--text); font-weight: 540; }
.facts .off dd { color: var(--muted); font-weight: 500; }
.p-foot { display: flex; align-items: center; gap: 6px; margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border); }
.users-link { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 560; color: var(--accent); }
.users-link:hover { text-decoration: underline; }
.users-link.zero { color: var(--muted); }
.flush { padding: 12px 0 0; }
</style>
