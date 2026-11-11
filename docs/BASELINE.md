# Adım 1: karşılaştırılabilir referans kaydı

Amaç mevcut motor davranışını sabitlemek. Bu adım motorun oyun gücünü veya arama
algoritmasını değiştirmez. İlk referans kaynak commit'i:
`db058b344df8759810e957f11a58b4149055fe49` (0.8.2, artımlı değerlendirme geri alınmış).

## Kaggle

Sekiz geliştirme adımı Kaggle'da doğrulandı. Güncel notebook
`VALIDATION_LABEL="main-validation"` ile ana dalı yeniden doğrular. Referans,
396 testten geçen 8. adımın `2c3312b3b45dcb8cf354940fc1f6b52c788fb970`
commit'idir. Önceki adımların
GitHub'a gönderilmiş kayıtları değiştirilmez. UCI, TT ve ayar regresyonları güncel
test paketine dahildir; gerçek aramalar, tam paket ve benchmark Kaggle'da çalışır.
Maçlar varsayılan olarak kapalı kalır.

Pat, güvenlik sınırında mat/pat ve ufukta kale terfisi regresyonları tam pakete
dahildir; bu adım için ayrıca uzun oyun analizi veya maç çalıştırmak gerekmez.
Yeni analiz çıktı kuralları: [ANALYSIS.md](ANALYSIS.md).

Bu adım maç/analiz araçlarının modüllerini ayırır; motor kodunu değiştirmez.
`REQUIRE_IDENTICAL_SEARCH=True`. Konum/FEN/derinlik, skor/düğüm/hamleler
doğrulanmış 8. adımla aynı olmalıdır; fark çıkarsa
kayıtlar gönderilip notebook durur. Süre farkı arama eşitsizliği değildir.
`REQUIRE_IDENTICAL_ENGINE_TREE=True` motor dosyalarının ağacını da aynı tutar;
sonuç `session.json` içindeki `engine_tree_matches` alanına yazılır.
3. ve 6. adımlarda doğruluk düzeltmeleri nedeniyle eşitlik zorunlu değildi;
4–5. adımlarda ve 7–8. adımlarda zorunludur. Normal, profilsiz benchmark'ın
süre oranı tek koşunun gözlemidir; hız kazancı sonuçlar gelmeden varsayılmaz.

İlk 7. adım kaydı (`20261111T142955Z_aef1069f`) 382 test ve arama eşitliğini
doğruladı; süre 14,438→14,424 saniye ile yaklaşık %0,1 değişti. Anlamlı hız
kazanımı gösterilmedi. Profilli çağrılarda açmaz taraması 82567→61818 azaldı,
ancak tam `make_move`/`unmake_move` sayısı 271497 olarak kaldı. İkinci deneme,
yasal hamle sınamasındaki bu tam durum güncellemelerini kaldırır. Aramada
gerçekten seçilip incelenen hamleler yine normal make/unmake kullanır.

7b kaydı (`20261111T144401Z_61796702`) 387 test ve 10 konumda aynı aramayı
doğruladı. Aynı koşudaki süre 14,411→11,130 saniye (%22,8 azalma), hız
12055→15609 düğüm/saniye idi. Bu sonuç tek koşudur; Elo ölçümü değildir.
Modül ayrımının kapsamı ve uyumluluk kuralları: [TOOLS.md](TOOLS.md).

`RUN_SEARCH_PROFILES=False` 8. adımın varsayılanıdır; motor değişmediği için ek
profil koşusu gerekmez. `True` seçilirse normal benchmark bittikten sonra iki motor ağacı
için `PROFILE_DEPTH=3` düzeyinde ayrı cProfile kayıtları alır. Güncel
`tools.profile_search` aracı eski checkout'un motorunu ayrı Python sürecinde
yükler ve motor ağacını toplanan benchmark'a karşı doğrular. Çıktılar aynı
oturumun `profiles/reference.json`, `current.json`, günlükleri ve `comparison.log`
dosyalarıdır. Motor fonksiyonlarının primitive/toplam çağrıları, kendi/kümülatif
süreleri ve kaynak kimliği kaydedilir. Derinlik 3 profilli aramaların da skor,
düğüm ve hamleleri aynı olmak zorundadır. Profil süreleri enstrümantasyon yükü
içerir; hız oranı olarak kullanılmaz. Profil hücresi tekrarında üzerine yazılmaz;
yeni kayıt için toplama hücresiyle yeni oturum oluşturun. İstenirse bu ek teşhis
ilk ayar hücresinden kapatılabilir. Gerçek arama/profil yerel bilgisayarda başlatılmaz.

1. `main` dalındaki güncel `notebooks/kaggle_runner.ipynb` dosyasını
   Kaggle'a alın. İlk hücrede `GITHUB_BRANCH="main"` varsayılandır;
   sonuçlar bu dala gönderilir. Geliştirme dalı geçmiş kayıtlarıyla korunur.
   Kurulum hücresi eski Kaggle checkout'unu seçilen dala geçirir ve referans
   aracının varlığını testlerden önce denetler.
2. Internet'i açın ve `GITHUB_TOKEN` Kaggle Secret'ını tanımlayın. Token yalnızca
   GitHub yazma yetkili çalışma ortamında kullanılır; sonuç dosyalarına yazılmaz.
3. Hücreleri sırayla çalıştırın. `BASELINE_DEPTH=4`, `RUN_VALIDATION_MATCHES=False`
   başlangıç ayarlarıdır. Sabit kaynak ve güncel kaynak için tam test paketi ayrı
   çalışır; bu yüzden bu adım tek test çalıştırmasından uzun sürer.
