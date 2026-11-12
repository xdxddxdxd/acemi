# Temel değerlendirme toplamasını hızlandırma adayı

Dal: `codex/packed-eval`. Notebook: `notebooks/kaggle_packed_eval.ipynb`.
Kaggle'a bu daldan içe alıp Internet ve Contents yazma yetkili GITHUB_TOKEN
secret'ını açın; Run All çalıştırın. Bilgisayarda gerçek arama/maç başlatılmaz.

## Aday

`EvalPackedBase` varsayılan kapalıdır. Malzeme, kare puanı ve ham oyun evresi
önceden hesaplanmış tek tamsayıda ayrı alanlarda tutulur. Her taş için bir
tamsayı toplaması yapılır; sonunda üç alan tam olarak ayrılır. Pozisyonun
puanı ve değerlendirme terimleri değişmez. Terfilerde evre toplamı sonradan
24'e sınırlanır; negatif puanlar ve renk simetrisi korunur.

Alanlar 20 bit: 64 kareli bir FEN'deki en yoğun terfili konumda bile MG/EG
toplamı ±524.288 sınırının çok altındadır. Ayrıştırma işaretli taşıma/ödünç
durumlarını iki puan alanına eklenen sabit ile düzeltir.

Bu bir artımlı Board önbelleği değildir. Hamle yapma/geri alma ve null-move
yoluna yeni işlem eklemez. Önceki artımlı denemenin depth-4 kayıtları aynı
150.018 düğümde 9,942 / 10,048 saniye göstermişti; o tek eski ölçümün yöntemi
kesin olarak dışladığı iddia edilmez. Yeni küçük aday ayrıca ölçülür.

## Sabitler ve kontroller

- Her iki tarafta **TTTwoContexts=true**, SEE=false, NextIterationPct=150,
  Hash=16, Threads=1, OwnBook=false. Beraberlik politikası değişmez.
- Aday/kontrol aynı tam kaynak commit'ini kullanır; tek fark EvalPackedBase.
- Referans `b22b8597dcdf40fa632d9585cd4901c87d97b306`: TT'nin açık olduğu main.
- Önce tüm testler Kaggle'da. Kısa testler işaretli alanları, yoğun terfileri,
  diğer 32 değerlendirme seçeneği birleşimini ve ayar değişiminde TT temizliğini
  sınar. Uzun Kaggle testleri yasal hamle akışları, null/undo/FEN yükleme ve
  rok/geçerken alma/terfi konumlarında sabit işli arama eşdeğerliğini kontrol eder.
- Depth-4 / 10 pozisyonda main referansı bir kez, her politika üç kez ölçülür.
  Sıra düz/paketli, paketli/düz, düz/paketli. Normal Searcher kullanılır;
  sayaç/profil ek yükü yoktur. Skor, hamle, derinlik, düğüm, mat ve başlatılan
  derinlik bütün geçişlerde aynı olmalıdır.
- Paketli medyan arama süresi en az %2 kısa ise **100 ms / tek toplu 100 maç**
  başlar; aksi halde maçlar atlanır, ölçümler GitHub'a gönderilir.
  Bu pratik eşik küçük zaman gürültüsünü elemek içindir; üç geçiş istatistiksel
  hız veya Elo kanıtı değildir. Aynı aramanın zaman sınırında farklı derinliğe
  ulaşması, maçta farklı hamleler üretmesini sağlayabilir.

## Kayıt ve devam

`data/ab/packed-eval-100ms-100games-v1/` altında protokol, validation logları,
yedi benchmark JSON'u, hash manifest'i ve eligibility.json tutulur.
Tamamlanmış ön kontroller içerik özetleri ve karar yeniden hesaplanarak doğrulanır;
tekrarlanmaz. Hazırlık ve ön kontrol ayrı Python süreçlerindedir, Kaggle kernel'ının
eski tools/engine importları kullanılmaz.

Başarısız/yarım ön kontrolde logları inceleyip yeni SESSION_ID kullanın.
Kesilmiş maçta önce eski oturumu durdurup RETRY_INCOMPLETE=True ile devam edin.
Tamamlanmış 100 maç yeniden oynanmaz. Son hücre yalnız yayınlamayı tekrarlar.
Yeni aday main'e alınmamıştır; sonuçlar sonradan değerlendirilir.
