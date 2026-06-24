-- oh-my-wiki registry schema v1
-- Idempotent: safe to run multiple times via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vaults (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  path        TEXT NOT NULL UNIQUE,
  type        TEXT NOT NULL CHECK (type IN ('markdown', 'obsidian')),
  mode        TEXT NOT NULL CHECK (mode IN ('memo', 'wiki', 'personal', 'book', 'business', 'github-codebase', 'website')),
  is_active   INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
  created_at  TEXT NOT NULL,
  last_used   TEXT NOT NULL,
  config_json TEXT
);

-- Partial unique index: at most one row with is_active=1.
CREATE UNIQUE INDEX IF NOT EXISTS idx_active_vault
  ON vaults(is_active) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS notes (
  id           INTEGER PRIMARY KEY,
  vault_id     INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
  relpath      TEXT NOT NULL,
  layer        TEXT NOT NULL CHECK (layer IN ('raw', 'wiki', 'memo', 'meta')),
  title        TEXT,
  summary      TEXT,
  mtime        REAL NOT NULL,
  size_bytes   INTEGER NOT NULL,
  parse_error  INTEGER NOT NULL DEFAULT 0 CHECK (parse_error IN (0, 1)),
  visibility   TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('public', 'private')),
  aliases      TEXT NOT NULL DEFAULT '[]',
  type         TEXT,
  status       TEXT,
  UNIQUE(vault_id, relpath)
);
CREATE INDEX IF NOT EXISTS idx_notes_vault ON notes(vault_id);
CREATE INDEX IF NOT EXISTS idx_notes_layer ON notes(vault_id, layer);

CREATE TABLE IF NOT EXISTS links (
  id          INTEGER PRIMARY KEY,
  vault_id    INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
  src_note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  dst_slug    TEXT NOT NULL,
  dst_note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL,  -- NULL = broken/unresolved
  link_type   TEXT NOT NULL,    -- 'wikilink' | 'markdown' (syntactic; semantic types are F#2)
  position    INTEGER NOT NULL  -- 0-based order of appearance in the src body
);
CREATE INDEX IF NOT EXISTS idx_links_src   ON links(src_note_id);
CREATE INDEX IF NOT EXISTS idx_links_dst   ON links(dst_note_id);
CREATE INDEX IF NOT EXISTS idx_links_vault ON links(vault_id);

CREATE TABLE IF NOT EXISTS tags (
  id    INTEGER PRIMARY KEY,
  name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS note_tags (
  note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (note_id, tag_id)
);

CREATE TABLE IF NOT EXISTS inbox_queue (
  id             INTEGER PRIMARY KEY,
  vault_id       INTEGER NOT NULL REFERENCES vaults(id) ON DELETE CASCADE,
  url            TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'fetched', 'ingested', 'failed')),
  title          TEXT,
  added_at       TEXT NOT NULL,
  fetched_at     TEXT,
  raw_relpath    TEXT,
  error          TEXT,
  UNIQUE(vault_id, normalized_url)
);
CREATE INDEX IF NOT EXISTS idx_inbox_vault_status ON inbox_queue(vault_id, status);
