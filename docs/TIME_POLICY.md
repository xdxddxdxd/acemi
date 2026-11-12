# Süre politikası deneyi: 100 / 150

Dal `codex/time-policy`, notebook `notebooks/kaggle_time_policy.ipynb`.
Kaggle'a bu dosyayı içe alın; Internet ve yazma yetkili `GITHUB_TOKEN`
secret'ını açıp yeni oturumda Run All çalıştırın.

## Amaç ve tek değişken

Motor çekirdeği ve varsayılanlar değiştirilmedi. Yeni taraf
`NextIterationPct=100`, kontrol tarafı mevcut `NextIterationPct=150`.
Her iki tarafta `QuiescenceSEE=false`, Contempt=0, kitap kapalı,
Hash 16 MB ve Threads=1. Aynı tam commit'in iki ayrı checkout'u kullanılır.

Mevcut motor `kalan_süre < son_iterasyon_süresi * NextIterationPct / 100`
olduğunda yeni iterasyona başlamıyor. 100 ayarı daha az kalan süreyle yeni
derinliğe başlamaya izin veriyor; 100 ms/hamle sınırını kaldırmıyor.
Kesilmiş iterasyonun bazı adayları mevcut motor tarafından kullanılabildiğinden
daha çok iterasyon başlatmak daha iyi hamle veya daha yüksek puan garantisi değil.

## Kaggle akışı

1. Yeni kimlik: `time-policy-100vs150-100ms-100games-v1`. İlk çalıştırmadaki
   tam commit ve seçenekler protokole kaydedilip GitHub'a gönderilir.
   Devam ederken veri push'ları yerine kayıtlı kaynak SHA'sı kullanılır.
2. Tam doğruluk testleri yalnız Kaggle'da çalışır. Ardından süre sınırı olmayan
   depth-3 / 10 pozisyon aramaları: doğrulanmış `4068a04`, kontrol 150 ve aday 100.
   Her üçünün skor/hamle/derinlik/düğüm değerleri aynı olmalıdır: bu ayar
   yalnız süre sınırında etkili olmalı. Fark varsa maç başlatılmaz.
3. Aynı 10 pozisyonda 100 ms sınırlı teşhis: ilk tur 100 sonra 150;
   ikinci tur 150 sonra 100. Her pozisyonda temiz Searcher; derinlik üst sınırı 64.
   Skor, hamle, düğüm, tamamlanan/başlatılan derinlik, motor ve duvar süresi kaydedilir.
   Bunlar küçük betimleyici ölçümler; maç gücü kararı veya gerçek oyun TT'sinin
   tam temsili değildir. Matta erken dönüş ayrıca `mate` alanında görülebilir.
4. Kontroller geçerse **tek çağrıda 100 oyun, iki tarafa 100 ms/hamle**.
   50 renk değiştirmeli açılış çifti, Seed 1, concurrency 2, 400 ply üst sınırı,
   SPRT kapalı. Yeni/engine tarafı 100, eski/opponent tarafı 150 ayarıdır.
5. Ham sonuçlar, test ve teşhis günlükleri aynı dala gönderilir.

İki taraf zaman aşımı/çökme/geçersiz hamlede kaybeder; dahili hatalar ayrı
aborted kaydıdır. Zaman aşımı toleransı mevcut 1000 ms'dir.
Beraberlik politikası mevcut `claim_draw=True` olarak iki tarafta korunur.
SEE denemesinin etkisi, süre ayarı ve beraberlik politikası birbirine karıştırılmaz.

## Kayıt ve tekrar çalıştırma

`data/ab/<SESSION_ID>/protocol.json` kaynakları ve seçenekleri sabitler;
`validation/` testleri, sabit derinlik teşhislerini, dört zaman sınırlı ölçümü,
doğrulama aracının kaynak özetini ve dosya SHA-256 değerlerini tutar.
Tüm kontroller geçmeden maç başlamaz. Başarılı kontroller doğrulanıp atlanır;
başarısız/kesilmiş kontrol önce incelenmeli ve yeni SESSION_ID kullanılmalıdır.

Bitmiş 100 oyun tekrar oynanmaz. Kesilmiş maç otomatik tekrarlanmaz;
RETRY_INCOMPLETE yalnız eski Kaggle oturumu durdurulunca açılmalıdır.
Son hücre yalnız push'u tekrarlar, maç başlatmaz. Ham maçlar `data/runs/`
altında korunur. Önceki deneylerin kayıtları ve main değiştirilmez.

Başarı ölçütü yalnız bütçenin tamamını kullanmak değil: doğru hamle, tamamlanan
derinlik, teknik hatalar, toplam süre ve maç puanı birlikte incelenir.
100 oyun kesin küçük Elo farklarını göstermeyebilir. Sonuç alınana kadar
varsayılan `NextIterationPct=150` kalır.
