-- =====================================================================
--  ESQUEMA DE LA BASE DE DATOS (Supabase / PostgreSQL)
-- ---------------------------------------------------------------------
--  Copia y ejecuta esto en:  Supabase > SQL Editor > New query
-- =====================================================================

create table if not exists public.leaderboard (
    discord_id  text        primary key,           -- ID único de Discord del jugador
    username    text        not null,              -- Nick visible (para el ranking)
    best_score  integer     not null default 0,    -- Mejor puntuación registrada
    best_kills  integer     not null default 0,    -- Bajas de esa mejor partida
    updated_at  timestamptz not null default now() -- Última actualización
);

-- Índice para ordenar el ranking rápidamente por puntuación.
create index if not exists leaderboard_best_score_idx
    on public.leaderboard (best_score desc);

-- NOTA SOBRE SEGURIDAD:
-- El bot usa la SECRET key (sb_secret_...), que tiene acceso privilegiado
-- e ignora las políticas RLS, así que esto funciona tal cual.
-- Si algún día quisieras usar la PUBLISHABLE key (sb_publishable_...),
-- tendrías que activar RLS y crear políticas de INSERT/UPDATE/SELECT.
