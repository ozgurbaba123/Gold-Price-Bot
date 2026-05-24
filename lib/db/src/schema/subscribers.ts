import { pgTable, bigint, integer, timestamp } from "drizzle-orm/pg-core";

export const subscribersTable = pgTable("subscribers", {
  chatId: bigint("chat_id", { mode: "number" }).primaryKey(),
  intervalMinutes: integer("interval_minutes").notNull(),
  lastNotified: timestamp("last_notified", { withTimezone: true }),
});

export type SubscriberRow = typeof subscribersTable.$inferSelect;
