import os
import json
import time
import logging
import requests
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN        = os.environ["BOT_TOKEN"]
CHAT_IDS_RAW     = os.getenv("CHAT_IDS", "")
INTERVAL_MINUTES = int(os.getenv("INTERVAL_MINUTES", "30"))
TIMEZONE         = os.getenv("TIMEZONE", "Europe/Istanbul")
SUBSCRIBERS_FILE = "subscribers.json"

TZ       = pytz.timezone(TIMEZONE)
VERSIYON = "v4.7"

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
        raise ValueError("Gecersiz yanit")
    a = raw["data"]

    def item(key):
        d = a[key]
        return make_item(float(d["alis"]), float(d["satis"]))

    gram    = item("ALTIN")
    ons     = item("ONS")
    usd_try = make_item(float(a["USDTRY"]["alis"]), float(a["USDTRY"]["satis"]))
    eur_try = make_item(float(a["EURTRY"]["alis"]), float(a["EURTRY"]["satis"]))
    usd_eur = make_item(usd_try["alis"] / eur_try["alis"], usd_try["satis"] / eur_try["satis"])
    return {"gram": gram, "ons": ons, "usd_try": usd_try, "eur_try": eur_try, "usd_eur": usd_eur, "kaynak": "Harem Altin"}


def get_prices_yedek() -> dict:
    resp = requests.get(
        "https://finans.truncgil.com/today.json",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    def item(key):
        alis  = parse_price(list(data[key].values())[0])
        satis = parse_price(list(data[key].values())[1])
        return make_item(alis, satis)

    gram    = item("gram-altin")
    ons     = item("ons")
    usd_try = item("USD")
    eur_try = item("EUR")
    usd_eur = make_item(usd_try["alis"] / eur_try["alis"], usd_try["satis"] / eur_try["satis"])
    return {"gram": gram, "ons": ons, "usd_try": usd_try, "eur_try": eur_try, "usd_eur": usd_eur, "kaynak": "Guncel Kur"}


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
    ok   = "\U0001f4c8" if p["degisim"] >= 0 else "\U0001f4c9"
    sign = "+" if p["degisim"] >= 0 else ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"\U0001f4e5 Alis: {p['alis']:,.2f} \u20ba\n"
        f"\U0001f4e4 Satis: {p['satis']:,.2f} \u20ba\n"
        f"{ok} Degisim: {sign}{p['degisim']:,.2f} \u20ba ({sign}{p['pct']:.2f}%)\n"
    )


def fmt_doviz(label: str, emoji: str, p: dict) -> str:
    ok   = "\U0001f4c8" if p["degisim"] >= 0 else "\U0001f4c9"
    sign = "+" if p["degisim"] >= 0 else ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"\U0001f4e5 Alis: {p['alis']:,.4f}\n"
        f"\U0001f4e4 Satis: {p['satis']:,.4f}\n"
        f"{ok} Degisim: {sign}{p['degisim']:,.4f} ({sign}{p['pct']:.2f}%)\n"
    )


def format_message(prices: dict) -> str:
    now = datetime.now(TZ).strftime("%H:%M \u2014 %d.%m.%Y")
    msg  = fmt_altin("Gram Altin",  "\U0001f947", prices["gram"])    + "\n"
    msg += fmt_altin("Ons Altin",   "\U0001f3c5", prices["ons"])     + "\n"
    msg += fmt_doviz("USD/TRY",     "\U0001f1fa\U0001f1f8", prices["usd_try"]) + "\n"
    msg += fmt_doviz("EUR/TRY",     "\U0001f1ea\U0001f1fa", prices["eur_try"]) + "\n"
    msg += fmt_doviz("USD/EUR",     "\U0001f4b1", prices["usd_eur"])
    msg += f"\n\U0001f550 {now} | {prices.get('kaynak', '')}"
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
            f"\u2705 <b>Abone oldunuz!</b> Her <b>{INTERVAL_MINUTES} dakikada</b> bir otomatik fiyat alacaksiniz.\n"
            f"Durdurmak icin /dur yazin.\n\n"
        ) if yeni else f"\u2705 Zaten abonesiniz. Her <b>{INTERVAL_MINUTES} dakikada</b> bir fiyat aliyorsunuz.\n\n"
        await update.message.reply_text(bilgi + msg, parse_mode="HTML")
    except Exception as e:
        logger.error("Abone hatasi: %s", e)
        await update.message.reply_text("\u274c Fiyatlar alinamadi, lutfen tekrar deneyin.")


async def fiyatlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(format_message(get_prices()), parse_mode="HTML")
    except Exception as e:
        logger.error("Fiyatlar hatasi: %s", e)
        await update.message.reply_text("\u274c Fiyatlar alinamadi.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"\U0001f44b <b>Altin & Doviz Fiyatlari Botuna Hos Geldiniz!</b>\n\n"
        f"\u2022 /abone veya <b>abone</b> \u2014 Abone ol\n"
        f"\u2022 /fiyatlar \u2014 Anlik fiyatlari goster\n"
        f"\u2022 /dur \u2014 Otomatik guncellemeleri durdur",
        parse_mode="HTML",
    )


async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers()
        await update.message.reply_text("\U0001f515 Durduruldu. Tekrar icin /abone yazin.")
    else:
        await update.message.reply_text("Zaten abone degilsiniz.")


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        await update.message.reply_text(
            f"\U0001f527 <b>{VERSIYON}</b>\n"
            f"Kaynak: {prices['kaynak']}\n"
            f"Gram: {prices['gram']['satis']:,.2f}\n"
            f"Ons: {prices['ons']['satis']:,.2f}\n"
            f"USD/TRY: {prices['usd_try']['satis']:,.4f}\n"
            f"EUR/TRY: {prices['eur_try']['satis']:,.4f}\n"
            f"USD/EUR: {prices['usd_eur']['satis']:,.4f}\n"
            f"Abone: {len(subscribers)}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"\u274c Hata: {e}")


async def metin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if (update.message.text or "").strip().lower() == "abone":
        await subscribe_and_show(update, context)


def build_app():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",    start_command))
    app.add_handler(CommandHandler("abone",    subscribe_and_show))
    app.add_handler(CommandHandler("fiyatlar", fiyatlar_command))
    app.add_handler(CommandHandler("dur",      dur_command))
    app.add_handler(CommandHandler("debug",    debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_handler))
    app.job_queue.run_repeating(send_prices_to_all, interval=INTERVAL_MINUTES * 60, first=15)
    return app


def main():
    load_subscribers()
    attempt = 0
    while True:
        attempt += 1
        wait = min(10 * attempt, 60)  # 10s, 20s, 30s... maks 60s
        logger.info("%s — deneme %d, %ds bekleniyor", VERSIYON, attempt, wait)
        time.sleep(wait)
        try:
            app = build_app()
            logger.info("Polling baslatildi")
            app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
            break  # Normal cikis
        except Conflict:
            logger.warning("Conflict hatasi — baska instance calisiyor, yeniden denenecek")
        except Exception as e:
            logger.error("Beklenmedik hata: %s — yeniden denenecek", e)


if __name__ == "__main__":
    main()
