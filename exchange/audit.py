import json


def write(connection, at, actor, action, subject, details):
    connection.execute(
        "INSERT INTO audit(at,actor,action,subject,details) VALUES(?,?,?,?,?)",
        (at, actor, action, subject, json.dumps(details, ensure_ascii=False, sort_keys=True)),
    )


def history(connection, subject):
    rows = connection.execute(
        "SELECT at,actor,action,details FROM audit WHERE subject=? ORDER BY id",
        (subject,),
    ).fetchall()
    return [dict(row) for row in rows]
