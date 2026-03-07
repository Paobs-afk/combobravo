-- ComboBravo Supabase schema
-- Run this in Supabase SQL editor before importing CSV data.

create extension if not exists pgcrypto;

create table if not exists public.cb_datasets (
  dataset_key text primary key,
  label text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.cb_transactions (
  id bigint generated always as identity primary key,
  dataset_key text not null references public.cb_datasets(dataset_key) on delete cascade,
  tx_id bigint not null,
  timestamp timestamptz,
  segment text,
  day_type text,
  items text not null,
  batch_no int,
  created_at timestamptz not null default now()
);

create unique index if not exists cb_transactions_dataset_txid_uidx
  on public.cb_transactions(dataset_key, tx_id);

create index if not exists cb_transactions_dataset_batch_idx
  on public.cb_transactions(dataset_key, batch_no);

create index if not exists cb_transactions_dataset_time_idx
  on public.cb_transactions(dataset_key, timestamp);

create table if not exists public.cb_item_margins (
  id bigint generated always as identity primary key,
  dataset_key text not null references public.cb_datasets(dataset_key) on delete cascade,
  item text not null,
  margin_php numeric(10,2) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(dataset_key, item)
);

create or replace function public.cb_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists cb_datasets_set_updated_at on public.cb_datasets;
create trigger cb_datasets_set_updated_at
before update on public.cb_datasets
for each row execute function public.cb_set_updated_at();

drop trigger if exists cb_item_margins_set_updated_at on public.cb_item_margins;
create trigger cb_item_margins_set_updated_at
before update on public.cb_item_margins
for each row execute function public.cb_set_updated_at();

alter table public.cb_datasets enable row level security;
alter table public.cb_transactions enable row level security;
alter table public.cb_item_margins enable row level security;

grant usage on schema public to anon, authenticated, service_role;
grant select, insert, update, delete on table public.cb_datasets to anon, authenticated, service_role;
grant select, insert, update, delete on table public.cb_transactions to anon, authenticated, service_role;
grant select, insert, update, delete on table public.cb_item_margins to anon, authenticated, service_role;
grant usage, select on all sequences in schema public to anon, authenticated, service_role;

drop policy if exists "cb_datasets_all" on public.cb_datasets;
create policy "cb_datasets_all"
  on public.cb_datasets
  for all
  using (true)
  with check (true);

drop policy if exists "cb_transactions_all" on public.cb_transactions;
create policy "cb_transactions_all"
  on public.cb_transactions
  for all
  using (true)
  with check (true);

drop policy if exists "cb_item_margins_all" on public.cb_item_margins;
create policy "cb_item_margins_all"
  on public.cb_item_margins
  for all
  using (true)
  with check (true);

-- Optional starter rows:
insert into public.cb_datasets (dataset_key, label)
values
  ('datasetA', 'Dataset A'),
  ('datasetB', 'Dataset B'),
  ('datasetC', 'Dataset C'),
  ('datasetD', 'Dataset D'),
  ('datasetE', 'Dataset E'),
  ('datasetF', 'Dataset F')
on conflict (dataset_key) do nothing;
