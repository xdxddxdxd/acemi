# RootMateGuard: erken matları azaltma adayı

Amaç, daha fazla kazanmak veya daha az kaybetmek. Bu adayın genel oyun gücünü
artırdığı henüz ölçülmedi; varsayılan `RootMateGuard=false` kalır.

## Değişiklik

Kök araması başlamadan önce, şah altında değilse sanal pas sonrası rakibin
bir hamlede mat edip edemeyeceği denetlenir. Tehdit varsa veya kök şah
altındaysa yasal kök hamleleri için aynı kesin mat kontrolü yapılır.
Önce saldıran taşı alma, mat hattını kapatma ve şah hamleleri denenir;
bu geometrik sıralama kendi başına güvenli hamle kanıtı sayılmaz.

Yalnız rakibe kesin mat veren hamleler, en az bir doğrulanmış alternatif
bulunursa elenir. Kısmi taramada bilinmeyen hamleler korunur, doğrulanmış
alternatifler öne alınır. Bütün hamleler kaybediyorsa liste korunur.
Bu yöntem yeni oluşabilecek bütün tehditleri veya daha uzun matları çözmez.
Beraberlik, pat, terfi, TT bağlam güvenliği ve değerlendirme ağırlıkları değişmez.
Hakemin gelecek hamle için beraberlik iddiasını da kabul etmesine karşı
temkinli davranılır: yarım hamle sayacı 98'e ulaşmışsa veya geri alınabilir
geçmişte herhangi bir konum tekrarlanmışsa guard elemesi bütünüyle atlanır.
Bu, olası beraberlik hamlesini yanlışlıkla kayıp diye elememek içindir.

Ön kontrol asıl toplam süre ve düğüm limitinin içindedir; kendisine %20 pay
ayrılır. Kontroller arasındaki bir hamle üretiminin maliyeti küçük süre
taşmalarına neden olabilir; bu işletim sistemi düzeyinde kesin zaman sınırı
değildir. Sanal pas/hamleler kesinti ve hatada `finally` ile geri alınır.
Guard düğümleri toplam düğüm sayısına dahildir. Tek kök hamlesi ve depth=0
yolunda kontrol atlanır. Seçenek değiştiğinde TT geçersizleştirilir.

## Kısa PC doğrulaması — 12 Kasım 2026

Kullanıcı kısa analiz/kontrolleri PC'de, yoğun testleri ve maçları Kaggle'da
istedi. Son 15 motor testi 0,851 saniyede geçti; iki kısa 100/500 ms araması dahil.
Kritik konumun iki rengi için bağımsız python-chess terminal oracle'ı ile
yasal mat kontrolü, kesintide tahta geri yükleme ve bütçe davranışı denetlendi.

FEN: `rnb2rk1/ppp2ppp/8/1N1p4/1b1PnB1q/P7/1P1NPPPP/R2QKB1R w KQ - 1 10`

Ayrı kısa karşılaştırmada iki tarafta TTTwoContexts ve EvalPackedBase açık:

- 100 ms kontrol: `a3b4`, tamamlanan depth 0, mat −1; `...Qxf2#` geliyor.
- 100 ms aday: `f4g3` (Bg3), depth 1, −32 cp; bir hamlede matı önlüyor.
- 500 ms kontrol: `f4g3`, depth 1, −32 cp.
- 500 ms aday: `f4g3`, depth 4, −14 cp.

Bunlar tek konumda, tek PC koşusunun gözlemleri. Süre/düğüm farkları genel
hız kazancı, doğru nihai skor veya Elo artışı kanıtı değildir. Maç oynanmadı.

## Kaggle'da çalıştırma

`codex/root-mate-guard` dalındaki `notebooks/kaggle_root_mate_guard.ipynb`
dosyasını Kaggle'a içe alın. Internet'i ve Contents yazma yetkili
`GITHUB_TOKEN` secret'ını açıp Run All çalıştırın. Notebook mevcut diğer
deneylerin kayıtlarını değiştirmez.

1. İlk kaynak commit'i dondurulur; aday/kontrol aynı commit'in ayrı temiz
   checkout'larıdır. Tek seçenek farkı RootMateGuard true/false.
2. **Tam test paketi yalnız Kaggle'da** çalışır. Kapalı sürümün 10 konumda
   sabit depth-3 hamle/skor/mat/derinlik/düğüm sonuçları, main `38b0722` ile
   aynı olmalıdır.
3. Açık/kapalı üçer normal ölçüm dönüşümlü çalışır. Kritik konum ayrıca
   100 ve 500 ms'de tekrarlanır; aday seçiminin rakibe bir hamlede mat
   vermediği bağımsız oracle ile kontrol edilir.
4. Aday kritik kontrolde mat yiyorsa veya sabit iş medyan süresi %10'dan
   fazla uzuyorsa maç atlanır. Bu maliyet kapısı güç kararı değildir.
5. Kontroller geçerse **iki tarafa 500 ms/hamle, 100 oyun**, 50 renk değişimli
   açılış çifti oynanır. Hash 16 MB, Threads 1, kitap/SPRT kapalı, Seed 11.
   TTTwoContexts/EvalPackedBase açık; SEE kapalı; süre eşiği 150.
   Her 10 oyun sonrası sonuçlar GitHub'a gönderilir.

Tamamlanan kontroller ve maç bölümleri içerik özetleriyle doğrulanıp atlanır;
yeniden oynanmaz. Başarısız/yarım ön kontrolde yeni SESSION_ID gerekir.
Yarım maç bölümünde eski Kaggle oturumunu durdurmadan RETRY_INCOMPLETE
açılmamalıdır. Son hücre yalnız yayınlar, maç başlatmaz.

100 oyun ilk taramadır. Kabul kararı yalnız bu tek pozisyona veya %50'nin
az üstünde bir puana dayanmaz; renk çiftleri, teknik hatalar, güven aralığı
ve gerekirse daha geniş açılışlarda teyit birlikte incelenir. Yeni varsayılan
ve main'e alma kararı notebook tarafından verilmez.
