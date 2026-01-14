# =========================================================
# PACIFICA CCXT ADAPTER (AGENT WALLET, NO SDK)
# =========================================================

import asyncio
import time
import json
from inspect import signature

import base58
import requests
from decimal import Decimal
from typing import Dict, Any, Optional, List
import math
import ccxt
from ccxt import AuthenticationError, InvalidOrder, OrderNotFound
from ccxt.base.types import Market, Ticker, Trade, Order, Position, Balances
from coincurve.ecdsa import signature_normalize
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from pacifica_ccxt_adapter.const import EOrderType, EOrderSide, EOrderStatus
#from const import EOrderType, EOrderSide, EOrderStatus

from ccxt.base.types import (
    Market,
    Ticker,
    Trade,
    Order,
    Position,
    Balances,
    FundingRate, Int, Str,
)
import os
import time
import json
import base58
import requests
import logging
import traceback
import uuid
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from solders.keypair import Keypair

from solders.keypair import Keypair

# =========================================================
# SIGNING HELPERS (FROM YOUR DOCUMENT)
# =========================================================
def sort_json_keys(value):
    if isinstance(value, dict):
        return {k: sort_json_keys(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [sort_json_keys(v) for v in value]
    return value


def prepare_message(header: dict, payload: dict) -> str:
    data = {**header, "data": payload}
    return json.dumps(sort_json_keys(data), separators=(",", ":"))


def sign_message(message: str, keypair: Keypair) -> str:
    signature = keypair.sign_message(message.encode("utf-8"))
    return base58.b58encode(bytes(signature)).decode("utf-8")

# =========================================================
# EXCHANGE
# =========================================================
class Pacifica(ccxt.Exchange):
    id = "pacifica"
    name = "Pacifica"
    rateLimit = 1000

    def __init__(self, config: Dict[str, Any] = {}):
        super().__init__(config)

        self.id = "pacifica"

        self.base_url = config.get(
            "baseUrl", "https://api.pacifica.fi/api/v1"
        )

        # -------------------------
        # Credentials
        # -------------------------
        self.l1_wallet_address = self.safe_string(config, "l1walletAddress")
        agent_private_key = self.safe_string(config, "privateKey")

        if not self.l1_wallet_address or not agent_private_key:
            raise AuthenticationError(
                "Pacifica requires l1walletAddress + agentPrivateKey"
            )

        self.agent_keypair = Keypair.from_base58_string(agent_private_key)
        self.agent_public_key = str(self.agent_keypair.pubkey())

        self.currency = "USDC"

        # -------------------------
        # Capabilities
        # -------------------------
        self.has.update({
            "spot": False,
            "margin": False,
            "swap": True,
            "future": False,
            "option": False,

            "fetchMarkets": True,
            "fetchTicker": True,
            "fetchTickers": True,
            "fetchOrderBook": True,
            "fetchOHLCV": False,

            "fetchBalance": True,
            "fetchTrades": True,
            "fetchMyTrades": True,

            "createOrder": True,
            "cancelOrder": True,
            "cancelAllOrders": True,
            "fetchOrder": True,
            "fetchOrders": True,
            "fetchOpenOrders": False,
            "fetchClosedOrders": True,

            "fetchPositions": True,
            "fetchPosition": True,

            "fetchFundingRate": True,
            "fetchFundingRates": True,
        })

        self.options = self.deep_extend({
            "defaultType": "swap",
        }, self.options)

        self.fees.update({
            'swap': {
                'taker': self.parse_number('0.0002'),
                'maker': self.parse_number('0.0002'),
            },
            'spot': {
                'taker': self.parse_number('0.0002'),
                'maker': self.parse_number('0.0002'),
            },
        })

        self.name = "Pacifica"
        self.rateLimit = 1000

    # =====================================================
    # INTERNAL REQUEST
    # =====================================================
    def _private_post(self, endpoint: str, payload: dict, type_name: str):
        ts = int(time.time() * 1000)

        signature_header = {
            "type": type_name,
            "timestamp": ts,
            "expiry_window": 30000,
        }

        signature_payload = {
            **payload
        }

        message = prepare_message(signature_header, signature_payload)
        signature = sign_message(message, self.agent_keypair)

        body = {
            "account": self.l1_wallet_address,
            "agent_wallet": self.agent_public_key,
            "signature": signature,
            "timestamp": signature_header["timestamp"],
            "expiry_window": signature_header["expiry_window"],
            **signature_payload
        }

        r = requests.post(
            self.base_url + endpoint,
            json=body,
            timeout=15,
        )

        if r.status_code != 200:
            raise ccxt.ExchangeError(r.text)

        data = r.json()
        if not data.get("success", True):
            raise ccxt.ExchangeError(data.get("error"))

        return data.get("data", data)

    # =====================================================
    # HELPERS
    # =====================================================
    def _ccxt_symbol(self, market: str):
        if "-" in market:
            base, quote = market.split("-")
        else:
            base = market
            quote = self.currency
        return f"{base}/{quote}:{quote}"

    def _market_name(self, symbol: str):
        return symbol.replace("/", "-").split(":")[0]

    def _crypto_name(self, symbol: str):
        if "/" in symbol:
            return symbol.split("/")[0]
        return symbol

    def _decimal_places(self, x):
        return int(-math.log10(float(x)))

    # =====================================================
    # MARKETS
    # =====================================================
    def fetch_markets(self, params={}) -> List[Market]:
        r = requests.get(self.base_url + "/info", timeout=10).json()
        out = []

        for m in r["data"]:
            symbol = f"{m['symbol']}/{self.currency}:{self.currency}"
            out.append({
                "id": symbol,
                "symbol": symbol,
                "base": m['symbol'],
                "quote": self.currency,
                "settle": self.currency,
                "spot": False,
                "swap": True,
                "contract": True,
                "linear": True,
                "precision": {
                    "price": self._decimal_places(m["tick_size"]),
                    "amount": self._decimal_places(m["lot_size"]),
                },
                "limits": {
                    "amount": {
                        "min": float(m["min_order_size"]),
                        "max": float(m["max_order_size"]),
                    },
                },
                "info": m,
            })
        return out

    # =====================================================
    # TICKER
    # =====================================================
    def fetch_ticker(self, symbol: str, params={}) -> Ticker:
        r = requests.get(
            self.base_url + "/info/prices",
            timeout=10,
        ).json()["data"]

        for price in r:
            if price["symbol"] == self._crypto_name(symbol):
                return {
                    "symbol": symbol,
                    "timestamp": price["timestamp"],
                    "datetime": self.iso8601(price["timestamp"]),
                    "last": float(price["mid"]),
                    "bid": float(price["mark"]),
                    "ask": float(price["mark"]),
                    "high":-1,
                    "low": -1,
                    "baseVolume": float(price["volume_24h"]),
                    "info": price,
                }
        return None

    # =====================================================
    # BALANCE
    # =====================================================
    def fetch_balance(self, params={}) -> Balances:
        account_data = self.fetch_accounts()
        result = {"info": account_data}
        result["USDC"] = {
            "free": float(account_data["available_to_spend"]),
            "used": float(account_data["total_margin_used"]),
            "total": float(account_data["balance"]),
        }
        return self.safe_balance(result)

    def fetch_order(self, order_id, symbol=None, params=None):
        if order_id is not None:
            try:
                orders = self.fetch_orders()
                for order in orders:
                    if order["id"] == order_id:
                        return self._parse_order(order)
            except Exception as e:
                if "Order not found" in str(e):
                    raise OrderNotFound(order_id)
                raise OrderNotFound(str(e))
        orders = self.fetch_orders(symbol)
        for o in orders:
            if o["id"] == order_id:
                return self._parse_order(o)
        raise OrderNotFound(order_id)

    def _parse_order(self, order):
        return {
            "id": order.id,
            "symbol": order.symbol,
            "status": order.status,
            "type": order.type,
            "side": order.side,
            "price": float(order.price or 0),
            "amount": float(order.quantity or 0),
            "filled": float(order.filled or 0),
            "remaining": float(order.remaining or 0),
            "info": order.to_dict(),
        }

    def fetch_orders(self, symbol: str = None, since: Int = None, limit: Int = None, params={}) -> List[Order]:
        url = f"{self.base_url}/orders?account={self.l1_wallet_address}"
        orders = requests.get(url, params=params, timeout=10).json()["data"]

        parsed = []

        for o in orders:
            sym = self._ccxt_symbol(o["symbol"])
            if symbol is not None and sym != symbol:
                continue

            parsed.append({
                "id": o["order_id"],
                "symbol": sym,
                "side": EOrderSide.BUY.value if o["side"] == "bid" else EOrderSide.SELL.value,
                "type": str(o["order_type"]),
                "price": float(o["price"]),
                "amount": float(o["initial_amount"]),
                "filled": float(o["filled_amount"]),
                "status": EOrderStatus.OPEN.value,
                "info": o,
            })

        if symbol:
            parsed = [o for o in parsed if o["symbol"] == symbol]

        return parsed

    # =====================================================
    # ORDERS
    # =====================================================
    def normalize_order(self, market, price, amount, side):
        price = Decimal(str(price))
        amount = Decimal(str(amount))

        # PRICE
        price_precision = market["precision"]["price"]
        price_tick = Decimal("10") ** -price_precision
        price_rounding = ROUND_CEILING if side == "sell" else ROUND_FLOOR
        price = self.round_to_step(price, price_tick, price_rounding)

        # AMOUNT
        amount_precision = market["precision"]["amount"]
        lot_size = Decimal("10") ** -amount_precision
        amount = self.round_to_step(amount, lot_size, ROUND_FLOOR)

        return price, amount

    def round_to_step(self, value, step, rounding):
        return (value / step).to_integral_value(rounding=rounding) * step

    def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Dict = {},
    ) -> Order:

        if type.lower() == "market":
            time_in_force = "ioc"
            if side.lower() == "buy":
                price = price * 1.001
            else:
                price = price * 0.999
        else:
            time_in_force = "gtc"

        market = self.markets[symbol]
        price, amount = self.normalize_order(market, price, amount, side)

        payload = {}
        payload.update(params)

        payload = {
            "symbol": self._crypto_name(symbol),
            "side": "bid" if side == EOrderSide.BUY.value else "ask",
            "amount": str(amount),
            "client_order_id": str(uuid.uuid4()),
            "tif": time_in_force,
            "reduce_only": False,
        }

        if "tp" in params:
            payload["take_profit"] = {
                "stop_price": str(params["tp"].get("price")),
                "limit_price": str(params["tp"].get("price")),
                "client_order_id": str(uuid.uuid4())
            }

        if "sl" in params:
            payload["stop_loss"] = {
                "stop_price": str(params["sl"].get("price")),
                "limit_price": str(params["sl"].get("price")),
                "client_order_id": str(uuid.uuid4())
            }

        if price:
            payload["price"] = str(price)


        try:
            o = self._private_post("/orders/create", payload, "create_order")
        except Exception as e:
            raise InvalidOrder(str(e))

        fee = float(self.fees["swap"]["taker"]) * float(amount) * float(price)

        return {
            "id": str(o["order_id"]),
            "symbol": symbol,
            "type": type,
            "side": side,
            "price": float(price),
            "amount": float(amount),
            'fees':
                {
                    'cost': fee,
                    'currency': 'USDC',
                    'rate': 0.004
                },
            'fee':
                {
                    'cost': fee,
                    'currency': 'USDC',
                    'rate': 0.004
                },
            "status": o.get("status", "open"),
            "info": o,
        }

    def cancel_order(self, id: str, symbol=None, params={}):
        try:
            if symbol is not None:
                response = self._private_post(
                    "/cancel",
                    {"order_id": int(id), "symbol": symbol},
                    "cancel_order",
                )
                if response is not None:
                    return {"id": id, "status": "canceled", "info": response}
            raise UnsupportedError(self.id + ' cancelOrder() needs id and symbol')
        except Exception:
            raise OrderNotFound(id)

    def fetch_funding_rate(self, symbol: str, params={}) -> Optional[FundingRate]:
        url = f"{self.base_url}/funding_rate/history"
        params = {'symbol': self._crypto_name(symbol), 'limit': 1}

        response = requests.get(url, params=params, timeout=10).json()

        response = response["data"][0]

        funding_rate = float(response["funding_rate"])
        funding_time = int(response.get("created_at", time.time()))

        response["fundingRate"] = funding_rate
        response["fundingRateAnnualized"] = funding_rate * 24 * 365
        response["symbol"] = symbol

        return {
            "symbol": symbol,
            "fundingRate": funding_rate,
            "timestamp": funding_time,
            "datetime": self.iso8601(funding_time),
            "fundingDatetime": self.iso8601(funding_time),
            "interval": "1h",
            "info": response,
        }

    # -----------------------------------------------------
    # POSITIONS
    # -----------------------------------------------------
    def fetch_position(self, symbol: str, params={}) -> Optional[Position]:
        positions = self.fetch_positions()
        for p in positions:
            if p["symbol"] == symbol:
                return p
        return None


    def fetch_positions(self, symbols=None, params={}) -> List[Position]:
        url = f"{self.base_url}/positions"
        params = {'account': self.l1_wallet_address}
        positions = requests.get(url, params=params, timeout=10).json()["data"]
        out = []

        for p in positions:
            symbol = self._ccxt_symbol(p["symbol"])
            current_price = self.fetch_ticker(symbol)["last"]
            notional = float(p["amount"]) * float(current_price)
            unrealized_pnl = (float(current_price) - float(p["entry_price"])) * float(p["amount"])
            out.append({
                "symbol": symbol,
                "side": "buy" if p["side"] == "bid" else "sell",
                "contracts": float(p["amount"]),
                "amount": float(p["amount"]),
                "entryPrice": float(p["entry_price"]),
                "markPrice": float(current_price),
                "unrealisedPnl": unrealized_pnl,
                "leverage": self.fetch_leverage(symbol),
                "marginMode": "cross",
                "info": self.extend({"unrealisedPnl": unrealized_pnl, "curRealisedPnl": 0, "size": p["amount"], "positionValue":notional}, p)
            })

        if symbols:
            out = [p for p in out if p["symbol"] in symbols]

        return out

    def fetch_leverage(self, symbol: str, params={}):
        url = f"{self.base_url}/account/settings"
        params = {'account': self.l1_wallet_address}
        response = requests.get(url, params=params, timeout=10).json()

        account_settings = response["data"]
        for setting in account_settings:
            if setting["symbol"] == self._crypto_name(symbol):
                return float(setting[("leverage")])
        return 10 # default

    # =====================================================
    # TRADES
    # =====================================================
    def fetch_trades(self, symbol: str, since=None, limit=100, params={}) -> List[Trade]:
        return self.fetch_my_trades(symbol, since, limit)

    def fetch_my_trades(self, symbol=None, since=None, limit=100, params={}):
        payload = {}
        if symbol:
            payload["symbol"] = self._market_name(symbol)

        trades = self._private_post(
            "/trades",
            payload,
            "get_trades",
        )

        out = []
        for t in trades:
            ts = int(t["timestamp"] * 1000)
            out.append({
                "id": str(t["trade_id"]),
                "symbol": self._ccxt_symbol(t["symbol"]),
                "side": t["side"],
                "price": float(t["price"]),
                "amount": float(t["size"]),
                "timestamp": ts,
                "datetime": self.iso8601(ts),
                "cost": float(t["price"]) * float(t["size"]),
                "fee": t.get("fee"),
                "info": t,
            })
        return out


    def fetch_accounts(self, params={}):
        url = f"{self.base_url}/account"
        params = {'account': self.l1_wallet_address}

        r = requests.get(url, params=params, timeout=10).json()["data"]
        return r

    # =====================================================
    # OHLCV
    # =====================================================
    def fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=100):
        params = {
            "symbol": self._market_name(symbol),
            "interval": timeframe,
        }
        if since:
            params["start_time"] = since

        r = requests.get(
            self.base_url + "/kline",
            params=params,
            timeout=10,
        ).json()

        candles = []
        for c in r["data"]:
            candles.append([
                int(c["t"]),
                float(c["o"]),
                float(c["h"]),
                float(c["l"]),
                float(c["c"]),
                float(c["v"]),
            ])
        return candles

    def fetch_margin_mode(self, symbol: str, params={}):
        return "cross"

    def set_margin_mode(self, marginMode: str, symbol: Str = None, params={}):
        return None