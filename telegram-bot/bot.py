import os, json, time, logging, threading, traceback, requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN        = os.environ["BOT_TOKEN"]
CHAT_IDS_RAW     = os.getenv("CHAT_IDS", "")
INTERVAL_MINUTES = int(os.getenv("INTERVAL_MINUTES", "30"))
PORT             = int(os.getenv("PORT", "8080"))
TZ               = pytz.timezone(os.getenv("TIMEZONE", "Europe/Istanbul"))
SUBSCRIBERS_FILE = "subscribers.json"
VERSIYON         = "v5.1"

subscribers: set[str] = set(c.strip() for c in CHAT_IDS_RAW.split(",") if c.strip())

def load_subs():
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE) as f:
                subscribers.update(str(x) for x in json.load(f))
        except Exception: pass

def save_subs():
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
    except Exception as e:
        logger.error("save_subs: %s", e)

def parse_price(v: str) -> float:
    return float(v.replace(".", "").replace(",", ".").replace("$", "").strip())

def make_item(alis: float, satis: float) -> dict:
    d = satis - alis
    return {"alis": alis, "satis": satis, "d": d, "pct": d / alis * 100 if alis else 0}

def yedek_item(data, key):
    obj = data[key]
    alis  = parse_price(next(v for k, v in obj.items() if k[:2] == "Al"))
    satis = parse_price(next(v for k, v in obj.items() if k[:2] == "Sa"))
    return make_item(alis, satis)

def get_prices() -> dict:
    # --- Haremaltin ---
    try:
        r = requests.post(
            "https://www.haremaltin.com/dashboard/ajax/getData",
            headers={"User-Agent":"Mozilla/5.0","X-Requested-With":"XMLHttpRequest",
                     "Accept":"application/json","Content-Type":"application/x-www-form-urlencoded",
                     "Referer":"https://www.haremaltin.com/altin-fiyatlari",
                     "Origin":"https://www.haremaltin.com"},
            data={"dil_id":"0"}, timeout=10)
        r.raise_for_status()
        a = r.json()["data"]
        def hi(k): return make_item(float(a[k]["alis"]), float(a[k]["satis"]))
        gram = hi("ALTIN"); ons = hi("ONS")
        usd  = make_item(float(a["USDTRY"]["alis"]), float(a["USDTRY"]["satis"]))
        eur  = make_item(float(a["EURTRY"]["alis"]), float(a["EURTRY"]["satis"]))
        usdeur = make_item(usd["alis"]/eur["alis"], usd["satis"]/eur["satis"])
        logger.info("Haremaltin OK")
        return {"gram":gram,"ons":ons,"usd":usd,"eur":eur,"usdeur":usdeur,"src":"Harem Altin"}
    except Exception as e:
        logger.warning("Haremaltin fail: %s", e)

    # --- Yedek ---
    r = requests.get("https://finans.truncgil.com/today.json",
                     headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
    r.raise_for_status()
    data = r.json()
    gram   = yedek_item(data, "gram-altin")
    ons    = yedek_item(data, "ons")
    usd    = yedek_item(data, "USD")
    eur    = yedek_item(data, "EUR")
    usdeur = make_item(usd["alis"]/eur["alis"], usd["satis"]/eur["satis"])
    logger.info("Yedek OK")
    return {"gram":gram,"ons":ons,"usd":usd,"eur":eur,"usdeur":usdeur,"src":"Guncel Kur"}

def row_altin(label, emoji, p):
    ok = "\U0001f4c8" if p["d"] >= 0 else "\U0001f4c9"
    s  = "+" if p["d"] >= 0 else ""
    return (f"{emoji} <b>{label}</b>\n"
            f"\U0001f4e5 Alis: {p['alis']:,.2f} \u20ba\n"
            f"\U0001f4e4 Satis: {p['satis']:,.2f} \u20ba\n"
            f"{ok} Degisim: {s}{p['d']:,.2f} \u20ba ({s}{p['pct']:.2f}%)\n")

def row_doviz(label, emoji, p):
    ok = "\U0001f4c8" if p["d"] >= 0 else "\U0001f4c9"
    s  = "+" if p["d"] >= 0 else ""
    return (f"{emoji} <b>{label}</b>\n"
            f"\U0001f4e5 Alis: {p['alis']:,.4f}\n"
            f"\U0001f4e4 Satis: {p['satis']:,.4f}\n"
            f"{ok} Degisim: {s}{p['d']:,.4f} ({s}{p['pct']:.2f}%)\n")

def fmt(prices):
    now = datetime.now(TZ).strftime("%H:%M \u2014 %d.%m.%Y")
    msg  = row_altin("Gram Altin",  "\U0001f947", prices["gram"])   + "\n"
    msg += row_altin("Ons Altin",   "\U0001f3c5", prices["ons"])    + "\n"
    msg += row_doviz("USD/TRY", "\U0001f1fa\U0001f1f8", prices["usd"]) + "\n"
    msg += row_doviz("EUR/TRY", "\U0001f1ea\U0001f1fa", prices["eur"]) + "\n"
    msg += row_doviz("USD/EUR", "\U0001f4b1",            prices["usdeur"])
    msg += f"\n\U0001f550 {now} | {prices['src']} | {VERSIYON}"
    return msg

async def send_all(context: ContextTypes.DEFAULT_TYPE):
    if not subscribers: return
    try:
        msg = fmt(get_prices())
        for cid in list(subscribers):
            try: await context.bot.send_message(cid, msg, parse_mode="HTML")
            except Exception as e: logger.warning("send %s: %s", cid, e)
    except Exception as e: logger.error("send_all: %s", e)

async def cmd_abone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    new = cid not in subscribers
    if new: subscribers.add(cid); save_subs()
    try:
        msg  = fmt(get_prices())
        info = (f"\u2705 <b>Abone oldunuz!</b> Her <b>{INTERVAL_MINUTES} dk</b> fiyat gelecek.\n"
                f"/dur ile durdurabilirsiniz.\n\n") if new else \
               f"\u2705 Zaten abonesiniz ({INTERVAL_MINUTES} dk).\n\n"
        await update.message.reply_text(info + msg, parse_mode="HTML")
    except Exception as e:
        tb = traceback.format_exc()[-400:]
        await update.message.reply_text(f"\u274c {VERSIYON} | {type(e).__name__}: {e}\n<pre>{tb}</pre>",
                                        parse_mode="HTML")

async def cmd_fiyatlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(fmt(get_prices()), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"\u274c {type(e).__name__}: {e}")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"\U0001f44b <b>Altin & Doviz Botu</b> ({VERSIYON})\n\n"
        "/abone \u2014 Abone ol\n/fiyatlar \u2014 Anlik fiyat\n/dur \u2014 Durdur",
        parse_mode="HTML")

