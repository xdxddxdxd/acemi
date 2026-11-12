# Acemi kullanım rehberi

[← Proje ana sayfası](../README.md)

Bu rehber `main` dalındaki UCI motorunu ve ölçüm araçlarını anlatır.
Deney dallarındaki ek seçenekler ilgili deney belgesinde açıklanır.

## Motoru başlatma

Motor çekirdeği harici Python paketi gerektirmez. Depo kökünde:

```bash
python -u -m engine
```

CI Python 3.12 kullanır; kayıtlı Kaggle deneylerinde CPython 3.13 de kullanılmıştır.
Sanal ortam kullanıyorsanız UCI arayüzünde o ortamın Python yürütücüsünü seçin.

## Bir satranç arayüzüne bağlama

UCI destekleyen bir arayüzde program olarak Python yürütücüsünü, argüman
olarak `-u -m engine`, çalışma dizini olarak `acemi` depo kökünü belirtin.
Arayüz program/argüman alanlarını ayrı tutuyorsa `python -m engine` metnini
tek bir yürütülebilir dosya adı olarak vermeyin.

Python ve depo yolları farklı makinelerde değişir; gerektiğinde mutlak yol
kullanın. Motor kendi grafik tahtasını sağlamaz.

## UCI oturumu

Motor açıldıktan sonra komutları satır satır gönderin:

```text
uci
isready
ucinewgame
position startpos
go movetime 500
```

`uci` motor kimliğini ve seçenekleri, `isready` ise `readyok` yanıtını döndürür.
Arama bittiğinde seçilen hamle `bestmove` olarak gelir. `stop` aramayı durdurur;
`quit` oturumu kapatır. Sıralı komutları bir dosyadan çok hızlı gönderirken
`quit` komutunun devam eden aramayı iptal edeceğini dikkate alın.

Desteklenen `go` sınırları: `movetime`, `depth`, `nodes`, `wtime`, `btime`,
`winc`, `binc`, `movestogo` ve `infinite`. Süre, derinlik ve düğüm aramaları
worker üzerinden yürür; giriş döngüsü `isready` ve `stop` için açık kalır.
`info depth` son tamamlanan derinliği gösterir. Başlatılıp tamamlanmamış
iterasyon `info string attempted_depth` ile ayrıca bildirilir.

<a id="uci-secenekleri"></a>
## UCI seçenekleri

Seçenekler `setoption name <ad> value <değer>` ile ayarlanır. Aşağıdaki
varsayılanlar `main` dalının UCI oturumu içindir.

| Seçenek | Varsayılan | Açıklama |
| --- | --- | --- |
| `Hash` | `16` | Yaklaşık tablo kapasitesi, MB ayarı; aralık 1–4096. |
| `Threads` | `1` | Tek arama iş parçacığı; desteklenen değer 1. |
| `Seed` | `1` | Eşit kök hamlelerinde tekrarlanabilir seçim; 0–2147483647. |
| `NullMove`, `LMR`, `Killers` | `true` | Ana arama sezgiselleri. |
| `TTTwoContexts` | `true` | Aynı konum için iki ayrı tam beraberlik bağlamı saklama. |
| `EvalPackedBase` | `true` | Temel değerlendirmeyi aynı puanla paketli toplama. |
| `PVS`, `CheckExtension`, `LateMovePruning`, `QuiescenceSEE` | `false` | Deneysel arama/sıralama seçenekleri. |
| `OwnBook` | `false` | Polyglot açılış kitabını kullanma. |
| `BookFile` | `openings/book.bin` | Kitap yolu. |
| `EvalPassedPawns`, `EvalPawnStructure`, `EvalBishopPair`, `EvalKingSafety`, `EvalEndgameMate` | `false` | Deneysel değerlendirme terimleri. |
| `NextIterationPct` | `150` | Son iterasyon maliyetine göre yeni derinlik başlatma eşiği; 50–500. |
| `Contempt` | `0` | Üstün konumda beraberlik puanını değiştirme; 0–200, 0 kapalı. |

`Hash` bir Python giriş sayısı modelidir; sürecin gerçek RAM kullanımını tam
olarak bu MB değeriyle sınırlamaz. Skorun anlamını değiştiren geçerli seçenek
değişikliklerinde TT temizlenir. Her UCI oturumu kendi değerlendirme ayarını taşır.

