🚀 Advanced Triple-Engine AI Trader (MT5)
This repository houses a high-frequency algorithmic trading framework for MetaTrader 5, engineered to bridge the gap between institutional Order Flow dynamics and modern Machine Learning. Unlike standard bots, this engine doesn't just follow indicators; it cross-validates structural market imbalances with a multi-layered AI consensus.
🧠 Core Architecture
• Triple-Timeframe AI Consensus: Features a hierarchical decision-making process using separate Random Forest Classifiers for M1, M5, and M15.
• M15 (Macro): Establishes the institutional trend and structural bias.
• M5 (Execution): Identifies high-probability Volume Profile setups (VAH/VAL Breakouts).
• M1 (Precision): Acts as a high-speed volatility filter to optimize entry timing and minimize slippage.
• Volume Profile & Order Flow Engine: Moves beyond simple price action by calculating the Value Area (70% Volume). It identifies the Point of Control (POC) as a magnet and Low Volume Areas (LVAs) as structural support/resistance to validate if a move is backed by real participation.
• Shadow Trading & MFE/MAE Analytics: The engine runs a "Ghost Instance" in the background. It spawns virtual trade variants with different RRR (Risk-Reward-Ratio) parameters to analyze Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE). This data is fed back into the database to refine future AI training.
• Smart Risk Execution:
• Dynamic Position Sizing: Automatically calculates lot sizes based on ATR-volatility and fixed account risk percentages.
• Protection Layers: Includes Spread-Guard (blocking trades during high-volatility spikes), News-Awareness, and a "Night Guard" to handle low-liquidity rollover periods.
• Hybrid Infrastructure: Fully decoupled architecture allowing the AI Engine to run independently of the MT5 Terminal, integrated with a Discord C2 (Command & Control) interface for real-time remote management and account switching.
🛠️ Setup & AI Training Protocol
IMPORTANT: The AI models are asset-specific and must be trained on your local brokerage data to account for specific spreads and liquidity profiles.
1. Configure: Define your universe of assets in settings.py.
2. Synchronize: Open your MT5 Terminal and ensure the history for M1, M5, and M15 is fully downloaded (Scroll back in charts).
3. Execute Trainer: Launch Trainer.py.
• The engine will perform Feature Engineering on 50,000+ candles per timeframe.
• It simulates thousands of historical setups to "teach" the Random Forest how a winning trade looks on your specific broker.
4. Monitor: Check the log for the "True Test Accuracy". Models with >52% accuracy are generally considered tradeable for high-RRR setups.
5. Hot-Reload: Once _model.pkl files appear in the ai_models/ folder, the main.py will automatically recognize and load the new intelligence.
