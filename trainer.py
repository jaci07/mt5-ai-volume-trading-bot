import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score
# WICHTIG: Wir importieren genau das, was die Main nutzt
from infrastructure import AIEngine, VolumeProfileEngine, log
from advanced_engine import AdvancedMarketEngine # <--- Korrigierter Name
from settings import cfg

class ModelTrainer:
    def __init__(self):
        self.ai_engine = AIEngine()
        self.vp_engine = VolumeProfileEngine()
        # Wir brauchen eine MT5 Instanz für die Engine (Dummy/None ist ok für Berechnungen)
        self.strat_engine = AdvancedMarketEngine(None, None) 
        self.models_dir = "ai_models"
        
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)

    def fetch_training_data(self, symbol, n_candles=50000):
        if not mt5.initialize(): return None
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, n_candles)
        if rates is None: return None
        
        df_raw = pd.DataFrame(rates)
        df = self.ai_engine.feature_engineering(df_raw)
        return df

    def simulate_path_fast(self, np_data, start_idx, side="LONG"):
        lookahead = 60 # 5 Stunden Outlook
        if start_idx + lookahead >= len(np_data): return 0
        
        subset = np_data[start_idx + 1 : start_idx + lookahead + 1]
        entry_p = np_data[start_idx, 2] # close
        atr = np_data[start_idx, 3] # atr
        
        tp = entry_p + (atr * 2.0) if side == "LONG" else entry_p - (atr * 2.0)
        sl = entry_p - (atr * 1.5) if side == "LONG" else entry_p + (atr * 1.5)
        
        if side == "LONG":
            tp_hits = np.where(subset[:, 0] >= tp)[0] # high
            sl_hits = np.where(subset[:, 1] <= sl)[0] # low
        else:
            tp_hits = np.where(subset[:, 1] <= tp)[0] # low
            sl_hits = np.where(subset[:, 0] >= sl)[0] # high
            
        f_tp = tp_hits[0] if tp_hits.size > 0 else 999
        f_sl = sl_hits[0] if sl_hits.size > 0 else 999
        return 1 if (f_tp < f_sl and f_tp != 999) else 0

    def train_model(self, symbol):
        log.info(f"🚀 SYNC-TRAINING: {symbol} (Synchronisiere mit AdvancedMarketEngine)")
        
        df = self.fetch_training_data(symbol)
        if df is None or len(df) < 5000: return

        setup_indices = []
        labels = []
        np_vals = df[['high', 'low', 'close', 'atr']].values

        # Wir scannen die 50.000 Kerzen exakt wie der Bot es tun würde
        for i in range(300, len(df) - 65):
            # Simulation des Bot-Feeds
            subset_df = df.iloc[i-250:i+1] 
            
            # RUFE DEINE ECHTE STRATEGIE-LOGIK AUF
            direction, strat_name = self.strat_engine.check_entry_signal(symbol, subset_df, self.vp_engine)
            
            if direction:
                is_win = self.simulate_path_fast(np_vals, i, direction)
                setup_indices.append(i)
                labels.append(is_win)

        if len(setup_indices) < 30:
            log.warning(f"⚠️ Zu wenige Setups für {symbol} ({len(setup_indices)}).")
            return

        # Training nur auf den Features der Setups
        features = [
            'rsi', 'stoch_k', 'cci', 'rsi_prev1', 'rsi_prev2',
            'macd_hist', 'trend_strength', 'macd_hist_prev1', 'macd_hist_prev2',
            'trend_strength_prev1', 'trend_strength_prev2',
            'bb_pct', 'bb_width', 'atr',
            'mfi', 'obv_slope', 'mfi_prev1', 'mfi_prev2',
            'wick_upper', 'wick_lower', 'is_doji', 'engulfing'
        ]

        X = df.iloc[setup_indices][features]
        y = pd.Series(labels)

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

        model = RandomForestClassifier(n_estimators=150, max_depth=8, min_samples_leaf=10, n_jobs=-1)
        model.fit(X_train, y_train)

        # Qualitäts-Check
        probs = model.predict_proba(X_test)
        # Wir filtern die Test-Ergebnisse auf hohe Sicherheit (>60%)
        conf_mask = (probs[:, 1] > 0.60)
        
        if sum(conf_mask) > 0:
            final_prec = precision_score(y_test[conf_mask], [1]*sum(conf_mask), zero_division=0)
            log.info(f"🎯 Strategie-Winrate für {symbol}: {final_prec:.2%} bei {sum(conf_mask)} Elite-Signalen")
        
        joblib.dump(model, os.path.join(self.models_dir, f"{symbol}_model.pkl"))
        log.info(f"✅ Modell synchronisiert und gespeichert.")

    def run_training_cycle(self):
        for symbol in cfg.SYMBOLS:
            try: self.train_model(symbol)
            except Exception as e: log.error(f"Fehler bei {symbol}: {e}")

if __name__ == "__main__":
    trainer = ModelTrainer()
    trainer.run_training_cycle()