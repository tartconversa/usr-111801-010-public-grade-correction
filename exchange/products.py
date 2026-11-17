from .audit import write


class Products:
    def __init__(self, connection):
        self.connection = connection

    def assemble(self, product_id, name, asset_ids, at, actor):
        asset_ids = list(dict.fromkeys(asset_ids))
        if not asset_ids:
            raise ValueError("数据产品缺少输入")
        placeholders = ",".join("?" for _ in asset_ids)
        found = self.connection.execute(
            "SELECT count(*) FROM assets WHERE id IN (" + placeholders + ") AND state='active'",
            asset_ids,
        ).fetchone()[0]
        if found != len(asset_ids):
            raise ValueError("输入记录不可用")
        revision = self.connection.execute("SELECT COALESCE(MAX(revision),0)+1 FROM products WHERE id=?", (product_id,)).fetchone()[0]
        with self.connection:
            self.connection.execute("INSERT INTO products(id,revision,name,created_at) VALUES(?,?,?,?)", (product_id, revision, name, at))
            self.connection.executemany(
                "INSERT INTO product_inputs(product_id,product_revision,asset_id) VALUES(?,?,?)",
                [(product_id, revision, asset_id) for asset_id in asset_ids],
            )
            write(self.connection, at, actor, "product.assemble", product_id, {"revision": revision, "inputs": asset_ids})
        return revision

    def inputs(self, product_id, revision):
        rows = self.connection.execute(
            "SELECT a.*,s.owner,s.jurisdiction,s.classification,s.active AS source_active FROM product_inputs p "
            "JOIN assets a ON a.id=p.asset_id JOIN sources s ON s.id=a.source_id "
            "WHERE p.product_id=? AND p.product_revision=? ORDER BY a.id",
            (product_id, revision),
        ).fetchall()
        return [dict(row) for row in rows]
