import TelegramBot from "node-telegram-bot-api";
import cron from "node-cron";
import { fetchGoldPrice, type GoldPrice } from "./goldPrice";
import {
  setSubscriber,
  removeSubscriber,
  getSubscriber,
  getDueSubscribers,
  markNotified,
  subscriberCount,
} from "./subscribers";
import { logger } from "../lib/logger";

let bot: TelegramBot | null = null;

const INTERVALS: Record<string, { label: string; minutes: number }> = {
  "5":  { label: "Her 5 dakika",  minutes: 5  },
  "15": { label: "Her 15 dakika", minutes: 15 },
  "30": { label: "Her 30 dakika", minutes: 30 },
  "60": { label: "Her 1 saat",    minutes: 60 },
};

function formatTR(n: number): string {
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatTime(timestamp: Date): string {
  return timestamp.toLocaleTimeString("tr-TR", {
    timeZone: "Europe/Istanbul",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPrice(price: GoldPrice, intervalLabel?: string): string {
  const arrow = price.change > 0 ? "📈" : price.change < 0 ? "📉" : "➡️";
  const changeSign = price.change > 0 ? "+" : "";
  const time = formatTime(price.timestamp);
  const hasGramSpread = Math.abs(price.alis - price.satis) > 0.01;
  const hasOnsSpread = Math.abs(price.onsAlis - price.onsSatis) > 0.01;

  return (
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
      : `💰 Fiyat: *${formatTR(price.onsTL)} ₺*\n`) +
    `\n🕐 ${time}` +
    (intervalLabel ? ` — _${intervalLabel}_` : ` — _${price.source}_`)
  );
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
    const price = await fetchGoldPrice();
    await bot.sendMessage(chatId, formatPrice(price), { parse_mode: "Markdown" });
  } catch {
    logger.warn({ chatId }, "İlk fiyat gönderilemedi");
  }
}

export function initBot(): void {
  const token = process.env["TELEGRAM_BOT_TOKEN"];
  if (!token) {
    logger.error("TELEGRAM_BOT_TOKEN eksik — bot başlatılmıyor");
    return;
  }

  bot = new TelegramBot(token, { polling: true });
  logger.info("Telegram botu başlatıldı");

  bot.onText(/\/start/, async (msg) => {
    const chatId = msg.chat.id;
    const firstName = msg.from?.first_name ?? "Kullanıcı";
    await bot!.sendMessage(
      chatId,
      `Merhaba ${firstName}! 👋\n\n` +
      `🥇 *Altın Fiyat Botu*\n\n` +
      `Harem Altın'dan canlı gram ve ons altın fiyatlarını Türk Lirası cinsinden bildirir.\n\n` +
      `📋 *Komutlar:*\n` +
      `/fiyat — Gram + ons altın fiyatı\n` +
      `/gram — Sadece gram altın fiyatı\n` +
      `/ons — Sadece ons altın fiyatı\n` +
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
      const price = await fetchGoldPrice();
      await bot!.editMessageText(formatPrice(price), {
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

  bot.onText(/\/durum/, async (msg) => {
    const chatId = msg.chat.id;
    const sub = getSubscriber(chatId);
    if (sub) {
      const label = INTERVALS[String(sub.intervalMinutes)]?.label ?? `${sub.intervalMinutes} dakika`;
      const last = sub.lastNotified
        ? sub.lastNotified.toLocaleTimeString("tr-TR", { timeZone: "Europe/Istanbul", hour: "2-digit", minute: "2-digit" })
        : "Henüz gönderilmedi";
      await bot!.sendMessage(
        chatId,
        `📊 *Abonelik Durumunuz*\n\n` +
        `✅ Durum: Aktif\n` +
        `⏰ Sıklık: *${label}*\n` +
        `📨 Son bildirim: ${last}\n\n` +
        `Değiştirmek için /abone yazın.\nDudurmak için /iptal yazın.`,
        { parse_mode: "Markdown" }
      );
    } else {
      await bot!.sendMessage(
        chatId,
        `❌ *Aboneliğiniz yok.*\n\nBildirim almak için /abone yazın.`,
        { parse_mode: "Markdown" }
      );
    }
  });

  bot.onText(/\/yardim/, async (msg) => {
    const chatId = msg.chat.id;
    await bot!.sendMessage(
      chatId,
      `🥇 *Altın Fiyat Botu — Yardım*\n\n` +
      `📋 *Komutlar:*\n` +
      `/fiyat — Gram + ons altın fiyatı\n` +
      `/gram — Sadece gram altın fiyatı\n` +
      `/ons — Sadece ons altın fiyatı\n` +
      `/abone — Bildirim sıklığını seç (butonlu menü)\n` +
      `/durum — Abonelik durumunu gör\n` +
      `/iptal — Bildirimleri durdur\n` +
      `/yardim — Bu yardım mesajını göster\n\n` +
      `👥 Toplam abone: *${subscriberCount()}*\n` +
      `📡 Kaynak: Harem Altın (altinkuru.net)`,
      { parse_mode: "Markdown" }
    );
  });

  bot.on("polling_error", (err) => {
    logger.error({ err: err.message }, "Telegram polling hatası");
  });

  // Dakikada bir çalışır, her kullanıcının kendi intervaline göre bildirim gönderir
  cron.schedule("* * * * *", async () => {
    const due = getDueSubscribers();
    if (due.length === 0) return;

    logger.info({ count: due.length }, "Cron: bildirim gönderilecek aboneler");

    try {
      const price = await fetchGoldPrice();

      await Promise.allSettled(
        due.map(async (sub) => {
          const label = INTERVALS[String(sub.intervalMinutes)]?.label;
          const message = formatPrice(price, label);
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
