This repository houses a sophisticated algorithmic trading engine designed for MetaTrader 5. It merges traditional technical analysis with a deep-learning AI model (Random Forest Classifier) to score trade probabilities based on historical win/loss data.

Core Features:

AI Engine: Evaluates setups dynamically, categorizing trade setups using deep Random Forest models trained on 15,000+ candles per asset.

Volume Profile Engine: Identifies Value Area High/Low (VAH/VAL), Point of Control (POC), and Low Volume Areas (LVAs) to validate breakouts and rejections.

Shadow Trading Memory: Spawns virtual trade variants in the background to continuously analyze optimal SL/TP ratios without risking live capital.

Smart Trade Management: Features automated Break-Even, ATR-based Smart Trailing SL, and a "Night Guard" to auto-close positions before high-spread rollover hours.

Remote Control: Fully integrated with a Discord bot for live monitoring, status updates, and remote account switching.

!! YOU NEED TO TRAIN THE AI YOURSELF !!
How to:
  -Select wanted Symbols in settings.py
  -Launch Trainer.py
  -Wait a few Minutes or hours or even days...
  -(If you stopped while it trained, delete *finished* Symbols from Settings.py (remember which) , and launch again)
  -Should be ready.
