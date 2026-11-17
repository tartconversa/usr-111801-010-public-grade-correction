import hashlib
import json

from .announcements import Announcements
from .audit import write
from .grants import Grants
from .policy import Policies
from .products import Products


class Delivery:
    def __init__(self, connection):
        self.connection = connection
        self.grants = Grants(connection)
        self.policies = Policies(connection)
        self.products = Products(connection)
        self.announcements = Announcements(connection)

    def send(self, delivery_id, product_id, revision, recipient, purpose, at):
        existing = self.connection.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if existing:
            if (existing["product_id"], existing["product_revision"], existing["recipient"], existing["purpose"]) != (product_id, revision, recipient, purpose):
                raise ValueError("交付编号已用于其他请求")
            return dict(existing)
        product = self.connection.execute("SELECT state FROM products WHERE id=? AND revision=?", (product_id, revision)).fetchone()
        if product is None or product["state"] != "draft":
            raise ValueError("数据产品修订不可交付")
        inputs = self.products.inputs(product_id, revision)
        if not inputs:
            raise ValueError("数据产品缺少输入")
        reasons, revisions = [], {}
        for asset in inputs:
            source_id = asset["source_id"]
            if asset["state"] != "active" or not asset["source_active"]:
                reasons.append({"source": source_id, "reason": "inactive"})
            # 公告依据闸门：新领取只能获得当前可核实版本。旧条目保留在库中供
            # 历史回执说明依据，但不得再作为新交付的输入。
            basis_id = asset["basis_announcement_id"]
            if basis_id is not None and not self.announcements.is_effective(basis_id):
                reasons.append({"source": source_id, "reason": "stale-announcement",
                                "announcement": basis_id, "asset": asset["id"]})
            if not self.grants.permits(source_id, recipient, purpose, at):
                reasons.append({"source": source_id, "reason": "grant"})
            decision, policy_revision = self.policies.decision(asset["jurisdiction"], asset["classification"], purpose)
            revisions[source_id] = policy_revision
            if decision != "allow":
                reasons.append({"source": source_id, "reason": "policy"})
        if reasons:
            with self.connection:
                write(self.connection, at, recipient, "delivery.reject", product_id, {"revision": revision, "reasons": reasons})
            raise PermissionError(reasons)
        digest = hashlib.sha256("|".join(asset["digest"] for asset in inputs).encode()).hexdigest()
        # 依据快照随回执固化：日后公告再变更，本回执仍能说明当时依据的版本。
        basis_snapshot = [
            {
                "asset_id": asset["id"],
                "scenic_area": asset["scenic_area"],
                "basis_announcement_id": asset["basis_announcement_id"],
                "digest": asset["digest"],
            }
            for asset in inputs
        ]
        with self.connection:
            self.connection.execute(
                "INSERT INTO deliveries(id,product_id,product_revision,recipient,purpose,created_at,"
                "input_digest,policy_revisions,basis_snapshot) VALUES(?,?,?,?,?,?,?,?,?)",
                (delivery_id, product_id, revision, recipient, purpose, at, digest,
                 json.dumps(revisions, sort_keys=True),
                 json.dumps(basis_snapshot, ensure_ascii=False, sort_keys=True)),
            )
            write(self.connection, at, recipient, "delivery.accept", delivery_id, {"product": product_id, "revision": revision, "inputs": [a["id"] for a in inputs]})
        return dict(self.connection.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone())
