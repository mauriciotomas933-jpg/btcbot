import requests
import time
import datetime

# ============================================================
# CONFIGURACION - EDITÁ ESTOS VALORES
# ============================================================
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = "1867234680"
CHECK_INTERVAL_MINUTES = 15  # cada cuántos minutos analiza
# ============================================================
# Estado interno del bot
in_position = False
buy_price = 0.0
last_signal = ""
last_heartbeat = datetime.datetime.now()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error enviando mensaje: {e}")

def get_btc_price():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", timeout=10)
        return float(r.json()["bitcoin"]["usd"])
    except:
        return None

def get_klines(interval="15m", limit=60):
    try:
        url = f"https://api.binance.us/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=10)
        data = r.json()
        closes = [float(c[4]) for c in data]
        volumes = [float(c[5]) for c in data]
        return closes, volumes
    except:
        return None, None

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema

def analyze():
    global in_position, buy_price, last_signal

    price = get_btc_price()
    if not price:
        print("No se pudo obtener el precio.")
        return

    closes, volumes = get_klines(interval="15m", limit=60)
    if not closes:
        print("No se pudieron obtener datos de velas.")
        return

    rsi = calc_rsi(closes)
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)

    if not all([rsi, ema9, ema21, ema50]):
        return

    avg_volume = sum(volumes[:-1]) / len(volumes[:-1])
    current_volume = volumes[-1]
    volume_ok = current_volume > avg_volume * 1.2

    now = datetime.datetime.now().strftime("%H:%M:%S")
    profit_pct = 0
    if in_position and buy_price > 0:
        profit_pct = ((price - buy_price) / buy_price) * 100

    print(f"[{now}] BTC: ${price:,.2f} | RSI: {rsi:.1f} | EMA9: {ema9:,.0f} | EMA21: {ema21:,.0f} | EMA50: {ema50:,.0f} | Vol+: {volume_ok}")

    # ---- LÓGICA DE SEÑALES ----

    # Señal de COMPRA
    buy_signal = (
        not in_position and
        rsi < 40 and
        ema9 > ema21 and
        price > ema50 and
        volume_ok
    )

    # Señal de VENTA con ganancia
    sell_signal_profit = (
        in_position and
        profit_pct >= 1.5 and
        (rsi > 65 or ema9 < ema21)
    )

    # Stop loss: salir si cae más del 2%
    sell_signal_stoploss = (
        in_position and
        profit_pct <= -2.0
    )

    if buy_signal and last_signal != "BUY":
        last_signal = "BUY"
        in_position = True
        buy_price = price
        msg = (
            f"🟢 <b>SEÑAL DE COMPRA</b>\n\n"
            f"💰 Precio actual: <b>${price:,.2f}</b>\n"
            f"📊 RSI: {rsi:.1f} (oversold)\n"
            f"📈 EMA9 &gt; EMA21 ✅\n"
            f"📦 Volumen elevado ✅\n"
            f"⏰ {now}\n\n"
            f"👉 Abrí Binance y comprá BTC ahora."
        )
        send_telegram(msg)
        print(">>> SEÑAL DE COMPRA enviada")

    elif sell_signal_profit and last_signal != "SELL":
        last_signal = "SELL"
        in_position = False
        msg = (
            f"🔴 <b>SEÑAL DE VENTA</b> (con ganancia)\n\n"
            f"💰 Precio actual: <b>${price:,.2f}</b>\n"
            f"💵 Precio de entrada: ${buy_price:,.2f}\n"
            f"📈 Ganancia estimada: <b>+{profit_pct:.2f}%</b>\n"
            f"📊 RSI: {rsi:.1f}\n"
            f"⏰ {now}\n\n"
            f"👉 Abrí Binance y vendé BTC ahora."
        )
        send_telegram(msg)
        print(">>> SEÑAL DE VENTA (ganancia) enviada")
        buy_price = 0.0

    elif sell_signal_stoploss and last_signal != "STOPLOSS":
        last_signal = "STOPLOSS"
        in_position = False
        msg = (
            f"🛑 <b>STOP LOSS ACTIVADO</b>\n\n"
            f"💰 Precio actual: <b>${price:,.2f}</b>\n"
            f"💵 Precio de entrada: ${buy_price:,.2f}\n"
            f"📉 Pérdida: <b>{profit_pct:.2f}%</b>\n"
            f"⏰ {now}\n\n"
            f"⚠️ Pérdida superó el 2%. Salí ahora para proteger capital."
        )
        send_telegram(msg)
        print(">>> STOP LOSS enviado")
        buy_price = 0.0

def main():
    global last_heartbeat
    print("=" * 50)
    print("Bot BTC Signal arrancado")
    print(f"Analizando cada {CHECK_INTERVAL_MINUTES} minutos")
    print("=" * 50)

    send_telegram(
        f"🤖 <b>Bot BTC Signal activo</b>\n\n"
        f"Voy a analizar BTC cada {CHECK_INTERVAL_MINUTES} minutos y te aviso cuando haya señal de compra o venta.\n\n"
        f"Indicadores: RSI, EMA9/21/50, Volumen"
    )

    last_heartbeat = datetime.datetime.now()

    while True:
        try:
            analyze()
            now = datetime.datetime.now()
            if (now - last_heartbeat).seconds >= 86400:
                price = get_btc_price()
                send_telegram(
                    f"💓 <b>Bot activo</b>\n\n"
                    f"Sigo funcionando correctamente.\n"
                    f"💰 BTC ahora: ${price:,.2f}\n"
                    f"⏰ {now.strftime('%H:%M')}"
                )
                last_heartbeat = now
        except Exception as e:
            print(f"Error en análisis: {e}")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)
