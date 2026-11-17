from .audit import write


class Policies:
    def __init__(self, connection):
        self.connection = connection

    def set(self, jurisdiction, classification, purpose, decision, at, actor):
        if decision not in {"allow", "deny"}:
            raise ValueError("规则决策无效")
        old = self.connection.execute(
            "SELECT revision FROM policies WHERE jurisdiction=? AND classification=? AND purpose=?",
            (jurisdiction, classification, purpose),
        ).fetchone()
        revision = old["revision"] + 1 if old else 1
        with self.connection:
            self.connection.execute(
                "INSERT INTO policies(jurisdiction,classification,purpose,decision,revision) VALUES(?,?,?,?,?) "
                "ON CONFLICT(jurisdiction,classification,purpose) DO UPDATE SET decision=excluded.decision,revision=excluded.revision",
                (jurisdiction, classification, purpose, decision, revision),
            )
            write(self.connection, at, actor, "policy.set", jurisdiction, {"purpose": purpose, "revision": revision})
        return revision

    def decision(self, jurisdiction, classification, purpose):
        row = self.connection.execute(
            "SELECT decision,revision FROM policies WHERE jurisdiction=? AND classification=? AND purpose=?",
            (jurisdiction, classification, purpose),
        ).fetchone()
        return (row["decision"], row["revision"]) if row else ("deny", 0)
