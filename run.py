import uvicorn

if __name__ == "__main__":
    print("=" * 56)
    print("  ABC Inventory running")
    print("  Open in your browser:  http://localhost:8000")
    print("  (leave this window open; close it to stop)")
    print("=" * 56)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
