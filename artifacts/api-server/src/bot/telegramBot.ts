// v8.3
import TelegramBot from "node-telegram-bot-api";
import cron from "node-cron";
import { fetchGoldPrice, fetchForexRates, type GoldPrice, type ForexRate } from "./goldPrice.js";
import {
  setSubscriber,
  removeSubscriber,
  getSubscriber,
  getDueSubscribers,
  markNotified,
  subscriberCount,
  loadSubscribers,
} from "./subscribers.js";
import { initSubscriberTable, loadAllFromDb } from "./subscriberDb.js";
import { logger } from "../lib/logger.js";

let bot: TelegramBot | null = null;

const INTERVALS: Record<string, { label: string; minutes: number }> = {
  "5":  { label: "Her 5 dakika",  minutes: 5  },
  "15": { label: "Her 15 dakika", minutes: 15 },
  "30": { label: "Her 30 dakika", minutes: 30 },
  "60": { label: "Her 1 saat",    minutes: 60 },
};

function formatTR(n: number, decimals = 2): string {
  return n.toLocaleString("tr-TR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function formatTime(timestamp: Date): string {
  return timestamp.toLocaleTimeString("tr-TR", {
    timeZone: "Europe/Istanbul",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPrice(price: GoldPrice, rates?: ForexRate[], intervalLabel?: string): string {
  const arrow = price.change > 0 ? "📈" : price.change < 0 ? "📉" : "➡️";
  const changeSign = price.change > 0 ? "+" : "";
  const time = formatTime(price.timestamp);
  const hasGramSpread = Math.abs(price.alis - price.satis) > 0.01;
  const hasOnsSpread = Math.abs(price.onsAlis - price.onsSatis) > 0.01;

  let msg =
    `🥇 *Gram Altın*\n` +
    (hasGramSpread
      ? `📥 Alış: *${formatTR(price.alis)} ₺*\n` +
        `📤 Satış: *${formatTR(price.satis)} ₺*\n`
      : `💰 Fiyat: *${formatTR(price.gramTL)} ₺*\n`) +
    `${arrow} Değişim: *${changeSign}${formatTR(price.change)} ₺* (${changeSign}${price.changePercent.toFixed(2)}%)\n\n` +
    `🏅 *Ons Altın*\n` +
    (hasOnsSpread
      ? `📥 Alış: *${formatTR(price.onsAlis)} ₺*\n` +
        `📤 Satış: *${formatTR(price.onsSatis)} ₺*\n`
      : `💰 Fiyat: *${formatTR(price.onsTL)} ₺*\n`);

  if (rates && rates.length > 0) {
    const rateMap = new Map(rates.map((r) => [r.pair, r]));
    const usd = rateMap.get("USD/TRY");
    const eur = rateMap.get("EUR/TRY");
    const eurusdDirect = rateMap.get("EUR/USD");
    const eurusd = eurusdDirect ?? (usd && eur
      ? { alis: parseFloat((eur.alis / usd.satis).toFixed(4)), satis: parseFloat((eur.satis / usd.alis).toFixed(4)) }
      : null);
    if (usd) {
      msg += `\n🇺🇸 *USD/TRY*\n` +
        `📥 Alış: *${formatTR(usd.alis, 2)}*\n` +
        `📤 Satış: *${formatTR(usd.satis, 2)}*\n`;
    }
    if (eur) {
      msg += `\n🇪🇺 *EUR/TRY*\n` +
        `📥 Alış: *${formatTR(eur.alis, 2)}*\n` +
        `📤 Satış: *${formatTR(eur.satis, 2)}*\n`;
    }
    if (eurusd) {
      msg += `\n💶 *EUR/USD*\n` +
        `📥 Alış: *${formatTR(eurusd.alis, 4)}*\n` +
        `📤 Satış: *${formatTR(eurusd.satis, 4)}*\n`;
    }
  }

  msg += `\n🕐 ${time}` +
    (intervalLabel ? ` — _${intervalLabel}_` : ` — _${price.source}_`);
  return msg;
}

function formatGramOnly(price: GoldPrice): string {
  const arrow = price.change > 0 ? "📈" : price.change < 0 ? "📉" : "➡️";
  const changeSign = price.change > 0 ? "+" : "";
  const hasSpread = Math.abs(price.alis - price.satis) > 0.01;
  return (
    `🥇 *Gram Altın Fiyatı*\n\n` +
    (hasSpread
      ? `📥 Alış: *${formatTR(price.alis)} ₺*\n` +
        `📤 Satış: *${formatTR(price.satis)} ₺*\n`
      : `💰 Fiyat: *${formatTR(price.gramTL)} ₺*\n`) +
    `${arrow} Değişim: *${changeSign}${formatTR(price.change)} ₺* (${changeSign}${price.changePercent.toFixed(2)}%)\n` +
    `🕐 ${formatTime(price.timestamp)} — _${price.source}_`
  );
}

function formatOnsOnly(price: GoldPrice): string {
  const hasSpread = Math.abs(price.onsAlis - price.onsSatis) > 0.01;
  return (
    `🏅 *Ons Altın Fiyatı*\n\n` +
    (hasSpread
      ? `📥 Alış: *${formatTR(price.onsAlis)} ₺*\n` +
        `📤 Satış: *${formatTR(price.onsSatis)} ₺*\n`
      : `💰 Fiyat: *${formatTR(price.onsTL)} ₺*\n`) +
    `🕐 ${formatTime(price.timestamp)} — _${price.source}_`
  );
}

function formatForex(rates: ForexRate[]): string {
  const pairEmoji: Record<string, string> = {
    "USD/TRY": "🇺🇸",
    "EUR/TRY": "🇪🇺",
    "EUR/USD": "💶",
  };
  const pairOrder = ["USD/TRY", "EUR/TRY", "EUR/USD"];
  const rateMap = new Map(rates.map((r) => [r.pair, r]));

  const lines = pairOrder
    .filter((p) => rateMap.has(p))
    .map((p) => {
      const r = rateMap.get(p)!;
      const emoji = pairEmoji[p] ?? "💱";
      const decimals = p === "EUR/USD" ? 4 : 2;
      return (
        `${emoji} *${p}*\n` +
        `📥 Alış: *${formatTR(r.alis, decimals)}*\n` +
        `📤 Satış: *${formatTR(r.satis, decimals)}*`
      );
    });

  const source = rates[0]?.source ?? "—";
  const time = formatTime(rates[0]?.timestamp ?? new Date());
  return lines.join("\n\n") + `\n\n🕐 ${time} — _${source}_`;
}

function formatSingleForex(rate: ForexRate): string {
  const pairEmoji: Record<string, string> = {
    "USD/TRY": "🇺🇸",
    "EUR/TRY": "🇪🇺",
    "EUR/USD": "💶",
  };
  const emoji = pairEmoji[rate.pair] ?? "💱";
  const decimals = rate.pair === "EUR/USD" ? 4 : 2;
  return (
    `${emoji} *${rate.pair} Kuru*\n\n` +
    `📥 Alış: *${formatTR(rate.alis, decimals)}*\n` +
    `📤 Satış: *${formatTR(rate.satis, decimals)}*\n` +
    `🕐 ${formatTime(rate.timestamp)} — _${rate.source}_`
  );
}

function intervalKeyboard(): TelegramBot.InlineKeyboardMarkup {
  return {
    inline_keyboard: [
      [
        { text: "⚡ 5 dakika",  callback_data: "interval_5"  },
        { text: "🕐 15 dakika", callback_data: "interval_15" },
      ],
      [
        { text: "🕧 30 dakika", callback_data: "interval_30" },
        { text: "⏰ 1 saat",    callback_data: "interval_60" },
      ],
      [
        { text: "❌ Bildirimleri Durdur", callback_data: "interval_stop" },
      ],
    ],
  };
}

async function sendCurrentPrice(chatId: number): Promise<void> {
  if (!bot) return;
  try {
    const [price, rates] = await Promise.all([fetchGoldPrice(), fetchForexRates().catch(() => [])]);
    await bot.sendMessage(chatId, formatPrice(price, rates as ForexRate[]), { parse_mode: "Markdown" });
  } catch {
    logger.warn({ chatId }, "İlk fiyat gönderilemedi");
  }
}

export async function initBot(): Promise<void> {
  const token = process.env["TELEGRAM_BOT_TOKEN"];
  if (!token) {
    logger.error("TELEGRAM_BOT_TOKEN eksik — bot başlatılmıyor");
    return;
  }

  await initSubscriberTable();
  const saved = await loadAllFromDb();
  if (saved.length > 0) {
    loadSubscribers(saved);
    logger.info({ count: saved.length }, "Aboneler DB'den yüklendi");
  }

  bot = new TelegramBot(token, { polling: true });
  logger.info("Telegram botu başlatıldı");

  bot.onText(/\/start/, async (msg) => {
    const chatId = msg.chat.id;
    const firstName = msg.from?.first_name ?? "Kullanıcı";
    await bot!.sendMessage(
      chatId,
      `Merhaba ${firstName}! 👋\n\n` +
      `🥇 *Altın & Döviz Fiyat Botu*\n\n` +
      `Canlı altın ve döviz kuru verilerini Türk Lirası cinsinden bildirir.\n\n` +
      `📋 *Altın Komutları:*\n` +
      `/fiyat — Gram + ons altın fiyatı\n` +
      `/gram — Sadece gram altın fiyatı\n` +
      `/ons — Sadece ons altın fiyatı\n\n` +
      `💱 *Döviz Komutları:*\n` +
      `/doviz — EUR/USD, EUR/TRY, USD/TRY kurları\n` +
      `/usdtry — Dolar/TL kuru\n` +
      `/eurtry — Euro/TL kuru\n` +
      `/eurusd — Euro/Dolar kuru\n\n` +
      `🔔 *Bildirim Komutları:*\n` +
      `/abone — Otomatik bildirim ayarla\n` +
      `/durum — Abonelik durumunu gör\n` +
      `/iptal — Bildirimleri durdur\n` +
      `/yardim — Yardım`,
      { parse_mode: "Markdown" }
    );
  });

  bot.onText(/\/abone/, async (msg) => {
    const chatId = msg.chat.id;
    const sub = getSubscriber(chatId);
    const currentInfo = sub
      ? `\n\n⚙️ Mevcut ayarınız: *${INTERVALS[String(sub.intervalMinutes)]?.label ?? sub.intervalMinutes + " dakika"}*`
      : "";

    await bot!.sendMessage(
      chatId,
      `🔔 *Bildirim Sıklığını Seçin*${currentInfo}\n\nKaç dakikada bir gram altın fiyatı almak istiyorsunuz?`,
      {
        parse_mode: "Markdown",
        reply_markup: intervalKeyboard(),
      }
    );
  });

  bot.on("callback_query", async (query) => {
    if (!query.data || !query.message) return;
    const chatId = query.message.chat.id;
    const data = query.data;

    if (data === "interval_stop") {
      removeSubscriber(chatId);
      await bot!.answerCallbackQuery(query.id, { text: "Bildirimler durduruldu." });
      await bot!.editMessageText(
        "❌ *Bildirimler durduruldu.*\n\nTekrar başlatmak için /abone yazın.",
        {
          chat_id: chatId,
          message_id: query.message.message_id,
          parse_mode: "Markdown",
        }
      );
      return;
    }

    if (data.startsWith("interval_")) {
      const key = data.replace("interval_", "");
      const interval = INTERVALS[key];
      if (!interval) return;

      const status = setSubscriber(chatId, interval.minutes);
      await bot!.answerCallbackQuery(query.id, { text: `✅ ${interval.label} ayarlandı!` });

      await bot!.editMessageText(
        `✅ *Abonelik ${status === "new" ? "başlatıldı" : "güncellendi"}!*\n\n` +
        `⏰ Sıklık: *${interval.label}*\n\n` +
        `Şu an güncel fiyat gönderiliyor...`,
        {
          chat_id: chatId,
          message_id: query.message.message_id,
          parse_mode: "Markdown",
        }
      );

      await sendCurrentPrice(chatId);
    }
  });

  bot.onText(/\/iptal/, async (msg) => {
    const chatId = msg.chat.id;
    const removed = removeSubscriber(chatId);
    if (removed) {
      await bot!.sendMessage(chatId, `❌ Bildirimler durduruldu.\n\nTekrar başlatmak için /abone yazın.`);
    } else {
      await bot!.sendMessage(chatId, `ℹ️ Zaten abone değilsiniz. Abone olmak için /abone yazın.`);
    }
  });

  bot.onText(/\/fiyat/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Fiyat alınıyor...");
    try {
      const [price, rates] = await Promise.all([fetchGoldPrice(), fetchForexRates().catch(() => [])]);
      await bot!.editMessageText(formatPrice(price, rates as ForexRate[]), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "Fiyat alınamadı");
      await bot!.editMessageText("❌ Fiyat alınırken hata oluştu. Lütfen tekrar deneyin.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  bot.onText(/\/gram/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Fiyat alınıyor...");
    try {
      const price = await fetchGoldPrice();
      await bot!.editMessageText(formatGramOnly(price), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "Fiyat alınamadı");
      await bot!.editMessageText("❌ Fiyat alınırken hata oluştu. Lütfen tekrar deneyin.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  bot.onText(/\/ons/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Fiyat alınıyor...");
    try {
      const price = await fetchGoldPrice();
      await bot!.editMessageText(formatOnsOnly(price), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "Fiyat alınamadı");
      await bot!.editMessageText("❌ Fiyat alınırken hata oluştu. Lütfen tekrar deneyin.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  // Döviz komutları
  bot.onText(/\/doviz/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Kurlar alınıyor...");
    try {
      const rates = await fetchForexRates();
      await bot!.editMessageText(formatForex(rates), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "Döviz kuru alınamadı");
      await bot!.editMessageText("❌ Döviz kuru alınırken hata oluştu. Lütfen tekrar deneyin.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  bot.onText(/\/usdtry/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Kur alınıyor...");
    try {
      const rates = await fetchForexRates();
      const rate = rates.find((r) => r.pair === "USD/TRY");
      if (!rate) throw new Error("USD/TRY bulunamadı");
      await bot!.editMessageText(formatSingleForex(rate), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "USD/TRY alınamadı");
      await bot!.editMessageText("❌ USD/TRY kuru alınırken hata oluştu.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  bot.onText(/\/eurtry/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Kur alınıyor...");
    try {
      const rates = await fetchForexRates();
      const rate = rates.find((r) => r.pair === "EUR/TRY");
      if (!rate) throw new Error("EUR/TRY bulunamadı");
      await bot!.editMessageText(formatSingleForex(rate), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "EUR/TRY alınamadı");
      await bot!.editMessageText("❌ EUR/TRY kuru alınırken hata oluştu.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  bot.onText(/\/eurusd/, async (msg) => {
    const chatId = msg.chat.id;
    const loadingMsg = await bot!.sendMessage(chatId, "⏳ Kur alınıyor...");
    try {
      const rates = await fetchForexRates();
      const rate = rates.find((r) => r.pair === "EUR/USD");
      if (!rate) throw new Error("EUR/USD bulunamadı");
      await bot!.editMessageText(formatSingleForex(rate), {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "EUR/USD alınamadı");
      await bot!.editMessageText("❌ EUR/USD kuru alınırken hata oluştu.", {
        chat_id: chatId,
        message_id: loadingMsg.message_id,
      });
    }
  });

  bot.onText(/\/durum/, async (msg) => {
    const chatId = msg.chat.id;
    const sub = getSubscriber(chatId);
    const total = subscriberCount();
    if (sub) {
      const label = INTERVALS[String(sub.intervalMinutes)]?.label ?? `${sub.intervalMinutes} dakika`;
      const toTR = (d: Date) =>
        d.toLocaleTimeString("tr-TR", { timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit" });
      const last = sub.lastNotified ? toTR(sub.lastNotified) : null;
      const nextDate = sub.lastNotified
        ? new Date(sub.lastNotified.getTime() + sub.intervalMinutes * 60 * 1000)
        : new Date();
      const next = toTR(nextDate);
      await bot!.sendMessage(
        chatId,
        `📊 *Abonelik Durumunuz*\n\n` +
        `✅ Durum: *Aktif*\n` +
        `⏰ Sıklık: *${label}*\n` +
        `📨 Son bildirim: *${last ?? "Henüz gönderilmedi"}*\n` +
        `🔜 Sonraki bildirim: *${next}* civarı\n\n` +
        `👥 Toplam abone: *${total}*\n\n` +
        `Değiştirmek için /abone yazın.\nDudurmak için /iptal yazın.`,
        { parse_mode: "Markdown" }
      );
    } else {
      await bot!.sendMessage(
        chatId,
        `❌ *Aboneliğiniz yok.*\n\n👥 Şu an toplam *${total}* abone var.\n\nBildirim almak için /abone yazın.`,
        { parse_mode: "Markdown" }
      );
    }
  });

  bot.onText(/\/yardim/, async (msg) => {
    const chatId = msg.chat.id;
    await bot!.sendMessage(
      chatId,
      `🥇 *Altın & Döviz Fiyat Botu — Yardım*\n\n` +
      `📋 *Altın Komutları:*\n` +
      `/fiyat — Gram + ons altın fiyatı\n` +
      `/gram — Sadece gram altın fiyatı\n` +
      `/ons — Sadece ons altın fiyatı\n\n` +
      `💱 *Döviz Komutları:*\n` +
      `/doviz — EUR/USD, EUR/TRY, USD/TRY\n` +
      `/usdtry — Dolar/TL alış-satış\n` +
      `/eurtry — Euro/TL alış-satış\n` +
      `/eurusd — Euro/Dolar alış-satış\n\n` +
      `🔔 *Bildirim Komutları:*\n` +
      `/abone — Bildirim sıklığını seç (butonlu menü)\n` +
      `/durum — Abonelik durumunu gör\n` +
      `/iptal — Bildirimleri durdur\n` +
      `/yardim — Bu yardım mesajını göster\n\n` +
      `👥 Toplam abone: *${subscriberCount()}*\n` +
      `📡 Kaynak: altinkuru.net / TCMB`,
      { parse_mode: "Markdown" }
    );
  });

  bot.on("polling_error", (err) => {
    logger.error({ err: err.message }, "Telegram polling hatası");
  });

  cron.schedule("* * * * *", async () => {
    const due = getDueSubscribers();
    if (due.length === 0) return;

    logger.info({ count: due.length }, "Cron: bildirim gönderilecek aboneler");

    try {
      const [price, rates] = await Promise.all([fetchGoldPrice(), fetchForexRates().catch(() => [])]);

      await Promise.allSettled(
        due.map(async (sub) => {
          const label = INTERVALS[String(sub.intervalMinutes)]?.label;
          const message = formatPrice(price, rates as ForexRate[], label);
          try {
            await bot!.sendMessage(sub.chatId, message, { parse_mode: "Markdown" });
            markNotified(sub.chatId);
          } catch (err) {
            logger.warn({ chatId: sub.chatId, err: (err as Error).message }, "Mesaj gönderilemedi");
          }
        })
      );
    } catch (err) {
      logger.error({ err }, "Cron: fiyat alınamadı");
    }
  });

  logger.info("Cron job: dakikada bir kontrol aktif");
}

export function getBot(): TelegramBot | null {
  return bot;
}
