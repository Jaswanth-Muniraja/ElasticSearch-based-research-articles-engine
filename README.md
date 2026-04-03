# ResearchHub: AI-Powered Research Article Engine

ResearchHub is a full-stack platform designed for indexing, searching, and managing academic research papers. It leverages Elasticsearch for powerful full-text searching, Python (FastAPI) for backend metadata extraction (layout, keywords, abstract, and entities), and React for a modern user interface.

## 📁 Project Structure

```text
elasticsearch-search/
├── backend/            # FastAPI, metadata extraction, and indexing logic
├── frontend/           # React + Vite + Tailwind CSS dashboard
└── papers/             # [Action Required] Place your PDF files here
```

## 🚀 Prerequisites

Before you begin, ensure you have the following installed:
- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js (v18+)](https://nodejs.org/)
- [Elasticsearch (v8.x)](https://www.elastic.co/downloads/elasticsearch)

---

## 🛠️ Step 1: Data Setup (Papers)

By default, the backend scans a folder named `papers` located at the root of the project.
1. Create a folder named `papers` in the project root if it doesn't exist.
2. Download and place your **PDF research articles** into this folder.
   > [!TIP]
   > The backend will automatically detect additions and changes in this folder and synchronize them with the Elasticsearch index.

---

## ⚙️ Step 2: Backend Configuration

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables**:
   Update the `backend/config.py` file or create a `.env` file in the `backend/` folder.
   
   **Key Configuration Points (in `backend/config.py`):**
   - `ELASTICSEARCH_URL`: URL of your Elasticsearch instance (default: `https://localhost:9200`).
   - `ELASTICSEARCH_PASSWORD`: Your Elasticsearch user password.
   - `ADMIN_PASSWORD`: Credentials for the admin edit portal.
   - `PAPERS_FOLDER`: Path to the PDF folder (relative to `backend/`).

4. **Run the Backend**:
   ```bash
   python main.py
   ```

---

## 💻 Step 3: Frontend Configuration

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```
2. **Install dependencies**:
   ```bash
   npm install
   ```
3. **Configure Firebase**:
   Update your Firebase credentials in `frontend/src/firebase.js`. Replace the placeholder values in the `firebaseConfig` object with your own:
   ```javascript
   // frontend/src/firebase.js
   const firebaseConfig = {
     apiKey: "YOUR_API_KEY",
     authDomain: "YOUR_AUTH_DOMAIN",
     projectId: "YOUR_PROJECT_ID",
     // ...
   };
   ```
4. **Run the Frontend**:
   ```bash
   npm run dev
   ```
   Open your browser to the URL shown in your terminal (typically `http://localhost:5173`).

---

## 🔍 Features
- **Smart Extraction**: Automatically extracts title, authors, abstracts, and keywords from academic PDFs.
- **Advanced Search**: Search through full-text, snippets, and domain-specific keywords.
- **Admin Dashboard**: Edit article metadata and manage indexed papers securely.
- **Real-time Sync**: Automatically indexes new files placed in the `papers/` folder.
