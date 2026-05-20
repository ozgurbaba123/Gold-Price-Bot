# Railway'de 7/24 Bot Kurulumu

Railway'e deploy ederek botu Replit kapalıyken de 7/24 çalıştırabilirsiniz.

## Adımlar

### 1. GitHub'a Push Edin
- Replit'te sol menüden **Git** sekmesine tıklayın
- Değişiklikleri commit edip GitHub repo'nuza push edin

### 2. Railway Hesabı Açın
- https://railway.app adresine gidin
- "Start a New Project" → GitHub ile giriş yapın

### 3. Projeyi Bağlayın
- "Deploy from GitHub repo" seçin
- Repo'nuzu seçin
- Railway `Dockerfile`'ı otomatik algılar

### 4. Environment Variable Ekleyin
Railway dashboard'da projenizi açın:
- **Variables** sekmesine tıklayın
- Aşağıdaki değişkeni ekleyin:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan aldığınız token |

> `DATABASE_URL` gerekmez — aboneler bellekte tutulur, Railway yeniden başlatınca sıfırlanır.

### 5. Deploy Edin
- "Deploy" butonuna basın
- 2-3 dakika bekleyin — bot aktif olacak!

## Kontrol
Deploy tamamlandıktan sonra Railway loglarında şunu görmelisiniz:
```
Server listening
Telegram botu başlatıldı
Cron job: dakikada bir kontrol aktif
```

## Bot Komutları
| Komut | Açıklama |
|-------|----------|
| `/fiyat` | Gram + ons altın (alış/satış) |
| `/gram` | Gram altın |
| `/ons` | Ons altın |
| `/doviz` | EUR/USD · EUR/TRY · USD/TRY (alış/satış) |
| `/usdtry` | Dolar/TL kuru |
| `/eurtry` | Euro/TL kuru |
| `/eurusd` | Euro/Dolar kuru |
| `/abone` | Otomatik bildirim ayarla |
| `/iptal` | Bildirimleri durdur |
| `/durum` | Abonelik durumunu gör |

## Ücretsiz Plan
Railway'in ücretsiz planı aylık **$5 kredi** verir.
Bu bot için aylık tahmini maliyet: **~$0.50–1.00** → ücretsiz kreditinizle aylarca çalışır!
