"""Seite »Abläufe«: fertige Befehlsfolgen je Modul mit Parametern und Schritt-für-Schritt-Ausführung."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFormLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..theme import C
from ..uart.recipes import RECIPES
from ..uart.runner import RecipeRunner, expect_label, step_label
from .common import Card, hbox, label
from .widgets import HelpPanel, help_dot

COL_NR, COL_STEP, COL_CMD, COL_EXP, COL_STATE = range(5)
STATE = {"run": ("▶ läuft", C["amber"]), "ok": ("✔ OK", C["teal"]), "error": ("✖ Fehler", C["red"]),
         "timeout": ("⏱ keine Antwort", C["red"]), "optional": ("– nicht unterstützt", C["muted"]), "skipped": ("– übersprungen", C["muted"]), "": ("", C["muted"])}


class RecipesPage(QWidget):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.ctl = mw.uart
        self.runner = RecipeRunner(self.ctl)
        self.recipe = None
        self.var_edits: dict[str, QLineEdit] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(HelpPanel("recipes", mw.settings))

        head = Card("Modul")
        self.mod_lbl = label("", "Accent")
        self.conn_lbl = label("", "Muted")
        b_uart = QPushButton("Zum UART-Terminal")
        b_uart.clicked.connect(lambda: mw.goto("uart"))
        head.lay.addWidget(hbox(self.mod_lbl, help_dot(
            "Die Abläufe gehören zum Modul, das im UART-Terminal (Schritt ②) gewählt ist. "
            "Dort auch den COM-Port verbinden."), None, self.conn_lbl, b_uart))
        root.addWidget(head)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(10)

        # Liste der Abläufe
        left = Card("Abläufe")
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setStyleSheet("QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #233041; }")
        self.list.currentRowChanged.connect(self._select)
        left.lay.addWidget(self.list)
        split.addWidget(left)

        # Details
        right = Card("Ablauf")
        self.title = label("", "Big")
        self.title.setWordWrap(True)
        self.desc = label("", "Muted")
        self.desc.setWordWrap(True)
        right.lay.addWidget(self.title)
        right.lay.addWidget(self.desc)
        self.var_host = QWidget()
        self.var_form = QFormLayout(self.var_host)
        self.var_form.setContentsMargins(0, 0, 0, 0)
        self.var_form.setSpacing(6)
        right.lay.addWidget(label("PARAMETER", "CardTitle"))
        right.lay.addWidget(self.var_host)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "SCHRITT", "BEFEHL", "ERWARTET", "STATUS"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NR, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_STEP, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_CMD, QHeaderView.Stretch)
        hh.setSectionResizeMode(COL_EXP, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_STATE, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._row_sel)
        right.lay.addWidget(self.table, 3)

        self.answer = QLabel("")
        self.answer.setObjectName("Muted")
        self.answer.setWordWrap(True)
        self.answer.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.lay.addWidget(hbox(label("ANTWORT", "CardTitle"), help_dot(
            "Antwort des Moduls auf den ausgewählten Schritt. Das vollständige Protokoll steht im UART-Terminal."),
            None))
        right.lay.addWidget(self.answer)

        self.cb_stop = QCheckBox("Bei Fehler anhalten")
        self.cb_stop.setChecked(True)
        self.cb_stop.setToolTip("Optionale Schritte (z. B. Abfragen, die nicht jedes Modul kennt) brechen nie ab")
        self.b_start = QPushButton("▶  Ablauf starten")
        self.b_start.setObjectName("Primary")
        self.b_start.setMinimumWidth(160)
        self.b_start.clicked.connect(self.start)
        self.b_from = QPushButton("Ab Auswahl")
        self.b_from.setToolTip("Ab dem ausgewählten Schritt bis zum Ende ausführen")
        self.b_from.clicked.connect(lambda: self.start(from_sel=True))
        self.b_one = QPushButton("Nur Auswahl")
        self.b_one.setToolTip("Nur den ausgewählten Schritt senden")
        self.b_one.clicked.connect(lambda: self.start(from_sel=True, single=True))
        self.b_stop = QPushButton("Stopp")
        self.b_stop.setObjectName("Danger")
        self.b_stop.clicked.connect(lambda: self.runner.stop())
        self.status = label("", "Teal")
        self.status.setWordWrap(True)
        right.lay.addWidget(hbox(self.cb_stop, None, self.b_one, self.b_from, self.b_stop, self.b_start))
        right.lay.addWidget(self.status)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        split.setSizes([300, 900])
        root.addWidget(split, 1)

        self.runner.step_started.connect(self._started)
        self.runner.step_done.connect(self._step_done)
        self.runner.finished.connect(self._finished)
        self.runner.need_confirm.connect(self._confirm)
        self.ctl.module_changed.connect(lambda _m: self.reload())
        self.ctl.state.connect(lambda *_: self._update_head())
        self.answers: dict[int, str] = {}
        self.reload()

    # ------------------------------------------------------------------
    def _update_head(self):
        m = self.ctl.module
        self.mod_lbl.setText(f"{m.label}  ·  {m.family}")
        self.conn_lbl.setText(f"● verbunden ({self.ctl.port})" if self.ctl.is_open else "○ COM-Port nicht verbunden")
        self.conn_lbl.setStyleSheet(f"color:{C['teal'] if self.ctl.is_open else C['muted']}")
        self._buttons()

    def _buttons(self):
        run = self.runner.running
        ok = self.ctl.is_open and self.recipe is not None and not run
        self.b_start.setEnabled(ok)
        has_sel = bool(self.table.selectionModel() and self.table.selectionModel().selectedRows())
        self.b_from.setEnabled(ok and has_sel)
        self.b_one.setEnabled(ok and has_sel)
        self.b_stop.setEnabled(run)
        self.list.setEnabled(not run)

    def reload(self):
        self.runner.stop()
        self.list.clear()
        recs = RECIPES.get(self.ctl.module.key, [])
        for r in recs:
            it = QListWidgetItem(f"{r.name}\n{len(r.steps)} Schritte")
            it.setToolTip(r.desc)
            self.list.addItem(it)
        self._update_head()
        if recs:
            self.list.setCurrentRow(0)
        else:
            self.recipe = None
            self.title.setText("Keine Abläufe für dieses Modul")
            self.desc.setText("")
            self.table.setRowCount(0)

    def _select(self, row):
        recs = RECIPES.get(self.ctl.module.key, [])
        if not 0 <= row < len(recs):
            return
        self.recipe = recs[row]
        self.title.setText(self.recipe.name)
        self.desc.setText(self.recipe.desc)
        while self.var_form.rowCount():
            self.var_form.removeRow(0)
        self.var_edits = {}
        saved = (self.mw.settings.get("recipe_vars") or {})
        for v in self.recipe.vars:
            e = QLineEdit(saved.get(v.key, v.default))
            e.setPlaceholderText(v.default)
            e.setToolTip(v.hint)
            e.textChanged.connect(self._refresh_cmds)
            lab = hbox(label(v.label, "Muted"), help_dot(v.hint), spacing=4) if v.hint else label(v.label, "Muted")
            self.var_form.addRow(lab, e)
            self.var_edits[v.key] = e
        if not self.recipe.vars:
            self.var_form.addRow(label("Keine Parameter nötig.", "Muted"))
        self.answers = {}
        self.answer.setText("")
        self.status.setText("")
        self._fill_table()

    def values(self):
        return {k: e.text() for k, e in self.var_edits.items()}

    def _fill_table(self):
        m = self.ctl.module
        vals = self.values()
        self.table.setRowCount(0)
        for i, st in enumerate(self.recipe.steps):
            self.table.insertRow(i)
            desc = st.desc + ("  (optional)" if st.optional else "")
            cells = [str(i + 1), desc, step_label(st, vals, m), expect_label(st, m), ""]
            for c, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if c == COL_CMD:
                    f = it.font()
                    f.setFamily("Consolas")
                    it.setFont(f)
                    it.setForeground(QColor(C["amber"] if st.kind in ("at", "frame", "text", "hex") else C["violet"]))
                elif c in (COL_NR, COL_EXP):
                    it.setForeground(QColor(C["muted"]))
                elif c == COL_STEP and st.kind == "hint":
                    it.setForeground(QColor(C["teal"]))
                self.table.setItem(i, c, it)
        self._buttons()

    def _refresh_cmds(self):
        if self.recipe is None:
            return
        vals = self.values()
        for i, st in enumerate(self.recipe.steps):
            it = self.table.item(i, COL_CMD)
            if it:
                it.setText(step_label(st, vals, self.ctl.module))

    def _row_sel(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.answer.setText(self.answers.get(rows[0].row(), ""))
        self._buttons()

    # ------------------------------------------------------------------ Ausführung
    def start(self, from_sel=False, single=False):
        if self.recipe is None:
            return
        if not self.ctl.is_open:
            self.mw.toast("Zuerst im UART-Terminal den COM-Port verbinden.", error=True)
            return
        start = 0
        if from_sel:
            rows = self.table.selectionModel().selectedRows()
            if not rows:
                return
            start = rows[0].row()
        vals = self.values()
        saved = dict(self.mw.settings.get("recipe_vars") or {})
        saved.update(vals)
        self.mw.settings.set("recipe_vars", saved)
        for i in range(self.table.rowCount()):
            if i >= start:
                self._set_state(i, "")
                self.answers.pop(i, None)
        self.status.setText("Läuft …")
        self.runner.start(self.recipe, vals, self.cb_stop.isChecked(), start, single)
        self._buttons()

    def _set_state(self, i, key, text=""):
        it = self.table.item(i, COL_STATE)
        if it is None:
            return
        t, col = STATE.get(key, ("", C["muted"]))
        it.setText(t)
        it.setForeground(QColor(col))
        it.setToolTip(text)

    def _started(self, i):
        self._set_state(i, "run")
        self.table.blockSignals(True)
        self.table.selectRow(i)
        self.table.blockSignals(False)
        self.table.scrollToItem(self.table.item(i, 0))
        self.answer.setText("")

    def _step_done(self, i, status, text):
        self._set_state(i, status, text)
        self.answers[i] = text
        self.answer.setText(text)

    def _finished(self, summary):
        bad = "Angehalten" in summary or "Fehler" in summary or "abgebrochen" in summary.lower()
        self.status.setText(summary)
        self.status.setStyleSheet(f"color:{C['red'] if bad else C['teal']}")
        self._buttons()

    def _confirm(self, i, text):
        r = QMessageBox.question(self, "Ablauf – Hinweis", text, QMessageBox.Ok | QMessageBox.Cancel)
        self.runner.confirm(r == QMessageBox.Ok)
