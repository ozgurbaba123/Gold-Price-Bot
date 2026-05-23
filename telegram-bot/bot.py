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
ALARMS_FILE = "alarms.json"

TZ = pytz.timezone(TIMEZONE)

subscribers: set[str] = set(
    cid.strip() for cid in CHAT_IDS_RAW.split(",") if cid.strip()
)

# alarm_listesi: { chat_id: [ {tur, esik, yon, tetiklendi}, ... ] }
alarm_listesi: dict[str, list] = {}

VERSIYON = "v5.0"


# ─── Abone kayıt ───────────────────────────────────────────────────────────────

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


# ─── Alarm kayıt ───────────────────────────────────────────────────────────────

def load_alarms():
    if os.path.exists(ALARMS_FILE):
        try:
            with open(ALARMS_FILE) as f:
                data = json.load(f)
                alarm_listesi.update(data)
        except Exception:
            pass


def save_alarms():
    try:
        with open(ALARMS_FILE, "w") as f:
            json.dump(alarm_listesi, f, ensure_ascii=False)
    except Exception as e:
        logger.error("Alarm kaydedilemedi: %s", e)


# ─── Fiyat çekme ───────────────────────────────────────────────────────────────

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
    raw = resp.json()
    a = raw["data"]

    def item(key):
        d = a[key]
        alis = float(d["alis"])
        satis = float(d["satis"])
        deg = satis - alis
        pct = (deg / alis * 100) if alis else 0
        return {"alis": alis, "satis": satis, "degisim": deg, "pct": pct}

    def doviz(a_, s_):
        deg = s_ - a_
        return {"alis": a_, "satis": s_, "degisim": deg, "pct": (deg / a_ * 100) if a_ else 0}

    gram = item("ALTIN")

    try:
        ons = item("ONS")
    except Exception:
        gram_alis = gram["alis"]
        gram_satis = gram["satis"]
        ons_alis = gram_alis * 31.1035
        ons_satis = gram_satis * 31.1035
        ons = doviz(ons_alis, ons_satis)

    # Çeyrek, Yarım, Tam altın (gram bazlı)
    ceyrek_alis  = gram["alis"]  * 1.6
    ceyrek_satis = gram["satis"] * 1.6
    yarim_alis   = gram["alis"]  * 3.2
    yarim_satis  = gram["satis"] * 3.2
    tam_alis     = gram["alis"]  * 6.4
    tam_satis    = gram["satis"] * 6.4

    usd_try_a = float(a["USDTRY"]["alis"])
    usd_try_s = float(a["USDTRY"]["satis"])
    eur_try_a = float(a["EURTRY"]["alis"])
    eur_try_s = float(a["EURTRY"]["satis"])
    usd_eur_a = usd_try_a / eur_try_a
    usd_eur_s = usd_try_s / eur_try_s

    return {
        "gram":    gram,
        "ons":     ons,
        "ceyrek":  {"alis": ceyrek_alis,  "satis": ceyrek_satis},
        "yarim":   {"alis": yarim_alis,   "satis": yarim_satis},
        "tam":     {"alis": tam_alis,     "satis": tam_satis},
        "usd_try": doviz(usd_try_a, usd_try_s),
        "eur_try": doviz(eur_try_a, eur_try_s),
        "usd_eur": doviz(usd_eur_a, usd_eur_s),
        "kaynak":  "haremaltin.com",
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

    usd_try_a = parse_price(data["USD"]["Alış"])
    usd_try_s = parse_price(data["USD"]["Satış"])
    eur_try_a = parse_price(data["EUR"]["Alış"])
    eur_try_s = parse_price(data["EUR"]["Satış"])
    usd_eur_a = usd_try_a / eur_try_a
    usd_eur_s = usd_try_s / eur_try_s

    def doviz(a_, s_):
        deg = s_ - a_
        return {"alis": a_, "satis": s_, "degisim": deg, "pct": (deg / a_ * 100) if a_ else 0}

    gram = item("gram-altin")
    ceyrek_alis  = gram["alis"]  * 1.6
    ceyrek_satis = gram["satis"] * 1.6
    yarim_alis   = gram["alis"]  * 3.2
    yarim_satis  = gram["satis"] * 3.2
    tam_alis     = gram["alis"]  * 6.4
    tam_satis    = gram["satis"] * 6.4

    return {
        "gram":    gram,
        "ons":     item("ons"),
        "ceyrek":  {"alis": ceyrek_alis,  "satis": ceyrek_satis},
        "yarim":   {"alis": yarim_alis,   "satis": yarim_satis},
        "tam":     {"alis": tam_alis,     "satis": tam_satis},
        "usd_try": doviz(usd_try_a, usd_try_s),
        "eur_try": doviz(eur_try_a, eur_try_s),
        "usd_eur": doviz(usd_eur_a, usd_eur_s),
        "kaynak":  "yedek",
    }


def get_prices() -> dict:
    try:
        prices = get_prices_haremaltin()
        logger.info("Fiyatlar haremaltin.com'dan alındı")
        return prices
    except Exception as e:
        logger.warning("Haremaltin erişilemedi (%s), yedek kaynak kullanılıyor", e)
        return get_prices_yedek()


# ─── Mesaj formatlama ──────────────────────────────────────────────────────────

def fmt_altin(label: str, emoji: str, p: dict) -> str:
    degisim = p.get("degisim")
    if degisim is not None:
        ok = "📈" if degisim >= 0 else "📉"
        sign = "+" if degisim >= 0 else ""
        degisim_str = f"{ok} Değişim: {sign}{degisim:,.2f} ₺ ({sign}{p['pct']:.2f}%)\n"
    else:
        degisim_str = ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"📥 Alış: {p['alis']:,.2f} ₺\n"
        f"📤 Satış: {p['satis']:,.2f} ₺\n"
        f"{degisim_str}"
    )


