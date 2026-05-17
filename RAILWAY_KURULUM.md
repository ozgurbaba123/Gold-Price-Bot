# Railway'de Ücretsiz Bot Kurulumu

Railway'e deploy ederek botu Replit kapalıyken de 7/24 çalıştırabilirsiniz.

## Adımlar

### 1. GitHub'a yükleyin
Projeyi GitHub'a push etmeniz gerekiyor.
- https://github.com adresine gidin ve yeni bir **private** repo oluşturun
- Replit'te sol menüden **Git** sekmesine tıklayın
- "Connect to GitHub" ile GitHub hesabınızı bağlayın ve push edin

### 2. Railway hesabı açın
- https://railway.app adresine gidin
- "Start a New Project" → GitHub ile giriş yapın

### 3. Projeyi bağlayın
- "Deploy from GitHub repo" seçin
- Az önce oluşturduğunuz repo'yu seçin
- Railway Dockerfile'ı otomatik algılar

### 4. Environment variable ekleyin
Railway dashboard'da projenizi açın:
- **Variables** sekmesine tıklayın
- "Add Variable" ile şunu ekleyin:
  - Key: `TELEGRAM_BOT_TOKEN`
  - Value: Bot token'ınız (BotFather'dan aldığınız)

### 5. Deploy edin
- "Deploy" butonuna basın
- 2-3 dakika bekleyin — bot aktif olacak!

## Kontrol
Deploy tamamlandıktan sonra Railway loglarında şunu görmelisiniz:
```
Telegram botu başlatıldı
Cron job: her 5 dakikada bildirim aktif
Server listening
```

## Ücretsiz Plan Limitleri
Railway'in ücretsiz planı aylık **$5 kredi** verir.
Bu bot için aylık tahmini maliyet: **~$0.50-1.00** (çok düşük)
Yani ücretsiz kreditinizle aylarca çalışır!
