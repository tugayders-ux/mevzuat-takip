-- Supabase → SQL Editor'da bir kez çalıştır.
create table if not exists public.begeniler (
  post_slug  text not null check (char_length(post_slug) <= 120),
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_slug, user_id)
);

alter table public.begeniler enable row level security;

create policy "herkes sayabilir" on public.begeniler
  for select using (true);
create policy "kendi begenisini ekler" on public.begeniler
  for insert to authenticated with check (auth.uid() = user_id);
create policy "kendi begenisini siler" on public.begeniler
  for delete to authenticated using (auth.uid() = user_id);