def fmt_doviz(label: str, emoji: str, p: dict) -> str:
    ok = "📈" if p["degisim"] >= 0 else "📉"
    sign = "+" if p["degisim"] >= 0 else ""
    return (
        f"{emoji} <b>{label}</b>\n"
        f"📥 Alış: {p['alis']:,.4f}\n"
        f"📤 Satış: {p['satis']:,.4f}\n"
        f"{ok} Değişim: {sign}{p['degisim']:,.4f} ({sign}{p['pct']:.2f}%)\n"
    )


def format_message(prices: dict) -> str:
    now = datetime.now(TZ).strftime("%H:%M — %d.%m.%Y")
    kaynak = prices.get("kaynak", "")
    msg = ""
    msg += fmt_altin("Gram Altın",    "🥇", prices["gram"])
    msg += "\n"
    msg += fmt_altin("Ons Altın",     "🏅", prices["ons"])
    msg += "\n"
    msg += fmt_altin("Çeyrek Altın",  "🔸", prices["ceyrek"])
    msg += "\n"
    msg += fmt_altin("Yarım Altın",   "🔶", prices["yarim"])
    msg += "\n"
    msg += fmt_altin("Tam Altın",     "💰", prices["tam"])
    msg += "\n"
    msg += fmt_doviz("USD/TRY",       "🇺🇸", prices["usd_try"])
    msg += "\n"
    msg += fmt_doviz("EUR/TRY",       "🇪🇺", prices["eur_try"])
    msg += "\n"
    msg += fmt_doviz("USD/EUR",       "💱",  prices["usd_eur"])
    msg += f"\n🕐 {now}"
    if kaynak == "yedek":
        msg += " <i>(yedek kaynak)</i>"
    return msg


def format_altin_only(prices: dict) -> str:
    """Sadece altın fiyatları (kısa mesaj)."""
    now = datetime.now(TZ).strftime("%H:%M")
    msg = f"🏆 <b>Altın Fiyatları</b> — {now}\n\n"
    msg += fmt_altin("Gram",    "🥇", prices["gram"])
    msg += "\n"
    msg += fmt_altin("Çeyrek",  "🔸", prices["ceyrek"])
    msg += "\n"
    msg += fmt_altin("Yarım",   "🔶", prices["yarim"])
    msg += "\n"
    msg += fmt_altin("Tam",     "💰", prices["tam"])
    msg += "\n"
    msg += fmt_altin("Ons",     "🏅", prices["ons"])
    return msg


