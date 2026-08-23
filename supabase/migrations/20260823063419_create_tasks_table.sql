/*
# Create tasks table for PhantomDev dashboard

1. New Tables
- `tasks`
  - `id` (uuid, primary key, auto-generated)
  - `title` (text, not null) — task title / GitHub issue title
  - `body` (text, nullable) — task description / GitHub issue body
  - `repo` (text, nullable) — GitHub repository in owner/name format
  - `issue_number` (integer, nullable) — GitHub issue number
  - `base_branch` (text, default 'main') — target branch for the PR
  - `status` (text, default 'pending') — pipeline status
  - `current_agent` (text, nullable) — currently active agent
  - `pr_url` (text, nullable) — link to the generated pull request
  - `messages` (jsonb, default '[]') — agent activity messages
  - `created_at` (timestamptz, default now())
  - `updated_at` (timestamptz, default now())

2. Security
- Enable RLS on `tasks`.
- This is a single-tenant app with no sign-in screen, so policies
  use `TO anon, authenticated` with `USING (true)` / `WITH CHECK (true)`
  because the data is intentionally shared/public.
*/

CREATE TABLE IF NOT EXISTS tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  body text,
  repo text,
  issue_number integer,
  base_branch text NOT NULL DEFAULT 'main',
  status text NOT NULL DEFAULT 'pending',
  current_agent text,
  pr_url text,
  messages jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_select_tasks" ON tasks;
CREATE POLICY "anon_select_tasks" ON tasks FOR SELECT
  TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "anon_insert_tasks" ON tasks;
CREATE POLICY "anon_insert_tasks" ON tasks FOR INSERT
  TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "anon_update_tasks" ON tasks;
CREATE POLICY "anon_update_tasks" ON tasks FOR UPDATE
  TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "anon_delete_tasks" ON tasks;
CREATE POLICY "anon_delete_tasks" ON tasks FOR DELETE
  TO anon, authenticated USING (true);
