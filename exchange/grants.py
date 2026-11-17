from .audit import write


class Grants:
    def __init__(self, connection):
        self.connection = connection

    def issue(self, grant_id, source_id, recipient, purpose, valid_until, at):
        source = self.connection.execute("SELECT owner FROM sources WHERE id=?", (source_id,)).fetchone()
        if source is None:
            raise KeyError(source_id)
        with self.connection:
            self.connection.execute(
                "INSERT INTO grants(id,source_id,recipient,purpose,valid_until) VALUES(?,?,?,?,?)",
                (grant_id, source_id, recipient, purpose, valid_until),
            )
            write(self.connection, at, source["owner"], "grant.issue", grant_id, {"source": source_id, "recipient": recipient})

    def permits(self, source_id, recipient, purpose, at):
        row = self.connection.execute(
            "SELECT id FROM grants WHERE source_id=? AND recipient=? AND purpose=? "
            "AND status='active' AND valid_until>=? ORDER BY id LIMIT 1",
            (source_id, recipient, purpose, at),
        ).fetchone()
        return row["id"] if row else None
