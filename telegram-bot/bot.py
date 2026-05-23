import os
import json
import logging
import requests
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN      = os.environ["BOT_TOKEN"]
CHAT_IDS_RAW   = os.getenv("CHAT_IDS", "")
INTERVAL_MINUTES = int(os.getenv("INTERVAL_MINUTES", "30"))
TIMEZONE       = os.getenv("TIMEZONE", "Europe/Istanbul")
WEBHOOK_URL    = os.getenv("WEBHOOK_URL", "")          # Railway public URL
PORT           = int(os.getenv("PORT", "8080"))
SUBSCRIBERS_FILE = "subscribers.json"

TZ = pytz.timezone(TIMEZONE)
VERSIYON = "v4.5"

subscribers: set[str] = set(
    cid.strip() for cid in CHAT_IDS_RAW.split(",") if cid.strip()
)


def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE) as f:
                subscribers.update(str(cid) for cid in json.load(f))
        except Exception:
            pass


def save_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
    except Exception as e:
        logger.error("Abone kaydedilemedi: %s", e)


def parse_price(val: str) -> float:
    return float(val.replace(".", "").replace(",", ".").replace("$", "").strip())


def make_item(alis: float, satis: float) -> dict:
    deg = satis - alis
    return {"alis": alis, "satis": satis, "degisim": deg, "pct": (deg / alis * 100) if alis else 0}


def get_prices_haremaltin() -> dict:
    resp = requests.post(
        "https://www.haremaltin.com/dashboard/ajax/getData",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "https://www.haremaltin.com/altin-fiyatlari",
            "Origin": "https://www.haremaltin.com",
        },
        data={"dil_id": "0"},
        timeout=10,
    )
    resp.raise_for_status()
    raw = resp.json()
    if "data" not in raw:
        raise ValueError("Geçersiz yanıt")
    a = raw["data"]

    def item(key):
        d = a[key]
        return make_item(float(d["alis"]), float(d["satis"]))

    gram = item("ALTIN")
    try:
        ons = item("ONS")
    except Exception:
        ons = make_item(gram["alis"] * 31.1035, gram["satis"] * 31.1035)

    usd_try = make_item(float(a["USDTRY"]["alis"]), float(a["USDTRY"]["satis"]))
    eur_try = make_item(float(a["EURTRY"]["alis"]), float(a["EURTRY"]["satis"]))
    usd_eur = make_item(usd_try["alis"] / eur_try["alis"], usd_try["satis"] / eur_try["satis"])
    return {"gram": gram, "ons": ons, "usd_try": usd_try, "eur_try": eur_try, "usd_eur": usd_eur, "kaynak": "Harem Altın"}


def get_prices_yedek() -> dict:
    resp = requests.get(
        "https://finans.truncgil.com/today.json",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    def item(key):
        return make_item(parse_price(data[key]["Alış"]), parse_price(data[key]["Satış"]))

    gram    = item("gram-altin")
    ons     = item("ons")
    usd_try = make_item(parse_price(data["USD"]["Alış"]), parse_price(data["USD"]["Satış"]))
    eur_try = make_item(parse_price(data["EUR"]["Alış"]), parse_price(data["EUR"]["Satış"]))
    usd_eur = make_item(usd_try["alis"] / eur_try["alis"], usd_try["satis"] / eur_try["satis"])
    return {"gram": gram, "ons": ons, "usd_try": usd_try, "eur_try": eur_try, "usd_eur": usd_eur, "kaynak": "Güncel Kur"}


def get_prices() -> dict:
    try:
        p = get_prices_haremaltin()
        logger.info("Haremaltin'den alindi")
        return p
    except Exception as e:
        logger.warning("Haremaltin basarisiz (%s), yedek deneniyor", e)
    p = get_prices_yedek()
    logger.info("Yedek kaynaktan alindi")
    return p


def fmt_altin(label: str, emoji: str, p: dict) -> str:
    ok   = "📈" if p["degisim"] >= 0 else "📉"
    sign = "+" if p["degisim"] >= 0 else ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"📥 Alış: {p['alis']:,.2f} ₺\n"
        f"📤 Satış: {p['satis']:,.2f} ₺\n"
        f"{ok} Değişim: {sign}{p['degisim']:,.2f} ₺ ({sign}{p['pct']:.2f}%)\n"
    )


