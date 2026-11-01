"""Структура компании, вход по домену, модель доступа 2.0 (версия 0.2.0).

- departments — дерево: parent_id, kind, sort_order, external_id, org_source, name_key;
  имена уникальны среди соседей (частичные индексы), код необязателен;
- department_heads — руководители подразделений с основным;
- users: основное подразделение, явный руководитель, «первое лицо», внешний идентификатор,
  способ входа (local/ldap) и связь с каталогом, профиль доступа и личные настройки,
  полномочия администрирования (org.manage, users.manage);
  password_hash может быть пустым (учётная запись домена или «без доступа»);
- user_departments → user_access_units: первое по алфавиту подразделение пользователя становится
  основным, остальные — дополнительными подразделениями области доступа;
- service_access: уровень «none», вместо department_scope — org_scope
  (department_scope = true → 'branch');
- access_profiles, app_settings, org_revision.

Доступ существующих пользователей не меняется: профиль не назначен («индивидуальная настройка»).

Revision ID: 0014_org_access
Revises: 0013_data_revisions
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0014_org_access"
down_revision = "0013_data_revisions"
branch_labels = None
depends_on = None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _name_key(value: str) -> str:
    return " ".join((value or "").split()).casefold()


def upgrade() -> None:
    bind = op.get_bind()
    now = _now()

    op.create_table(
        "access_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("service_levels", sa.JSON(), nullable=False),
        sa.Column("org_scope", sa.String(16), nullable=False),
        sa.Column("data_classes", sa.JSON(), nullable=False),
        sa.Column("drill_depth", sa.Integer(), nullable=True),
        sa.Column("can_view_records", sa.Boolean(), nullable=False),
        sa.Column("can_export", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_access_profiles"),
        sa.UniqueConstraint("key", name="uq_access_profiles_key"),
        sa.UniqueConstraint("name", name="uq_access_profiles_name"),
        sa.CheckConstraint("org_scope IN ('company', 'branch', 'unit')", name="ck_access_profiles_org_scope"),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("key", name="pk_app_settings"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], name="fk_app_settings_updated_by_id_users",
                                ondelete="SET NULL"),
    )
    op.create_table(
        "org_revision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_org_revision"),
    )
    op.execute(sa.text("INSERT INTO org_revision (id, revision, updated_at) VALUES (1, 0, :now)").bindparams(now=now))

    # ---------------------------------------------------------------- departments
    with op.batch_alter_table("departments") as batch:
        batch.add_column(sa.Column("name_key", sa.String(200), nullable=True))
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("kind", sa.String(32), nullable=True))
        batch.add_column(sa.Column("sort_order", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("external_id", sa.String(200), nullable=True))
        batch.add_column(sa.Column("org_source", sa.String(20), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch.alter_column("code", existing_type=sa.String(50), nullable=True)
        batch.drop_constraint("uq_departments_name", type_="unique")

    departments = sa.table("departments", sa.column("id", sa.Integer), sa.column("name", sa.String),
                           sa.column("name_key", sa.String), sa.column("kind", sa.String),
                           sa.column("sort_order", sa.Integer), sa.column("org_source", sa.String),
                           sa.column("updated_at", sa.DateTime), sa.column("created_at", sa.DateTime))
    for row in bind.execute(sa.select(departments.c.id, departments.c.name, departments.c.created_at)).all():
        name = " ".join((row.name or "").split())
        bind.execute(departments.update().where(departments.c.id == row.id).values(
            name=name, name_key=_name_key(name), kind="department", sort_order=0, org_source="manual",
            updated_at=row.created_at or now))

    with op.batch_alter_table("departments") as batch:
        batch.alter_column("name_key", existing_type=sa.String(200), nullable=False)
        batch.alter_column("kind", existing_type=sa.String(32), nullable=False)
        batch.alter_column("sort_order", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("org_source", existing_type=sa.String(20), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)
        batch.create_foreign_key("fk_departments_parent_id_departments", "departments", ["parent_id"], ["id"],
                                 ondelete="RESTRICT")
        batch.create_index("ix_departments_parent_id", ["parent_id"])
        batch.create_index("ix_departments_external_id", ["external_id"])
    op.create_index("uq_departments_root_name", "departments", ["name_key"], unique=True,
                    sqlite_where=sa.text("parent_id IS NULL"), postgresql_where=sa.text("parent_id IS NULL"))
    op.create_index("uq_departments_sibling_name", "departments", ["parent_id", "name_key"], unique=True,
                    sqlite_where=sa.text("parent_id IS NOT NULL"), postgresql_where=sa.text("parent_id IS NOT NULL"))

    op.create_table(
        "department_heads",
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("department_id", "user_id", name="pk_department_heads"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"],
                                name="fk_department_heads_department_id_departments", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_department_heads_user_id_users",
                                ondelete="CASCADE"),
    )
    op.create_index("ix_department_heads_user_id", "department_heads", ["user_id"])
    op.create_index("uq_department_heads_primary", "department_heads", ["department_id"], unique=True,
                    sqlite_where=sa.text("is_primary"), postgresql_where=sa.text("is_primary"))

    # ---------------------------------------------------------------- users
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("manager_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("reports_to_none", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("external_id", sa.String(200), nullable=True))
        batch.add_column(sa.Column("org_source", sa.String(20), nullable=True))
        batch.add_column(sa.Column("auth_source", sa.String(10), nullable=True))
        batch.add_column(sa.Column("auth_external_id", sa.String(200), nullable=True))
        batch.add_column(sa.Column("auth_linked_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("access_profile_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("access_overrides", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("capabilities", sa.JSON(), nullable=True))
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)

    users = sa.table("users", sa.column("id", sa.Integer), sa.column("department_id", sa.Integer),
                     sa.column("reports_to_none", sa.Boolean), sa.column("auth_source", sa.String),
                     sa.column("access_overrides", sa.JSON), sa.column("capabilities", sa.JSON))
    bind.execute(users.update().values(reports_to_none=False, auth_source="local", access_overrides={},
                                       capabilities=[]))

    # Основное подразделение — первое по алфавиту из прежних; остальные — дополнительная область доступа
    links = bind.execute(sa.text(
        "SELECT ud.user_id, ud.department_id FROM user_departments ud "
        "JOIN departments d ON d.id = ud.department_id ORDER BY ud.user_id, d.name_key")).all()
    home: dict[int, int] = {}
    extra: list[dict] = []
    for user_id, department_id in links:
        if user_id not in home:
            home[user_id] = department_id
        else:
            extra.append({"user_id": user_id, "department_id": department_id})
    for user_id, department_id in home.items():
        bind.execute(users.update().where(users.c.id == user_id).values(department_id=department_id))

    with op.batch_alter_table("users") as batch:
        batch.alter_column("reports_to_none", existing_type=sa.Boolean(), nullable=False)
        batch.alter_column("auth_source", existing_type=sa.String(10), nullable=False)
        batch.alter_column("access_overrides", existing_type=sa.JSON(), nullable=False)
        batch.alter_column("capabilities", existing_type=sa.JSON(), nullable=False)
        batch.create_foreign_key("fk_users_department_id_departments", "departments", ["department_id"], ["id"],
                                 ondelete="SET NULL")
        batch.create_foreign_key("fk_users_manager_id_users", "users", ["manager_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_users_access_profile_id_access_profiles", "access_profiles",
                                 ["access_profile_id"], ["id"], ondelete="RESTRICT")
        batch.create_unique_constraint("uq_users_auth_external_id", ["auth_external_id"])
        batch.create_check_constraint("ck_users_auth_source", "auth_source IN ('local', 'ldap')")
        batch.create_index("ix_users_department_id", ["department_id"])
        batch.create_index("ix_users_manager_id", ["manager_id"])
        batch.create_index("ix_users_external_id", ["external_id"])
        batch.create_index("ix_users_access_profile_id", ["access_profile_id"])

    access_units = op.create_table(
        "user_access_units",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "department_id", name="pk_user_access_units"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_access_units_user_id_users",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"],
                                name="fk_user_access_units_department_id_departments", ondelete="CASCADE"),
    )
    if extra:
        op.bulk_insert(access_units, extra)
    op.drop_table("user_departments")

    # ---------------------------------------------------------------- service_access
    with op.batch_alter_table("service_access") as batch:
        batch.add_column(sa.Column("org_scope", sa.String(16), nullable=True))
    op.execute("UPDATE service_access SET org_scope = 'branch' WHERE department_scope")
    with op.batch_alter_table("service_access") as batch:
        batch.drop_column("department_scope")
        batch.drop_constraint("ck_service_access_level", type_="check")
        batch.create_check_constraint("ck_service_access_level", "level IN ('none', 'viewer', 'editor', 'manager')")
        batch.create_check_constraint("ck_service_access_org_scope",
                                      "org_scope IS NULL OR org_scope IN ('company', 'branch', 'unit')")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM service_access WHERE level = 'none'")).scalar():
        op.execute("DELETE FROM service_access WHERE level = 'none'")
    with op.batch_alter_table("service_access") as batch:
        batch.add_column(sa.Column("department_scope", sa.Boolean(), nullable=True))
    op.execute("UPDATE service_access SET department_scope = (org_scope IS NOT NULL AND org_scope <> 'company')")
    with op.batch_alter_table("service_access") as batch:
        batch.alter_column("department_scope", existing_type=sa.Boolean(), nullable=False)
        batch.drop_constraint("ck_service_access_org_scope", type_="check")
        batch.drop_constraint("ck_service_access_level", type_="check")
        batch.create_check_constraint("ck_service_access_level", "level IN ('viewer', 'editor', 'manager')")
        batch.drop_column("org_scope")

    user_departments = op.create_table(
        "user_departments",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "department_id", name="pk_user_departments"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_departments_user_id_users",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"],
                                name="fk_user_departments_department_id_departments", ondelete="CASCADE"),
    )
    rows = {(r.user_id, r.department_id) for r in bind.execute(sa.text(
        "SELECT user_id, department_id FROM user_access_units UNION "
        "SELECT id AS user_id, department_id FROM users WHERE department_id IS NOT NULL")).all()}
    if rows:
        op.bulk_insert(user_departments, [{"user_id": u, "department_id": d} for u, d in sorted(rows)])
    op.drop_table("user_access_units")

    # Учётные записи без пароля (домен, «без доступа») получают непригодный для входа хеш
    op.execute("UPDATE users SET password_hash = '!' WHERE password_hash IS NULL")
    with op.batch_alter_table("users") as batch:
        for index in ("ix_users_department_id", "ix_users_manager_id", "ix_users_external_id",
                      "ix_users_access_profile_id"):
            batch.drop_index(index)
        batch.drop_constraint("fk_users_department_id_departments", type_="foreignkey")
        batch.drop_constraint("fk_users_manager_id_users", type_="foreignkey")
        batch.drop_constraint("fk_users_access_profile_id_access_profiles", type_="foreignkey")
        batch.drop_constraint("uq_users_auth_external_id", type_="unique")
        batch.drop_constraint("ck_users_auth_source", type_="check")
        for column in ("department_id", "manager_id", "reports_to_none", "external_id", "org_source", "auth_source",
                       "auth_external_id", "auth_linked_at", "access_profile_id", "access_overrides", "capabilities"):
            batch.drop_column(column)
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)

    op.drop_table("department_heads")
    op.drop_index("uq_departments_sibling_name", table_name="departments")
    op.drop_index("uq_departments_root_name", table_name="departments")
    # Плоский справочник: дерево и дубли имён в разных ветках не сохраняются
    op.execute("UPDATE departments SET parent_id = NULL")
    for row in bind.execute(sa.text(
            "SELECT id, name FROM departments WHERE name IN "
            "(SELECT name FROM departments GROUP BY name HAVING COUNT(*) > 1) ORDER BY id")).all():
        bind.execute(sa.text("UPDATE departments SET name = :name WHERE id = :id").bindparams(
            name=f"{row.name} ({row.id})", id=row.id))
    op.execute("UPDATE departments SET code = 'D' || CAST(id AS VARCHAR(20)) WHERE code IS NULL")
    with op.batch_alter_table("departments") as batch:
        batch.drop_index("ix_departments_parent_id")
        batch.drop_index("ix_departments_external_id")
        batch.drop_constraint("fk_departments_parent_id_departments", type_="foreignkey")
        for column in ("name_key", "parent_id", "kind", "sort_order", "external_id", "org_source", "updated_at"):
            batch.drop_column(column)
        batch.alter_column("code", existing_type=sa.String(50), nullable=False)
        batch.create_unique_constraint("uq_departments_name", ["name"])

    op.drop_table("org_revision")
    op.drop_table("app_settings")
    op.drop_table("access_profiles")
