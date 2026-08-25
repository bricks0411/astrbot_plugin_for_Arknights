BEGIN IMMEDIATE;

DROP TABLE IF EXISTS skland_account_snapshots_new;

CREATE TABLE skland_account_snapshots_new (
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

INSERT INTO skland_account_snapshots_new (
    uid,
    server_type,
    payload,
    compression,
    encryption_version,
    payload_sha256,
    api_current_ts,
    fetched_at,
    updated_at,
    schema_version
)
SELECT
    uid,
    COALESCE(NULLIF(server_type, ''), 'official'),
    payload,
    COALESCE(compression, 'zlib'),
    COALESCE(encryption_version, 1),
    payload_sha256,
    api_current_ts,
    fetched_at,
    updated_at,
    schema_version
FROM skland_account_snapshots;

DROP TABLE skland_account_snapshots;

ALTER TABLE skland_account_snapshots_new
RENAME TO skland_account_snapshots;

COMMIT;
