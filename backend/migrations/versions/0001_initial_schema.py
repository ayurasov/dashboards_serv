"""Initial schema — baseline migration for all tables that existed before
Alembic was introduced.  Each CREATE TABLE is guarded by has_table() so this
migration is safe to run against an already-populated database.

Revision ID: 0001_initial_schema
Revises:     (none — this is the root migration)
Create Date: 2026-08-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:

    if not _exists('departments'):
        op.create_table(
            'departments',
            sa.Column('id',   sa.Integer(),     primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(200),   nullable=False),
            sa.Column('code', sa.String(20),    nullable=False, unique=True),
        )

    if not _exists('users'):
        op.create_table(
            'users',
            sa.Column('id',                   sa.Integer(),     primary_key=True, autoincrement=True),
            sa.Column('username',             sa.String(80),    nullable=False, unique=True),
            sa.Column('full_name',            sa.String(200),   nullable=True),
            sa.Column('email',                sa.String(200),   nullable=True),
            sa.Column('hashed_password',      sa.String(200),   nullable=False),
            sa.Column('role',                 sa.String(30),    nullable=False, server_default='viewer'),
            sa.Column('is_active',            sa.Boolean(),     nullable=False, server_default='1'),
            sa.Column('must_change_password', sa.Boolean(),     nullable=False, server_default='0'),
            sa.Column('phone',                sa.String(50),    nullable=True),
            sa.Column('avatar',               sa.Text(),        nullable=True),
            sa.Column('position',             sa.String(200),   nullable=True),
        )

    if not _exists('user_departments'):
        op.create_table(
            'user_departments',
            sa.Column('user_id',       sa.Integer(), sa.ForeignKey('users.id'),       primary_key=True),
            sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.id'), primary_key=True),
        )

    if not _exists('month_records'):
        op.create_table(
            'month_records',
            sa.Column('id',         sa.Integer(),  primary_key=True, autoincrement=True),
            sa.Column('year',       sa.Integer(),  nullable=False),
            sa.Column('month',      sa.Integer(),  nullable=False),
            sa.Column('notes',      sa.Text(),     nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if not _exists('employee_events'):
        op.create_table(
            'employee_events',
            sa.Column('id',              sa.Integer(),     primary_key=True, autoincrement=True),
            sa.Column('month_record_id', sa.Integer(),     sa.ForeignKey('month_records.id'), nullable=False),
            sa.Column('event_type',      sa.String(20),    nullable=False),
            sa.Column('event_date',      sa.Date(),        nullable=True),
            sa.Column('full_name',       sa.String(300),   nullable=True),
            sa.Column('position',        sa.String(300),   nullable=True),
            sa.Column('department',      sa.String(200),   nullable=True),
            sa.Column('employment_type', sa.String(100),   nullable=True),
        )

    if not _exists('metric_definitions'):
        op.create_table(
            'metric_definitions',
            sa.Column('key',         sa.String(80),  primary_key=True),
            sa.Column('label',       sa.String(200), nullable=False),
            sa.Column('unit',        sa.String(30),  nullable=True),
            sa.Column('category',    sa.String(50),  nullable=True),
            sa.Column('value_type',  sa.String(20),  nullable=True),
            sa.Column('aggregation', sa.String(20),  nullable=True),
            sa.Column('direction',   sa.String(30),  nullable=True),
            sa.Column('description', sa.Text(),      nullable=True),
            sa.Column('sort_order',  sa.Integer(),   nullable=True, server_default='0'),
        )

    if not _exists('metric_values'):
        op.create_table(
            'metric_values',
            sa.Column('id',              sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('month_record_id', sa.Integer(), sa.ForeignKey('month_records.id'), nullable=False),
            sa.Column('metric_key',      sa.String(80), nullable=False),
            sa.Column('numeric_value',   sa.Float(),    nullable=True),
            sa.Column('text_value',      sa.Text(),     nullable=True),
            sa.Column('source_note',     sa.Text(),     nullable=True),
        )

    if not _exists('traffic_light_rules'):
        op.create_table(
            'traffic_light_rules',
            sa.Column('id',               sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('metric_key',       sa.String(80), nullable=False, unique=True),
            sa.Column('green_threshold',  sa.Float(),    nullable=True),
            sa.Column('yellow_threshold', sa.Float(),    nullable=True),
            sa.Column('direction',        sa.String(30), nullable=True),
            sa.Column('enabled',          sa.Boolean(),  nullable=False, server_default='1'),
        )

    if not _exists('benchmarks'):
        op.create_table(
            'benchmarks',
            sa.Column('id',           sa.Integer(),    primary_key=True, autoincrement=True),
            sa.Column('metric_key',   sa.String(80),   nullable=False),
            sa.Column('label',        sa.String(200),  nullable=True),
            sa.Column('year',         sa.Integer(),    nullable=True),
            sa.Column('value',        sa.Float(),      nullable=True),
            sa.Column('target_value', sa.Float(),      nullable=True),
            sa.Column('description',  sa.Text(),       nullable=True),
            sa.Column('source',       sa.String(300),  nullable=True),
        )

    if not _exists('dashboard_modules'):
        op.create_table(
            'dashboard_modules',
            sa.Column('id',           sa.Integer(),    primary_key=True, autoincrement=True),
            sa.Column('key',          sa.String(80),   nullable=False, unique=True),
            sa.Column('title',        sa.String(200),  nullable=True),
            sa.Column('subtitle',     sa.String(400),  nullable=True),
            sa.Column('icon',         sa.String(80),   nullable=True),
            sa.Column('route_prefix', sa.String(100),  nullable=True),
            sa.Column('enabled',      sa.Boolean(),    nullable=False, server_default='0'),
            sa.Column('sort_order',   sa.Integer(),    nullable=True,  server_default='0'),
        )

    if not _exists('audit_log'):
        op.create_table(
            'audit_log',
            sa.Column('id',          sa.Integer(),   primary_key=True, autoincrement=True),
            sa.Column('user_id',     sa.Integer(),   sa.ForeignKey('users.id'), nullable=True),
            sa.Column('action',      sa.String(100), nullable=False),
            sa.Column('entity_type', sa.String(80),  nullable=True),
            sa.Column('entity_id',   sa.String(80),  nullable=True),
            sa.Column('detail',      sa.Text(),      nullable=True),
            sa.Column('ip_address',  sa.String(50),  nullable=True),
            sa.Column('created_at',  sa.DateTime(),  nullable=True),
        )

    if not _exists('partnerships'):
        op.create_table(
            'partnerships',
            sa.Column('id',            sa.Integer(),   primary_key=True, autoincrement=True),
            sa.Column('partner',       sa.String(300), nullable=True),
            sa.Column('product',       sa.String(300), nullable=True),
            sa.Column('direction',     sa.String(200), nullable=True),
            sa.Column('almi_product',  sa.String(200), nullable=True),
            sa.Column('almi_version',  sa.String(100), nullable=True),
            sa.Column('status',        sa.String(80),  nullable=True, server_default='В работе'),
            sa.Column('cert_date',     sa.Date(),      nullable=True),
            sa.Column('nda',           sa.Boolean(),   nullable=True, server_default='0'),
            sa.Column('agreement',     sa.Boolean(),   nullable=True, server_default='0'),
            sa.Column('bitrix',        sa.String(300), nullable=True),
            sa.Column('website',       sa.String(300), nullable=True),
            sa.Column('comment',       sa.Text(),      nullable=True),
            sa.Column('type',          sa.String(50),  nullable=True, server_default='ПО'),
            sa.Column('last_modified', sa.Date(),      nullable=True),
            sa.Column('created_at',    sa.DateTime(),  nullable=True),
        )

    if not _exists('color_palettes'):
        op.create_table(
            'color_palettes',
            sa.Column('id',          sa.Integer(),  primary_key=True, autoincrement=True),
            sa.Column('scope',       sa.String(30), nullable=False, server_default='global'),
            sa.Column('module_key',  sa.String(80), nullable=True),
            sa.Column('name',        sa.String(100),nullable=True),
            sa.Column('colors_json', sa.Text(),     nullable=False),
            sa.Column('is_active',   sa.Boolean(),  nullable=False, server_default='0'),
            sa.Column('created_at',  sa.DateTime(), nullable=True),
        )

    if not _exists('user_service_access'):
        op.create_table(
            'user_service_access',
            sa.Column('id',           sa.Integer(),  primary_key=True, autoincrement=True),
            sa.Column('user_id',      sa.Integer(),  sa.ForeignKey('users.id'), nullable=False),
            sa.Column('service_key',  sa.String(80), nullable=False),
            sa.Column('access_level', sa.String(30), nullable=False, server_default='read'),
            sa.Column('granted_at',   sa.DateTime(), nullable=True),
        )

    if not _exists('dashboard_prefs'):
        op.create_table(
            'dashboard_prefs',
            sa.Column('id',          sa.Integer(),  primary_key=True, autoincrement=True),
            sa.Column('user_id',     sa.Integer(),  sa.ForeignKey('users.id'), nullable=False),
            sa.Column('service_key', sa.String(80), nullable=False),
            sa.Column('prefs_json',  sa.Text(),     nullable=True),
            sa.Column('updated_at',  sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    for table in [
        'dashboard_prefs', 'user_service_access', 'color_palettes',
        'partnerships', 'audit_log', 'dashboard_modules', 'benchmarks',
        'traffic_light_rules', 'metric_values', 'metric_definitions',
        'employee_events', 'month_records', 'user_departments', 'users', 'departments',
    ]:
        op.drop_table(table)
