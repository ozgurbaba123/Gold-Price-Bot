const subscribers = new Set<number>();

export function addSubscriber(chatId: number): boolean {
  if (subscribers.has(chatId)) return false;
  subscribers.add(chatId);
  return true;
}

export function removeSubscriber(chatId: number): boolean {
  return subscribers.delete(chatId);
}

export function isSubscriber(chatId: number): boolean {
  return subscribers.has(chatId);
}

export function getAllSubscribers(): number[] {
  return Array.from(subscribers);
}

export function subscriberCount(): number {
  return subscribers.size;
}
