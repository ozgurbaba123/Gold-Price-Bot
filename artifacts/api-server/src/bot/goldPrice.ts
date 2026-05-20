import axios from "axios";
import * as cheerio from "cheerio";
import { logger } from "../lib/logger.js";

export interface GoldPrice {
  gramTL: number;
  alis: number;
  satis: number;
  onsTL: number;
  onsAlis: number;
  onsSatis: number;
  change: number;
  changePercent: number;
  source: string;
  timestamp: Date;
}

export interface ForexRate {
  pair: string;
  alis: number;
  satis: number;
  source: string;
  timestamp: Date;
}

let lastPrice: GoldPrice | null = null;

function parseTurkishNumber(s: string): number {
  return parseFloat(s.replace(/[^\d,]/g, "").replace(",", "."));
}

function buildResult(
  gramTL: number,
  alis: number,
  satis: number,
  onsTL: number,
  onsAlis: number,
  onsSatis: number,
  source: string
): GoldPrice {
  const prev = lastPrice?.gramTL ?? gramTL;
  const change = parseFloat((gramTL - prev).toFixed(2));
  const changePercent = parseFloat(prev > 0 ? (((gramTL - prev) / prev) * 100).toFixed(2) : "0");
  const result: GoldPrice = {
    gramTL: parseFloat(gramTL.toFixed(2)),
    alis: parseFloat(alis.toFixed(2)),
    satis: parseFloat(satis.toFixed(2)),
    onsTL: parseFloat(onsTL.toFixed(2)),
    onsAlis: parseFloat(onsAlis.toFixed(2)),
    onsSatis: parseFloat(onsSatis.toFixed(2)),
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
  let onsAlis = 0;
  let onsSatis = 0;

  $("table tbody tr").each((_i, row) => {
    const cells = $(row).find("td");
    const name = $(cells[0]).text().toLowerCase().trim();

    if (alis === 0 && (name.includes("gram altın") || (name.includes("gram") && name.includes("xau")))) {
      const b = parseTurkishNumber($(cells[1]).text());
      const a = parseTurkishNumber($(cells[2]).text());
      if (b > 100 && a > 100) {
        alis = b;
        satis = a;
      }
    }

    if (onsAlis === 0 && (name.includes("ons altın") || (name.includes("ons") && name.includes("xau")))) {
      const b = parseTurkishNumber($(cells[1]).text());
      const a = parseTurkishNumber($(cells[2]).text());
      if (b > 1000 && a > 1000) {
        onsAlis = b;
        onsSatis = a;
      }
    }
  });

  if (!alis || !satis) {
    alis = parseTurkishNumber($("#bid-KULCEALTIN").text());
    satis = parseTurkishNumber($("#ask-KULCEALTIN").text());
  }
  if (!onsAlis || !onsSatis) {
    onsAlis = parseTurkishNumber($("#bid-ONSALTIN").text());
    onsSatis = parseTurkishNumber($("#ask-ONSALTIN").text());
  }

  if (!alis || !satis || alis < 100) throw new Error("Harem sayfası: gram fiyat bulunamadı");

  const gramTL = (alis + satis) / 2;
  const onsTL = onsAlis && onsSatis ? (onsAlis + onsSatis) / 2 : gramTL * 31.1035;
  const finalOnsAlis = onsAlis || gramTL * 31.1035;
  const finalOnsSatis = onsSatis || gramTL * 31.1035;

  return buildResult(gramTL, alis, satis, onsTL, finalOnsAlis, finalOnsSatis, "Harem Altın");
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
  const onsAlis = parseTurkishNumber($("#bid-ONSALTIN").text());
  const onsSatis = parseTurkishNumber($("#ask-ONSALTIN").text());

  if (!alis || !satis || alis < 100) throw new Error("Ana sayfa: fiyat bulunamadı");

  const gramTL = (alis + satis) / 2;
  const onsTL = onsAlis && onsSatis ? (onsAlis + onsSatis) / 2 : gramTL * 31.1035;
  const finalOnsAlis = onsAlis || gramTL * 31.1035;
  const finalOnsSatis = onsSatis || gramTL * 31.1035;

  return buildResult(gramTL, alis, satis, onsTL, finalOnsAlis, finalOnsSatis, "altinkuru.net");
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
  const onsTL = parseFloat(ozTRY.toFixed(2));

  return buildResult(gramTL, gramTL, gramTL, onsTL, onsTL, onsTL, "CoinGecko XAU/TRY");
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
      logger.info({ source: s.name, gramTL: result.gramTL, onsTL: result.onsTL }, "Fiyat alındı");
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

async function fetchForexFromAltinkuru(): Promise<ForexRate[]> {
  const res = await axios.get("https://altinkuru.net/doviz/", {
    timeout: 10000,
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
      Accept: "text/html,application/xhtml+xml",
      "Accept-Language": "tr-TR,tr;q=0.9",
    },
  });

  const $ = cheerio.load(res.data as string);
  const rates: ForexRate[] = [];

  const targets: Record<string, string> = {
    USDTRY: "USD/TRY",
    EURTRY: "EUR/TRY",
    EURUSD: "EUR/USD",
  };

  for (const [id, pair] of Object.entries(targets)) {
    const alis = parseTurkishNumber($(`#bid-${id}`).text());
    const satis = parseTurkishNumber($(`#ask-${id}`).text());
    if (alis > 0 && satis > 0) {
      rates.push({ pair, alis, satis, source: "altinkuru.net", timestamp: new Date() });
    }
  }

  if (rates.length === 0) throw new Error("altinkuru doviz: kur bulunamadı");
  return rates;
}

async function fetchForexFromTCMB(): Promise<ForexRate[]> {
  const res = await axios.get("https://www.tcmb.gov.tr/kurlar/today.xml", {
    timeout: 10000,
    headers: { "User-Agent": "Mozilla/5.0" },
  });

  const $ = cheerio.load(res.data as string, { xmlMode: true });
  const rates: ForexRate[] = [];

  $("Currency").each((_i, el) => {
    const code = $(el).attr("CurrencyCode");
    const buying = parseFloat($(el).find("ForexBuying").text());
    const selling = parseFloat($(el).find("ForexSelling").text());

    if (code === "USD" && buying > 0 && selling > 0) {
      rates.push({ pair: "USD/TRY", alis: buying, satis: selling, source: "TCMB", timestamp: new Date() });
    }
    if (code === "EUR" && buying > 0 && selling > 0) {
      rates.push({ pair: "EUR/TRY", alis: buying, satis: selling, source: "TCMB", timestamp: new Date() });
    }
  });

  const usd = rates.find((r) => r.pair === "USD/TRY");
  const eur = rates.find((r) => r.pair === "EUR/TRY");
  if (usd && eur) {
    const eurusdAlis = parseFloat((eur.alis / usd.satis).toFixed(5));
    const eurusdSatis = parseFloat((eur.satis / usd.alis).toFixed(5));
    rates.push({ pair: "EUR/USD", alis: eurusdAlis, satis: eurusdSatis, source: "TCMB", timestamp: new Date() });
  }

  if (rates.length === 0) throw new Error("TCMB: kur bulunamadı");
  return rates;
}

async function fetchForexFromFrankfurter(): Promise<ForexRate[]> {
  const [usdtryRes, eurtryRes, eurusdRes] = await Promise.all([
    axios.get("https://api.frankfurter.app/latest?from=USD&to=TRY", { timeout: 10000 }),
    axios.get("https://api.frankfurter.app/latest?from=EUR&to=TRY", { timeout: 10000 }),
    axios.get("https://api.frankfurter.app/latest?from=EUR&to=USD", { timeout: 10000 }),
  ]);

  const usdtry: number = usdtryRes.data?.rates?.TRY;
  const eurtry: number = eurtryRes.data?.rates?.TRY;
  const eurusd: number = eurusdRes.data?.rates?.USD;

  if (!usdtry || !eurtry || !eurusd) throw new Error("Frankfurter: veri eksik");

  return [
    { pair: "USD/TRY", alis: parseFloat((usdtry * 0.998).toFixed(4)), satis: parseFloat((usdtry * 1.002).toFixed(4)), source: "Frankfurter", timestamp: new Date() },
    { pair: "EUR/TRY", alis: parseFloat((eurtry * 0.998).toFixed(4)), satis: parseFloat((eurtry * 1.002).toFixed(4)), source: "Frankfurter", timestamp: new Date() },
    { pair: "EUR/USD", alis: parseFloat((eurusd * 0.998).toFixed(5)), satis: parseFloat((eurusd * 1.002).toFixed(5)), source: "Frankfurter", timestamp: new Date() },
  ];
}

export async function fetchForexRates(): Promise<ForexRate[]> {
  const sources = [
    { name: "altinkuru-doviz", fn: fetchForexFromAltinkuru },
    { name: "tcmb", fn: fetchForexFromTCMB },
    { name: "frankfurter", fn: fetchForexFromFrankfurter },
  ];

  for (const s of sources) {
    try {
      const result = await s.fn();
      logger.info({ source: s.name, count: result.length }, "Döviz kurları alındı");
      return result;
    } catch (err) {
      logger.warn({ source: s.name, err: (err as Error).message }, "Döviz kaynağı başarısız");
    }
  }

  throw new Error("Tüm döviz kaynakları başarısız oldu");
}
