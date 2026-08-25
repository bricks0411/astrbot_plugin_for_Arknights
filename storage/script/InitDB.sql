CREATE TABLE IF NOT EXISTS account_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    platform_name TEXT NOT NULL,
    user_id TEXT NOT NULL,

    server_type TEXT NOT NULL,
    auth_provider TEXT NOT NULL,

    account_id TEXT NOT NULL,           -- 即用户 uid
    nickname TEXT,
    phone_mask TEXT,
    phone_hash TEXT,

    token_encrypted TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,

    UNIQUE(platform_name, user_id, server_type)
);

CREATE TABLE IF NOT EXISTS gacha_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    uid TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',

    pool_id TEXT NOT NULL,
    pool_name TEXT NOT NULL,

    char_id TEXT NOT NULL,
    char_name TEXT NOT NULL,
    rarity INTEGER NOT NULL,
    is_new INTEGER NOT NULL,

    gacha_ts TEXT NOT NULL,
    pos INTEGER NOT NULL,

    created_at INTEGER NOT NULL,

    UNIQUE(uid, pool_id, gacha_ts, pos, char_id)
);

CREATE TABLE IF NOT EXISTS skland_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    uid TEXT NOT NULL UNIQUE,

    cred_encrypted TEXT NOT NULL,
    token_encrypted TEXT NOT NULL,

    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS skland_account_snapshots (
    uid TEXT NOT NULL,
    server_type TEXT NOT NULL DEFAULT 'official',

    payload BLOB NOT NULL,
    compression TEXT NOT NULL DEFAULT 'zlib',
    encryption_version INTEGER NOT NULL DEFAULT 1,

    payload_sha256 TEXT NOT NULL,
    api_current_ts INTEGER DEFAULT 0,
    fetched_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,

    schema_version TEXT,

    PRIMARY KEY (uid, server_type)
);
