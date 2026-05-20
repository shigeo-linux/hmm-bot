#!/usr/bin/env python3
"""HMM Bot runner — called hourly by systemd timer. Sends regime signal at configured hour."""

import sys
import os
import datetime
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, LOG_FILE, CONFIG_DIR
from data import fetch_ohlcv
from features import build_features
from regime import train, regime_series
from paper_trader import backtest, DEFAULT_FEE_RATE, DEFAULT_MIN_HOLD
from trade_log import update as trade_update, format_trade_section
from telegram_client import send_message, TelegramError

BARS_PER_YEAR = 365

os.makedirs(CONFIG_DIR, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)


def _sweep_best(ohlcv, regimes):
    """Return best (threshold, hold, sharpe, ann_ret, total_ret, max_dd) from grid sweep."""
    thresholds = [t / 100 for t in range(60, 96, 5)]
    hold_periods = [1, 3, 5, 7, 10, 15]
    best = None
    best_sharpe = -999

    for thresh in thresholds:
        for hold in hold_periods:
            bt = backtest(ohlcv, regimes, allow_short=False,
                          confidence_threshold=thresh,
                          fee_rate=DEFAULT_FEE_RATE,
                          min_hold=hold)
            strat = bt['strat_ret']
            ann_ret = (1 + strat).prod() ** (BARS_PER_YEAR / len(strat)) - 1
            ann_v = strat.std() * (BARS_PER_YEAR ** 0.5)
            sharpe = ann_ret / ann_v if ann_v else 0.0
            max_dd = ((bt['equity'] / bt['equity'].cummax()) - 1).min()
            total_ret = bt['equity'].iloc[-1] / bt['equity'].iloc[0] - 1

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best = (thresh, hold, sharpe, ann_ret, total_ret, max_dd)

    return best


def _format_message(regime, conf, p_bull, p_side, p_bear, best, last_signals,
                    strat_total, strat_equity, bah_total, bah_equity, start_date, end_date,
                    trade_section):
    thresh, hold, sharpe, ann_ret, _, max_dd = best

    regime_emoji = {'BULL': '🟢', 'BEAR': '🔴', 'SIDEWAYS': '🟡'}.get(regime, '⚪')
    strat_arrow = '📈' if strat_total >= 0 else '📉'
    bah_arrow   = '📈' if bah_total >= 0 else '📉'

    lines = [
        '🤖 <b>BTC/USD Regime Signal</b>',
        f'<b>{datetime.date.today()}</b>',
        '',
        f'{regime_emoji} <b>{regime}</b> — {conf:.1f}% confidence',
        f'Bull: {p_bull:.1f}% | Sideways: {p_side:.1f}% | Bear: {p_bear:.1f}%',
        '',
        trade_section,
        '',
        f'💼 <b>Backtest</b> ({start_date} → {end_date})',
        f'{strat_arrow} Strategy:   ${strat_equity:,.0f}  ({strat_total:+.1f}%)',
        f'{bah_arrow} Buy &amp; hold: ${bah_equity:,.0f}  ({bah_total:+.1f}%)',
        '',
        f'🏆 <b>Best params</b> ({thresh*100:.0f}% threshold · {hold}d hold)',
        f'Sharpe: {sharpe:.2f} · Ann: {ann_ret*100:+.1f}% · Max DD: {max_dd*100:.1f}%',
        '',
        '📅 <b>Last 5 signals</b>',
    ]

    for ts, state, confidence in last_signals[-5:]:
        lines.append(f'{ts.strftime("%Y-%m-%d")}  {state:<10}  {confidence*100:.1f}%')

    return '\n'.join(lines)


def run():
    config = Config()
    now = datetime.datetime.now()
    now_str = now.isoformat(sep=' ', timespec='seconds')

    if now.hour != config.signal_hour:
        sys.exit(0)

    if not config.telegram_token or not config.telegram_chat_id:
        logging.error("Telegram not configured — open HMM Bot settings.")
        config.set('last_status', 'Error: Telegram not configured')
        config.save()
        sys.exit(1)

    try:
        logging.info("Fetching BTC/USD data from Kraken")
        ohlcv = fetch_ohlcv('XBTUSD', '1d', 730)

        logging.info("Building features")
        features = build_features(ohlcv, bars_per_year=BARS_PER_YEAR)

        logging.info("Training HMM (20 restarts)")
        model = train(features)

        logging.info("Inferring regimes")
        regimes = regime_series(model, features)

        latest = regimes.iloc[-1]
        regime = latest['state'].upper()
        conf = latest['confidence'] * 100
        p_bull = latest.get('p_bull', 0) * 100
        p_side = latest.get('p_sideways', 0) * 100
        p_bear = latest.get('p_bear', 0) * 100

        logging.info("Running parameter sweep")
        best = _sweep_best(ohlcv, regimes)

        # Re-run the winning backtest to get equity curve
        thresh, hold = best[0], best[1]
        bt = backtest(ohlcv, regimes, allow_short=False,
                      confidence_threshold=thresh,
                      fee_rate=DEFAULT_FEE_RATE,
                      min_hold=hold)

        initial = 10_000.0
        strat_equity = bt['equity'].iloc[-1]
        strat_total  = (strat_equity / initial - 1) * 100
        bah_equity   = bt['bah_equity'].iloc[-1]
        bah_total    = (bah_equity / initial - 1) * 100
        start_date   = bt.index[0].strftime('%b %Y')
        end_date     = bt.index[-1].strftime('%b %Y')

        last_signals = [
            (ts, row['state'], row['confidence'])
            for ts, row in regimes.tail(5).iterrows()
        ]

        current_price = float(ohlcv['close'].iloc[-1])
        trade_state = trade_update(regime, conf, current_price)
        trade_section = format_trade_section(
            trade_state['open_trade'], trade_state['closed_trades'], current_price
        )
        logging.info(f"Trade log: {trade_state['action']}")

        msg = _format_message(regime, conf, p_bull, p_side, p_bear, best, last_signals,
                              strat_total, strat_equity, bah_total, bah_equity,
                              start_date, end_date, trade_section)
        send_message(config.telegram_token, config.telegram_chat_id, msg)

        status = f'OK — {regime} ({conf:.1f}%)'
        config.set('last_run', now_str)
        config.set('last_status', status)
        config.set('last_signal', regime)
        config.set('last_confidence', f'{conf:.1f}%')
        config.save()
        logging.info(status)

    except TelegramError as e:
        msg = f'Telegram error: {str(e)[:120]}'
        logging.error(msg)
        config.set('last_run', now_str)
        config.set('last_status', f'Error: {msg}')
        config.save()
        sys.exit(1)

    except Exception as e:
        msg = str(e)[:120]
        logging.error(f"Error: {msg}")
        config.set('last_run', now_str)
        config.set('last_status', f'Error: {msg}')
        config.save()
        sys.exit(1)


if __name__ == '__main__':
    run()