4. Her kaynak için kayıt tamamlanınca GitHub'a push denenir. Hata olan testin özeti
   ve günlüğü de gönderilir, sonra notebook durur. Push hatasında kayıtlar Kaggle
   klasöründe kalır; en son hücreyi tekrar çalıştırın.
5. Başarılı iki kayıttan sonra karşılaştırma günlüğü ve `session.json` gönderilir.

Notebook eski artımlı eval A/B deneyine ait `accept_h1` şartını kullanmaz. İsteğe
bağlı kısa kontroller yalnızca `RUN_VALIDATION_MATCHES=True` ile çalışır:
`SELF_PLAY_GAMES=10` self-play, `STOCKFISH_GAMES=20` SF1500 ve aynı sayıda SF1320;
toplam 50 oyun. Sayılar ilk ayar hücresinden değiştirilebilir; renk değişimli
çiftler için pozitif çift sayılar kullanın. Varsayılan ayarda hiç maç oynanmaz.
Bu küçük örnekler hata yakalamak içindir; Elo artışını kanıtlamaz. Maç sonuçları
daha önceki gibi `data/runs/` altına yazılır.

### `No module named tools.baseline` hatası

Bu hata test başlamadan, Kaggle checkout'unda yeni aracın bulunmadığını gösterir.
GitHub içe aktarma ekranında dal seçmek, notebook içindeki eski `GITHUB_BRANCH`
ayarını değiştirmez. Güncel notebook'u geliştirme dalından yeniden içe aktarın;
ayarlar ve depo kurulumundan başlayarak hücreleri sırayla çalıştırın. Kurulum
çıktısında `main; tools/baseline.py found` görülmeli.

Maçlar, benchmark ve tam test paketi Kaggle'da çalıştırılır; yerel bilgisayarda
bu uzun kontrolleri başlatmak gerekmez.

## Dosyalar

Her oturum `data/baselines/<UTC>_<benzersiz-ek>/` altında saklanır:

- `reference/`: sabit commit'in test ve benchmark kaydı.
- `current/`: notebook'un çalıştırdığı güncel kaynak için aynı kayıt.
- `comparison.log`: iki benchmark'ın konum bazında karşılaştırması.
- `session.json`: sabit referans commit'i, güncel kod commit'i, derinlik ve eşitlik sonucu.
  Güncel kayıtlar `validation_label`, `protocol_matches`, `require_identical_search`,
  `comparison_returncode` ve `review_required` alanlarını da içerir. Geçersiz protokol
  veya karşılaştırma komutunun hatası, eşitlik ayarı kapalı olsa da notebook'u durdurur.

Her kaynak kaydında:

- `meta.json`: kaynak commit/ağaç kimlikleri, kaydedici sürümü, Python/işletim
  sistemi, bağımlılık sürümleri ve protokol.
- `tests.json`, `tests.log`: test sayısı, başarısız/hatalı/atlanmış test kimlikleri
  ve tam çıktı. Test sayısı günlük metninden tahmin edilmez; unittest sonucundan alınır.
- `bench.json`, `bench.log`: her FEN için skor, tamamlanan derinlik, düğüm,
  en iyi hamle ve süre; CPU/runtime bilgisi. Test başarısızsa benchmark atlanır.
- `results.json`, `SUMMARY.md`: aşamaların çıkış kodları ve genel durum.

Kayıt klasörü zaten varsa araç üzerine yazmaz. Referans kaynağında commit edilmemiş
motor/araç/test/açılış değişikliği varsa kayıt başlamaz. Eksik veya sıfır testli
bir çalıştırma başarılı sayılmaz. Başarısız benchmark sonuçları da saklanır.

## Komut satırı

Bu komutlar Kaggle terminalinde de kullanılabilir. Yerel bilgisayarda uzun test,
benchmark veya maç başlatılması gerekmez.

Temiz bir kaynak checkout'u için:

```bash
python -m tools.baseline --source-root ../acemi-reference --depth 4 --label step1-reference
```

Varsayılan çıktı yeni bir `data/baselines/` klasörüdür. `--out-dir` ile yeni bir
hedef verilebilir. `--expected-commit <tam-SHA>` kaynak HEAD'ini denetler.
Kaydedici ve kaynak farklı checkout'larda olabilir; testler ve benchmark kaynak
checkout'unda ayrı süreçlerde çalıştırılır.

Sonraki bir sürümü karşılaştırmak için aynı derinlikte yeni kayıt alın:

```bash
python -m tools.bench --compare <eski-kayit>/bench.json <yeni-kayit>/bench.json
```

Eksik/fazla/tekrarlı konumlar veya farklı FEN'ler eşit kabul edilmez. Yalnızca
aynı adlı konumların aynı skor vermesi yeterli değildir. İlk adımda arama
değişmediği için eşitlik beklenir. İleride kasıtlı bir arama/doğruluk düzeltmesi
skorları veya hamleleri değiştirebilir; o aşamada farkın nedeni değerlendirilir.

Süre oranı tek koşunun gözlemidir. Farklı CPU, Python veya arama sonuçları bir
hız kazanımı iddiasına dönüştürülmez. Sabit derinlik ölçümü Elo ölçümü değildir.
Ham kayıtlar incelenmeden performans ya da güç artışı sonucu çıkarılmaz.
