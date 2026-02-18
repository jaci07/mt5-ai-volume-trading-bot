# settings.py
import os

class Config:
    # --- DEINE MT5 ZUGANGSDATEN ---
    MT5_LOGIN = 5046691332      
    MT5_PASSWORD = "*5XiEqLo"
    MT5_SERVER = "MetaQuotes-Demo"  # z.B. "Eightcap-Demo"

    # --- TRADING CONFIG ---
    # Deine Liste ist gut! (Forex, Krypto, Indizes)
    SYMBOLS = [
        #"BTCUSD", "BCHUSD", "ETHUSD", "LTCUSD", 
        #"AUS200", "GER40", "JPN225", "UK100", "US30", "SPX500", "NAS100", 
        #"BRENT", "WTI", 
        #"XAGUSD", "XAUUSD", --Derzeit zu volatil 
        "EURUSD", "GBPUSD", "USDCHF", "USDJPY", "USDCAD", "AUDUSD", "AUDNZD", 
        "AUDCAD", "AUDCHF", "AUDJPY", "CHFJPY", "EURNZD", "EURCAD", "GBPCHF", 
        "GBPJPY", "CADCHF", "CADJPY", "GBPAUD", "GBPCAD", "GBPNZD", "NZDCAD", 
        "NZDCHF", "NZDJPY", "NZDUSD"
    ]
    
    # --- RISIKO MANAGEMENT (Angepasst an Atlas Funded 5% Regel) ---
    
    # WICHTIG: Nur 1% Risiko pro Trade!
    # Bei 5% Tageslimit darfst du nicht aggressiver sein.
    MAX_ACCOUNT_RISK = 0.01 
    
    # Begrenzung: Max 20% des Kapitals in EINEN Trade stecken.
    # Das verhindert "Klumpenrisiko" und hilft bei der Consistency-Rule.
    MAX_POSITION_SIZE = 0.20

    # Datenbank Name
    DB_NAME = "trading_bot.db"

cfg = Config()