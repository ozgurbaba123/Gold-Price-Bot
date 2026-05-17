import axios from "axios";
import * as cheerio from "cheerio";
import { logger } from "../lib/logger";

export interface GoldPrice {
  gramTL: number;
  alis: number;
  satis: number;
  change: number;
  changePercent: number;
  source: string;
  timestamp: Date;
}

let lastPrice: GoldPrice | null = null;

function parseTurkishNumber(s: string): number {
  return parseFloat(s.replace(/[^\d,]/g, "").replace(",", "."));
}

function buildResult(gramTL: number, alis: number, satis: number, source: string): GoldPrice {
  const prev = lastPrice?.gramTL ?? gramTL;
  const change = parseFloat((gramTL - prev).toFixed(2));
  const changePercent = parseFloat(prev > 0 ? (((gramTL - prev) / prev) * 100).toFixed(2) : "0");
  const result: GoldPrice = {
    gramTL: parseFloat(gramTL.toFixed(2)),
    alis: parseFloat(alis.toFixed(2)),
    satis: parseFloat(satis.toFixed(2)),
    change,
    changePercent,
    source,
    timestamp: new Date(),
  };
  lastPrice = result;
  return result;
}

async function fromHaremAltin(): Promise<GoldPrice> {
  const res = await axios.get("https://altinkuru.net/harem-altin/", {
    timeout: 10000,
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "tr-TR,tr;q=0.9",
    },
  });

  const $ = cheerio.load(res.data as string);

  let alis = 0;
  let satis = 0;

  $("table tbody tr").each((_i, row) => {
    if (alis > 0) return;
    const cells = $(row).find("td");
    const name = $(cells[0]).text().toLowerCase();
    if (
      name.includes("gram altın") ||
      (name.includes("gram") && name.includes("xau/try"))
    ) {
      const b = parseTurkishNumber($(cells[1]).text());
      const a = parseTurkishNumber($(cells[2]).text());
      if (b > 100 && a > 100) {
        alis = b;
        satis = a;
      }
    }
  });

  if (!alis || !satis) {
    const bidText = $("#bid-KULCEALTIN").text();
    const askText = $("#ask-KULCEALTIN").text();
    alis = parseTurkishNumber(bidText);
    satis = parseTurkishNumber(askText);
  }

  if (!alis || !satis || alis < 100) throw new Error("Harem sayfası: fiyat bulunamadı");

  const gramTL = (alis + satis) / 2;
  return buildResult(gramTL, alis, satis, "Harem Altın");
}

async function fromAltinkuruMain(): Promise<GoldPrice> {
  const res = await axios.get("https://altinkuru.net/", {
    timeout: 10000,
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "tr-TR,tr;q=0.9",
    },
  });

  const $ = cheerio.load(res.data as string);
  const alis = parseTurkishNumber($("#bid-KULCEALTIN").text());
  const satis = parseTurkishNumber($("#ask-KULCEALTIN").text());

  if (!alis || !satis || alis < 100) throw new Error("Ana sayfa: fiyat bulunamadı");

  const gramTL = (alis + satis) / 2;
  return buildResult(gramTL, alis, satis, "altinkuru.net");
}

async function fromCoinGecko(): Promise<GoldPrice> {
  const res = await axios.get(
    "https://api.coingecko.com/api/v3/simple/price?ids=tether-gold&vs_currencies=try",
    {
      timeout: 10000,
      headers: { "User-Agent": "Mozilla/5.0" },
    }
  );
  const ozTRY: number = res.data?.["tether-gold"]?.try;
  if (!ozTRY || ozTRY < 1000) throw new Error("CoinGecko: veri yok");

  const gramTL = parseFloat((ozTRY / 31.1035).toFixed(2));
  return buildResult(gramTL, gramTL, gramTL, "CoinGecko XAU/TRY");
}

export async function fetchGoldPrice(): Promise<GoldPrice> {
  const sources = [
    { name: "harem-altin", fn: fromHaremAltin },
    { name: "altinkuru-main", fn: fromAltinkuruMain },
    { name: "coingecko", fn: fromCoinGecko },
  ];

  for (const s of sources) {
    try {
      const result = await s.fn();
      logger.info({ source: s.name, gramTL: result.gramTL }, "Fiyat alındı");
      return result;
    } catch (err) {
      logger.warn({ source: s.name, err: (err as Error).message }, "Kaynak başarısız, sonraki deneniyor");
    }
  }

  throw new Error("Tüm kaynaklar başarısız oldu");
}

export function getLastPrice(): GoldPrice | null {
  return lastPrice;
}
