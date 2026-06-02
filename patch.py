with open('dashboard_app.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = "def main():\n    root = Tk()\n    app = DashboardApp(root)\n    root.mainloop()"
rep = """def main():
    import sys
    autostart = "--autostart" in sys.argv
    root = Tk()
    app = DashboardApp(root)
    if autostart:
        root.after(1000, app._on_start)
    root.mainloop()"""

if target in text:
    with open('dashboard_app.py', 'w', encoding='utf-8') as f:
        f.write(text.replace(target, rep))
    print('OK')
else:
    print('Not found')
