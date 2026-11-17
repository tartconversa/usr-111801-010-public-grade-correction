import argparse
import json
from .service import Exchange

def main():
    parser = argparse.ArgumentParser(description="景区资料本地协作演练")
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    service = Exchange(args.database)
    try:
        service.catalog.register("source", "资料室", "甲地", "review",
                                 [("finding", "服务观察", "text", False)], "2026-11-17")
        service.catalog.ingest("item-1", "source", {"finding": "指引可见"}, "2026-11-17")
        service.grants.issue("g-1", "source", "复核组", "质量复核", "2026-12-31", "2026-11-17")
        service.policies.set("甲地", "review", "质量复核", "allow", "2026-11-17", "资料室")
        revision = service.products.assemble("dossier", "复核资料", ["item-1"], "2026-11-17", "资料室")
        receipt = service.delivery.send("d-1", "dossier", revision, "复核组", "质量复核", "2026-11-17")
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    finally:
        service.close()

if __name__ == "__main__":
    main()
