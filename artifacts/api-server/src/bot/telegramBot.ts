import TelegramBot from "node-telegram-bot-api";
import cron from "node-cron";
import { fetchGoldPrice, getLastPrice, type GoldPrice } from "./goldPrice";
import {
  addSubscriber,
  removeSubscriber,
  isSubscriber,
  getAllSubscribers,
  subscriberCount,
} from "./subscribers";
import { logger } from "../lib/logger";

let bot: TelegramBot | null = null;

function formatTR(n: number): string {
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPrice(price: GoldPrice): string {
  const arrow = price.change > 0 ? "📈" : price.change < 0 ? "📉" : "➡️";
  const changeSign = price.change > 0 ? "+" : "";
  const time = price.timestamp.toLocaleTimeString("tr-TR", {
    timeZone: "Europe/Istanbul",
    hour: "2-digit",
    minute: "2-digit",
  });

  const hasSpread = Math.abs(price.alis - price.satis) > 0.01;

  return (
    `🥇 *Gram Altın Fiyatı*\n\n` +
    (hasSpread
      ? `📥 Alış: *${formatTR(price.alis)} ₺*\n` +
        `📤 Satış: *${formatTR(price.satis)} ₺*\n`
      : `💰 Fiyat: *${formatTR(price.gramTL)} ₺*\n`) +
    `${arrow} Değişim: *${changeSign}${formatTR(price.change)} ₺* (${changeSign}${price.changePercent.toFixed(2)}%)\n` +
    `🕐 ${time} — _${price.source}_`
  );
}

async function broadcast(message: string): Promise<void> {
  if (!bot) return;
  const subs = getAllSubscribers();
  const results = await Promise.allSettled(
    subs.map((chatId) =>
      bot!.sendMessage(chatId, message, { parse_mode: "Markdown" })
    )
  );
  const failed = results.filter((r) => r.status === "rejected").length;
  logger.info({ total: subs.length, failed }, "Broadcast done");
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
        `🥇 *Gram Altın Fiyat Botu*\n\n` +
        `Bu bot size anlık gram altın fiyatlarını Türk Lirası (₺) cinsinden bildirir.\n\n` +
        `📋 *Komutlar:*\n` +
        `/abone — Her 5 dakikada fiyat bildirimi al\n` +
        `/iptal — Bildirimleri durdur\n` +
        `/fiyat — Anlık fiyatı gör\n` +
        `/yardim — Bu mesajı göster`,
      { parse_mode: "Markdown" }
    );
  });

  bot.onText(/\/abone/, async (msg) => {
    const chatId = msg.chat.id;
    const isNew = addSubscriber(chatId);
    if (isNew) {
      await bot!.sendMessage(
        chatId,
        `✅ *Abonelik başarılı!*\n\nHer 5 dakikada bir gram altın fiyatını alacaksınız.\n\nİptal etmek için /iptal yazın.`,
        { parse_mode: "Markdown" }
      );
      try {
        const price = await fetchGoldPrice();
        await bot!.sendMessage(chatId, formatPrice(price), {
          parse_mode: "Markdown",
        });
      } catch {
        logger.warn("İlk fiyat gönderilemedi");
      }
    } else {
      await bot!.sendMessage(
        chatId,
        `ℹ️ Zaten abonesiniz. Fiyatlar her 5 dakikada gönderilecek.\n\nİptal etmek için /iptal yazın.`
      );
    }
  });

  bot.onText(/\/iptal/, async (msg) => {
    const chatId = msg.chat.id;
    const removed = removeSubscriber(chatId);
    if (removed) {
      await bot!.sendMessage(
        chatId,
        `❌ Aboneliğiniz iptal edildi.\n\nTekrar abone olmak için /abone yazın.`
      );
    } else {
      await bot!.sendMessage(
        chatId,
        `ℹ️ Zaten abone değilsiniz. Abone olmak için /abone yazın.`
      );
    }
  });

  bot.onText(/\/fiyat/, async (msg) => {
    const chatId = msg.chat.id;
    try {
      await bot!.sendMessage(chatId, "⏳ Fiyat alınıyor...");
      const price = await fetchGoldPrice();
      await bot!.sendMessage(chatId, formatPrice(price), {
        parse_mode: "Markdown",
      });
    } catch (err) {
      logger.error({ err }, "Fiyat alınamadı");
      await bot!.sendMessage(
        chatId,
        "❌ Fiyat alınırken hata oluştu. Lütfen tekrar deneyin."
      );
    }
  });

  bot.onText(/\/yardim/, async (msg) => {
    const chatId = msg.chat.id;
    await bot!.sendMessage(
      chatId,
      `🥇 *Gram Altın Fiyat Botu — Yardım*\n\n` +
        `📋 *Komutlar:*\n` +
        `/abone — Her 5 dakikada fiyat bildirimi al\n` +
        `/iptal — Bildirimleri durdur\n` +
        `/fiyat — Anlık fiyatı gör\n` +
        `/yardim — Bu mesajı göster\n\n` +
        `👥 Toplam abone: ${subscriberCount()}`,
      { parse_mode: "Markdown" }
    );
  });

  bot.on("polling_error", (err) => {
    logger.error({ err: err.message }, "Telegram polling hatası");
  });

  cron.schedule("*/5 * * * *", async () => {
    if (subscriberCount() === 0) return;
    logger.info("Cron: fiyat güncelleniyor ve gönderiliyor...");
    try {
      const price = await fetchGoldPrice();
      const message = formatPrice(price);
      await broadcast(message);
    } catch (err) {
      logger.error({ err }, "Cron: fiyat alınamadı");
    }
  });

  logger.info("Cron job: her 5 dakikada bildirim aktif");
}

export function getBot(): TelegramBot | null {
  return bot;
}
