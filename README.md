# បម្លែងវីដេអូទៅអក្សរ

កម្មវិធី Streamlit សម្រាប់បម្លែងសំឡេងក្នុងវីដេអូ ឬឯកសារសំឡេងទៅជាអក្សរ។ វាបង្កើត subtitle មានពេលវេលា ហើយអាចទាញយកជា **TXT, SRT, STR, VTT** ឬ ZIP ដែលរួមបញ្ចូលទាំងអស់។

## អ្វីដែលវាធ្វើបាន

- គាំទ្រ MP4, MOV, MKV, AVI, WebM, MP3, WAV, M4A, AAC, OGG និង FLAC
- ជ្រើសភាសាខ្មែរ ឬឱ្យ Whisper ស្គាល់ភាសាដោយស្វ័យប្រវត្តិ
- បង្កើត SRT/STR និង VTT ដោយមាន timecode សម្រាប់ដាក់ subtitle
- ដំណើរការដោយ local Whisper; ឯកសាររបស់អ្នកមិនត្រូវផ្ញើទៅ API ខាងក្រៅទេ
- អាចជ្រើស CPU ឬ NVIDIA GPU (CUDA)

## ដំឡើង និងបើក

ត្រូវមាន Python 3.10 ឬថ្មីជាងនេះ។ បើក PowerShell នៅក្នុងថតគម្រោង ហើយរត់៖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m streamlit run main.py
```

បើ PowerShell មិនអនុញ្ញាតឱ្យ activate virtual environment សូមប្រើពាក្យបញ្ជានេះដោយផ្ទាល់៖

```powershell
.\.venv\Scripts\python.exe -m streamlit run main.py
```

លើកដំបូងដែលអ្នកជ្រើស model មួយ Faster-Whisper នឹងទាញយក model នោះ។ សម្រាប់ការបំប្លែងភាសាខ្មែរ យើងណែនាំ **Small** ឬ **Medium**។

> `STR` មិនមែនជានាមទ្រង់ទ្រាយ subtitle ស្តង់ដារទេ ប៉ុន្តែកម្មវិធីផ្ដល់វាជាច្បាប់ចម្លងនៃ SRT ដើម្បីឆបគ្នានឹងប្រព័ន្ធដែលទាមទារ extension `.str`។

## ដាក់ឲ្យប្រើសាធារណៈ

គម្រោងមាន [Dockerfile](Dockerfile) និង [render.yaml](render.yaml) រួចស្រេចសម្រាប់ deploy ជា Web App សាធារណៈនៅលើ Render។

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/langchhely-ui/MLK-Khmer-voice/tree/public-video-transcriber)

1. បញ្ចូលឯកសារគម្រោងទៅ GitHub repository របស់អ្នក។ កុំបញ្ចូល `.venv` ឬឯកសារសំឡេង/វីដេអូរបស់អ្នក។
2. ចូល Render ហើយជ្រើស **New → Blueprint**។ ភ្ជាប់ GitHub repository នោះ ហើយ Render នឹងស្គាល់ `render.yaml` ដោយស្វ័យប្រវត្តិ។
3. ជ្រើស plan **Standard ឬខ្ពស់ជាងនេះ**។ វាមាន 2 GB RAM ដែលសមស្របសម្រាប់ Whisper Small; Free និង Starter មាន 512 MB ប៉ុណ្ណោះ។ Free plan សម្រាប់សាកល្បងប៉ុណ្ណោះ ព្រោះវាបិទ service បន្ទាប់ពីមិនមានអ្នកប្រើ 15 នាទី។
4. បន្ទាប់ពី deploy រួច អ្នកនឹងទទួលបាន link `https://khmer-video-transcriber.onrender.com` (ឈ្មោះពិតអាចខុសតាម service ដែលមាន) ដែលអាចចែករំលែកឲ្យគ្រប់គ្នាប្រើ។
5. សម្រាប់ link ថេរផ្ទាល់ខ្លួន ដូចជា `https://transcribe.yourdomain.com` សូមទិញ/ប្រើ domain របស់អ្នក រួចបញ្ចូលវានៅ **Settings → Custom Domains** ក្នុង Render និងធ្វើតាម DNS records ដែល Render បង្ហាញ។ HTTPS certificate ត្រូវបានបង្កើត និងបន្តសុពលភាពដោយស្វ័យប្រវត្តិ។

Link មិនអាចធានា “អចិន្ត្រៃយ៍” ដោយគ្មានលក្ខខណ្ឌបានទេ៖ វានឹងនៅដំណើរការដរាបណាអ្នករក្សាគណនី hosting, បង់ plan ដែលជ្រើស និងបន្ត domain របស់អ្នក។
