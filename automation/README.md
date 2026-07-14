# Bravo → Inventory automation

Two layers. **Layer 1 is here and ready.** Layer 2 (driving Bravo itself) needs
screenshots of the Bravo screens before it can be built reliably.

## Layer 1 — auto-import the exported CSVs (ready)

Once you've exported Bravo's CSVs into a folder, this cleans and uploads them
into the inventory app for you — no manual upload, no Excel macro, and it fixes
the UPC/barcode scientific-notation problem automatically (the app does the
cleanup on import).

### One-time setup
1. Make sure the inventory app is running (`start.bat`) — it must be reachable
   at `http://localhost:8000`.
2. Open `auto_import.py` and check the settings at the top:
   - `WATCH_DIR` — the folder Bravo exports land in
     (default `C:\Users\DELL\Desktop\BRAVO DOWNLOADS`).
   - `SOURCE_RULES` — maps each file to a report type by a word in its name
     (e.g. a file named `...retail...` → retail, `...loan...` → loan). Adjust
     these to match your 4 export names.

### Run it manually
Double-click **`run-auto-import.bat`**. It imports every CSV in the folder,
moves each into a `processed\` subfolder, and writes results to
`auto_import.log`.

### Run it automatically every day (Task Scheduler)
1. Open **Task Scheduler** → **Create Basic Task**.
2. Name: `ABC Auto Import`. Trigger: **Daily** at the time you finish the Bravo
   export (e.g. 9:15 AM).
3. Action: **Start a program** → Program/script: `run-auto-import.bat`
   (browse to this folder). Finish.
4. To run continuously instead (import the moment a file appears), set the
   program to `python` with arguments `auto_import.py --watch` and trigger
   **At log on**.

### What it does NOT do
- It does **not** open Bravo or export anything — you (or Layer 2) put the CSVs
  in the folder first.
- It never deletes your files; processed ones are moved to `processed\`.

## Layer 2 — drive Bravo (not built yet)

Automating Bravo itself (advance to next business day → Print → export 4 CSVs)
is desktop UI automation and must be tuned against the real screens. It's also
more fragile and the "advance business day" step changes Bravo data, so it
needs guards. To build it, send screenshots of:
1. The Bravo **login window**.
2. The **advance / next-business-day** screen.
3. The exact **menu path** to each report.
4. The **Print / export-to-CSV dialog** (this is the finicky part).

Recommended first: ask Bravo support whether it can **export/schedule reports
to a file** or has an API — if so, Layer 2 becomes trivial and reliable.
