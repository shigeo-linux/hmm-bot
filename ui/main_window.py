import os
import threading
import subprocess
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from config import Config, LOG_FILE
from telegram_client import send_message, test_connection, TelegramError

STYLE_PATH = os.path.join(os.path.dirname(__file__), 'style.css')


def _load_css():
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(STYLE_PATH)
    except Exception:
        pass
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def field_label(text):
    lbl = Gtk.Label(label=text, xalign=1)
    lbl.get_style_context().add_class('field-label')
    return lbl


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='HMM Bot')
        self.set_default_size(480, -1)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        self.set_icon_name('hmm-bot')
        _load_css()
        self.config = Config()
        self._busy = False
        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title('HMM Bot')
        header.set_subtitle('BTC/USD Regime → Telegram')
        self.set_titlebar(header)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_border_width(20)
        main.pack_start(content, True, True, 0)

        # ── Status card ───────────────────────────────────────────
        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        status_card.get_style_context().add_class('status-card')

        status_title = Gtk.Label(label='Status', xalign=0)
        status_title.get_style_context().add_class('section-title')
        status_card.pack_start(status_title, False, False, 0)

        self._status_label = Gtk.Label(label='Not yet run', xalign=0)
        self._status_label.set_line_wrap(True)
        self._status_label.set_max_width_chars(55)
        self._status_label.get_style_context().add_class('status-pending')
        status_card.pack_start(self._status_label, False, False, 0)

        self._last_run_label = Gtk.Label(label='', xalign=0)
        self._last_run_label.set_ellipsize(3)
        self._last_run_label.set_max_width_chars(55)
        self._last_run_label.get_style_context().add_class('meta-label')
        status_card.pack_start(self._last_run_label, False, False, 0)

        content.pack_start(status_card, False, False, 0)

        # ── Send now ──────────────────────────────────────────────
        run_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        self._run_btn = Gtk.Button(label='Send Signal Now')
        self._run_btn.get_style_context().add_class('action-btn')
        self._run_btn.connect('clicked', self._on_run_now)
        run_row.pack_start(self._run_btn, False, False, 0)

        self._spinner = Gtk.Spinner()
        run_row.pack_start(self._spinner, False, False, 0)

        content.pack_start(run_row, False, False, 0)

        sep = Gtk.Separator()
        content.pack_start(sep, False, False, 0)

        # ── Settings ──────────────────────────────────────────────
        settings_title = Gtk.Label(label='Settings', xalign=0)
        settings_title.get_style_context().add_class('section-title')
        content.pack_start(settings_title, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(10)

        grid.attach(field_label('Telegram Token:'), 0, 0, 1, 1)
        self._tg_token_entry = Gtk.Entry()
        self._tg_token_entry.set_hexpand(True)
        self._tg_token_entry.set_visibility(False)
        self._tg_token_entry.set_text(self.config.telegram_token)
        self._tg_token_entry.set_placeholder_text('123456789:ABCdef...')
        grid.attach(self._tg_token_entry, 1, 0, 1, 1)

        grid.attach(field_label('Telegram Chat ID:'), 0, 1, 1, 1)
        self._tg_chat_entry = Gtk.Entry()
        self._tg_chat_entry.set_text(self.config.telegram_chat_id)
        self._tg_chat_entry.set_placeholder_text('e.g. 7369835363')
        grid.attach(self._tg_chat_entry, 1, 1, 1, 1)

        grid.attach(field_label('Daily signal time:'), 0, 2, 1, 1)
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        self._hour_spin.set_value(self.config.signal_hour)
        self._hour_spin.set_size_request(60, -1)
        time_box.pack_start(self._hour_spin, False, False, 0)
        colon_label = Gtk.Label(label=':00 (24h local)')
        colon_label.get_style_context().add_class('field-label')
        time_box.pack_start(colon_label, False, False, 0)
        grid.attach(time_box, 1, 2, 1, 1)

        content.pack_start(grid, False, False, 0)

        # ── Buttons ───────────────────────────────────────────────
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        save_btn = Gtk.Button(label='Save Settings')
        save_btn.get_style_context().add_class('action-btn')
        save_btn.connect('clicked', self._on_save)
        btn_row.pack_start(save_btn, False, False, 0)

        test_btn = Gtk.Button(label='Test Telegram')
        test_btn.connect('clicked', self._on_test_telegram)
        btn_row.pack_start(test_btn, False, False, 0)

        log_btn = Gtk.Button(label='View Log')
        log_btn.connect('clicked', self._on_view_log)
        btn_row.pack_end(log_btn, False, False, 0)

        content.pack_start(btn_row, False, False, 0)

        # ── Status bar ────────────────────────────────────────────
        self._status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._status_bar.get_style_context().add_class('status-bar')
        self._bar_label = Gtk.Label(label='', xalign=0)
        self._status_bar.pack_start(self._bar_label, True, True, 0)
        main.pack_start(self._status_bar, False, False, 0)

    def _refresh_status(self):
        last_run = self.config.get('last_run', '')
        last_status = self.config.get('last_status', '')
        last_signal = self.config.get('last_signal', '')
        last_conf = self.config.get('last_confidence', '')

        ctx = self._status_label.get_style_context()

        if last_status.startswith('OK'):
            label = last_status
            if last_signal:
                label = f'{last_signal} — {last_conf}'
            self._status_label.set_text(label)
            ctx.add_class('status-ok')
            ctx.remove_class('status-error')
            ctx.remove_class('status-pending')
        elif last_status.startswith('Error'):
            self._status_label.set_text(last_status)
            ctx.add_class('status-error')
            ctx.remove_class('status-ok')
            ctx.remove_class('status-pending')
        else:
            self._status_label.set_text('Not yet run')

        self._last_run_label.set_text(f'Last run: {last_run}' if last_run else 'Last run: never')

    def _on_save(self, btn):
        self.config.set('telegram_token', self._tg_token_entry.get_text().strip())
        self.config.set('telegram_chat_id', self._tg_chat_entry.get_text().strip())
        self.config.set('signal_hour', int(self._hour_spin.get_value()))
        self.config.save()
        self._set_bar('Settings saved.')

    def _on_test_telegram(self, btn):
        token = self._tg_token_entry.get_text().strip()
        chat_id = self._tg_chat_entry.get_text().strip()
        if not token or not chat_id:
            self._show_error('Missing details', 'Enter your Telegram token and chat ID first.')
            return
        try:
            test_connection(token, chat_id)
            self._set_bar('Test message sent to Telegram.')
        except TelegramError as e:
            self._show_error('Telegram test failed', str(e))

    def _on_run_now(self, btn):
        if self._busy:
            return
        token = self._tg_token_entry.get_text().strip()
        chat_id = self._tg_chat_entry.get_text().strip()
        if not token or not chat_id:
            self._show_error('Not configured', 'Save your Telegram token and chat ID first.')
            return

        self._busy = True
        self._run_btn.set_sensitive(False)
        self._spinner.start()
        self._set_bar('Running HMM… this takes ~60s')

        def run():
            import sys as _sys
            import os as _os
            install_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            _sys.path.insert(0, install_dir)
            try:
                from data import fetch_ohlcv
                from features import build_features
                from regime import train, regime_series
                from runner import _sweep_best, _format_message, BARS_PER_YEAR
                from paper_trader import backtest, DEFAULT_FEE_RATE, DEFAULT_MIN_HOLD
                import datetime as dt

                ohlcv = fetch_ohlcv('XBTUSD', '1d', 730)
                features = build_features(ohlcv, bars_per_year=BARS_PER_YEAR)
                model = train(features)
                regimes = regime_series(model, features)

                latest = regimes.iloc[-1]
                regime = latest['state'].upper()
                conf = latest['confidence'] * 100
                p_bull = latest.get('p_bull', 0) * 100
                p_side = latest.get('p_sideways', 0) * 100
                p_bear = latest.get('p_bear', 0) * 100

                best = _sweep_best(ohlcv, regimes)

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

                last_sigs = [
                    (ts, row['state'], row['confidence'])
                    for ts, row in regimes.tail(5).iterrows()
                ]
                msg = _format_message(regime, conf, p_bull, p_side, p_bear, best, last_sigs,
                                      strat_total, strat_equity, bah_total, bah_equity,
                                      start_date, end_date)
                send_message(token, chat_id, msg)

                now_str = dt.datetime.now().isoformat(sep=' ', timespec='seconds')
                self.config.set('last_run', now_str)
                self.config.set('last_status', f'OK — {regime} ({conf:.1f}%)')
                self.config.set('last_signal', regime)
                self.config.set('last_confidence', f'{conf:.1f}%')
                self.config.save()

                GLib.idle_add(self._on_run_done, True, f'Signal sent: {regime} ({conf:.1f}%)')
            except Exception as e:
                GLib.idle_add(self._on_run_done, False, str(e)[:120])

        threading.Thread(target=run, daemon=True).start()

    def _on_run_done(self, success, msg):
        self._busy = False
        self._spinner.stop()
        self._run_btn.set_sensitive(True)
        self._refresh_status()
        self._set_bar(msg)

    def _on_view_log(self, btn):
        if os.path.exists(LOG_FILE):
            subprocess.Popen(['xdg-open', LOG_FILE])
        else:
            self._set_bar('No log file yet.')

    def _set_bar(self, msg):
        self._bar_label.set_text(msg)

    def _show_error(self, title, msg):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()
