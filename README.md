# Acemi

Acemi, Python ile sıfırdan geliştirilen bir satranç motorudur. Öncelik sırası doğruluk, güç ve hızdır. Motor çekirdeği `engine/` altında standart kütüphane ile yazılır; `python-chess` yalnızca `tools/` içindeki araçlarda kullanılabilir.

## Aşama durumu

Şu an Aşama 0 (altyapı) hazırlanıyor. Motor henüz hamle üretmez veya gerçek maç oynamaz. `tools/demo_run.py`, yalnızca kayıt hattını denemek için açıkça sentetik bir örnek koşu üretir; bu kayıt güç ölçümü değildir.

## Dizinler

- `engine/`: satranç motoru ve değerlendirme arayüzü
- `tests/`: doğruluk ve taktik testleri
- `tools/`: maç, ölçüm ve veri kayıt araçları
- `notebooks/kaggle_runner.ipynb`: Kaggle'da kurulum, sentetik kayıt ve GitHub push akışı
- `data/`: sürümlü test verileri ve koşu indeksi
- `analysis/`: yalnızca analiz ajanının raporları

## Yerel sentetik kayıt

Python 3.10+ ile:

```powershell
python tools/demo_run.py
```

Komut `data/runs/` altında şema v1'e uygun örnek kayıt, `data/index.csv` satırı ve `data/positions/` girdisi oluşturur. Bu veriler sentetiktir.

## Kaggle hazırlığı

1. GitHub'da `acemi` adında public bir depo oluşturup varsayılan dalı `main` yapın ve bu proje dosyalarını yükleyin.
2. `notebooks/kaggle_runner.ipynb` dosyasını Kaggle'a notebook olarak ekleyin. Notebook ayarlarında Internet'i açın.
3. Kaggle **Add-ons → Secrets** bölümünde `GITHUB_TOKEN` adlı Secret oluşturun. Fine-grained token yalnızca bu depoya Contents: Read and write izni taşımalıdır.
4. Notebook'taki `GITHUB_REPO_URL` adresinin `https://github.com/xdxddxdxd/acemi.git` olduğunu doğrulayın.
5. Hücreleri sırayla çalıştırın. Aşama 0'da sentetik koşu kaydedilir ve `data/` değişiklikleri push edilir. Motor ve Stockfish maçları sonraki aşamalarda eklenecektir.

Token hiçbir dosyaya yazılmaz veya hücre çıktısına basılmaz. Notebook push hatasında token'ı yeniden istemek yerine hatanın token içermeyen Git mesajını gösterir.

## Araç bağımlılığı

`python-chess` yalnızca araçlar içindir; motor çekirdeğinin bağımlılığı değildir. Yerelde araçları kurmak için `python -m pip install -r requirements-tools.txt` kullanın.

## Veri ve analiz

Veri alanları ve analiz ajanının kuralları için [AGENT_GUIDE.md](AGENT_GUIDE.md) dosyasına bakın. Her veri dosyası `schema_version` taşır. Gerçek test sonuçları ile sentetik demo kayıtlarını karıştırmayın.
