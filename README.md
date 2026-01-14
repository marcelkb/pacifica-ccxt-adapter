![Python Version](https://img.shields.io/badge/python-3.13+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

# Pacifica CCXT Adapter

A CCXT-compatible adapter/wrapper for the pacifica Python SDK. It maps pacifica SDK methods onto familiar CCXT interfaces.

- CCXT: https://github.com/ccxt/ccxt
- pacifica SDK (Python): https://github.com/pacifica-fi/python-sdk/

DOES NOT IMPLEMENT ALL METHODS OR SHOW ALL VALUES, USE WITH CAUTION

# Features

- CCXT-style API backed by the pacifica SDK
- Simple environment-based configuration
- Python 3.13+ support

## Installation

For installation and inclusion in another projects use

```
pip install {localpath}\pacifica_ccxt_adapter      
or
pip install git+https://github.com/marcelkb/pacifica-ccxt-adapter.git  
```


## Environment Setup

Create a `.env` file in the project root with the following variables:

```
L1_WALLET_ADDRESS= your l1 main wallet address
PRIVATE_KEY= Your private key
PUBLIC_KEY= Your Api puplic wallet address
```

## Usage

```
from Pacifica import Pacifica
from const import EOrderSide, EOrderType

    load_dotenv()
    PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
    L1_WALLET_ADDRESS = os.environ.get("L1_WALLET_ADDRESS")

    exchange = Pacifica({
        "l1walletAddress": L1_WALLET_ADDRESS,
        "privateKey": PRIVATE_KEY,
    })
    symbol = 'SUI/USDC:USDC'  # market symbol
    AMOUNT = 11

    ticker = exchange.fetch_ticker(symbol)
    print(f"{symbol} price: {ticker['last']}")
    
    position = exchange.fetch_position(symbol)
    print(f"{position['info']['unrealisedPnl']} {position['info']['curRealisedPnl']} {position['info']['size']}")
    
    print(f"Creating LIMIT BUY order for {symbol}")
    print(exchange.create_order(symbol, EOrderType.LIMIT.value, EOrderSide.BUY.value, AMOUNT, ticker['last'] * 0.5))
  
    print(f"Creating TAKE PROFIT MARKET SELL order for {symbol}")
    print(exchange.create_order(
        symbol,
        EOrderType.MARKET.value,
        EOrderSide.SELL.value,
        AMOUNT,
        ticker['last'] * 1.01,
        params={'takeProfitPrice': '250', 'reduceOnly': True}
    ))
    
    print(f"Creating STOP LOSS MARKET SELL order for {symbol}")
    print(exchange.create_order(
        symbol,
        EOrderType.MARKET.value,
        EOrderSide.SELL.value,
        AMOUNT,
        ticker['last'] * 1.01,
        params={'stopLossPrice': '100', 'reduceOnly': True}
    ))

```
