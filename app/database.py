import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "inventory.db")

# Ensure the data directory exists (git does not track empty folders)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS locations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sublocations (
                id TEXT PRIMARY KEY,
                location_id TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES locations(id)
            );

            CREATE TABLE IF NOT EXISTS audit_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS audit_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                location_id TEXT,
                sublocation_id TEXT,
                barcode TEXT NOT NULL,
                item_number TEXT,
                full_ref TEXT NOT NULL,
                match_status TEXT DEFAULT 'unknown',
                description TEXT,
                category TEXT,
                item_status TEXT,
                cost REAL,
                item_date TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES audit_sessions(id),
                FOREIGN KEY (location_id) REFERENCES locations(id),
                FOREIGN KEY (sublocation_id) REFERENCES sublocations(id)
            );

            CREATE TABLE IF NOT EXISTS items (
                item_number TEXT PRIMARY KEY,
                barcode TEXT UNIQUE,
                description TEXT,
                category TEXT,
                item_type TEXT,
                item_status TEXT,
                cost REAL,
                item_date TEXT,
                source TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_items_barcode ON items(barcode);

            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Seed the default store if none exist
        async with db.execute("SELECT COUNT(*) FROM stores") as cur:
            if (await cur.fetchone())[0] == 0:
                await db.execute("INSERT INTO stores (name) VALUES (?)", ("ABC Money Loan",))

        # Migrations: add columns to existing databases if missing
        async with db.execute("PRAGMA table_info(audit_sessions)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        if "source" not in cols:
            await db.execute("ALTER TABLE audit_sessions ADD COLUMN source TEXT DEFAULT ''")
        if "categories" not in cols:
            await db.execute("ALTER TABLE audit_sessions ADD COLUMN categories TEXT DEFAULT ''")
        if "store_id" not in cols:
            await db.execute("ALTER TABLE audit_sessions ADD COLUMN store_id INTEGER")

        async with db.execute("PRAGMA table_info(locations)") as cur:
            loc_cols = {row[1] for row in await cur.fetchall()}
        if "photo" not in loc_cols:
            await db.execute("ALTER TABLE locations ADD COLUMN photo TEXT DEFAULT ''")

        await db.commit()
