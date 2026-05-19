-- =====================================================================
--  ESQUEMA DE LA BASE DE DATOS (Supabase / PostgreSQL)
-- ---------------------------------------------------------------------
--  Ejecuta esto en:  Supabase > SQL Editor > New query
--
--  IMPORTANTE: si vienes de la versión anterior (tabla 'leaderboard'
--  con columnas discord_id/username/best_score/best_kills), bórrala
--  antes con:    drop table if exists public.leaderboard;
--  Los datos previos NO se conservan: el modelo cambia.
-- =====================================================================

-- Una fila por (juego, jugador, estadística).
-- best_value es BIGINT porque algunos juegos manejan cifras enormes
-- (M, B, T) y un int normal se queda corto.
create table if not exists public.leaderboard (
    game        text   not null,
    discord_id  text   not null,
    stat        text   not null,
    best_value  bigint not null default 0,
    username    text   not null,
    updated_at  timestamptz not null default now(),
    primary key (game, discord_id, stat)
);

-- Para sacar el Top N de una stat concreta de un juego (la consulta más habitual).
create index if not exists leaderboard_game_stat_value_idx
    on public.leaderboard (game, stat, best_value desc);

-- Tabla de estado: almacén clave/valor.
-- Se usa para 'last_message:<game>' y 'pinned:<game>:<stat>'.
create table if not exists public.bot_state (
    key   text primary key,
    value text
);
