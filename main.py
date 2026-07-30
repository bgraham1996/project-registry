from app.cache.cache_manager import Db
from app.cache.watchlist_repo import WatchlistRepo
from app.scanner.scanner import Scanner


def main():
    db = Db()
    existed = db.init()
    verb = "Connected to existing" if existed else "Created new"
    print(f"{verb} registry database at {db.path()}")

    repo = WatchlistRepo(db.connection)

    roots = db.config.scan_roots()
    print(f"Scanning {len(roots)} root(s): {', '.join(str(r) for r in roots)}")
    Scanner(repo, roots).scan()  # idempotent upserts; re-running just refreshes rows

    items = repo.all()
    print(f"{len(items)} watched dir(s):")
    for item in items:
        branch = f" @{item.branchName}" if item.branchName else ""
        print(f"  - {item.projectName or '?'} [{item.dirType or '?'}]{branch}  {item.path}")

    db.close()


if __name__ == "__main__":
    main()
