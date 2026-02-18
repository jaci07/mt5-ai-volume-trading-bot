# risk_manager.py
import math
from settings import cfg
from infrastructure import log

class RiskManager:
    def __init__(self, mt5_handler):
        self.mt5 = mt5_handler

    def check_can_trade(self):
        """Prüft, ob global überhaupt getradet werden darf"""
        account = self.mt5.get_account()
        if not account:
            return False
            
        # Sicherheits-Puffer: Wenn Margin Level unter 100% ist -> Stop
        if account.margin_level > 0 and account.margin_level < 150:
            # log.warning("⚠️ Margin Level kritisch (<150%). Kein neuer Trade.")
            return False
            
        return True

    def calculate_position_size(self, symbol, entry_price, stop_loss):
        """
        Berechnet die korrekte Lot-Größe basierend auf Risiko & Asset-Klasse.
        NEU: Mit automatischem Margin-Check für Low-Leverage Assets (Crypto).
        """
        try:
            account = self.mt5.get_account()
            if not account: return 0.0

            # 1. Geld-Risiko berechnen
            # Balance * 1% (0.01)
            risk_per_trade = account.balance * cfg.MAX_ACCOUNT_RISK
            
            # 2. Distanz zum Stop Loss
            dist = abs(entry_price - stop_loss)
            if dist == 0: return 0.0

            # 3. Symbol Informationen holen
            symbol_info = self.mt5.mt5.symbol_info(symbol)
            if not symbol_info:
                log.error(f"❌ Kann Symbol-Info für {symbol} nicht laden.")
                return 0.0

            # --- PREIS-WERTE ---
            contract_size = symbol_info.trade_contract_size
            if contract_size == 0: contract_size = 1.0

            tick_value = symbol_info.trade_tick_value
            sl_points = dist / symbol_info.point

            # --- LOT BERECHNUNG (Risiko-basiert) ---
            if tick_value == 0:
                # Fallback Formel
                lots_raw = (risk_per_trade / dist) / contract_size
            else:
                # Exakte Formel (Wichtig für JPY, CHF Paare)
                lots_raw = risk_per_trade / (sl_points * tick_value)

            # Limits holen
            min_vol = symbol_info.volume_min
            max_vol = symbol_info.volume_max
            step_vol = symbol_info.volume_step

            # Erstes Runden
            lots = math.floor(lots_raw / step_vol) * step_vol
            lots = round(lots, 6)

            # --- NEU: MARGIN CHECK (Der "Crypto-Schutz") ---
            # Wir prüfen, ob wir genug Geld für diese Lots haben.
            # Bei Forex (1:100) meist kein Problem. Bei Crypto (1:2) sehr wichtig!
            
            action_type = self.mt5.mt5.ORDER_TYPE_BUY
            margin_required = self.mt5.mt5.order_calc_margin(action_type, symbol, lots, entry_price)
            
            # Fallback Berechnung, falls MT5 nichts liefert
            if margin_required is None:
                lev = account.leverage
                if lev <= 0: lev = 30 # Default 1:30 annehmen
                margin_required = (lots * contract_size * entry_price) / lev

            free_margin = account.margin_free
            
            # Puffer: Wir nutzen maximal 90% der freien Margin für einen Trade
            if margin_required > (free_margin * 0.9):
                # Wir müssen reduzieren!
                log.warning(f"⚠️ {symbol}: Zu wenig Margin für {lots} Lots (Brauche {margin_required:.2f}, Habe {free_margin:.2f}).")
                
                # Verhältnis berechnen
                ratio = (free_margin * 0.9) / margin_required
                
                # Lots anpassen
                lots = lots * ratio
                
                # Neu runden auf Step
                lots = math.floor(lots / step_vol) * step_vol
                lots = round(lots, 6)
                
                log.info(f"📉 Automatisch korrigiert auf {lots} Lots.")

            # --- FINALE CHECKS ---
            if lots < min_vol:
                # log.warning(f"⚠️ {symbol}: Position wäre zu klein ({lots} < {min_vol}). Skip.")
                return 0.0
            
            if lots > max_vol:
                lots = max_vol

            # Log Ausgabe zur Kontrolle
            log.info(f"⚖️ {symbol}: Risk {risk_per_trade:.2f}$ | SL-Dist {dist:.5f} -> {lots} Lots")

            return lots

        except Exception as e:
            log.error(f"Risk Calc Error {symbol}: {e}")
            return 0.0