# How to see what changed on the store PC

Use this when the printer (or anything else) suddenly stops working right and
you want to know **what changed recently** on the computer — whether someone
did it here at the keyboard or connected in remotely.

## The easy way — one click

1. Open the `automation` folder.
2. Double-click **`system-change-report.bat`**.
3. Click **Yes** when Windows asks for administrator permission (this is needed
   to read the sign-in history — the report only *reads*, it changes nothing).
4. A window opens and builds the report. A copy is also saved to the **Desktop**
   as `PC-Changes-<date>.txt`, so you can send it to whoever helps you.

The report is in plain English and has 6 sections:

| Section | What it tells you |
|---------|-------------------|
| 1. Remote-access tools | Whether Remote Desktop is on, and if TeamViewer / AnyDesk / etc. are installed or running right now |
| 2. Sign-ins | Who logged in and whether it was **at the keyboard** or **REMOTE (over the network)** |
| 3. Installs, driver changes & failures | Windows' own timeline of software installs, **driver changes**, and crashes — the most useful section for printer problems |
| 4. Programs installed/updated | New or updated programs in the period |
| 5. Windows updates | Windows updates that installed (these often change printer drivers) |
| 6. Printers | Your current printers, and recent printer add/remove/error events |

### What to look for when a printer breaks
- **Section 3 / 5** around the date it stopped working: a **driver change** or a
  **Windows update** on that day is the usual cause.
- **Section 2**: any row marked **REMOTE** means someone connected in over the
  network — check whether that was expected (e.g. your IT person).
- **Section 1**: if a remote-control app is **RUNNING NOW** and you didn't start
  it, close it and change your passwords.

## Look back further than 2 weeks

By default it covers the last **14 days**. To see a full month, edit
`system-change-report.bat` and change `-Days 14` to `-Days 30`.

## Want it to run by itself

You can have Windows run this weekly (e.g. every Monday 9 AM) the same way the
auto-import task is set up — see the Task Scheduler steps in `README.md`, but
point the task at `system-change-report.bat` instead. Note it needs admin
rights, so in the task's settings tick **"Run with highest privileges."**

## Built-in Windows tools (no file needed)

If you ever want to check without this script:
- **Reliability Monitor** — press Start, type *reliability*, open **View
  reliability history**. A day-by-day chart of installs, updates, and crashes.
- **Event Viewer** — press Start, type *event viewer*. Sign-ins are under
  *Windows Logs → Security*; printer issues under *Applications and Services
  Logs → Microsoft → Windows → PrintService*.