Doğrudan Python API'sindeki `EvalFlags()` / `Searcher()` varsayılanları,
tarihsel araç uyumluluğu nedeniyle UCI varsayılanlarından farklı olabilir.
Açık bir yapılandırma için `evaluate(board, flags)` ve
`Searcher(eval_flags=flags)` kullanın.

## Açılış kitabı

Motor açıldıktan sonra:

```text
setoption name BookFile value openings/book.bin
setoption name OwnBook value true
```

Göreli `BookFile` yolu çalışma dizinine göre çözülür. GUI farklı bir dizinden
başlatıyorsa mutlak yol verin. Kitap, ilk 24 yarım hamlede yasal adaylar
arasından ağırlıklı seçim yapar; uygun kayıt bulunamazsa normal aramaya döner.
Karşılaştırma testlerinde kitap açıkça kapatılır.

- [acemi-64.txt](../openings/acemi-64.txt): sabit 64 hatlık test açılış kümesi.
- [book_seeds.txt](../openings/book_seeds.txt): kitap üretimi için 90 hat.
- [book.bin](../openings/book.bin): gönderilen Polyglot kitap dosyası.

Kaggle'da kitap üretme örneği; Stockfish yürütücüsünün yolu sisteme göre değişir:

```bash
python -m pip install -r requirements-tools.txt
python -m tools.bookgen --stockfish /path/to/stockfish --openings openings/book_seeds.txt --branches 90 --max-plies 18 --depth 12 --cp-window 40
```

## Kısa PC kontrolü

Araç/test bağımlılıklarını bir kez kurun:

```bash
python -m pip install -r requirements-tools.txt
```

Kısa, recursive arama veya maç başlatmayan yapılandırma kontrolleri:

```bash
python -m unittest tests.test_uci_configuration.UciConfigurationTests -q
```

Tam test paketi ve uzun aramalar için Kaggle/CI kullanın.

<a id="kaggle"></a>
## Kaggle, testler ve maçlar

Notebook'lar belirli kaynak commit'lerini ve protokolleri sabitler. Çalıştırmadan
önce ilgili belgeden doğru dalı/notebook'u seçin:

- [Sabit referans toplama](BASELINE.md)
- [Önce/sonra A/B](AB_100.md)
- [Paketli değerlendirme](PACKED_EVAL.md)
- [İki TT bağlamı](TT_TWO_CONTEXTS.md)
- [Süre politikası](TIME_POLICY.md)
- [Quiescence SEE](QUIESCENCE_SEE.md)
- [RootMateGuard — deney dalı](https://github.com/xdxddxdxd/acemi/blob/codex/root-mate-guard/docs/ROOT_MATE_GUARD.md)

Kaggle'da Internet'i açın. Sonuç yayınlayan notebook'lar için Add-ons → Secrets
altında `GITHUB_TOKEN` tanımlayın ve Contents yazma yetkisi sağlayın.
Tamamlanan kayıtlar tekrar oynatılmaz; kaynak veya ayar değiştiğinde yeni deney
kimliği kullanılır. Yarım koşuya devam etme kuralları her deney belgesindedir.

Kaggle/CI ortamında tam doğrulama:

```bash
python -m unittest discover -s tests -v
python -m tools.bench --depth 3
```

Kaggle'da bağımsız maç örneği; Stockfish'in sistemde erişilebilir olması gerekir:

```bash
python -m tools.match --games 100 --movetime-ms 500 --uci-elo 1500 --openings openings/acemi-64.txt
```

`--sprt` erken durdurma, `--seed` tekrarlanabilir seçim, `--concurrency` paralel
oyun sayısı, `--no-record` kalıcı kayıt yazmayan deneme içindir. Sabit protokollü
deneylerde ilgili notebook'un ayarlarını kullanın; farklı koşulları aynı sonuç
örneklemine karıştırmayın.

Maç kayıtları `data/runs/` altında PGN, hamle akışı, metadata, sonuç ve günlük
olarak tutulur. [Veri şeması](../AGENT_GUIDE.md), [analiz kimliği ve devam](ANALYSIS.md)
ve [araç modülleri](TOOLS.md) ayrıntıları açıklar.
