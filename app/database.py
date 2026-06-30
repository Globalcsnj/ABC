import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "inventory.db")


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
                item_code TEXT NOT NULL,
                full_ref TEXT NOT NULL,
                description TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES audit_sessions(id),
                FOREIGN KEY (location_id) REFERENCES locations(id),
                FOREIGN KEY (sublocation_id) REFERENCES sublocations(id)
            );

            CREATE TABLE IF NOT EXISTS items (
                code TEXT PRIMARY KEY,
                description TEXT,
                category TEXT,
                price REAL,
                source TEXT,
                imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()
