"""Trading 212 — nur API mit Order-Rechten."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from integrations.trading212.t212_auth_profile_model import (
    PROFILE_CONFIRMED_EXECUTION,
    PROFILE_MONITORING_READONLY,
)
from integrations.trading212.t212_credentials_ui_controller import (
    apply_credentials_from_gui,
    populate_stored_credentials_in_gui,
    test_credentials_from_gui,
)
from integrations.trading212.t212_dual_profile_credential_store import set_profile_credentials
from integrations.trading212.t212_dual_profile_secure_store import save_profile_credentials
from integrations.trading212.t212_execution_profile_bootstrap import ensure_execution_profile_ready
from integrations.trading212.t212_readonly_connection_service import sync_readonly_account
from ui.interactive_cockpit.button_roles import ROLE_PRIMARY, ROLE_SECONDARY, set_button_role
from ui.invest_layout import body_label, configure_form, make_section, set_banner, uniform_button_row

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class BrokerSetupPanel:
    def __init__(self, parent: "QWidget", root: Path) -> None:
        self._parent = parent
        self.root = Path(root)
        self._widget, outer = make_section("Trading 212 — API mit Order-Rechten")

        hint = body_label(
            "Nur dieser Zugang wird genutzt (Konto lesen + Orders senden). "
            "Key muss in der T212-App Order-Rechte haben."
        )
        set_banner(hint, "info")
        outer.addWidget(hint)

        form = QFormLayout()
        configure_form(form)
        self._key = QLineEdit()
        self._key.setPlaceholderText("API Key einfügen oder eingeben")
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._secret = QLineEdit()
        self._secret.setPlaceholderText("API Secret")
        self._secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._secret.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        form.addRow("API Key", self._key)
        form.addRow("API Secret", self._secret)
        outer.addLayout(form)

        test_btn = QPushButton("Verbindung testen")
        save_btn = QPushButton("Speichern")
        set_button_role(test_btn, ROLE_SECONDARY)
        set_button_role(save_btn, ROLE_PRIMARY)
        test_btn.clicked.connect(self._test)
        save_btn.clicked.connect(self._save)
        outer.addLayout(uniform_button_row(test_btn, save_btn))

        self._status_line = body_label("")
        outer.addWidget(self._status_line)

        populate_stored_credentials_in_gui(self.root, self._key, self._secret, only_if_empty=True)
        self.refresh_readiness_line()

    @property
    def widget(self):
        return self._widget

    def refresh_readiness_line(self) -> None:
        from execution.confirmed_live.trading_mode_policy import execution_credentials_ready

        if execution_credentials_ready(self.root):
            self._status_line.setText("API bereit — «Order ausführen» sendet direkt an Trading 212.")
            set_banner(self._status_line, "ok")
        else:
            self._status_line.setText("API Key und Secret speichern (mit Order-Rechten).")
            set_banner(self._status_line, "warn")

    def _test(self) -> None:
        ok, msg = test_credentials_from_gui(
            self._key.text(),
            self._secret.text(),
            "LIVE_READ_ONLY",
            root=self.root,
        )
        if ok:
            QMessageBox.information(
                self._parent,
                "Verbindung",
                msg + "\n\nAPI bleibt aktiv — «Aktualisieren» und Orders sind nicht gesperrt.",
            )
            set_banner(self._status_line, "ok")
            self._status_line.setText(msg + "\nAPI aktiv — Test sperrt Handel nicht.")
        else:
            QMessageBox.warning(self._parent, "Verbindung", msg)
            set_banner(self._status_line, "warn")
            self._status_line.setText(msg)

    def _save(self) -> None:
        key = self._key.text().strip()
        secret = self._secret.text().strip()
        if not key or not secret:
            QMessageBox.warning(self._parent, "API", "Key und Secret erforderlich.")
            return
        apply_credentials_from_gui(
            api_key=key,
            api_secret=secret,
            mode="LIVE_READ_ONLY",
            connection_name="Trading 212",
            persist=True,
            session_only=False,
            root=self.root,
        )
        set_profile_credentials(
            PROFILE_MONITORING_READONLY,
            api_key=key,
            api_secret=secret,
            mode="LIVE_READ_ONLY",
            persist_requested=True,
        )
        set_profile_credentials(
            PROFILE_CONFIRMED_EXECUTION,
            api_key=key,
            api_secret=secret,
            mode="LIVE_READ_ONLY",
            persist_requested=True,
        )
        save_profile_credentials(PROFILE_CONFIRMED_EXECUTION, key, secret)
        from integrations.trading212.t212_execution_dpapi_store import save_execution_credentials

        save_execution_credentials(self.root, key, secret)
        ensure_execution_profile_ready(self.root)
        from integrations.trading212.t212_sync_throttle import should_sync_now

        cached = None
        try:
            from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

            cached = load_cached_broker_status(self.root)
        except Exception:
            pass
        last_ok = cached.last_successful_sync_utc if cached else None
        allow_sync, sync_reason = should_sync_now(self.root, force=True, last_successful_sync_utc=last_ok)
        if allow_sync:
            sync_readonly_account(self.root, force=True)
            sync_note = ""
        else:
            from integrations.trading212.t212_user_messages import humanize_t212_error

            sync_note = f"\n\n{humanize_t212_error(sync_reason) if sync_reason else ''}"
        QMessageBox.information(
            self._parent,
            "Gespeichert",
            "API gespeichert. Orders werden mit einem Klick gesendet." + sync_note,
        )
        if hasattr(self._parent, "_refresh_all"):
            self._parent._refresh_all()
        elif hasattr(self._parent, "_refresh_ui"):
            self._parent._refresh_ui(force=True)
        self.refresh_readiness_line()
