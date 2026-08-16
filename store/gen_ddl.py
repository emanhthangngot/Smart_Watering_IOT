"""Generate store/schema.sql from registry/specs.py.

Design reference: plans/reports/plan.md §11.4. schema.sql is GENERATED,
never hand-edited — this script is the only thing allowed to write it, so
schema and registry can never drift apart (§16 risk).

Usage: python -m store.gen_ddl > store/schema.sql
       (or just `python -m store.gen_ddl` — it writes the file itself)
"""

from __future__ import annotations

import sys
from pathlib import Path

from registry.specs import DEVICES, SPECS, metrics_for_device

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_PG_COLUMN_TYPE = "double precision"

_SHARED_COLUMNS = """\
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false"""


def _table_name(device_code: str) -> str:
    return f"{device_code.lower()}_readings"


def _gen_sensor_table(device_code: str) -> str:
    metric_specs = metrics_for_device(device_code)
    metric_columns = "\n".join(
        f"  {spec.metric:<15} {_PG_COLUMN_TYPE}"
        f"{',' if index < len(metric_specs) - 1 else ''}  -- {spec.unit}"
        for index, spec in enumerate(metric_specs)
    )
    table = _table_name(device_code)
    return (
        f"create table {table} (\n"
        f"{_SHARED_COLUMNS},\n"
        f"{metric_columns}\n"
        f");\n"
        f"create index on {table} (team_code, epoch desc);\n"
    )


def _gen_readings_all_view() -> str:
    branches: list[str] = []
    for spec in SPECS:
        table = _table_name(spec.device_code)
        branches.append(
            "  select id, "
            f"'{spec.device_code}' as device, '{spec.metric}' as metric, "
            f"{spec.metric} as value, epoch, event_time, received_at, "
            f"source_status, late, scenario\n"
            f"    from {table} where {spec.metric} is not null"
        )
    body = "\n  union all\n".join(branches)
    return f"create view readings_all as\n{body}\n;\n"


def _gen_ingest_batch_rpc() -> str:
    branches: list[str] = []
    for device_code in DEVICES:
        table = _table_name(device_code)
        specs = metrics_for_device(device_code)
        insert_cols = ", ".join(
            ["id", "epoch", "event_time", "team_code", "scenario", "source_status", "late"]
            + [spec.metric for spec in specs]
        )
        metric_values = ", ".join(
            f"(d->'metrics'->>'{spec.metric}')::double precision" for spec in specs
        )
        # `->>` and `||` share precedence and associate left in Postgres, so
        # every json extraction below is parenthesised.
        #
        # `id` and `late` come from the caller (ingest/normalize.py), not
        # generated here — normalize.py already assigns one readingId per
        # device-batch row (§3.2) and computes `late` from the watermark;
        # this RPC must not mint a second, disagreeing id.
        values = (
            "(d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late"
        )
        if metric_values:
            values = f"{values}, {metric_values}"
        branches.append(
            f"      when '{device_code}' then\n"
            f"        insert into {table} ({insert_cols})\n"
            f"        values ({values})\n"
            f"        on conflict (id) do nothing;"
        )
    case_body = "\n".join(branches)
    return f"""\
create or replace function ingest_batch(payload jsonb) returns void as $$
declare
  v_epoch      bigint := (payload->>'epoch')::bigint;
  v_event_time timestamptz := coalesce(
    (payload->>'eventTime')::timestamptz,
    to_timestamp((payload->>'epoch')::bigint)
  );
  v_team_code  text := payload->>'teamCode';
  v_scenario   text := payload->>'scenario';
  v_late       boolean := coalesce((payload->>'late')::boolean, false);
  d            jsonb;
begin
  for d in select * from jsonb_array_elements(coalesce(payload->'devices', '[]'::jsonb)) loop
    case d->>'deviceCode'
{case_body}
      else
        -- unknown deviceCode: ignored here, counted upstream by ingest/normalize.py
        null;
    end case;
  end loop;
end;
$$ language plpgsql;
"""


