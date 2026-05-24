import { upsertToDb, deleteFromDb, updateLastNotifiedDb } from "./subscriberDb.js";

export interface Subscriber {
  chatId: number;
  intervalMinutes: number;
  lastNotified: Date | null;
}

const subscribers = new Map<number, Subscriber>();

export function loadSubscribers(list: Subscriber[]): void {
  for (const s of list) {
    subscribers.set(s.chatId, s);
  }
}

export function setSubscriber(chatId: number, intervalMinutes: number): "new" | "updated" {
  const existing = subscribers.get(chatId);
  subscribers.set(chatId, {
    chatId,
    intervalMinutes,
    lastNotified: existing?.lastNotified ?? null,
  });
  void upsertToDb(chatId, intervalMinutes);
  return existing ? "updated" : "new";
}

export function removeSubscriber(chatId: number): boolean {
  const removed = subscribers.delete(chatId);
  if (removed) void deleteFromDb(chatId);
  return removed;
}

export function getSubscriber(chatId: number): Subscriber | undefined {
  return subscribers.get(chatId);
}

export function isSubscriber(chatId: number): boolean {
  return subscribers.has(chatId);
}

export function getAllSubscribers(): Subscriber[] {
  return Array.from(subscribers.values());
}

export function subscriberCount(): number {
  return subscribers.size;
}

export function markNotified(chatId: number): void {
  const sub = subscribers.get(chatId);
  if (sub) {
    sub.lastNotified = new Date();
    void updateLastNotifiedDb(chatId);
  }
}

export function getDueSubscribers(): Subscriber[] {
  const now = new Date();
  return Array.from(subscribers.values()).filter((sub) => {
    if (!sub.lastNotified) return true;
    const elapsedMs = now.getTime() - sub.lastNotified.getTime();
    return elapsedMs >= sub.intervalMinutes * 60 * 1000;
  });
}