def fmt_doviz(label: str, emoji: str, p: dict) -> str:
    ok   = "📈" if p["degisim"] >= 0 else "📉"
    sign = "+" if p["degisim"] >= 0 else ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"📥 Alış: {p['alis']:,.4f}\n"
        f"📤 Satış: {p['satis']:,.4f}\n"
        f"{ok} Değişim: {sign}{p['degisim']:,.4f} ({sign}{p['pct']:.2f}%)\n"
    )


def format_message(prices: dict) -> str:
    now = datetime.now(TZ).strftime("%H:%M — %d.%m.%Y")
    msg  = fmt_altin("Gram Altın", "🥇", prices["gram"]) + "\n"
    msg += fmt_altin("Ons Altın",  "🏅", prices["ons"])  + "\n"
    msg += fmt_doviz("USD/TRY",    "🇺🇸", prices["usd_try"]) + "\n"
    msg += fmt_doviz("EUR/TRY",    "🇪🇺", prices["eur_try"]) + "\n"
    msg += fmt_doviz("USD/EUR",    "💱",  prices["usd_eur"])
    msg += f"\n🕐 {now} | {prices.get('kaynak', '')}"
    return msg


async def send_prices_to_all(context: ContextTypes.DEFAULT_TYPE):
    if not subscribers:
        return
    try:
        msg = format_message(get_prices())
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.warning("Gonderilemedi %s: %s", chat_id, e)
    except Exception as e:
        logger.error("Gonderme hatasi: %s", e)


async def subscribe_and_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    yeni = chat_id not in subscribers
    if yeni:
        subscribers.add(chat_id)
        save_subscribers()
    try:
        msg = format_message(get_prices())
        bilgi = (
            f"✅ <b>Abone oldunuz!</b> Her <b>{INTERVAL_MINUTES} dakikada</b> bir otomatik fiyat alacaksınız.\n"
            f"Durdurmak için /dur yazın.\n\n"
        ) if yeni else f"✅ Zaten abonesiniz. Her <b>{INTERVAL_MINUTES} dakikada</b> bir fiyat alıyorsunuz.\n\n"
        await update.message.reply_text(bilgi + msg, parse_mode="HTML")
    except Exception as e:
        logger.error("Abone hatasi: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def fiyatlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(format_message(get_prices()), parse_mode="HTML")
    except Exception as e:
        logger.error("Fiyatlar hatasi: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 <b>Altın & Döviz Fiyatları Botuna Hoş Geldiniz!</b>\n\n"
        f"• /abone veya <b>abone</b> — Abone ol\n"
        f"• /fiyatlar — Anlık fiyatları göster\n"
        f"• /dur — Otomatik güncellemeleri durdur",
        parse_mode="HTML",
    )


async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers()
        await update.message.reply_text("🔕 Durduruldu. Tekrar için /abone yazın.")
    else:
        await update.message.reply_text("Zaten abone değilsiniz.")


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        mod = "webhook" if WEBHOOK_URL else "polling"
        await update.message.reply_text(
            f"🔧 <b>{VERSIYON}</b> | {mod}\n"
            f"Kaynak: {prices['kaynak']}\n"
            f"Gram: {prices['gram']['satis']:,.2f} ₺\n"
            f"USD/TRY: {prices['usd_try']['satis']:,.4f}\n"
            f"EUR/TRY: {prices['eur_try']['satis']:,.4f}\n"
            f"Abone: {len(subscribers)}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {e}")


async def metin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.message.text or "").strip().lower() == "abone":
        await subscribe_and_show(update, context)


def main():
    load_subscribers()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",    start_command))
    app.add_handler(CommandHandler("abone",    subscribe_and_show))
    app.add_handler(CommandHandler("fiyatlar", fiyatlar_command))
    app.add_handler(CommandHandler("dur",      dur_command))
    app.add_handler(CommandHandler("debug",    debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_handler))
    app.job_queue.run_repeating(send_prices_to_all, interval=INTERVAL_MINUTES * 60, first=10)

    if WEBHOOK_URL:
        logger.info("Webhook modu: %s port %d", WEBHOOK_URL, PORT)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            drop_pending_updates=True,
        )
    else:
        logger.info("Polling modu baslatildi — %s", VERSIYON)
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
