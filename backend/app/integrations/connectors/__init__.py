"""Встроенные коннекторы. Модуль коннектора регистрирует свой класс декоратором @register при импорте —
добавьте сюда импорт нового модуля (podelu, puls, jira, confluence, bitrix24, exchange, onec)."""
from . import bitrix24, confluence, exchange, folder, jira, onec, podelu, puls  # noqa: F401
