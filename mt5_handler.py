# mt5_handler.py
import MetaTrader5 as mt5
from settings import cfg
from infrastructure import log
import time

class MT5Handler:
    def __init__(self):
        self.mt5 = mt5
        self.connected = False
        self.connect()

    def connect(self):
        """Verbindet mit dem MT5 Terminal"""
        if not mt5.initialize():
            log.error(f"❌ MT5 Init fehlgeschlagen: {mt5.last_error()}")
            return False
        
        # Login versuchen
        authorized = mt5.login(login=cfg.MT5_LOGIN, password=cfg.MT5_PASSWORD, server=cfg.MT5_SERVER)
        if authorized:
            log.info(f"✅ Verbunden mit MT5 Konto: {cfg.MT5_LOGIN}")
            self.connected = True
            return True
        else:
            log.error(f"❌ MT5 Login fehlgeschlagen: {mt5.last_error()}")
            return False

    def modify_position(self, ticket, sl, tp):
        """
        Sendet den Befehl an MT5, die rote SL/TP Linie zu verschieben.
        """
        request = {
            "action": self.mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": float(sl),
            "tp": float(tp)
        }
        
        result = self.mt5.order_send(request)
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            log.error(f"❌ SL Update fehlgeschlagen: {result.comment}")
            return False
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        """
        Holt historische Kerzen basierend auf der Position (Index).
        Wichtig für den Trailing Stop, um alte Volumendaten zu prüfen.
        """
        rates = self.mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)
        
        if rates is None:
            log.error(f"❌ Fehler beim Laden der Historie für {symbol} (Code: {self.mt5.last_error()})")
            return None
            
        return rates

    def get_account(self):
        """
        Holt ECHTE Kontodaten.
        Keine Simulation mehr! Wenn keine Daten da sind, versuchen wir einen Reconnect.
        """
        # 1. Versuch: Daten holen
        account_info = self.mt5.account_info()
        
        if account_info is not None:
            return account_info
            
        # 2. Wenn das schief ging: WARUM?
        error_code = self.mt5.last_error()
        log.warning(f"⚠️ MT5 liefert keine Kontodaten (Code: {error_code}). Versuche Reconnect...")
        
        # 3. Reconnect versuchen
        self.connect()
        
        # 4. Zweiter Versuch
        account_info = self.mt5.account_info()
        
        if account_info is not None:
            log.info("✅ Reconnect erfolgreich! Echte Daten sind wieder da.")
            return account_info
            
        # 5. Wenn immer noch nichts geht: KEINE SIMULATION!
        # Wir geben None zurück, damit der RiskManager den Trade blockiert.
        log.error("❌ KRITISCH: Keine Verbindung zum Broker. Trade wird abgebrochen.")
        return None
        
        # Wir simulieren ein Objekt, das so aussieht wie bei Alpaca
        class AccountSim:
            def __init__(self, equity, balance):
                self.equity = equity
                self.balance = balance
                self.buying_power = equity # Wir ignorieren Margin für Sicherheit
                self.cash = balance
                self.trading_blocked = False
                self.account_blocked = False

        return AccountSim(info.equity, info.balance)

    def get_all_positions(self):
        """Holt alle offenen Trades"""
        positions = mt5.positions_get()
        alpaca_style = []
        
        if positions:
            for pos in positions:
                # MT5 Position in unser Format umwandeln
                class PosSim:
                    def __init__(self, ticket, symbol, qty, entry, current, pl, side):
                        self.id = ticket # Ticket ID ist wichtig für Updates
                        self.symbol = symbol
                        self.qty = qty
                        self.avg_entry_price = entry
                        self.current_price = current
                        self.unrealized_pl = pl
                        
                        # Prozentualen Gewinn berechnen
                        invest = entry * qty
                        if invest > 0:
                            self.unrealized_plpc = (pl / invest) # Rohwert (z.B. 0.01 für 1%)
                        else:
                            self.unrealized_plpc = 0
                            
                        self.market_value = current * qty
                        self.side = side # 'long' oder 'short'

                side = 'long' if pos.type == mt5.ORDER_TYPE_BUY else 'short'
                
                alpaca_style.append(
                    PosSim(pos.ticket, pos.symbol, pos.volume, pos.price_open, pos.price_current, pos.profit, side)
                )
        return alpaca_style

    def get_live_price(self, symbol):
        """Holt echten Bid und Ask Preis"""
        # Symbol im Market Watch aktivieren, falls nicht da
        if not mt5.symbol_select(symbol, True):
             return None, None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None, None
        return tick.bid, tick.ask

    def submit_order(self, symbol, side, qty, sl=None, tp=None, comment="Bot V3"):
        """Sendet Order an MT5 mit dynamischem Filling Mode Fix"""
        
        # 1. TICKET CHECK (Dein Original)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            log.error(f"❌ Keine Live-Daten für {symbol}")
            return False

        # 2. PREIS & TYP (Dein Original)
        price = tick.ask if side == "LONG" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if side == "LONG" else mt5.ORDER_TYPE_SELL


        # ============================================================
        # ⚡ DYNAMISCHER FILLING MODE CHECK (Hardcoded Fix)
        # ============================================================
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            log.error(f"❌ Konnte Info für {symbol} nicht abrufen")
            return False

        # Wir prüfen direkt die Bitmask-Zahlen: 1 = FOK, 2 = IOC
        filling = symbol_info.filling_mode
        
        if filling & 1: # 1 entspricht SYMBOL_FILLING_FOK
            fill_type = mt5.ORDER_FILLING_FOK
        elif filling & 2: # 2 entspricht SYMBOL_FILLING_IOC
            fill_type = mt5.ORDER_FILLING_IOC
        else:
            fill_type = mt5.ORDER_FILLING_RETURN
        # ============================================================

        # 3. ORDER REQUEST (Dein Original + Dynamisches Filling)
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(qty),
            "type": order_type,
            "price": price,
            "sl": float(sl) if sl else 0.0,
            "tp": float(tp) if tp else 0.0,
            "deviation": 20, 
            "magic": 202602,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_type, # <--- Hier wird der erkannte Mode genutzt
        }

        # 4. ABSENDEN & LOGS (Dein Original)
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"❌ MT5 Order Error: {result.comment} (Code: {result.retcode})")
            return False
        else:
            log.info(f"✅ MT5 Order ausgeführt: {symbol} {side} {qty} Lots @ {price}")
            return True

    def update_sl(self, ticket_id, new_sl):
        """Ändert den Stop Loss einer laufenden Position"""
        # Wir brauchen die aktuellen Positionsdaten
        pos_list = mt5.positions_get(ticket=ticket_id)
        if not pos_list:
            return
        
        pos = pos_list[0]
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "sl": float(new_sl),
            "tp": pos.tp # TP lassen wir unverändert
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"❌ SL Update Error: {result.comment}")
        else:
            log.info(f"🔄 SL erfolgreich auf {new_sl:.2f} nachgezogen.")

    
    def close_position(self, ticket_id, symbol, qty, type_side):
        """Schließt eine spezifische Position"""
        tick = mt5.symbol_info_tick(symbol)
        if not tick: return False
        
        # Gegenteilige Order erstellen
        # Wenn wir LONG sind (Buy), müssen wir zum BID verkaufen (Sell)
        # Wenn wir SHORT sind (Sell), müssen wir zum ASK kaufen (Buy)
        
        close_type = mt5.ORDER_TYPE_SELL if type_side == 'long' else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if type_side == 'long' else tick.ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket_id, # WICHTIG: Referenz auf die offene Position
            "symbol": symbol,
            "volume": float(qty),
            "type": close_type,
            "price": close_price,
            "deviation": 20,
            "magic": 202602,
            "comment": "Daily Target Reached",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error(f"❌ Close Error {symbol}: {result.comment}")
            return False
        else:
            log.info(f"🔒 Position geschlossen: {symbol} (Gewinn gesichert)")
            return True