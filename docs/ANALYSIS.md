# Analiz kimliği ve devam etme

`tools.analyze_games` yeni analizlerin `config.json` dosyasına
`analysis_configuration` ve onun SHA-256 özeti `analysis_fingerprint` alanlarını
yazar. Kimlik derinliği, Stockfish çalıştırılabilir dosyasının içeriğini,
Threads=1/Hash=64 ayarlarını, python-chess sürümünü, analiz kaynak dosyalarını
ve Syzygy WDL dosyalarının adlarını/içerik özetlerini kapsar. Tablo dosyaları
kimlik hazırlanırken bir defa okunur; çok büyük tablolarda bu işlem zaman alabilir.
Çalıştırma yolu, saat ve işçi sayısı kimliği değiştirmez.

Aynı kimlikle aynı `--out` klasörüne devam edilebilir. Ayar veya analiz kodu
değişirse araç eski `config.json` ve sonuçları değiştirmeden durur ve yeni
`--out` ister. Kimliği olmayan eski çıktıların yeni analizle devam ettirilmesi
de reddedilir. Eski klasörler `--aggregate-only` ve rapor aracıyla okunabilir;
bu, geçmiş sonuçların hangi ayarlarla üretildiğinin sonradan doğrulandığı anlamına gelmez.

Her oyun önbelleği kimlik taşır; dosya adı da kimliğe bağlıdır. JSON/payload
bozuksa oyun yeniden analiz edilir. Parça adları, `parts.json` ve parça girdileri
kimliğe bağlıdır. Farklı/eksik kimlikli cache veya parçalar yeni analizle
birleştirilemez. Dosya SHA-256 kontrolleri korunur. Rapor aracı da parça
kimliklerini ve dosya bütünlüğünü kontrol eder; raporda kimliği gösterir.
Ara cache atomik yazılır ve Git'e eklenmez.

Syzygy istenmişse eksik dizin/boş WDL kümesi hata verir. Yapılandırılmış tabloyu
açamayan worker Stockfish-only analize sessizce dönmez. Tabloda bulunmayan tekil
pozisyonlar için mevcut Stockfish etiketi kullanılmaya devam eder.
Kaggle indirme hücresi tabloyu hiç hazırlayamazsa `--syzygy` verilmez ve
Stockfish-only kimliği oluşur; daha sonra tablolar eklendiğinde yeni çıktı gerekir.

`notebooks/kaggle_analysis.ipynb` geliştirme dalını ve yeni
`ANALYSIS_DIR="data/analysis/step5"` klasörünü kullanır. İleride kimlik değişirse
bu yolu da değiştirin; eski klasörleri silmek gerekmez. 5. adımın doğrulaması
için normal `kaggle_runner.ipynb` yeterlidir; uzun analiz notebook'unu çalıştırma
zorunluluğu yoktur. Tam testler ve benchmark Kaggle'a aittir; maçlar kapalıdır.

Maç metadata'sındaki `engine_settings.opening_book` ve `opponent.opening_book`,
motorun ilan ettiği `OwnBook` varsayılanından ve sırayla uygulanan son seçenekten
üretilir. `book_file` aynı şekilde `BookFile` değerini kaydeder. Seçenek ilan
edilmemişse değer `null` olur. Bu alanlar kitap kullanım ayarını gösterir;
dosyanın başarıyla yüklendiğini veya her oyunda kitap hamlesi oynandığını kanıtlamaz.
Eski `data/runs/` kayıtları geriye dönük değiştirilmez.
