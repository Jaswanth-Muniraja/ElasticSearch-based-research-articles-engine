# Research Portal Backend

A production-grade university research paper portal backend built with **FastAPI**, **Elasticsearch 8.x**, and advanced NLP/PDF extraction tools.

## Features

- 📄 **PDF Extraction**: Title, authors, emails, abstract, full text, keywords, NER entities
- 🔍 **Smart Search**: Multi-field boosted Elasticsearch queries with fuzzy matching
- 🏷️ **Keyword Extraction**: KeyBERT + TF-IDF fallback + domain keyword matching
- 🧠 **NER**: spaCy-based entity recognition (people, orgs, technologies)
- 📁 **Auto-Indexing**: Watchdog folder watcher + APScheduler periodic sync
- 🔒 **Duplicate Detection**: SHA-256 hash-based deduplication

## Prerequisites

- **Python 3.11+**
- **Elasticsearch 8.x** running at `https://localhost:9200`
- ~3 GB disk space for NLP model downloads

## Setup

```bash
# 1. Navigate to backend
cd backend

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download spaCy model
python -m spacy download en_core_web_sm

# 5. Configure environment
# Edit .env if needed (defaults work for local dev)

# 6. Run the server
python main.py
```

The server starts at `http://localhost:8000`.

## Adding PDFs

Drop PDF files into the `papers/` folder (project root). They will be automatically:
1. Detected by the file watcher
2. Extracted (title, authors, abstract, keywords, etc.)
3. Indexed into Elasticsearch

You can also trigger a manual re-index:
```bash
curl -X POST http://localhost:8000/api/admin/index
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/search` | Search with query, filters, pagination |
| `GET` | `/api/papers` | List all papers (paginated) |
| `GET` | `/api/papers/{id}` | Get single paper details |
| `GET` | `/api/papers/download/{id}` | Download PDF file |
| `POST` | `/api/admin/index` | Trigger manual re-index |
| `GET` | `/api/admin/stats` | Index statistics |
| `GET` | `/api/health` | Health check |

## Frontend Integration

The frontend (Vite + React) connects to this backend at `http://localhost:8000`.
Start the frontend separately:

```bash
cd frontend
npm install
npm run dev
```

## Search Request Example

```json
POST /api/search
{
  "query": "deep learning",
  "filters": {
    "subjects": ["AI/ML"],
    "authors": ["John Smith"],
    "sizeRange": { "from": 0, "to": 10 }
  },
  "page": 1,
  "size": 10
}
```
