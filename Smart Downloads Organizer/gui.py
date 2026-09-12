"""
gui.py
------
Tkinter front-end for the Smart Downloads Organizer.
Run with:  python3 gui.py
Needs only the Python standard library (tkinter ships with most Python installs).
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import organizer_core as core

CONFIG_FILENAME = "organizer_config.json"


class OrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Downloads Organizer")
        self.geometry("780x560")
        self.minsize(680, 480)

        self.folder = tk.StringVar()
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)
        self.config = core.load_config(self.config_path)
        core.save_config(self.config, self.config_path)  # ensure a config file exists to edit

        self.last_report = None
        self.pending_actions = []  # actions from the most recent "Preview" click

        self._build_top_bar()
        self._build_tabs()
        self._build_status_bar()

    # ------------------------------------------------------------------ UI

    def _build_top_bar(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill="x")

        ttk.Label(bar, text="Folder to organize:").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.folder, width=50)
        entry.pack(side="left", padx=6)
        ttk.Button(bar, text="Browse...", command=self._choose_folder).pack(side="left")
        ttk.Button(bar, text="Scan", command=self._scan).pack(side="left", padx=(12, 0))

        # Default to the user's actual Downloads folder if it exists
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(default_downloads):
            self.folder.set(default_downloads)

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.tab_categorize = ttk.Frame(self.notebook)
        self.tab_duplicates = ttk.Frame(self.notebook)
        self.tab_stale = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_log = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_categorize, text="1. Categorize")
        self.notebook.add(self.tab_duplicates, text="2. Duplicates")
        self.notebook.add(self.tab_stale, text="3. Stale Files")
        self.notebook.add(self.tab_settings, text="Settings")
        self.notebook.add(self.tab_log, text="Log / Undo")

        self._build_categorize_tab()
        self._build_duplicates_tab()
        self._build_stale_tab()
        self._build_settings_tab()
        self._build_log_tab()

    def _build_categorize_tab(self):
        frame = self.tab_categorize
        ttk.Label(frame, text="Files will be sorted into folders by type (Images, Documents, etc.)",
                  wraplength=700).pack(anchor="w", padx=10, pady=(10, 4))

        self.categorize_tree = self._make_tree(frame, ("File", "Category"))
        btns = ttk.Frame(frame)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="Preview (dry run)", command=self._preview_categorize).pack(side="left")
        ttk.Button(btns, text="Apply", command=self._apply_categorize).pack(side="left", padx=6)

    def _build_duplicates_tab(self):
        frame = self.tab_duplicates
        ttk.Label(
            frame,
            text="Identical files (matched by content, not just filename). "
                 "The oldest copy is kept in place; others are moved to a Duplicates folder.",
            wraplength=700,
        ).pack(anchor="w", padx=10, pady=(10, 4))

        self.duplicates_tree = self._make_tree(frame, ("Duplicate group", "Kept copy"))
        btns = ttk.Frame(frame)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="Preview (dry run)", command=self._preview_duplicates).pack(side="left")
        ttk.Button(btns, text="Apply", command=self._apply_duplicates).pack(side="left", padx=6)

    def _build_stale_tab(self):
        frame = self.tab_stale
        self.stale_label = ttk.Label(
            frame,
            text=f"Files untouched for {self.config['stale_days']}+ days (change this in Settings).",
            wraplength=700,
        )
        self.stale_label.pack(anchor="w", padx=10, pady=(10, 4))

        self.stale_tree = self._make_tree(frame, ("File", "Last modified"))
        btns = ttk.Frame(frame)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="Preview (dry run)", command=self._preview_stale).pack(side="left")
        ttk.Button(btns, text="Apply", command=self._apply_stale).pack(side="left", padx=6)

    def _build_settings_tab(self):
        frame = self.tab_settings
        pad = {"padx": 10, "pady": 6}

        ttk.Label(frame, text="Stale threshold (days):").grid(row=0, column=0, sticky="w", **pad)
        self.stale_days_var = tk.IntVar(value=self.config["stale_days"])
        ttk.Spinbox(frame, from_=1, to=3650, textvariable=self.stale_days_var, width=8).grid(
            row=0, column=1, sticky="w", **pad
        )

        ttk.Label(frame, text="Duplicates folder name:").grid(row=1, column=0, sticky="w", **pad)
        self.dup_folder_var = tk.StringVar(value=self.config["duplicates_folder"])
        ttk.Entry(frame, textvariable=self.dup_folder_var, width=24).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(frame, text="Stale folder name:").grid(row=2, column=0, sticky="w", **pad)
        self.stale_folder_var = tk.StringVar(value=self.config["stale_folder"])
        ttk.Entry(frame, textvariable=self.stale_folder_var, width=24).grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(
            frame,
            text="Category -> extensions mapping is stored in organizer_config.json "
                 "next to this script if you want to hand-edit it.",
            wraplength=650,
        ).grid(row=3, column=0, columnspan=2, sticky="w", **pad)

        ttk.Button(frame, text="Save Settings", command=self._save_settings).grid(
            row=4, column=0, sticky="w", **pad
        )

    def _build_log_tab(self):
        frame = self.tab_log
        ttk.Label(
            frame,
            text="Every real move is logged so it can be undone. Nothing is ever deleted -"
                 " duplicates and stale files are only ever moved.",
            wraplength=700,
        ).pack(anchor="w", padx=10, pady=(10, 4))

        self.log_text = tk.Text(frame, height=18, wrap="none")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=6)

        btns = ttk.Frame(frame)
        btns.pack(fill="x", padx=10, pady=6)
        ttk.Button(btns, text="Refresh Log", command=self._refresh_log).pack(side="left")
        ttk.Button(btns, text="Undo Last Run", command=self._undo_last_run).pack(side="left", padx=6)

    def _build_status_bar(self):
        self.status_var = tk.StringVar(value="Choose a folder and click Scan to begin.")
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x")

    def _make_tree(self, parent, columns):
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=10)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=320, anchor="w")
        tree.pack(fill="both", expand=True, padx=10, pady=4)
        return tree

    # -------------------------------------------------------------- actions

    def _choose_folder(self):
        chosen = filedialog.askdirectory()
        if chosen:
            self.folder.set(chosen)

    def _require_folder(self):
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("No folder", "Please choose a valid folder first.")
            return None
        return folder

    def _scan(self):
        folder = self._require_folder()
        if not folder:
            return
        self.last_report = core.scan_folder(folder, self.config)
        self._render_categorize()
        self._render_duplicates()
        self._render_stale()
        self.status_var.set(
            f"Scanned {folder}: "
            f"{sum(len(v) for v in self.last_report['categorized'].values())} files, "
            f"{len(self.last_report['duplicates'])} duplicate group(s), "
            f"{len(self.last_report['stale'])} stale file(s)."
        )

    def _render_categorize(self):
        self.categorize_tree.delete(*self.categorize_tree.get_children())
        if not self.last_report:
            return
        for category, paths in self.last_report["categorized"].items():
            for path in paths:
                self.categorize_tree.insert("", "end", values=(os.path.basename(path), category))

    def _render_duplicates(self):
        self.duplicates_tree.delete(*self.duplicates_tree.get_children())
        if not self.last_report:
            return
        for group in self.last_report["duplicates"]:
            group_sorted = sorted(group, key=lambda p: os.path.getmtime(p))
            keeper = os.path.basename(group_sorted[0])
            others = ", ".join(os.path.basename(p) for p in group_sorted[1:])
            self.duplicates_tree.insert("", "end", values=(others, keeper))

    def _render_stale(self):
        self.stale_tree.delete(*self.stale_tree.get_children())
        if not self.last_report:
            return
        for path in self.last_report["stale"]:
            mtime = os.path.getmtime(path)
            from datetime import datetime
            when = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            self.stale_tree.insert("", "end", values=(os.path.basename(path), when))

    def _ensure_scanned(self):
        if not self.last_report:
            messagebox.showinfo("Scan first", "Click Scan first so there's something to preview.")
            return False
        return True

    def _preview_categorize(self):
        if not self._ensure_scanned():
            return
        folder = self._require_folder()
        actions = core.plan_categorize_actions(self.last_report, folder, self.config)
        preview = core.execute_actions(actions, self._log_path(), dry_run=True)
        self.pending_actions = actions
        self.status_var.set(f"Preview: {len(preview)} file(s) would be sorted into category folders.")

    def _apply_categorize(self):
        self._apply(self.pending_actions, "categorized")

    def _preview_duplicates(self):
        if not self._ensure_scanned():
            return
        folder = self._require_folder()
        actions = core.plan_duplicate_actions(self.last_report, folder, self.config)
        preview = core.execute_actions(actions, self._log_path(), dry_run=True)
        self.pending_actions = actions
        self.status_var.set(f"Preview: {len(preview)} duplicate file(s) would be moved to "
                             f"{self.config['duplicates_folder']}/.")

    def _apply_duplicates(self):
        self._apply(self.pending_actions, "de-duplicated")

    def _preview_stale(self):
        if not self._ensure_scanned():
            return
        folder = self._require_folder()
        actions = core.plan_stale_actions(self.last_report, folder, self.config)
        preview = core.execute_actions(actions, self._log_path(), dry_run=True)
        self.pending_actions = actions
        self.status_var.set(f"Preview: {len(preview)} stale file(s) would be archived to "
                             f"{self.config['stale_folder']}/.")

    def _apply_stale(self):
        self._apply(self.pending_actions, "archived")

    def _apply(self, actions, verb):
        if not actions:
            messagebox.showinfo("Nothing to apply", "Run a Preview first (or there's nothing to do).")
            return
        if not messagebox.askyesno("Confirm", f"Move {len(actions)} file(s) now? This can be undone "
                                               f"from the Log / Undo tab."):
            return
        performed = core.execute_actions(actions, self._log_path(), dry_run=False)
        self.pending_actions = []
        self.status_var.set(f"Done: {len(performed)} file(s) {verb}.")
        self._scan()  # refresh views since files have moved
        self._refresh_log()

    def _save_settings(self):
        self.config["stale_days"] = self.stale_days_var.get()
        self.config["duplicates_folder"] = self.dup_folder_var.get()
        self.config["stale_folder"] = self.stale_folder_var.get()
        core.save_config(self.config, self.config_path)
        self.stale_label.config(text=f"Files untouched for {self.config['stale_days']}+ days "
                                      f"(change this in Settings).")
        messagebox.showinfo("Saved", "Settings saved to organizer_config.json.")

    def _log_path(self):
        folder = self.folder.get().strip()
        return os.path.join(folder, "undo_log.json") if folder else "undo_log.json"

    def _refresh_log(self):
        self.log_text.delete("1.0", "end")
        log_path = self._log_path()
        if not os.path.exists(log_path):
            self.log_text.insert("end", "No moves logged yet for this folder.")
            return
        import json
        with open(log_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not entries:
            self.log_text.insert("end", "Log is empty.")
            return
        for entry in entries:
            self.log_text.insert(
                "end",
                f"[{entry['timestamp']}] {entry['reason']}\n"
                f"    {entry['src']}\n -> {entry['dst']}\n\n",
            )

    def _undo_last_run(self):
        log_path = self._log_path()
        last_ts = core.last_run_timestamp(log_path)
        if last_ts is None:
            messagebox.showinfo("Nothing to undo", "No recorded moves for this folder.")
            return
        if not messagebox.askyesno("Undo last run", "Move the most recent batch of files back to "
                                                      "where they came from?"):
            return
        reverted = core.undo_last_run(log_path, since_timestamp=last_ts)
        messagebox.showinfo("Undo complete", f"Restored {len(reverted)} file(s).")
        self._scan()
        self._refresh_log()


if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
