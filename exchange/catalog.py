import hashlib
import json

from .audit import write


class Catalog:
    def __init__(self, connection):
        self.connection = connection

    def register(self, source_id, owner, jurisdiction, classification, fields, at):
        if not fields or len({field[0] for field in fields}) != len(fields):
            raise ValueError("来源字段缺失或重复")
        with self.connection:
            self.connection.execute(
                "INSERT INTO sources(id,owner,jurisdiction,classification) VALUES(?,?,?,?)",
                (source_id, owner, jurisdiction, classification),
            )
            self.connection.executemany(
                "INSERT INTO fields(source_id,name,meaning,kind,sensitive) VALUES(?,?,?,?,?)",
                [(source_id, name, meaning, kind, int(sensitive)) for name, meaning, kind, sensitive in fields],
            )
            write(self.connection, at, owner, "source.register", source_id, {"jurisdiction": jurisdiction})

    def ingest(self, asset_id, source_id, payload, at):
        source = self.connection.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if source is None or not source["active"]:
            raise ValueError("来源不可用")
        allowed = {row[0] for row in self.connection.execute("SELECT name FROM fields WHERE source_id=?", (source_id,))}
        if not isinstance(payload, dict) or not payload or set(payload) - allowed:
            raise ValueError("记录字段不符合来源目录")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self.connection:
            self.connection.execute(
                "INSERT INTO assets(id,source_id,schema_version,payload,digest,received_at) VALUES(?,?,?,?,?,?)",
                (asset_id, source_id, source["schema_version"], canonical, digest, at),
            )
            write(self.connection, at, source["owner"], "asset.ingest", asset_id, {"source": source_id, "digest": digest})
        return digest

    def get(self, asset_id):
        row = self.connection.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        if row is None:
            raise KeyError(asset_id)
        return dict(row)
