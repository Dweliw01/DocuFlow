# Document Digitization MVP - Phase 1

AI-powered document categorization service that organizes bulk PDF uploads automatically.

## Features

- 📤 **Bulk PDF Upload** - Process up to 100 files at once
- 🔍 **OCR Text Extraction** - Uses Tesseract OCR (free, 85-90% accuracy)
- 🤖 **AI Categorization** - Claude Haiku intelligently categorizes into 9 document types
- 📁 **Automatic Organization** - Creates organized folder structure by category
- 📊 **Processing Logs** - Detailed logs with confidence scores and statistics
- ⬇️ **ZIP Download** - Get all organized documents in one click
- ⚡ **Real-time Progress** - Watch documents process live with progress bar

## Document Categories

- Invoice
- Contract
- Receipt
- Legal Document
- HR Document
- Tax Document
- Financial Statement
- Correspondence
- Other

## Prerequisites

Before you begin, ensure you have:

- **Python 3.11 or higher** - [Download Python](https://www.python.org/downloads/)
- **Tesseract OCR** - Free OCR engine (installation instructions below)
- **Poppler** - PDF to image converter (installation instructions below)
- **Anthropic API Key** - [Get your key](https://console.anthropic.com/)

## Installation

### Step 1: Install System Dependencies (Windows)

#### Install Tesseract OCR

1. Download the Tesseract installer:
   - Go to: https://github.com/UB-Mannheim/tesseract/wiki
   - Download the latest installer (e.g., `tesseract-ocr-w64-setup-5.3.3.exe`)

2. Run the installer:
   - Use default settings
   - Note the installation path (usually `C:\Program Files\Tesseract-OCR`)

3. Add Tesseract to your PATH:
   - Open System Properties → Environment Variables
   - Under "System Variables", find "Path" and click Edit
   - Click New and add: `C:\Program Files\Tesseract-OCR`
   - Click OK on all dialogs

4. Verify installation:
   ```bash
   tesseract --version
   ```
   You should see version information.

#### Install Poppler

1. Download Poppler for Windows:
   - Go to: https://github.com/oschwartz10612/poppler-windows/releases
   - Download the latest release (e.g., `Release-23.11.0-0.zip`)

2. Extract the ZIP file:
   - Extract to `C:\Program Files\poppler` (or any location)

3. Add Poppler to your PATH:
   - Open System Properties → Environment Variables
   - Under "System Variables", find "Path" and click Edit
   - Click New and add: `C:\Program Files\poppler\Library\bin`
   - Click OK on all dialogs

4. Verify installation:
   ```bash
   pdftoppm -h
   ```
   You should see help information.

### Step 2: Set Up Python Environment

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   ```

2. **Activate the virtual environment**:
   ```bash
   # Windows
   venv\Scripts\activate

   # You should see (venv) in your terminal prompt
   ```

3. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Step 3: Configure Environment Variables

1. **Copy the example environment file**:
   ```bash
   copy .env.example .env
   ```

2. **Edit `.env` and add your Anthropic API key**:
   - Open `.env` in a text editor
   - Replace `sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx` with your actual API key
   - Save the file

   Example `.env`:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
   USE_GOOGLE_VISION=false
   UPLOAD_DIR=./storage/uploads
   PROCESSED_DIR=./storage/processed
   LOG_DIR=./storage/logs
   MAX_FILE_SIZE=50
   ALLOWED_EXTENSIONS=pdf
   MAX_CONCURRENT_PROCESSING=5
   HOST=0.0.0.0
   PORT=8000
   ```

## Running the Application

1. **Make sure your virtual environment is activated**:
   ```bash
   venv\Scripts\activate
   ```

2. **Start the server**:
   ```bash
   python backend/main.py
   ```

3. **Open your browser** to:
   ```
   http://localhost:8000
   ```

4. **You should see**:
   - Welcome screen with upload interface
   - Check the terminal for startup confirmation:
     ```
     ============================================================
     📄 Document Digitization MVP
     ============================================================
     🌐 Server: http://0.0.0.0:8000
     📚 API Docs: http://0.0.0.0:8000/docs
     🤖 AI: Claude Haiku
     👁 OCR: Tesseract (free)
     📁 Max file size: 50MB
     ⚡ Concurrent processing: 5
     ============================================================
     ```

## Using the Application

### Upload and Process Documents

1. **Select files**:
   - Drag and drop PDF files onto the upload area, OR
   - Click "Browse Files" to select from your computer

2. **Review selected files**:
   - Check the file list
   - Remove any unwanted files with "Clear All"

3. **Process documents**:
   - Click "Process Documents"
   - Watch real-time progress as each document is processed

4. **Download results**:
   - When complete, click "Download Organized Documents"
   - You'll get a ZIP file with organized folders and a processing log

### Output Structure

Your downloaded ZIP will contain:

```
batch_20240115_143022/
├── Invoice/
│   ├── [Invoice] invoice_001.pdf
│   └── [Invoice] invoice_002.pdf
├── Contract/
│   └── [Contract] service_agreement.pdf
├── Receipt/
│   └── [Receipt] purchase_receipt.pdf
├── Other/
│   └── [Other] unknown_doc.pdf
└── PROCESSING_LOG.txt          # Detailed processing report
```

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

- `POST /api/upload` - Upload PDF files
- `GET /api/status/{batch_id}` - Check processing status
- `GET /api/download/{batch_id}` - Download organized results
- `GET /api/health` - Health check

## Cost Structure

### MVP (Current Setup)

- **OCR**: FREE (Tesseract)
- **AI Categorization**: ~$0.30 per 1,000 documents (Claude Haiku)
- **Total**: ~$0.30 per 1,000 documents

### After Upgrade to Google Vision (Optional)

When you have paying customers and want 99% OCR accuracy:

1. Install Google Cloud Vision:
   ```bash
   pip install google-cloud-vision
   ```

2. Update `.env`:
   ```bash
   USE_GOOGLE_VISION=true
   GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
   ```

3. Restart the app - done!

**New cost**: ~$2.00 per 1,000 documents (still excellent margins!)

## Troubleshooting

### "Tesseract not found" error

- Verify Tesseract is installed: `tesseract --version`
- Check PATH environment variable includes Tesseract directory
- Restart your terminal/IDE after adding to PATH

### "Poppler not found" or "pdftoppm not found"

- Verify Poppler is installed: `pdftoppm -h`
- Check PATH includes Poppler's `bin` directory
- Restart your terminal/IDE after adding to PATH

### "ANTHROPIC_API_KEY not set" error

- Check `.env` file exists in project root
- Verify API key is correct (starts with `sk-ant-`)
- Make sure there are no spaces around the `=` sign

### OCR quality is poor

- Try preprocessing: Uncomment the image enhancement lines in `ocr_service.py`:
  ```python
  image = image.convert('L')  # Convert to grayscale
  image = image.point(lambda x: 0 if x < 128 else 255, '1')  # Binarize
  ```
- Or upgrade to Google Vision API for 99% accuracy

### Port 8000 already in use

- Change the port in `.env`:
  ```bash
  PORT=8001
  ```
- Restart the application

## Performance Benchmarks

Based on MVP specs:

- **Processing Speed**: 50 documents in < 10 minutes
- **Categorization Accuracy**: 80%+ expected
- **Concurrent Processing**: 5 documents at a time (configurable)
- **Max File Size**: 50MB per PDF
- **Max Batch Size**: 100 files

## Project Structure

```
FileBot/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Configuration management
│   ├── models.py               # Pydantic data models
│   ├── routes/
│   │   └── upload.py           # API endpoints
│   └── services/
│       ├── ocr_service.py      # Tesseract OCR
│       ├── ai_service.py       # Claude categorization
│       └── file_service.py     # File organization
├── frontend/
│   ├── index.html              # Upload interface
│   ├── styles.css              # Styling
│   └── app.js                  # Frontend logic
├── storage/
│   ├── uploads/                # Temporary uploads
│   ├── processed/              # Organized outputs
│   └── logs/                   # Processing logs
├── .env                        # Environment variables (you create this)
├── .env.example                # Template
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Next Steps

After Phase 1 MVP is working:

- **Phase 2**: Add smart field extraction (invoice amounts, dates, parties)
- **Phase 3**: DocuWare API integration for DMS upload
- **Phase 4**: User accounts, batch history, API access

## Support

For issues or questions:

1. Check the Troubleshooting section above
2. Review the API documentation at http://localhost:8000/docs
3. Check console output for error messages

## License

This is an MVP project. Add your license here.

---

**Built with:**
- Python 3.11+ & FastAPI
- Claude AI (Anthropic)
- Tesseract OCR
- Vanilla JavaScript

**MVP Goal**: Validate business model before investing in cloud infrastructure! 🚀
