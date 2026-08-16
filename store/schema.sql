-- GENERATED FILE. DO NOT HAND-EDIT.
-- Regenerate with: python -m store.gen_ddl
-- Source of truth: registry/specs.py (plans/reports/plan.md §3.6, §11.4).

create table soil_01_readings (
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false,
  soil_moisture   double precision,  -- %
  temperature     double precision  -- °C
);
create index on soil_01_readings (team_code, epoch desc);

create table weather_01_readings (
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false,
  temperature     double precision,  -- °C
  humidity        double precision  -- %
);
create index on weather_01_readings (team_code, epoch desc);

create table pump_01_readings (
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false,
  flow_rate       double precision,  -- L/min
  power           double precision  -- W
);
create index on pump_01_readings (team_code, epoch desc);

create table ph_01_readings (
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false,
  ph              double precision  -- pH
);
create index on ph_01_readings (team_code, epoch desc);

create table tank_01_readings (
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false,
  level           double precision  -- %
);
create index on tank_01_readings (team_code, epoch desc);

create table sun_01_readings (
  id            text primary key,
  epoch         bigint      not null,
  event_time    timestamptz not null,
  received_at   timestamptz not null default now(),
  team_code     text        not null,
  scenario      text,
  source_status text        not null,
  late          boolean     not null default false,
  lux             double precision  -- lx
);
create index on sun_01_readings (team_code, epoch desc);

create view readings_all as
  select id, 'SOIL_01' as device, 'soil_moisture' as metric, soil_moisture as value, epoch, event_time, received_at, source_status, late, scenario
    from soil_01_readings where soil_moisture is not null
  union all
  select id, 'SOIL_01' as device, 'temperature' as metric, temperature as value, epoch, event_time, received_at, source_status, late, scenario
    from soil_01_readings where temperature is not null
  union all
  select id, 'WEATHER_01' as device, 'temperature' as metric, temperature as value, epoch, event_time, received_at, source_status, late, scenario
    from weather_01_readings where temperature is not null
  union all
  select id, 'WEATHER_01' as device, 'humidity' as metric, humidity as value, epoch, event_time, received_at, source_status, late, scenario
    from weather_01_readings where humidity is not null
  union all
  select id, 'PUMP_01' as device, 'flow_rate' as metric, flow_rate as value, epoch, event_time, received_at, source_status, late, scenario
    from pump_01_readings where flow_rate is not null
  union all
  select id, 'PUMP_01' as device, 'power' as metric, power as value, epoch, event_time, received_at, source_status, late, scenario
    from pump_01_readings where power is not null
  union all
  select id, 'PH_01' as device, 'ph' as metric, ph as value, epoch, event_time, received_at, source_status, late, scenario
    from ph_01_readings where ph is not null
  union all
  select id, 'TANK_01' as device, 'level' as metric, level as value, epoch, event_time, received_at, source_status, late, scenario
    from tank_01_readings where level is not null
  union all
  select id, 'SUN_01' as device, 'lux' as metric, lux as value, epoch, event_time, received_at, source_status, late, scenario
    from sun_01_readings where lux is not null
;

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

-- schedule/models.py::Schedule, schedule/claim.py::ScheduleRepository.
-- Added for coordination gate C4 (durable schedule state across restart);
-- mirrors InMemoryScheduleRepository's column shape 1:1.
create table if not exists schedules (
  schedule_id            text primary key,
  plan_revision_id       text not null,
  pump_id                text not null,
  start_at               timestamptz not null,
  end_at                 timestamptz not null,
  status                 text not null,
  claimed_by             text,
  verification_result    text,
  late_verification      boolean not null default false,
  status_reason          text,
  planned_drawdown_pct   double precision not null default 0,
  planned_pump_minutes   double precision not null default 0,
  closing_started_at     timestamptz,
  closing_failure        text,
  actuator_stopped       boolean not null default false,
  verification_attempts  int not null default 0,
  created_at             timestamptz not null default now()
);
-- DB-enforced single-RUNNING-schedule-per-pump: the concurrency guarantee
-- InMemoryScheduleRepository checks in application code, closed here as a
-- constraint so two concurrent claims can never both win.
create unique index if not exists schedules_one_running_per_pump
  on schedules (pump_id) where status = 'RUNNING';
create index on schedules (status) where status not in ('DONE', 'FAILED', 'MISSED', 'CANCELLED');

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
      when 'SOIL_01' then
        insert into soil_01_readings (id, epoch, event_time, team_code, scenario, source_status, late, soil_moisture, temperature)
        values ((d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late, (d->'metrics'->>'soil_moisture')::double precision, (d->'metrics'->>'temperature')::double precision)
        on conflict (id) do nothing;
      when 'WEATHER_01' then
        insert into weather_01_readings (id, epoch, event_time, team_code, scenario, source_status, late, temperature, humidity)
        values ((d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late, (d->'metrics'->>'temperature')::double precision, (d->'metrics'->>'humidity')::double precision)
        on conflict (id) do nothing;
      when 'PUMP_01' then
        insert into pump_01_readings (id, epoch, event_time, team_code, scenario, source_status, late, flow_rate, power)
        values ((d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late, (d->'metrics'->>'flow_rate')::double precision, (d->'metrics'->>'power')::double precision)
        on conflict (id) do nothing;
      when 'PH_01' then
        insert into ph_01_readings (id, epoch, event_time, team_code, scenario, source_status, late, ph)
        values ((d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late, (d->'metrics'->>'ph')::double precision)
        on conflict (id) do nothing;
      when 'TANK_01' then
        insert into tank_01_readings (id, epoch, event_time, team_code, scenario, source_status, late, level)
        values ((d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late, (d->'metrics'->>'level')::double precision)
        on conflict (id) do nothing;
      when 'SUN_01' then
        insert into sun_01_readings (id, epoch, event_time, team_code, scenario, source_status, late, lux)
        values ((d->>'id'), v_epoch, v_event_time, v_team_code, v_scenario, (d->>'status'), v_late, (d->'metrics'->>'lux')::double precision)
        on conflict (id) do nothing;
      else
        -- unknown deviceCode: ignored here, counted upstream by ingest/normalize.py
        null;
    end case;
  end loop;
end;
$$ language plpgsql;

-- RLS on, anon no write (§11.4). Backend writes via service_role, which
-- bypasses RLS entirely, so these policies only ever affect anon/authenticated.

alter table soil_01_readings enable row level security;
alter table weather_01_readings enable row level security;
alter table pump_01_readings enable row level security;
alter table ph_01_readings enable row level security;
alter table tank_01_readings enable row level security;
alter table sun_01_readings enable row level security;
alter table plans enable row level security;
alter table plan_revisions enable row level security;
alter table assumptions enable row level security;
alter table challenges enable row level security;
alter table approvals enable row level security;
alter table actions enable row level security;
alter table verifications enable row level security;
alter table edges enable row level security;
alter table water_ledger enable row level security;
alter table inspection_tasks enable row level security;
alter table notifications enable row level security;
alter table audit_log enable row level security;
alter table trust_snapshots enable row level security;
alter table schedules enable row level security;
