import os
import json
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
INTERVAL_MINUTES = int(os.getenv("INTERVAL_MINUTES", "30"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Istanbul")
SUBSCRIBERS_FILE = "subscribers.json"

TZ = pytz.timezone(TIMEZONE)

subscribers: set[str] = set(
    cid.strip() for cid in CHAT_IDS_RAW.split(",") if cid.strip()
)


def load_subscribers():
    global subscribers
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE) as f:
                data = json.load(f)
                subscribers.update(str(cid) for cid in data)
        except Exception:
            pass


def save_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
    except Exception as e:
        logger.error("Abone kaydedilemedi: %s", e)


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

    return {
        "gram_altin": gram_altin_try,
        "ceyrek": gram_altin_try * 1.75,
        "yarim": gram_altin_try * 3.5,
        "tam": gram_altin_try * 7.0,
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
    if not subscribers:
        return
    try:
        prices = get_prices()
        msg = format_message(prices)
        failed = set()
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(
                    chat_id=chat_id, text=msg, parse_mode="HTML"
                )
            except Exception as e:
                logger.warning("Gönderilemedi %s: %s", chat_id, e)
                failed.add(chat_id)
        logger.info("Fiyatlar gönderildi: %d sohbet", len(subscribers) - len(failed))
    except Exception as e:
        logger.error("Fiyat gönderme hatası: %s", e)


async def fiyatlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fiyatlar alınıyor...")
    try:
        prices = get_prices()
        await update.message.reply_text(format_message(prices), parse_mode="HTML")
    except Exception as e:
        logger.error("Komut hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers()
        status = f"✅ Otomatik fiyat güncellemelerine abone oldunuz!\nHer <b>{INTERVAL_MINUTES} dakikada</b> bir fiyatlar gönderilecek."
    else:
        status = f"✅ Zaten abonesiniz. Her <b>{INTERVAL_MINUTES} dakikada</b> bir fiyat alıyorsunuz."

    await update.message.reply_text(
        f"👋 <b>Altın & Döviz Fiyatları Botuna Hoş Geldiniz!</b>\n\n"
        f"{status}\n\n"
        f"<b>Komutlar:</b>\n"
        f"/fiyatlar — Anlık fiyatları göster\n"
        f"/dur — Otomatik güncellemeleri durdur\n"
        f"/start — Tekrar abone ol",
        parse_mode="HTML",
    )


async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers()
        await update.message.reply_text(
            "🔕 Otomatik güncellemeler durduruldu.\n"
            "Tekrar başlatmak için /start yazın."
        )
    else:
        await update.message.reply_text(
            "Zaten abone değilsiniz. /start ile abone olabilirsiniz."
        )


def main():
    load_subscribers()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("fiyatlar", fiyatlar_command))
    app.add_handler(CommandHandler("dur", dur_command))

    job_queue = app.job_queue
    job_queue.run_repeating(
        send_prices_to_all,
        interval=INTERVAL_MINUTES * 60,
        first=10,
    )
    logger.info("Bot başlatıldı — her %d dakikada bir fiyat gönderiliyor", INTERVAL_MINUTES)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
