import json
import pandas as pd
import os
from infrastructure import AIEngine, log

# Konfiguration
shadow_file = "shadow_trades.json"
memory_file = "ai_models/smart_memory.csv"

def feed_memory():
    log.info("👻 ANALYSE: Prüfe Shadow-Trades auf Lernerfolge...")

    if not os.path.exists(shadow_file):
        log.warning("❌ Keine Shadow-Trades Datei gefunden.")
        return

    try:
        # 1. Shadow Trades laden
        with open(shadow_file, "r") as f:
            shadows = json.load(f)
        
        # 2. Nur fertige Trades (WIN/LOSS) filtern, die Features haben
        new_memories = []
        pending_shadows = [] # Die noch offen sind, behalten wir

        for s in shadows:
            if s["status"] in ["WIN", "LOSS"]:
                # Check: Haben wir Features?
                if "features" not in s or not s["features"]:
                    continue # Alte Shadows ohne Features überspringen
                
                # Datenpaket schnüren
                data_point = s["features"].copy()
                data_point["symbol"] = s["symbol"]
                # WICHTIG: KI lernt 1 für WIN, 0 für LOSS
                data_point["outcome"] = 1 if s["status"] == "WIN" else 0
                
                new_memories.append(data_point)
            else:
                pending_shadows.append(s)

        if not new_memories:
            log.info("ℹ️ Keine neuen abgeschlossenen Shadow-Trades zum Lernen.")
            return

        # 3. In CSV speichern
        df_new = pd.DataFrame(new_memories)
        
        # Header-Check: Existiert die Datei schon?
        header = not os.path.exists(memory_file)
        
        df_new.to_csv(memory_file, mode='a', header=header, index=False)
        log.info(f"✅ ERFOLG: {len(new_memories)} Shadow-Trades ins Gedächtnis integriert!")

        # 4. Datei aufräumen (Nur offene behalten)
        with open(shadow_file, "w") as f:
            json.dump(pending_shadows, f, indent=4)
            
    except Exception as e:
        log.error(f"❌ Fehler beim Füttern der Shadows: {e}")

if __name__ == "__main__":
    feed_memory()