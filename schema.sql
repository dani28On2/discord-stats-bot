-- =====================================================================
--  ESQUEMA DE LA BASE DE DATOS (Supabase / PostgreSQL)
-- ---------------------------------------------------------------------
--  Copia y ejecuta esto en:  Supabase > SQL Editor > New query
-- =====================================================================

-- Tabla principal: mejor marca de cada jugador.
create table if not exists public.leaderboard (
    discord_id  text        primary key,           -- ID único de Discord del jugador
    username    text        not null,              -- Nick visible (para el ranking)
    best_score  integer     not null default 0,    -- Mejor puntuación registrada
    best_kills  integer     not null default 0,    -- Bajas de esa mejor partida
    updated_at  timestamptz not null default now() -- Última actualización
);

create index if not exists leaderboard_best_score_idx
    on public.leaderboard (best_score desc);

-- Tabla de estado: recuerda por dónde iba el procesado por lotes.
-- Es un simple almacén clave/valor; aquí guardamos el ID del último
-- mensaje de Discord ya analizado para no repetirlo en la siguiente
-- ejecución del GitHub Action.
create table if not exists public.bot_state (
    key   text primary key,
    value text
);

-- NOTA SOBRE SEGURIDAD:
-- El bot usa la SECRET key (sb_secret_...), con acceso privilegiado que
-- ignora las políticas RLS, así que esto funciona tal cual.
