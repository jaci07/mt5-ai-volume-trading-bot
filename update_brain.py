import pandas as pd
from infrastructure import AIEngine, log

ai = AIEngine()

# 1. Lade die gesammelten Erfahrungen aus der CSV
memory_file = "ai_models/smart_memory.csv"

try:
    df_memory = pd.read_csv(memory_file)
    log.info(f"📊 Gedächtnis geladen: {len(df_memory)} Zeilen gefunden.")
    
    # 2. Alle Symbole finden, die in der Datei sind
    symbols = df_memory['symbol'].unique()
    
    for symbol in symbols:
        log.info(f"🧠 Training gestartet für: {symbol}...")
        
        # Filter die Daten für das aktuelle Symbol
        df_symbol = df_memory[df_memory['symbol'] == symbol]
        
        # Rufe die Funktion mit den benötigten Argumenten auf
        # Wir übergeben das Symbol und die gefilterten Daten
        ai.train_models(symbol=symbol, df=df_symbol)
        
    log.info("✅ Alle .pkl Dateien im Ordner ai_models wurden aktualisiert!")

except FileNotFoundError:
    log.error(f"❌ Datei {memory_file} nicht gefunden. Hast du den Trainer schon laufen lassen?")
except Exception as e:
    log.error(f"❌ Fehler beim Training: {e}")