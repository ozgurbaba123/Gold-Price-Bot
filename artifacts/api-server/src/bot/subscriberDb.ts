import { db } from "@workspace/db";
import { sql } from "drizzle-orm";
import { logger } from "../lib/logger.js";

type AnyDb = { execute: (query: unknown) => Promise<{ rows: Record<string, unknown>[] }> };

function getDb(): AnyDb | null {
  if (!db) {
    return null;
  }
  return db as unknown as AnyDb;
}

export async function initSubscriberTable(): Promise<void> {
  const d = getDb();
  if (!d) {
    logger.warn("DATABASE_URL yok — abonelikler sadece RAM'de tutulacak");
    return;
  }
  try {
    await d.execute(sql`
      CREATE TABLE IF NOT EXISTS subscribers (
        chat_id          BIGINT   PRIMARY KEY,
        interval_minutes INTEGER  NOT NULL,
        last_notified    TIMESTAMPTZ
      )
    `);
    logger.info("Subscribers tablosu hazir");
  } catch (err) {
    logger.error({ err }, "Subscribers tablosu olusturulamadi");
  }
}

export async function loadAllFromDb(): Promise<Array<{ chatId: number; intervalMinutes: number; lastNotified: Date | null }>> {
  const d = getDb();
  if (!d) return [];
  try {
    const result = await d.execute(sql`SELECT chat_id, interval_minutes, last_notified FROM subscribers`);
    return (result.rows ?? []).map((r) => ({
      chatId: Number(r["chat_id"]),
      intervalMinutes: Number(r["interval_minutes"]),
      lastNotified: r["last_notified"] ? new Date(r["last_notified"] as string) : null,
    }));
  } catch (err) {
    logger.error({ err }, "DB'den aboneler yuklenemedi");
    return [];
  }
}

export async function upsertToDb(chatId: number, intervalMinutes: number): Promise<void> {
  const d = getDb();
  if (!d) return;
  try {
    await d.execute(sql`
      INSERT INTO subscribers (chat_id, interval_minutes, last_notified)
      VALUES (${chatId}, ${intervalMinutes}, NULL)
      ON CONFLICT (chat_id) DO UPDATE SET interval_minutes = ${intervalMinutes}
    `);
  } catch (err) {
    logger.error({ err, chatId }, "DB upsert basarisiz");
  }
}

export async function deleteFromDb(chatId: number): Promise<void> {
  const d = getDb();
  if (!d) return;
  try {
    await d.execute(sql`DELETE FROM subscribers WHERE chat_id = ${chatId}`);
  } catch (err) {
    logger.error({ err, chatId }, "DB delete basarisiz");
  }
}

export async function updateLastNotifiedDb(chatId: number): Promise<void> {
  const d = getDb();
  if (!d) return;
  try {
    await d.execute(sql`UPDATE subscribers SET last_notified = NOW() WHERE chat_id = ${chatId}`);
  } catch (err) {
    logger.error({ err, chatId }, "DB last_notified guncellenemedi");
  }
}
