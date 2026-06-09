"""Live-trading navigation — primary items + overflow menu."""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple

from PySide6.QtWidgets import QMenu, QPushButton

from ui.interactive_cockpit.button_roles import ROLE_NAV, ROLE_TERTIARY, set_button_role
if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow

LIVE_TRADING_PRIMARY_NAV: Tuple[str, str, ...] = (
    ("overview", "Start"),
    ("comparison", "Vergleich"),
    ("t212", "Broker"),
    ("live_setup", "Portfolio"),
    ("order_review", "Orders"),
    ("risk", "Stopp"),
)

# Full menu for «Mehr» — must match main_window.NAV_ITEMS keys.
MORE_NAV: Tuple[Tuple[str, str], ...] = (
    ("planning", "Planung"),
    ("market", "Kurse"),
    ("investments", "Investments"),
    ("paper", "Paper"),
    ("proposals", "Warteschlange"),
    ("confirmed_orders", "Erledigt"),
    ("tickets", "Tickets"),
    ("trigger", "Trigger"),
    ("intraday", "Intraday"),
    ("activity", "Aktivität"),
    ("audit", "Audit"),
    ("settings", "Mehr"),
)


PILOT_PRIMARY_NAV = LIVE_TRADING_PRIMARY_NAV


def build_live_trading_nav(win: "InteractiveCockpitWindow", nav_layout) -> List[QPushButton]:
    """Primary nav buttons + «Mehr» overflow."""
    buttons: List[QPushButton] = []
    for key, label in LIVE_TRADING_PRIMARY_NAV:
        btn = QPushButton(label)
        set_button_role(btn, ROLE_NAV)
        btn.setCheckable(True)
        btn.clicked.connect(lambda checked, k=key: win._go_nav(k))
        nav_layout.addWidget(btn)
        buttons.append(btn)

    more = QPushButton("Mehr …")
    set_button_role(more, ROLE_TERTIARY)
    more.clicked.connect(lambda: _show_more_menu(win, more))
    nav_layout.addWidget(more)
    buttons.append(more)
    return buttons


build_pilot_nav = build_live_trading_nav


def _show_more_menu(win: "InteractiveCockpitWindow", anchor: QPushButton) -> None:
    menu = QMenu(win)
    for key, label in MORE_NAV:
        menu.addAction(label, lambda k=key: win._go_nav(k))
    menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
