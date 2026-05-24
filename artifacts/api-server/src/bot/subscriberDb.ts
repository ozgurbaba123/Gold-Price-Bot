import pg from "pg";
import { logger } from "../lib/logger.js";

const { Pool } = pg;

let pool: InstanceType<typeof Pool> | null = null;

function getPool(): InstanceType<typeof Pool> | null {
  if (!process.env["DATABASE_URL"]) return null;
  if (!pool) pool = new Pool({ connectionString: process.env["DATABASE_URL"] });
  return pool;
}

export async function initSubscriberTable(): Promise<void> {
  const p = getPool();
  if (!p) {
    logger.warn("DATABASE_URL yok — abonelikler sadece RAM'de tutulacak");
    return;
  }
  try {
    await p.query(`
      CREATE TABLE IF NOT EXISTS subscribers (
        chat_id   BIGINT  PRIMARY KEY,
        interval_minutes INTEGER NOT NULL,
        last_notified    TIMESTAMPTZ
      )
    `);
    logger.info("Subscribers tablosu hazır");
  } catch (err) {
    logger.error({ err }, "Subscribers tablosu oluşturulamadı");
  }
}

export async function loadAllFromDb(): Promise<Array<{ chatId: number; intervalMinutes: number; lastNotified: Date | null }>> {
  const p = getPool();
  if (!p) return [];
  try {
    const res = await p.query("SELECT chat_id, interval_minutes, last_notified FROM subscribers");
    return res.rows.map((r) => ({
      chatId: Number(r.chat_id),
      intervalMinutes: Number(r.interval_minutes),
      lastNotified: r.last_notified ? new Date(r.last_notified) : null,
    }));
  } catch (err) {
    logger.error({ err }, "DB'den aboneler yüklenemedi");
    return [];
  }
}

export async function upsertToDb(chatId: number, intervalMinutes: number): Promise<void> {
  const p = getPool();
  if (!p) return;
  try {
    await p.query(
      `INSERT INTO subscribers (chat_id, interval_minutes, last_notified)
       VALUES ($1, $2, NULL)
       ON CONFLICT (chat_id) DO UPDATE SET interval_minutes = $2`,
      [chatId, intervalMinutes]
    );
  } catch (err) {
    logger.error({ err, chatId }, "DB upsert başarısız");
  }
}

export async function deleteFromDb(chatId: number): Promise<void> {
  const p = getPool();
  if (!p) return;
  try {
    await p.query("DELETE FROM subscribers WHERE chat_id = $1", [chatId]);
  } catch (err) {
    logger.error({ err, chatId }, "DB delete başarısız");
  }
}

export async function updateLastNotifiedDb(chatId: number): Promise<void> {
  const p = getPool();
  if (!p) return;
  try {
    await p.query("UPDATE subscribers SET last_notified = NOW() WHERE chat_id = $1", [chatId]);
  } catch (err) {
    logger.error({ err, chatId }, "DB last_notified güncellenemedi");
  }
}