def format_doviz_only(prices: dict) -> str:
    """Sadece döviz kurları (kısa mesaj)."""
    now = datetime.now(TZ).strftime("%H:%M")
    msg = f"💱 <b>Döviz Kurları</b> — {now}\n\n"
    msg += fmt_doviz("USD/TRY", "🇺🇸", prices["usd_try"])
    msg += "\n"
    msg += fmt_doviz("EUR/TRY", "🇪🇺", prices["eur_try"])
    msg += "\n"
    msg += fmt_doviz("USD/EUR", "💱",  prices["usd_eur"])
    return msg


# ─── Alarm sistemi ─────────────────────────────────────────────────────────────

TUR_LABELS = {
    "gram":    ("Gram Altın",   "🥇"),
    "ceyrek":  ("Çeyrek Altın", "🔸"),
    "yarim":   ("Yarım Altın",  "🔶"),
    "tam":     ("Tam Altın",    "💰"),
    "ons":     ("Ons Altın",    "🏅"),
    "usd_try": ("USD/TRY",      "🇺🇸"),
    "eur_try": ("EUR/TRY",      "🇪🇺"),
}


async def kontrol_alarmlar(context: ContextTypes.DEFAULT_TYPE):
    if not alarm_listesi:
        return
    try:
        prices = get_prices()
    except Exception as e:
        logger.warning("Alarm kontrolü için fiyat alınamadı: %s", e)
        return

    degisti = False
    for chat_id, alarmlar in list(alarm_listesi.items()):
        for alarm in alarmlar:
            if alarm.get("tetiklendi"):
                continue
            tur = alarm["tur"]
            esik = alarm["esik"]
            yon = alarm["yon"]
            p = prices.get(tur)
            if p is None:
                continue
            guncel = p["satis"]
            tetiklendi = (yon == "yukari" and guncel >= esik) or (yon == "asagi" and guncel <= esik)
            if tetiklendi:
                alarm["tetiklendi"] = True
                degisti = True
                label, emoji = TUR_LABELS.get(tur, (tur, "🔔"))
                yon_emoji = "📈" if yon == "yukari" else "📉"
                msg = (
                    f"🔔 <b>ALARM TETİKLENDİ!</b>\n\n"
                    f"{emoji} {label}\n"
                    f"{yon_emoji} Hedef: {esik:,.2f}\n"
                    f"💹 Güncel Satış: {guncel:,.2f}\n\n"
                    f"Yeni alarm için /alarm komutunu kullanın."
                )
                try:
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
                except Exception as e:
                    logger.warning("Alarm gönderilemedi %s: %s", chat_id, e)

    if degisti:
        save_alarms()


# ─── Otomatik yayın ───────────────────────────────────────────────────────────

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


# ─── Komut işleyicileri ───────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 <b>Altın & Döviz Fiyatları Botuna Hoş Geldiniz!</b> {VERSIYON}\n\n"
        f"<b>📌 Komutlar:</b>\n"
        f"• <b>abone</b> — Abone ol ve anlık fiyatları gör\n"
        f"• /fiyatlar — Tüm fiyatları göster\n"
        f"• /altin — Sadece altın fiyatları\n"
        f"• /doviz — Sadece döviz kurları\n"
        f"• /alarm — Fiyat alarmı kur\n"
        f"• /alarmlarim — Aktif alarmlarım\n"
        f"• /alarmiptal — Tüm alarmları sil\n"
        f"• /dur — Otomatik güncellemeleri durdur\n"
        f"• /yardim — Yardım menüsü",
        parse_mode="HTML",
    )


