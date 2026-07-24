import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "inventory.db")

# Ensure the data directory exists (git does not track empty folders)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


async def get_db():
    db = await aiosqlite.connect(DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    # Wait (up to 15s) for a busy lock instead of erroring; WAL lets readers
    # and a writer work concurrently so "database is locked" is far rarer.
    await db.execute("PRAGMA busy_timeout=15000")
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH, timeout=30) as db:
        # Concurrency hardening so startup doesn't fail with "database is locked"
        # when another connection (e.g. a still-running instance) is active.
        await db.execute("PRAGMA busy_timeout=15000")
        try:
            await db.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
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
                barcode TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);
            CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
            CREATE INDEX IF NOT EXISTS idx_scans_session ON audit_scans(session_id);
            CREATE INDEX IF NOT EXISTS idx_scans_barcode ON audit_scans(barcode);

            CREATE TABLE IF NOT EXISTS stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                filename TEXT,
                item_count INTEGER,
                mode TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS category_overrides (
                category TEXT PRIMARY KEY,
                big_group TEXT
            );

            CREATE TABLE IF NOT EXISTS reconcile_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id INTEGER,
                item_number TEXT,
                barcode TEXT,
                description TEXT,
                category TEXT,
                big_group TEXT,
                cost REAL,
                retail_price REAL,
                source TEXT,
                flagged_at TIMESTAMP,
                status TEXT DEFAULT 'missing',
                resolved_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                phone TEXT,
                items TEXT,
                status TEXT DEFAULT 'new',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                blurb TEXT DEFAULT '',
                discount_pct REAL DEFAULT 0,
                status TEXT DEFAULT 'active',       -- active / ended
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS campaign_items (
                campaign_id INTEGER NOT NULL,
                item_number TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (campaign_id, item_number),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            );
        """)

        # Seed the default store if none exist
        async with db.execute("SELECT COUNT(*) FROM stores") as cur:
            if (await cur.fetchone())[0] == 0:
                await db.execute("INSERT INTO stores (name) VALUES (?)", ("ABC Money Loan",))

        async with db.execute("PRAGMA table_info(stores)") as cur:
            store_cols = {row[1] for row in await cur.fetchall()}
        if "address" not in store_cols:
            await db.execute("ALTER TABLE stores ADD COLUMN address TEXT DEFAULT ''")
        # Seed the ABC store address if not set yet
        await db.execute(
            "UPDATE stores SET address=? WHERE name='ABC Money Loan' AND (address IS NULL OR address='')",
            ("146 E. State Street, Trenton, NJ 08608",)
        )

        async with db.execute("PRAGMA table_info(inquiries)") as cur:
            inq_cols = {row[1] for row in await cur.fetchall()}
        if "email" not in inq_cols:
            await db.execute("ALTER TABLE inquiries ADD COLUMN email TEXT DEFAULT ''")
        if "hold_expires" not in inq_cols:
            await db.execute("ALTER TABLE inquiries ADD COLUMN hold_expires TIMESTAMP")

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

        async with db.execute("PRAGMA table_info(sublocations)") as cur:
            sub_cols = {row[1] for row in await cur.fetchall()}
        if "photo" not in sub_cols:
            await db.execute("ALTER TABLE sublocations ADD COLUMN photo TEXT DEFAULT ''")

        async with db.execute("PRAGMA table_info(items)") as cur:
            item_cols = {row[1] for row in await cur.fetchall()}
        # Admin/sale fields (preserved across re-imports)
        add_item_cols = {
            "photo": "TEXT DEFAULT ''",
            "retail_price": "REAL",
            "for_sale": "INTEGER DEFAULT 1",
            "sold": "INTEGER DEFAULT 0",
            "sold_at": "TIMESTAMP",
            "sold_channel": "TEXT DEFAULT ''",     # eBay / Store / Online / …
            "missing": "INTEGER DEFAULT 0",         # in DB but not in latest upload
            "product_type": "TEXT DEFAULT ''",       # jewelry / manufactured / general
            "upc": "TEXT DEFAULT ''",                # UPC/GTIN (separate from Bravo barcode)
            # Jewelry detail fields
            "total_diamond": "TEXT DEFAULT ''",
            "metal_type": "TEXT DEFAULT ''",
            "metal_color": "TEXT DEFAULT ''",
            "total_stone_size": "TEXT DEFAULT ''",
            "condition": "TEXT DEFAULT ''",
            "diamond_authentic": "INTEGER DEFAULT 0",
            # Manufactured detail fields
            "serial_number": "TEXT DEFAULT ''",
            "manufacturer": "TEXT DEFAULT ''",
            "model": "TEXT DEFAULT ''",
            # More jewelry fields (match Bravo headers)
            "metal_purity": "TEXT DEFAULT ''",
            "total_jewelry_weight": "TEXT DEFAULT ''",
            "metal_weight": "TEXT DEFAULT ''",
            "quality": "TEXT DEFAULT ''",
            "authentic_stone": "INTEGER DEFAULT 0",
            "quantity": "TEXT DEFAULT ''",
            "vendor": "TEXT DEFAULT ''",
            "inventory_age": "TEXT DEFAULT ''",
            "date_to_inventory": "TEXT DEFAULT ''",
            "stage": "TEXT DEFAULT ''",   # Inventory / Scrap / Refined / Polish / Sold
            "list_price": "REAL",              # the price the item was listed at
            "customer_name": "TEXT DEFAULT ''",   # buyer name (from sold report)
            "customer_phone": "TEXT DEFAULT ''",  # buyer phone (for follow-up SMS)
        }
        for col, decl in add_item_cols.items():
            if col not in item_cols:
                await db.execute(f"ALTER TABLE items ADD COLUMN {col} {decl}")

        # Indexes on migrated columns (created after the columns exist)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_sold ON items(sold)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_items_upc ON items(upc)")

        # Migration: drop the UNIQUE constraint on items.barcode (multiple units
        # of the same product legitimately share one barcode). SQLite can't drop
        # a constraint, so rebuild the table once if the old schema is detected.
        async with db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='items'"
        ) as cur:
            row = await cur.fetchone()
        if row and row[0] and "barcode TEXT UNIQUE" in row[0]:
            new_sql = row[0].replace("barcode TEXT UNIQUE", "barcode TEXT")
            async with db.execute("PRAGMA table_info(items)") as cur:
                cols = [r[1] for r in await cur.fetchall()]
            collist = ", ".join(cols)
            await db.execute("ALTER TABLE items RENAME TO items_old_uniq")
            await db.execute(new_sql)
            await db.execute(f"INSERT INTO items ({collist}) SELECT {collist} FROM items_old_uniq")
            await db.execute("DROP TABLE items_old_uniq")
            # Recreate the item indexes lost with the old table
            await db.execute("CREATE INDEX IF NOT EXISTS idx_items_barcode ON items(barcode)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_items_source ON items(source)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_items_sold ON items(sold)")

        await db.commit()
