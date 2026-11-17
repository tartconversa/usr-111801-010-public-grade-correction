import sqlite3


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, jurisdiction TEXT NOT NULL,
    classification TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
    schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS fields (
    source_id TEXT NOT NULL REFERENCES sources(id), name TEXT NOT NULL,
    meaning TEXT NOT NULL, kind TEXT NOT NULL, sensitive INTEGER NOT NULL,
    PRIMARY KEY(source_id,name)
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    schema_version INTEGER NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
    received_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS grants (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    recipient TEXT NOT NULL, purpose TEXT NOT NULL, valid_until TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS policies (
    jurisdiction TEXT NOT NULL, classification TEXT NOT NULL, purpose TEXT NOT NULL,
    decision TEXT NOT NULL, revision INTEGER NOT NULL,
    PRIMARY KEY(jurisdiction,classification,purpose)
);
CREATE TABLE IF NOT EXISTS products (
    id TEXT NOT NULL, revision INTEGER NOT NULL, name TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
    PRIMARY KEY(id,revision)
);
CREATE TABLE IF NOT EXISTS product_inputs (
    product_id TEXT NOT NULL, product_revision INTEGER NOT NULL,
    asset_id TEXT NOT NULL REFERENCES assets(id),
    PRIMARY KEY(product_id,product_revision,asset_id),
    FOREIGN KEY(product_id,product_revision) REFERENCES products(id,revision)
);
CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY, product_id TEXT NOT NULL, product_revision INTEGER NOT NULL,
    recipient TEXT NOT NULL, purpose TEXT NOT NULL, created_at TEXT NOT NULL,
    input_digest TEXT NOT NULL, policy_revisions TEXT NOT NULL,
    FOREIGN KEY(product_id,product_revision) REFERENCES products(id,revision)
);
-- 公告：同一 notice_id 的每次发布、更正、撤回都追加一行，任何旧行不被修改。
CREATE TABLE IF NOT EXISTS announcements (
    id TEXT PRIMARY KEY, notice_id TEXT NOT NULL, seq INTEGER NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id),
    kind TEXT NOT NULL CHECK(kind IN ('publish','correction','withdrawal')),
    published_at TEXT NOT NULL, payload TEXT, digest TEXT,
    UNIQUE(notice_id, seq)
);
-- 更正关系：仅表达版本之间的依据关系；撤回只指向被撤回的更正公告。
CREATE TABLE IF NOT EXISTS announcement_relations (
    announcement_id TEXT PRIMARY KEY REFERENCES announcements(id),
    related_id TEXT NOT NULL REFERENCES announcements(id),
    relation TEXT NOT NULL CHECK(relation IN ('corrects','withdraws'))
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, subject TEXT NOT NULL, details TEXT NOT NULL
);
"""

# 旧版数据库的可空扩展列：公告依据随目录条目、依据快照随交付回执一起留存。
MIGRATIONS = {
    "assets": {
        "scenic_area": "ALTER TABLE assets ADD COLUMN scenic_area TEXT",
        "basis_announcement_id": "ALTER TABLE assets ADD COLUMN basis_announcement_id TEXT REFERENCES announcements(id)",
    },
    "deliveries": {
        "basis_snapshot": "ALTER TABLE deliveries ADD COLUMN basis_snapshot TEXT",
    },
}


def _migrate(connection):
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, statement in columns.items():
            if column not in existing:
                connection.execute(statement)


def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    _migrate(connection)
    return connection
