import axios from "axios";
import { logger } from "../lib/logger";

export interface GoldPrice {
  gramTL: number;
  change: number;
  changePercent: number;
  timestamp: Date;
}

let lastPrice: GoldPrice | null = null;

export async function fetchGoldPrice(): Promise<GoldPrice> {
  try {
    const response = await axios.get(
      "https://financialdata.in/api/commodities/XAU-TRY",
      { timeout: 8000 }
    );
    const data = response.data;
    const pricePerOz = parseFloat(data.price ?? data.last ?? data.close);
    const gramTL = pricePerOz / 31.1035;

    const prev = lastPrice?.gramTL ?? gramTL;
    const change = gramTL - prev;
    const changePercent = prev > 0 ? (change / prev) * 100 : 0;

    const result: GoldPrice = {
      gramTL: parseFloat(gramTL.toFixed(2)),
      change: parseFloat(change.toFixed(2)),
      changePercent: parseFloat(changePercent.toFixed(2)),
      timestamp: new Date(),
    };
    lastPrice = result;
    return result;
  } catch {
    logger.warn("financialdata.in failed, trying collectapi...");
  }

  try {
    const response = await axios.get(
      "https://api.collectapi.com/economy/goldPrice",
      {
        timeout: 8000,
        headers: {
          authorization: "apikey 0",
          "content-type": "application/json",
        },
      }
    );
    const items: Array<{ name: string; buying: string }> =
      response.data?.result ?? [];
    const gram = items.find((i) => i.name === "Gram Altın");
    if (gram) {
      const gramTL = parseFloat(gram.buying.replace(",", "."));
      const prev = lastPrice?.gramTL ?? gramTL;
      const change = gramTL - prev;
      const changePercent = prev > 0 ? (change / prev) * 100 : 0;
      const result: GoldPrice = {
        gramTL: parseFloat(gramTL.toFixed(2)),
        change: parseFloat(change.toFixed(2)),
        changePercent: parseFloat(changePercent.toFixed(2)),
        timestamp: new Date(),
      };
      lastPrice = result;
      return result;
    }
  } catch {
    logger.warn("collectapi failed, trying open.er-api.com fallback...");
  }

  const response = await axios.get(
    "https://open.er-api.com/v6/latest/XAU",
    { timeout: 10000 }
  );
  const tryRate: number = response.data?.rates?.TRY;
  if (!tryRate) throw new Error("Altın fiyatı alınamadı");
  const gramTL = parseFloat((tryRate / 31.1035).toFixed(2));
  const prev = lastPrice?.gramTL ?? gramTL;
  const change = parseFloat((gramTL - prev).toFixed(2));
  const changePercent = parseFloat(
    prev > 0 ? (((gramTL - prev) / prev) * 100).toFixed(2) : "0"
  );
  const result: GoldPrice = { gramTL, change, changePercent, timestamp: new Date() };
  lastPrice = result;
  return result;
}

export function getLastPrice(): GoldPrice | null {
  return lastPrice;
}
