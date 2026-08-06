<template>
  <div class="card" style="max-width:520px;margin:48px auto;text-align:center">
    <div style="font-size:34px;line-height:1">🔒</div>
    <h2 style="margin:12px 0 6px">Нет доступа</h2>
    <p style="color:var(--c-muted);font-size:.85rem;margin-bottom:16px">
      У вас нет прав на просмотр этого раздела. Обратитесь к администратору,
      чтобы получить доступ к нужной службе.
    </p>
    <router-link to="/profile" class="btn btn-g">Мой профиль</router-link>
  </div>
</template>