async def yardim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📖 <b>Yardım — {VERSIYON}</b>\n\n"
        f"<b>Fiyat Komutları:</b>\n"
        f"• /fiyatlar — Gram, Ons, Çeyrek, Yarım, Tam altın + döviz\n"
        f"• /altin — Sadece altın fiyatları\n"
        f"• /doviz — Sadece döviz kurları\n\n"
        f"<b>Abonelik:</b>\n"
        f"• <b>abone</b> yaz — Her {INTERVAL_MINUTES} dakikada otomatik bildirim\n"
        f"• /dur — Otomatik bildirimleri durdur\n\n"
        f"<b>Alarm Sistemi:</b>\n"
        f"• /alarm gram 2000 — Gram altın 2000₺ üstüne çıkınca bildir\n"
        f"• /alarm usd_try 35 — USD/TRY 35'in altına düşünce bildir\n"
        f"• /alarmlarim — Aktif alarmlarınız\n"
        f"• /alarmiptal — Tüm alarmları sil\n\n"
        f"<b>Alarm türleri:</b> gram, ceyrek, yarim, tam, ons, usd_try, eur_try",
        parse_mode="HTML",
    )


async def fiyatlar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        await update.message.reply_text(format_message(prices), parse_mode="HTML")
    except Exception as e:
        logger.error("Komut hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def altin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        await update.message.reply_text(format_altin_only(prices), parse_mode="HTML")
    except Exception as e:
        logger.error("Altın komut hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı.")


async def doviz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        await update.message.reply_text(format_doviz_only(prices), parse_mode="HTML")
    except Exception as e:
        logger.error("Döviz komut hatası: %s", e)
        await update.message.reply_text("❌ Kurlar alınamadı.")


async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Kullanım: /alarm <tür> <hedef_fiyat>
    Örnek:    /alarm gram 2000
              /alarm usd_try 35.5
    """
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "⚠️ Kullanım: <code>/alarm &lt;tür&gt; &lt;hedef&gt;</code>\n\n"
            "Örnekler:\n"
            "• <code>/alarm gram 2000</code>\n"
            "• <code>/alarm usd_try 35</code>\n\n"
            "Türler: gram, ceyrek, yarim, tam, ons, usd_try, eur_try",
            parse_mode="HTML",
        )
        return

    tur = args[0].lower()
    if tur not in TUR_LABELS:
        await update.message.reply_text(
            f"❌ Geçersiz tür: <b>{tur}</b>\n"
            f"Geçerli türler: {', '.join(TUR_LABELS.keys())}",
            parse_mode="HTML",
        )
        return

    try:
        esik = float(args[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Hedef fiyat sayı olmalı. Örnek: /alarm gram 2000")
        return

    # Mevcut fiyatı çek, yönü belirle
    try:
        prices = get_prices()
        guncel = prices[tur]["satis"]
    except Exception:
        await update.message.reply_text("❌ Güncel fiyat alınamadı, tekrar deneyin.")
        return

    yon = "yukari" if esik > guncel else "asagi"
    chat_id = str(update.effective_chat.id)

    if chat_id not in alarm_listesi:
        alarm_listesi[chat_id] = []

    alarm_listesi[chat_id].append({"tur": tur, "esik": esik, "yon": yon, "tetiklendi": False})
    save_alarms()

    label, emoji = TUR_LABELS[tur]
    yon_emoji = "📈" if yon == "yukari" else "📉"
    await update.message.reply_text(
        f"✅ <b>Alarm kuruldu!</b>\n\n"
        f"{emoji} {label}\n"
        f"{yon_emoji} Hedef: {esik:,.2f}\n"
        f"📊 Şu anki satış: {guncel:,.2f}\n\n"
        f"Fiyat hedefe ulaştığında bildirim alacaksınız.",
        parse_mode="HTML",
    )


async def alarmlarim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    alarmlar = [a for a in alarm_listesi.get(chat_id, []) if not a.get("tetiklendi")]

    if not alarmlar:
        await update.message.reply_text("🔕 Aktif alarmınız yok.\nYeni alarm için /alarm komutunu kullanın.")
        return

    msg = f"🔔 <b>Aktif Alarmlarınız ({len(alarmlar)}):</b>\n\n"
    for i, a in enumerate(alarmlar, 1):
        label, emoji = TUR_LABELS.get(a["tur"], (a["tur"], "📌"))
        yon_emoji = "📈" if a["yon"] == "yukari" else "📉"
        msg += f"{i}. {emoji} {label} {yon_emoji} {a['esik']:,.2f}\n"

    await update.message.reply_text(msg, parse_mode="HTML")


async def alarmiptal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in alarm_listesi:
        del alarm_listesi[chat_id]
        save_alarms()
        await update.message.reply_text("✅ Tüm alarmlarınız silindi.")
    else:
        await update.message.reply_text("Zaten aktif alarm yok.")


async def subscribe_and_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    yeni = chat_id not in subscribers
    if yeni:
        subscribers.add(chat_id)
        save_subscribers()

    try:
        prices = get_prices()
        msg = format_message(prices)
        bilgi = (
            f"✅ <b>Abone oldunuz!</b> Her <b>{INTERVAL_MINUTES} dakikada</b> bir otomatik fiyat alacaksınız.\n"
            f"Durdurmak için /dur yazın.\n\n"
        ) if yeni else (
            f"✅ Zaten abonesiniz. Her <b>{INTERVAL_MINUTES} dakikada</b> bir fiyat alıyorsunuz.\n\n"
        )
        await update.message.reply_text(bilgi + msg, parse_mode="HTML")
    except Exception as e:
        logger.error("Abone fiyat hatası: %s", e)
        await update.message.reply_text("❌ Fiyatlar alınamadı, lütfen tekrar deneyin.")


async def dur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in subscribers:
        subscribers.discard(chat_id)
        save_subscribers()
        await update.message.reply_text(
            "🔕 Otomatik güncellemeler durduruldu.\nTekrar başlatmak için <b>abone</b> yazın.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "Zaten abone değilsiniz. <b>abone</b> yazarak abone olabilirsiniz.",
            parse_mode="HTML",
        )


async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        prices = get_prices()
        kaynak = prices.get("kaynak", "?")
        gram_satis = prices["gram"]["satis"]
        await update.message.reply_text(
            f"🔧 <b>Debug — {VERSIYON}</b>\n"
            f"Kaynak: {kaynak}\n"
            f"Gram satış: {gram_satis:,.2f} ₺\n"
            f"Abone sayısı: {len(subscribers)}\n"
            f"Alarm sayısı: {sum(len(v) for v in alarm_listesi.values())}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {e}")


async def metin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = (update.message.text or "").strip().lower()
    if metin == "abone":
        await subscribe_and_show(update, context)


# ─── Ana fonksiyon ────────────────────────────────────────────────────────────

def main():
    load_subscribers()
    load_alarms()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       start_command))
    app.add_handler(CommandHandler("yardim",      yardim_command))
    app.add_handler(CommandHandler("fiyatlar",    fiyatlar_command))
    app.add_handler(CommandHandler("altin",       altin_command))
    app.add_handler(CommandHandler("doviz",       doviz_command))
    app.add_handler(CommandHandler("alarm",       alarm_command))
    app.add_handler(CommandHandler("alarmlarim",  alarmlarim_command))
    app.add_handler(CommandHandler("alarmiptal",  alarmiptal_command))
    app.add_handler(CommandHandler("dur",         dur_command))
    app.add_handler(CommandHandler("debug",       debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, metin_handler))

    job_queue = app.job_queue
    job_queue.run_repeating(
        send_prices_to_all,
        interval=INTERVAL_MINUTES * 60,
        first=10,
    )
    # Alarm kontrolü her dakika
    job_queue.run_repeating(
        kontrol_alarmlar,
        interval=60,
        first=15,
    )

    logger.info("Bot başlatıldı %s — her %d dakikada bir fiyat gönderiliyor", VERSIYON, INTERVAL_MINUTES)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
