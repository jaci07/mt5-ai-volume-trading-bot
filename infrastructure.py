# infrastructure.py
import logging
import sqlite3
import pandas as pd
import pandas_ta as ta # Falls du pandas_ta nutzt, sonst kann das weg
import numpy as np
import os
import time
import pickle
from datetime import datetime, timedelta
from colorama import init, Fore, Style
from sklearn.ensemble import RandomForestClassifier
from settings import cfg
import sys

# --- 1. LOGGING SYSTEM (Windows Safe) ---
# Windows Konsole auf UTF-8 zwingen (WICHTIG!)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': Fore.CYAN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
        'DEBUG': Fore.GREEN
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, Fore.WHITE)
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)

# Logger einrichten
log = logging.getLogger("EnterpriseBot")
log.setLevel(logging.DEBUG)

# Konsole Handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)

# Datei Handler
fh = logging.FileHandler("bot_activity.log", encoding='utf-8')
fh.setLevel(logging.INFO)
fh_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(fh_formatter)
log.addHandler(fh)

# --- 2. DATENBANK HANDLER (Mit Auto-Update) ---
class DatabaseHandler:
    def __init__(self):
        self.db_path = cfg.DB_NAME
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.create_tables()
        self.update_schema() # <--- DAS REPARIERT DEINE DB

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                side TEXT,
                qty REAL,
                price REAL,
                setup TEXT,
                features TEXT, 
                result REAL DEFAULT 0,
                status TEXT DEFAULT 'OPEN',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_models (
                symbol TEXT PRIMARY KEY,
                last_trained DATETIME,
                accuracy REAL
            )
        ''')
        self.conn.commit()

    def update_schema(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("PRAGMA table_info(trades)")
            columns = [info[1] for info in cursor.fetchall()]
            
            if 'features' not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN features TEXT")
            if 'result' not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN result REAL DEFAULT 0")
            if 'status' not in columns:
                cursor.execute("ALTER TABLE trades ADD COLUMN status TEXT DEFAULT 'OPEN'")
            
            # --- NEU: TICKET ID ---
            if 'ticket_id' not in columns:
                log.warning("🛠️ Datenbank-Update: Füge Spalte 'ticket_id' hinzu...")
                cursor.execute("ALTER TABLE trades ADD COLUMN ticket_id INTEGER DEFAULT 0")
                
            self.conn.commit()
        except Exception as e:
            log.error(f"Fehler beim DB-Update: {e}")

    def log_trade(self, symbol, side, qty, price, setup, features_dict=None, ticket_id=0):
        import json
        if features_dict is None: features_dict = {}
        features_json = json.dumps(features_dict)
        
        cursor = self.conn.cursor()
        # Wir speichern jetzt auch die TICKET ID!
        cursor.execute("""
            INSERT INTO trades (symbol, side, qty, price, setup, features, status, ticket_id) 
            VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (symbol, side, float(qty), float(price), setup, features_json, int(ticket_id)))
        
        self.conn.commit()
        log.info(f"💾 Trade {ticket_id} in DB gespeichert: {symbol}")
        return cursor.lastrowid

    def has_traded_today(self, symbol, setup_type):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT count(*) FROM trades 
            WHERE symbol=? AND setup LIKE ? AND date(timestamp) = date('now')
        ''', (symbol, f"%{setup_type}%"))
        count = cursor.fetchone()[0]
        return count > 0

    def get_minutes_since_last_trade(self, symbol):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT timestamp FROM trades 
            WHERE symbol=? ORDER BY timestamp DESC LIMIT 1
        ''', (symbol,))
        row = cursor.fetchone()
        if row:
            try:
                last_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                diff = datetime.now() - last_time
                return diff.total_seconds() / 60
            except: return 9999
        return 9999


# infrastructure.py - VolumeProfileEngine UPDATE

class VolumeProfileEngine:
    def __init__(self):
        self.poc = None
        self.vah = None
        self.val = None
        self.profile_data = None 

    def calculate_vwap(self, df):
        if df is None or df.empty: return 0.0
        # Fallback falls kein 'volume', nutze 'tick_volume'
        vol_col = 'volume' if 'volume' in df.columns else 'tick_volume'
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        volume = df[vol_col]
        cumulative_tp_vol = (typical_price * volume).cumsum()
        cumulative_vol = volume.cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        return vwap.iloc[-1]


    def find_last_pivot(self, df, lookback=30):
        """
        Findet den Anker-Punkt (Start des Trends) für das Volume Profile.
        Sucht das tiefste Low (oder höchste High) der letzten 'lookback' Kerzen.
        """
        if df is None or len(df) < lookback: return df.index[0]
        
        # Wir suchen vereinfacht das tiefste Low der letzten Bewegung als Startpunkt
        # (Ideal für Long-Einstiege nach Pullback)
        subset = df['low'].iloc[-lookback:]
        lowest_idx = subset.idxmin()
        
        return lowest_idx

    def calculate_enhanced_profile(self, df, lookback=96, decay=0.95):
        """
        LOGIK-UPDATE (Artikel):
        1. Nur kurze Historie (z.B. 96 Kerzen = 24h)
        2. 'Decay': Neue Kerzen zählen mehr als alte.
        3. 'Smoothing': Glättet das Profil.
        """
        if df is None or len(df) < 20: return 0,0,0

        subset = df.iloc[-lookback:].copy()
        
        # 1. Gewichtung berechnen (Exponentiell)
        # Die neueste Kerze hat Gewicht 1.0, die davor 0.95, davor 0.90...
        weights = [decay ** i for i in range(len(subset))]
        weights.reverse() # Umdrehen: Älteste zuerst, Neueste zuletzt (1.0)
        
        subset['weighted_vol'] = subset['volume'] * weights

        # 2. Histogramm erstellen
        bins = 50 # Weniger Bins = Mehr "Cluster" (Besser für Zonen)
        hist, bin_edges = np.histogram(subset['close'], bins=bins, weights=subset['weighted_vol'])
        
        # 3. Glättung (Smoothing) - Einfacher gleitender Durchschnitt über das Histogramm
        # Das entfernt kleine "Zacken" und findet echte Berge
        hist_smooth = pd.Series(hist).rolling(window=3, center=True, min_periods=1).mean().fillna(0).values

        self.profile_data = pd.DataFrame({'vol': hist_smooth, 'price': bin_edges[:-1]})
        
        # 4. POC finden (im geglätteten Profil)
        max_vol_idx = self.profile_data['vol'].idxmax()
        self.poc = self.profile_data.loc[max_vol_idx, 'price']
        
        # 5. Value Area (70%)
        total_volume = self.profile_data['vol'].sum()
        value_area_vol = total_volume * 0.70
        
        sorted_prof = self.profile_data.sort_values(by='vol', ascending=False)
        sorted_prof['cum_vol'] = sorted_prof['vol'].cumsum()
        
        va_bins = sorted_prof[sorted_prof['cum_vol'] <= value_area_vol]
        
        if not va_bins.empty:
            self.vah = va_bins['price'].max()
            self.val = va_bins['price'].min()
        else:
            self.vah = self.poc
            self.val = self.poc

        return self.poc, self.vah, self.val

    # Wrapper damit der alte Code in main.py nicht kaputt geht
    def calculate_frvp(self, df):
        return self.calculate_enhanced_profile(df)

    def find_nearest_lva(self, df, current_price, direction="DOWN"):
        # Nutzt jetzt das geglättete Profil -> Findet bessere "Lücken"
        if self.profile_data is None or self.profile_data.empty:
            self.calculate_enhanced_profile(df)
            
        profile = self.profile_data
        if profile is None or profile.empty: return None

        avg_vol = profile['vol'].mean()
        # Alles unter 40% des Durchschnitts ist eine Lücke (LVA)
        threshold = avg_vol * 0.40 
        
        if direction == "DOWN":
            candidates = profile[profile['price'] < current_price]
            candidates = candidates.sort_values(by='price', ascending=False) # Nächste unter uns
            for _, row in candidates.iterrows():
                if row['vol'] < threshold: return row['price']
                    
        elif direction == "UP":
            candidates = profile[profile['price'] > current_price]
            candidates = candidates.sort_values(by='price', ascending=True) # Nächste über uns
            for _, row in candidates.iterrows():
                if row['vol'] < threshold: return row['price']
        
        return None


# --- 4. AI ENGINE (Das Gehirn) ---
class AIEngine:
    def __init__(self):
        self.models_dir = "ai_models"
        self.models = {}
        if not os.path.exists(self.models_dir):
            os.makedirs(self.models_dir)

    # ---------------------------------------------------------
    # 1. Feature Engineering (Die "Augen" der KI anpassen)
    # ---------------------------------------------------------
    def feature_engineering(self, df):
        df = df.copy()
        try:
            if len(df) < 200: return pd.DataFrame()

            # --- 1. SPALTEN-CLEANUP & VOLUMEN-RETTUNG ---
            df.columns = [c.lower() for c in df.columns]
            
            if 'tick_volume' in df.columns:
                df['volume'] = df['tick_volume']
            elif 'real_volume' in df.columns:
                df['volume'] = df['real_volume']
            
            if 'volume' not in df.columns or df['volume'].sum() == 0:
                df['volume'] = 1 

            # --- 2. INDIKATOREN BERECHNEN ---
            
            # Momentum & Trend
            df['RSI'] = ta.rsi(df['close'], length=14)
            df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
            df['CCI'] = ta.cci(df['high'], df['low'], df['close'], length=20)
            
            # Stochastik RSI
            stoch_rsi = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
            if stoch_rsi is not None and not stoch_rsi.empty:
                df['Stoch_K'] = stoch_rsi.iloc[:, 0]
                df['Stoch_D'] = stoch_rsi.iloc[:, 1]
            else:
                df['Stoch_K'], df['Stoch_D'] = 50, 50
            
            # MACD
            macd = ta.macd(df['close'])
            if macd is not None and not macd.empty:
                df['MACD'] = macd.iloc[:, 0]
                df['MACD_Hist'] = macd.iloc[:, 1]
            else:
                df['MACD'], df['MACD_Hist'] = 0, 0
            
            df['EMA_20'] = ta.ema(df['close'], length=20)
            df['EMA_50'] = ta.ema(df['close'], length=50)
            df['Trend_Strength'] = df['EMA_20'] - df['EMA_50']

            # Volatilität (Bollinger Bänder)
            bb = ta.bbands(df['close'], length=20, std=2)
            if bb is not None:
                df['BB_Pct'] = (df['close'] - bb.iloc[:, 0]) / (bb.iloc[:, 2] - bb.iloc[:, 0])
                df['BB_Width'] = (bb.iloc[:, 2] - bb.iloc[:, 0]) / df['close']

            # Volumen-Indikatoren (MFI & OBV)
            try:
                df['MFI'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)
                df['OBV'] = ta.obv(df['close'], df['volume'])
                df['OBV_Slope'] = df['OBV'].diff(5)
            except:
                df['MFI'], df['OBV_Slope'] = 50, 0

            # --- 3. ZUSÄTZLICH: VERGANGENHEIT LERNEN (Lags) ---
            # WICHTIG: Erst hier unten, wenn RSI, MFI etc. existieren!
            for col in ['RSI', 'MACD_Hist', 'Trend_Strength', 'MFI']:
                if col in df.columns:
                    df[f'{col}_prev1'] = df[col].shift(1)
                    df[f'{col}_prev2'] = df[col].shift(2)

            # --- 4. PRICE ACTION (Manuelle Muster) ---
            body = abs(df['close'] - df['open'])
            df['Wick_Upper'] = df['high'] - df[['open', 'close']].max(axis=1)
            df['Wick_Lower'] = df[['open', 'close']].min(axis=1) - df['low']
            
            candle_range = df['high'] - df['low']
            df['Is_Doji'] = np.where(body <= (candle_range * 0.1), 1, 0)
            
            df['Engulfing'] = 0
            df.loc[(df['close'] > df['open']) & (body > body.shift(1)), 'Engulfing'] = 1
            df.loc[(df['close'] < df['open']) & (body > body.shift(1)), 'Engulfing'] = -1

            # --- 5. CLEANUP & FINAL LOWERCASE ---
            df.ffill(inplace=True)
            df.bfill(inplace=True)
            df.fillna(0, inplace=True)
            
            # DER ENTSCHEIDENDE FIX: 
            # Wir machen am Ende ALLES klein, damit der Trainer keine KeyErrors wirft
            df.columns = [c.lower() for c in df.columns]
            
            return df
            
        except Exception as e:
            log.error(f"⚠️ Feature Engineering Crash: {e}")
            return pd.DataFrame()

    # ---------------------------------------------------------
    # 2. Train Models (Das Training anpassen)
    # ---------------------------------------------------------
    def train_models(self, symbol, df):
        try:
            # 1. Features berechnen (jetzt mit VWAP & Volumen)
            df = self.feature_engineering(df)
            
            if len(df) < 50: return 
            
            # Target: 1 wenn der Preis in Zukunft steigt
            df['Target'] = (df['close'].shift(-1) > df['close']).astype(int)
            
            # WICHTIG: Hier nutzen wir jetzt die NEUEN Features!
            # Keine Standard-Indikatoren mehr, sondern deine Strategie-Logik.
            # WICHTIG: Hier nutzen wir jetzt die NEUEN Features!
            # Pump_Factor und Close_Loc helfen der KI, überdehnte Kerzen zu erkennen.
            features = [
                # --- Momentum & Kraft ---
                'RSI', 'Stoch_K', 'CCI',
                'RSI_prev1', 'RSI_prev2',           # Historie: RSI
    
                # --- Trend-Kontext ---
                'MACD_Hist', 'Trend_Strength',
                'MACD_Hist_prev1', 'MACD_Hist_prev2', # Historie: MACD
                'Trend_Strength_prev1', 'Trend_Strength_prev2', # Historie: Trend
    
                # --- Volatilität ---
                    'BB_Pct', 'BB_Width', 'ATR',
    
                # --- Volumen Flow ---
                'MFI', 'OBV_Slope',
                'MFI_prev1', 'MFI_prev2',           # Historie: MFI
    
                # --- Price Action & Muster ---
                'Wick_Upper', 'Wick_Lower',
                'Is_Doji', 'Engulfing'
            ]
            
            # Sicherheits-Check: Sind alle da?
            available_features = [f for f in features if f in df.columns]
            if not available_features: return

            X = df[available_features]
            y = df['Target']
            
            # --- SMART MEMORY INTEGRATION (Das Tagebuch laden) ---
            memory_file = os.path.join(self.models_dir, "smart_memory.csv")
            if os.path.exists(memory_file):
                try:
                    mem_df = pd.read_csv(memory_file)
                    mem_df = mem_df[mem_df['symbol'] == symbol]
                    
                    if not mem_df.empty:
                        # Wir nehmen nur die Spalten, die wir kennen
                        valid_cols = available_features + ['Target']
                        valid_cols = [c for c in valid_cols if c in mem_df.columns]
                        
                        if 'Target' in valid_cols and len(valid_cols) > 1:
                            mem_subset = mem_df[valid_cols]
                            
                            X_mem = mem_subset[available_features]
                            y_mem = mem_subset['Target']
                            
                            # Echte Erfahrung zählt 5x mehr als Backtest
                            X_mem = pd.concat([X_mem] * 5, ignore_index=True)
                            y_mem = pd.concat([y_mem] * 5, ignore_index=True)
                            
                            X = pd.concat([X, X_mem], ignore_index=True)
                            y = pd.concat([y, y_mem], ignore_index=True)
                            log.info(f"🧠 {len(mem_df)} echte Erfahrungen geladen.")
                except: pass
            # -----------------------------------------------------

            # Modell trainieren
            model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
            model.fit(X, y)

            # --- NEU: DOPPELT SPEICHERN ---
            # 1. In den RAM (für sofortigen Zugriff)
            self.models[symbol] = model
            
            # 2. Auf Festplatte (für Neustart)
            filename = os.path.join(self.models_dir, f"{symbol}_rf.pkl")
            with open(filename, 'wb') as f:
                pickle.dump(model, f)
            
            log.info(f"💾 Modell für {symbol} gespeichert (RAM + Disk).")
            
            # Speichern
            filename = os.path.join(self.models_dir, f"{symbol}_rf.pkl")
            with open(filename, 'wb') as f:
                pickle.dump(model,f)
            
            log.info(f"🧠 Modell trainiert für {symbol} (VWAP/Volumen Logik)")
            
        except Exception as e:
            log.error(f"Training Error {symbol}: {e}")

    def get_prediction_proba_all(self, symbol, df):
        """Gibt die Wahrscheinlichkeiten für alle 3 Klassen zurück"""
        model = self.models.get(symbol)
        if model is None:
            # Versuche von Disk zu laden
            filename = os.path.join(self.models_dir, f"{symbol}_model.pkl")
            if os.path.exists(filename):
                model = joblib.load(filename)
                self.models[symbol] = model
            else:
                return [1.0, 0.0, 0.0] # 100% Sicherheit für 'Nichts tun'

        try:
            # Features berechnen und letzte Zeile holen
            data = self.feature_engineering(df)
            if data.empty: return [1.0, 0.0, 0.0]
            
            # Die exakt gleiche Feature-Liste wie im Trainer!
            features = ['rsi', 'stoch_k', 'cci', 'rsi_prev1', 'rsi_prev2',
            'macd_hist', 'trend_strength', 'macd_hist_prev1', 'macd_hist_prev2',
            'trend_strength_prev1', 'trend_strength_prev2',
            'bb_pct', 'bb_width', 'atr',
            'mfi', 'obv_slope', 'mfi_prev1', 'mfi_prev2',
            'wick_upper', 'wick_lower', 'is_doji', 'engulfing'] 
            last_row = data[features].iloc[[-1]]
            
            # Gibt [Prob_0, Prob_1, Prob_2] zurück
            return model.predict_proba(last_row)[0]
        except:
            return [1.0, 0.0, 0.0]

        # Sicherheits-Check
        if model is None: return 0.5

        # --- SCHRITT B: BERECHNUNG (Muss für alle gelten!) ---
        try:
            # FIX: Wir brauchen mehr Historie für den VWAP (200 Kerzen)!
            calc_df = df.tail(200).copy() 
            
            data = self.feature_engineering(calc_df) 
            
            # Wenn Feature Engineering alles weggeschnitten hat (z.B. wegen NaNs)
            if data.empty: return 0.5
            
            # Features prüfen (Inklusive der neuen Features!)
            features = [
                # --- Momentum & Kraft ---
                'RSI', 'Stoch_K', 'CCI',
                'RSI_prev1', 'RSI_prev2',           # Historie: RSI
    
                # --- Trend-Kontext ---
                'MACD_Hist', 'Trend_Strength',
                'MACD_Hist_prev1', 'MACD_Hist_prev2', # Historie: MACD
                'Trend_Strength_prev1', 'Trend_Strength_prev2', # Historie: Trend
    
                # --- Volatilität ---
                    'BB_Pct', 'BB_Width', 'ATR',
    
                # --- Volumen Flow ---
                'MFI', 'OBV_Slope',
                'MFI_prev1', 'MFI_prev2',           # Historie: MFI
    
                # --- Price Action & Muster ---
                'Wick_Upper', 'Wick_Lower',
                'Is_Doji', 'Engulfing'
            ]
            
            # Nur Features nutzen, die wirklich da sind
            available_features = [f for f in features if f in data.columns]
            
            if not available_features: return 0.5

            # Letzte Zeile für Vorhersage nutzen
            last_row = data.iloc[[-1]][available_features]
            
            # Die magische Vorhersage
            prob_up = model.predict_proba(last_row)[0][1]
            return prob_up
            
        except Exception:
            return 0.5
        
    # Füge das zur AIEngine Klasse hinzu
    def save_experience(self, symbol, features, label):
        """
        Speichert einen echten Trade als Trainingsdaten.
        Label: 1 = Win, 0 = Loss
        """
        file_path = os.path.join(self.models_dir, "smart_memory.csv")
        
        # Features ist ein Dictionary. Wir machen daraus eine Zeile.
        data = features.copy()
        data['symbol'] = symbol
        data['Target'] = label # Das ist, was die AI lernen soll
        
        df_new = pd.DataFrame([data])
        
        # Anfügen an die Datei (oder neu erstellen)
        if os.path.exists(file_path):
            df_new.to_csv(file_path, mode='a', header=False, index=False)
        else:
            df_new.to_csv(file_path, mode='w', header=True, index=False)
            
        log.info(f"🧠 Erfahrung gespeichert: {symbol} -> {'WIN' if label==1 else 'LOSS'}")