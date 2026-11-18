-- Supabase の SQL Editor で実行する（何度実行しても壊れないように書いてある）

-- ===========================================================================
-- companies: EDINET取り込みデータ（source='edinet'）＋利用者の手入力（source='user'）
-- ===========================================================================
create table if not exists companies (
  id bigint generated always as identity primary key,
  industry text not null,
  company_name text not null
);

alter table companies
  add column if not exists source text not null default 'user',
  add column if not exists edinet_code text,
  add column if not exists sec_code text,
  add column if not exists doc_id text,
  add column if not exists period_end date,
  add column if not exists income numeric,
  add column if not exists age numeric,
  add column if not exists founding_year integer,
  add column if not exists overseas_ratio numeric,
  add column if not exists operating_margin numeric,
  add column if not exists revenue_growth numeric,
  add column if not exists operating_profit_growth numeric,
  add column if not exists avg_tenure numeric,
  add column if not exists next_year_growth_forecast numeric,
  add column if not exists operating_cf_margin numeric,
  add column if not exists segment_concentration numeric,
  add column if not exists created_by uuid default auth.uid(),
  add column if not exists updated_at timestamptz default now();

-- edinet_ingest.py の upsert(on_conflict="edinet_code") に必要
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'companies_edinet_code_key') then
    alter table companies add constraint companies_edinet_code_key unique (edinet_code);
  end if;
end $$;

create index if not exists companies_industry_idx on companies (industry);

alter table companies enable row level security;

-- ログイン済みユーザーは全件読める（企業データは公開情報）
drop policy if exists "companies_select_authenticated" on companies;
create policy "companies_select_authenticated" on companies
  for select to authenticated using (true);

-- ログイン済みユーザーは「自分の手入力データ」だけ追加できる
-- （EDINETデータの偽装・上書きは不可。EDINETデータは service_role キーの取り込みスクリプトのみが書く）
drop policy if exists "companies_insert_own_user_rows" on companies;
create policy "companies_insert_own_user_rows" on companies
  for insert to authenticated
  with check (source = 'user' and edinet_code is null and created_by = auth.uid());

-- ===========================================================================
-- company_texts: 有報の文章（AI要約の入力）。書き込みは取り込みスクリプト(service_role)のみ
-- ===========================================================================
create table if not exists company_texts (
  edinet_code text primary key,
  doc_id text,
  period_end date,
  business_description text,
  management_policy text,
  business_risks text,
  updated_at timestamptz default now()
);

alter table company_texts enable row level security;

drop policy if exists "company_texts_select_authenticated" on company_texts;
create policy "company_texts_select_authenticated" on company_texts
  for select to authenticated using (true);

-- ===========================================================================
-- results: 評価結果の保存
-- ===========================================================================
create table if not exists results (
  id bigint generated always as identity primary key,
  user_email text,
  industry text,
  company text,
  score integer,
  created_at timestamptz default now()
);

alter table results
  add column if not exists user_id uuid default auth.uid();

alter table results enable row level security;

drop policy if exists "results_insert_own" on results;
create policy "results_insert_own" on results
  for insert to authenticated with check (user_id = auth.uid());

-- 自分の結果は読める。管理者（app_metadata.role = 'admin'）は全件読める
drop policy if exists "results_select_own_or_admin" on results;
create policy "results_select_own_or_admin" on results
  for select to authenticated
  using (user_id = auth.uid() or (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

-- 更新は管理者のみ（アプリ側の画面制御だけでなくDB側でも制限する）
drop policy if exists "results_update_admin" on results;
create policy "results_update_admin" on results
  for update to authenticated
  using ((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin')
  with check ((auth.jwt() -> 'app_metadata' ->> 'role') = 'admin');

-- ===========================================================================
-- API（Data API）からの利用権限
-- 新しい Supabase プロジェクトは、SQL で作ったテーブルに自動で権限を付けないため明示する。
-- 実際に「どの行を読める/書けるか」は上の RLS ポリシーで制限される。anon（未ログイン）には何も付けない。
-- ===========================================================================
grant usage on schema public to authenticated, service_role;

grant select, insert, update, delete on companies, company_texts, results to service_role;
grant select, insert on companies to authenticated;
grant select on company_texts to authenticated;
grant select, insert, update on results to authenticated;

-- id 列（identity）の採番に必要
grant usage, select on all sequences in schema public to authenticated, service_role;

-- 管理者の付与例（SQL Editor で実行。メールアドレスは自分のものに置き換える）
-- update auth.users
--   set raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'
--   where email = 'you@example.com';