_OPERATIONAL_TABLES = """\
create table if not exists plans (
  plan_lineage_id     text primary key,
  latest_revision_id  text,
  created_at          timestamptz not null default now()
);

create table if not exists plan_revisions (
  plan_revision_id           text primary key,
  plan_lineage_id            text not null references plans(plan_lineage_id),
  version                    int not null,
  revision_of_plan_revision_id text,
  status                     text not null,
  goal                       jsonb,
  created_from_state_version bigint,
  evidence_refs              jsonb,
  constraints                jsonb,
  assumptions                jsonb,
  actions                    jsonb,
  expected_outcomes          jsonb,
  water_budget               jsonb,
  confidence                 jsonb,
  requires_approval          boolean not null default false,
  challenges                 jsonb,
  decision_log               jsonb,
  created_at                 timestamptz not null default now()
);
create index on plan_revisions (plan_lineage_id);

create table if not exists assumptions (
  assumption_id        text primary key,
  predicate            text not null,
  status               text not null,
  evidence_refs        jsonb,
  observation_window   text,
  affected_action_ids  jsonb,
  invalidated_at       timestamptz,
  invalidated_reason   text,
  invalidated_evidence text,
  created_at           timestamptz not null default now()
);

create table if not exists challenges (
  challenge_id            text primary key,
  target_plan_revision_id text not null,
  agent                   text not null,
  blocking                boolean not null,
  status                  text not null,
  reason                  text,
  evidence_refs           jsonb,
  requested_evidence      jsonb,
  requested_revision      text,
  created_at              timestamptz not null default now()
);

create table if not exists approvals (
  approval_id       text primary key,
  plan_revision_id  text not null,
  revision_hash     text not null,
  approver          text not null,
  decision          text not null,
  timestamp         timestamptz not null,
  expires_at        timestamptz,
  comment           text
);

create table if not exists actions (
  action_id         text primary key,
  plan_revision_id  text,
  tool              text not null,
  params            jsonb,
  status            text not null,
  idempotency_key   text unique,
  scheduled_for     timestamptz,
  created_at        timestamptz not null default now()
);

create table if not exists verifications (
  verification_id  text primary key,
  action_id        text,
  layer            text not null,
  expected         jsonb,
  observed         jsonb,
  result           text not null,
  -- `window` is a reserved word in Postgres; the contracts.py field is
  -- Verification.window, this column carries it under a safe name.
  observation_window text,
  evidence_refs    jsonb,
  created_at       timestamptz not null default now()
);

create table if not exists edges (
  edge_id     text primary key,
  from_type   text not null,
  from_id     text not null,
  to_type     text not null,
  to_id       text not null,
  relation    text not null,
  created_at  timestamptz not null default now()
);

create table if not exists water_ledger (
  entry_id                text primary key,
  plan_revision_id        text,
  action_id               text,
  planned_drawdown_pct    double precision,
  actual_drawdown_pct     double precision,
  event_time              timestamptz,
  created_at              timestamptz not null default now()
);

create table if not exists inspection_tasks (
  task_id        text primary key,
  reason         text not null,
  evidence_refs  jsonb,
  status         text not null,
  assigned_to    text,
  created_at     timestamptz not null default now(),
  resolved_at    timestamptz
);

create table if not exists notifications (
  notification_id  text primary key,
  kind             text not null,
  payload          jsonb,
  read             boolean not null default false,
  created_at       timestamptz not null default now()
);

create table if not exists audit_log (
  audit_id    text primary key,
  event_type  text not null,
  payload     jsonb,
  created_at  timestamptz not null default now()
);

create table if not exists trust_snapshots (
  snapshot_id         text primary key,
  scope               text not null,
  dcs                 double precision,
  f                   double precision,
  c                   double precision,
  k                   double precision,
  cap_applied         double precision,
  tier                text,
  rules_fired         jsonb,
  dcs_policy_version  int,
  farm_state_version  bigint,
  created_at          timestamptz not null default now()
);
"""

_RLS = """\
-- RLS on, anon no write (§11.4). Backend writes via service_role, which
-- bypasses RLS entirely, so these policies only ever affect anon/authenticated.
"""


def _gen_rls() -> str:
    lines = [_RLS]
    all_tables = [_table_name(d) for d in DEVICES] + [
        "plans",
        "plan_revisions",
        "assumptions",
        "challenges",
        "approvals",
        "actions",
        "verifications",
        "edges",
        "water_ledger",
        "inspection_tasks",
        "notifications",
        "audit_log",
        "trust_snapshots",
    ]
    for table in all_tables:
        lines.append(f"alter table {table} enable row level security;")
    return "\n".join(lines) + "\n"


def generate() -> str:
    header = """\
-- GENERATED FILE. DO NOT HAND-EDIT.
-- Regenerate with: python -m store.gen_ddl
-- Source of truth: registry/specs.py (plans/reports/plan.md §3.6, §11.4).
"""
    sections = [header]
    for device_code in DEVICES:
        sections.append(_gen_sensor_table(device_code))
    sections.append(_gen_readings_all_view())
    sections.append(_OPERATIONAL_TABLES)
    sections.append(_gen_ingest_batch_rpc())
    sections.append(_gen_rls())
    return "\n".join(sections)


def main() -> None:
    sql = generate()
    SCHEMA_PATH.write_text(sql)
    sys.stderr.write(f"wrote {SCHEMA_PATH}\n")


if __name__ == "__main__":
    main()
