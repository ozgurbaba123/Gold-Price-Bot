import os
import logging
import requests
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_IDS_RAW = os.getenv("CHAT_IDS", "")
CHAT_IDS = [cid.strip() for cid in CHAT_IDS_RAW.split(",") if cid.strip()]
INTERVAL_MINUTES = int(os.getenv("INTERVAL_MINUTES", "30"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Istanbul")

TZ = pytz.timezone(TIMEZONE)


def get_prices():
    currency = requests.get(
        "https://open.er-api.com/v6/latest/USD", timeout=10
    ).json()
    usd_try = currency["rates"]["TRY"]
    eur_try = currency["rates"]["TRY"] / currency["rates"]["EUR"]
    usd_eur = 1 / currency["rates"]["EUR"]

    gold = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    ).json()
    xau_usd = gold["chart"]["result"][0]["meta"]["regularMarketPrice"]

    troy_to_gram = 31.1035
    gram_altin_try = (xau_usd * usd_try) / troy_to_gram

    ceyrek = gram_altin_try * 1.75
    yarim = gram_altin_try * 3.5
    tam = gram_altin_try * 7.0

    return {
        "gram_altin": gram_altin_try,
        "ceyrek": ceyrek,
        "yarim": yarim,
        "tam": tam,
        "usd_try": usd_try,
        "eur_try": eur_try,
        "usd_eur": usd_eur,
    }


def format_message(prices: dict) -> str:
    now = datetime.now(TZ).strftime("%H:%M  |  %d %B %Y")
    return (
        f"📊 <b>Güncel Piyasa Fiyatları</b>\n"
        f"🕐 {now}\n"
        f"\n"
        f"🥇 <b>ALTIN</b>\n"
        f"Gram Altın:    <b>₺{prices['gram_altin']:,.2f}</b>\n"
        f"Çeyrek Altın:  <b>₺{prices['ceyrek']:,.2f}</b>\n"
        f"Yarım Altın:   <b>₺{prices['yarim']:,.2f}</b>\n"
        f"Tam Altın:     <b>₺{prices['tam']:,.2f}</b>\n"
        f"\n"
        f"💱 <b>DÖVİZ</b>\n"
        f"USD/TRY:  <b>₺{prices['usd_try']:,.4f}</b>\n"
        f"EUR/TRY:  <b>₺{prices['eur_try']:,.4f}</b>\n"
        f"USD/EUR:  <b>€{prices['usd_eur']:,.4f}</b>\n"
    )


async def send_prices_to_all(context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        msg = format_message(prices)
        for chat_id in CHAT_IDS:
            await context.bot.send_message(
                chat_id=chat_id, text=msg, parse_mode="HTML"
            )
        logger.info("Fiyatlar gönderildi: %d sohbet", len(CHAT_IDS))
    except Exception as e:
        logger.error("Fiyat gönderme hatası: %s", e)


async def fiyatlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fiyatlar alınıyor...")
    try:
        prices = get_prices()
        msg = format_message(prices)
        await update.message.reply_text(msg, parse_mode="HTML")
    except Exception as e:
        logger.error("Komut hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👋 Merhaba! Altın ve döviz fiyatları botuna hoş geldiniz.\n\n"
        f"📌 Chat ID'niz: <code>{chat_id}</code>\n\n"
        f"Komutlar:\n"
        f"/fiyatlar — Anlık fiyatları göster\n"
        f"/start — Bu mesajı göster\n\n"
        f"💡 Otomatik fiyat almak için Chat ID'nizi yöneticiye bildirin.",
        parse_mode="HTML",
    )


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable eksik!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("fiyatlar", fiyatlar_command))

    if CHAT_IDS:
        job_queue = app.job_queue
        job_queue.run_repeating(
            send_prices_to_all,
            interval=INTERVAL_MINUTES * 60,
            first=10,
        )
        logger.info(
            "Otomatik gönderim aktif: her %d dakikada bir, %d sohbet",
            INTERVAL_MINUTES,
            len(CHAT_IDS),
        )
    else:
        logger.warning("CHAT_IDS tanımlanmamış — otomatik gönderim devre dışı.")

    logger.info("Bot başlatılıyor...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