async def cmd_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    if cid in subscribers:
        subscribers.discard(cid); save_subs()
        await update.message.reply_text("\U0001f515 Durduruldu. /abone ile tekrar baslatabilirsiniz.")
    else:
        await update.message.reply_text("Abone degilsiniz.")

async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = get_prices()
        await update.message.reply_text(
            f"\U0001f527 <b>{VERSIYON}</b>\nKaynak: {p['src']}\n"
            f"Gram: {p['gram']['satis']:,.2f}\nOns: {p['ons']['satis']:,.2f}\n"
            f"USD/TRY: {p['usd']['satis']:,.4f}\nEUR/TRY: {p['eur']['satis']:,.4f}\n"
            f"USD/EUR: {p['usdeur']['satis']:,.4f}\nAbone: {len(subscribers)}",
            parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"\u274c {e}")

async def metin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.message.text or "").strip().lower() == "abone":
        await cmd_abone(update, context)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *a): pass

def health_server():
    HTTPServer(("0.0.0.0", PORT), Health).serve_forever()

def main():
    load_subs()
    threading.Thread(target=health_server, daemon=True).start()
    logger.info("Health server: port %d | %s", PORT, VERSIYON)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("abone",    cmd_abone))
    app.add_handler(CommandHandler("fiyatlar", cmd_fiyatlar))
    app.add_handler(CommandHandler("dur",      cmd_dur))
    app.add_handler(CommandHandler("debug",    cmd_debug))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin))
    app.job_queue.run_repeating(send_all, interval=INTERVAL_MINUTES * 60, first=10)

    attempt = 0
    while True:
        attempt += 1
        if attempt > 1:
            wait = min(30 * (attempt - 1), 120)
            logger.info("Deneme %d — %ds bekleniyor", attempt, wait)
            time.sleep(wait)
        try:
            logger.info("Polling basliyor — deneme %d", attempt)
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
            break
        except Conflict:
            logger.warning("Conflict — eski instance var, bekleniyor")
        except Exception as e:
            logger.error("Hata: %s", e)

if __name__ == "__main__":
    main()
