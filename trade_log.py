"""Persistent trade log — tracks long entries and exits to ~/.config/hmm-bot/trades.csv."""

import csv
import os
from datetime import date
from config import CONFIG_DIR

TRADES_FILE = os.path.join(CONFIG_DIR, 'trades.csv')
FIELDNAMES = ['date', 'action', 'price', 'regime', 'confidence', 'pnl_pct']

# Fixed threshold used for trade decisions — consistent across runs
TRADE_THRESHOLD = 0.75


def _load() -> list[dict]:
    if not os.path.exists(TRADES_FILE):
        return []
    with open(TRADES_FILE, newline='') as f:
        return list(csv.DictReader(f))


def _append(row: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    write_header = not os.path.exists(TRADES_FILE)
    with open(TRADES_FILE, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            w.writeheader()
        w.writerow(row)


def get_open_trade() -> dict | None:
    """Return the last ENTER row if it has no matching EXIT, else None."""
    trades = _load()
    last_enter = None
    for t in trades:
        if t['action'] == 'ENTER':
            last_enter = t
        elif t['action'] == 'EXIT':
            last_enter = None
    return last_enter


def signal_position(regime: str, confidence: float) -> str:
    """LONG if regime is Bull and confidence meets threshold, else FLAT."""
    if regime == 'BULL' and confidence >= TRADE_THRESHOLD * 100:
        return 'LONG'
    return 'FLAT'


def update(regime: str, confidence: float, price: float) -> dict:
    """
    Compare today's signal to the open trade state and record any transition.
    Returns a dict with keys: action (ENTER/EXIT/HOLD), open_trade, closed_trades.
    """
    today = date.today().isoformat()
    pos = signal_position(regime, confidence)
    open_trade = get_open_trade()
    action = 'HOLD'

    if pos == 'LONG' and open_trade is None:
        _append({'date': today, 'action': 'ENTER', 'price': f'{price:.2f}',
                 'regime': regime, 'confidence': f'{confidence:.1f}', 'pnl_pct': ''})
        action = 'ENTER'
        open_trade = get_open_trade()

    elif pos == 'FLAT' and open_trade is not None:
        entry_price = float(open_trade['price'])
        pnl = (price / entry_price - 1) * 100
        _append({'date': today, 'action': 'EXIT', 'price': f'{price:.2f}',
                 'regime': regime, 'confidence': f'{confidence:.1f}',
                 'pnl_pct': f'{pnl:.2f}'})
        action = 'EXIT'
        open_trade = None

    closed = _closed_trades()
    return {'action': action, 'open_trade': open_trade, 'closed_trades': closed}


def _closed_trades() -> list[dict]:
    """Return list of completed trades (ENTER+EXIT pairs), newest first."""
    trades = _load()
    completed = []
    pending = None
    for t in trades:
        if t['action'] == 'ENTER':
            pending = t
        elif t['action'] == 'EXIT' and pending:
            completed.append({
                'entry_date':  pending['date'],
                'entry_price': float(pending['price']),
                'exit_date':   t['date'],
                'exit_price':  float(t['price']),
                'pnl_pct':     float(t['pnl_pct']),
            })
            pending = None
    completed.reverse()
    return completed


def format_trade_section(open_trade: dict | None, closed_trades: list[dict],
                         current_price: float) -> str:
    lines = []

    if open_trade:
        entry_price = float(open_trade['price'])
        unrealised = (current_price / entry_price - 1) * 100
        arrow = '📈' if unrealised >= 0 else '📉'
        lines += [
            f'🔓 <b>Open trade</b> — LONG since {open_trade["date"]}',
            f'{arrow} Entry: ${entry_price:,.0f}  →  Now: ${current_price:,.0f}'
            f'  ({unrealised:+.1f}%)',
        ]
    else:
        lines.append('⬜ <b>No open trade</b> — currently flat')

    if closed_trades:
        lines.append('')
        lines.append('📋 <b>Recent trades</b>')
        for t in closed_trades[:5]:
            emoji = '✅' if t['pnl_pct'] >= 0 else '❌'
            lines.append(
                f'{emoji} {t["entry_date"]} → {t["exit_date"]}'
                f'  {t["pnl_pct"]:+.1f}%'
                f'  (${t["entry_price"]:,.0f} → ${t["exit_price"]:,.0f})'
            )

    return '\n'.join(lines)
