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


def parse_price(val: str) -> float:
    return float(val.replace(".", "").replace(",", ".").replace("$", "").strip())


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
    data = resp.json()
    a = data["data"]

    def item(key):
        d = a[key]
        alis = float(d["alis"])
        satis = float(d["satis"])
        deg = satis - alis
        pct = (deg / alis * 100) if alis else 0
        return {"alis": alis, "satis": satis, "degisim": deg, "pct": pct}

    usd_try_s = float(a["USDTRY"]["satis"])
    eur_try_s = float(a["EURTRY"]["satis"])
    usd_eur = usd_try_s / eur_try_s

    return {
        "gram":   item("ALTIN"),
        "ons":    item("ONS"),
        "ceyrek": item("CEYREK_YENI"),
        "yarim":  item("YARIM_YENI"),
        "tam":    item("ATA_YENI"),
        "usd_try": {"alis": float(a["USDTRY"]["alis"]), "satis": usd_try_s},
        "eur_try": {"alis": float(a["EURTRY"]["alis"]), "satis": eur_try_s},
        "usd_eur": usd_eur,
        "kaynak": "haremaltin.com",
    }


def get_prices_yedek() -> dict:
    data = requests.get(
        "https://finans.truncgil.com/today.json",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    ).json()

    def item(key):
        alis = parse_price(data[key]["Alış"])
        satis = parse_price(data[key]["Satış"])
        deg = satis - alis
        pct = (deg / alis * 100) if alis else 0
        return {"alis": alis, "satis": satis, "degisim": deg, "pct": pct}

    usd_try_s = parse_price(data["USD"]["Satış"])
    eur_try_s = parse_price(data["EUR"]["Satış"])

    return {
        "gram":   item("gram-altin"),
        "ons":    item("ons"),
        "ceyrek": item("ceyrek-altin"),
        "yarim":  item("yarim-altin"),
        "tam":    item("tam-altin"),
        "usd_try": {"alis": parse_price(data["USD"]["Alış"]), "satis": usd_try_s},
        "eur_try": {"alis": parse_price(data["EUR"]["Alış"]), "satis": eur_try_s},
        "usd_eur": usd_try_s / eur_try_s,
        "kaynak": "yedek",
    }


def get_prices() -> dict:
    try:
        prices = get_prices_haremaltin()
        logger.info("Fiyatlar haremaltin.com'dan alındı")
        return prices
    except Exception as e:
        logger.warning("Haremaltin erişilemedi (%s), yedek kaynak kullanılıyor", e)
        return get_prices_yedek()


def fmt_altin(label: str, emoji: str, p: dict) -> str:
    ok = "📈" if p["degisim"] >= 0 else "📉"
    sign = "+" if p["degisim"] >= 0 else ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"📥 Alış: {p['alis']:,.2f} ₺\n"
        f"📤 Satış: {p['satis']:,.2f} ₺\n"
        f"{ok} Değişim: {sign}{p['degisim']:,.2f} ₺ ({sign}{p['pct']:.2f}%)\n"
    )


def fmt_doviz(label: str, emoji: str, p: dict) -> str:
    return (
        f"{emoji} <b>{label}</b>\n"
        f"📥 Alış: {p['alis']:,.4f}\n"
        f"📤 Satış: {p['satis']:,.4f}\n"
    )


def format_message(prices: dict) -> str:
    now = datetime.now(TZ).strftime("%H:%M — Harem Altın")
    msg = ""
    msg += fmt_altin("Gram Altın",   "🥇", prices["gram"])
    msg += "\n"
    msg += fmt_altin("Ons Altın",    "🏅", prices["ons"])
    msg += "\n"
    msg += fmt_altin("Çeyrek Altın", "🪙", prices["ceyrek"])
    msg += "\n"
    msg += fmt_altin("Yarım Altın",  "🪙", prices["yarim"])
    msg += "\n"
    msg += fmt_altin("Tam Altın",    "🪙", prices["tam"])
    msg += "\n"
    msg += fmt_doviz("USD/TRY", "🇺🇸", prices["usd_try"])
    msg += "\n"
    msg += fmt_doviz("EUR/TRY", "🇪🇺", prices["eur_try"])
    msg += "\n"
    msg += f"💱 <b>USD/EUR:</b> {prices['usd_eur']:,.4f}\n"
    msg += f"\n🕐 {now}"
    return msg


async def send_prices_to_all(context: ContextTypes.DEFAULT_TYPE):
    if not subscribers:
        return
    try:
        prices = get_prices()
        msg = format_message(prices)
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
            except Exception as e:
                logger.warning("Gönderilemedi %s: %s", chat_id, e)
        logger.info("Fiyatlar gönderildi: %d sohbet", len(subscribers))
    except Exception as e:
        logger.error("Fiyat gönderme hatası: %s", e)


async def subscribe_and_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    yeni = chat_id not in subscribers
    if yeni:
        subscribers.add(chat_id)
        save_subscribers()

    await update.message.reply_text("⏳ Fiyatlar alınıyor...")
    try:
        prices = get_prices()
        msg = format_message(prices)

        if yeni:
            bilgi = (
                f"✅ <b>Abone oldunuz!</b> Her <b>{INTERVAL_MINUTES} dakikada</b> bir otomatik fiyat alacaksınız.\n"
                f"Durdurmak için /dur yazın.\n\n"
            )
        else:
            bilgi = f"✅ Zaten abonesiniz. Her <b>{INTERVAL_MINUTES} dakikada</b> bir fiyat alıyorsunuz.\n\n"

        await update.message.reply_text(bilgi + msg, parse_mode="HTML")
    except Exception as e:
        logger.error("Abone fiyat hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def fiyatlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fiyatlar alınıyor...")
    try:
        prices = get_prices()
        await update.message.reply_text(format_message(prices), parse_mode="HTML")
    except Exception as e:
        logger.error("Komut hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 <b>Altın & Döviz Fiyatları Botuna Hoş Geldiniz!</b>\n\n"
        f"<b>Komutlar:</b>\n"
        f"• <b>abone</b> — Abone ol ve anlık fiyatları gör\n"
        f"• /fiyatlar — Anlık fiyatları göster\n"
        f"• /dur — Otomatik güncellemeleri durdur\n"
        f"• /start — Bu mesajı göster",
        parse_mode="HTML",
    )


async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers()
        await update.message.reply_text(
            "🔕 Otomatik güncellemeler durduruldu.\n"
            "Tekrar başlatmak için <b>abone</b> yazın.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "Zaten abone değilsiniz. <b>abone</b> yazarak abone olabilirsiniz.",
            parse_mode="HTML",
        )


async def metin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = (update.message.text or "").strip().lower()
    if metin == "abone":
        await subscribe_and_show(update, context)


def main():
    load_subscribers()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("fiyatlar", fiyatlar_command))
    app.add_handler(CommandHandler("dur", dur_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_handler))

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
