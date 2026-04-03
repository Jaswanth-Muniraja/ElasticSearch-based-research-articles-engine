"""
extractor.py — Production-grade PDF metadata extraction for the Research Portal.

Extracts title, authors, emails, abstract, full text, keywords (KeyBERT + TF-IDF),
domain keywords, NER entities, and file metadata from PDF files.
Every function has fallback chains — never crashes on bad PDFs.
"""

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber

from config import DOMAIN_KEYWORDS

logger = logging.getLogger(__name__)

# ── Lazy-loaded heavy models (loaded once on first use) ──────────────────────
_keybert_model = None
_spacy_nlp = None


def _get_keybert():
    """Lazy-load KeyBERT model."""
    global _keybert_model
    if _keybert_model is None:
        try:
            from keybert import KeyBERT
            _keybert_model = KeyBERT(model="all-MiniLM-L6-v2")
            logger.info("KeyBERT model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load KeyBERT: {e}")
    return _keybert_model


def _get_spacy():
    """Lazy-load spaCy NLP model."""
    global _spacy_nlp
    if _spacy_nlp is None:
        try:
            import spacy
            _spacy_nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load spaCy: {e}")
    return _spacy_nlp


def _human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string (KB/MB/GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logger.error(f"Error computing SHA-256 for {file_path}: {e}")
        return ""


# ── Title extraction ─────────────────────────────────────────────────────────

# Words/phrases that should NEVER be part of a title
_TITLE_BLACKLIST_WORDS = {
    "abstract", "introduction", "received", "accepted", "published",
    "doi", "copyright", "issn", "isbn", "volume", "issue",
    "journal", "university", "department", "faculty", "corresponding",
    "email", "e-mail", "keywords", "key words", "manuscript",
    "article", "open access", "creative commons", "license",
    "editor", "reviewer", "acknowledgment", "references",
    "available online", "homepage", "www.", "http",
}


def _is_title_junk(text: str) -> bool:
    """Check if text contains metadata/junk that shouldn't be in a title."""
    text_lower = text.lower().strip()
    # Too short or just numbers/symbols
    if len(text_lower) < 4:
        return True
    # Starts with common non-title prefixes
    if re.match(r"^\d{1,2}\s*[\.\)]", text_lower):  # "1." or "1)"
        return True
    if re.match(r"^(vol|issue|pp|page|doi|issn|isbn)\b", text_lower, re.IGNORECASE):
        return True
    # Contains email or URL
    if "@" in text_lower or "http" in text_lower or "www." in text_lower:
        return True
    # Is mostly numbers
    alpha_chars = sum(1 for c in text_lower if c.isalpha())
    if alpha_chars < len(text_lower) * 0.4:
        return True
    return False


def _extract_title_pymupdf(doc: fitz.Document) -> Optional[str]:
    """
    Extract title by finding the text with the largest font on page 1.
    
    Strategy:
    1. Parse all text spans on page 1 with font size info
    2. Find the maximum font size
    3. Collect ONLY contiguous lines at/near the top with that font size
    4. Stop collecting when font size drops significantly
    5. Cap title at 300 characters
    """
    try:
        if len(doc) == 0:
            return None
        page = doc[0]
        page_height = page.rect.height
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        # Collect all text spans with their position and font info
        spans_info = []
        for block in blocks:
            if block.get("type") != 0:  # text blocks only
                continue
            for line in block.get("lines", []):
                line_y = line.get("bbox", [0, 0, 0, 0])[1]  # top y of line
                line_spans = []
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    size = span.get("size", 0)
                    flags = span.get("flags", 0)
                    is_bold = bool(flags & 16)
                    line_spans.append({
                        "text": text,
                        "size": size,
                        "bold": is_bold,
                        "y": line_y,
                    })
                if line_spans:
                    # Combine all spans in a line into one entry
                    combined_text = " ".join(s["text"] for s in line_spans)
                    max_size = max(s["size"] for s in line_spans)
                    any_bold = any(s["bold"] for s in line_spans)
                    spans_info.append({
                        "text": combined_text.strip(),
                        "size": max_size,
                        "bold": any_bold,
                        "y": line_y,
                    })

        if not spans_info:
            return None

        # Sort by vertical position (top to bottom)
        spans_info.sort(key=lambda s: s["y"])

        # Find the maximum font size on the page (only in top 60% of page)
        top_spans = [s for s in spans_info if s["y"] < page_height * 0.6]
        if not top_spans:
            top_spans = spans_info[:10]  # fallback to first 10 lines

        max_font_size = max(s["size"] for s in top_spans)

        # Threshold: title font must be within 15% of max AND at least 12pt
        title_threshold = max_font_size * 0.85
        min_font_for_title = 12.0

        # Collect title lines: contiguous large-font text near the top
        title_parts = []
        started = False
        for span in top_spans:
            text = span["text"].strip()
            if not text:
                continue

            is_title_sized = span["size"] >= title_threshold and span["size"] >= min_font_for_title
            is_junk = _is_title_junk(text)

            if is_title_sized and not is_junk:
                started = True
                title_parts.append(text)
            elif started:
                # Once we started collecting title and hit a non-title line, stop
                break

        if not title_parts:
            # Fallback: just take the single largest-font text
            best = max(top_spans, key=lambda s: s["size"])
            if not _is_title_junk(best["text"]):
                title_parts = [best["text"]]

        if not title_parts:
            return None

        title = " ".join(title_parts).strip()
        # Clean up
        title = re.sub(r"\s+", " ", title)
        # Remove trailing/leading punctuation junk
        title = title.strip(".,;:- \t")

        # Hard cap: no title should be longer than 300 chars
        if len(title) > 300:
            # Try to cut at a reasonable word boundary
            title = title[:300].rsplit(" ", 1)[0].strip(".,;:- ")

        return title if len(title) > 5 else None

    except Exception as e:
        logger.debug(f"PyMuPDF title extraction failed: {e}")
        return None


def _extract_title_from_metadata(doc: fitz.Document) -> Optional[str]:
    """Try to extract title from PDF metadata (embedded by authoring software)."""
    try:
        meta = doc.metadata
        if meta and meta.get("title"):
            title = meta["title"].strip()
            # Filter out junk metadata titles
            if (len(title) > 5 and
                not title.lower().startswith("microsoft") and
                not title.lower().startswith("untitled") and
                not re.match(r"^[\d\-_\.]+$", title) and
                len(title) < 300):
                return title
    except Exception:
        pass
    return None


def _extract_title_fallback(text: str) -> Optional[str]:
    """Fallback: first substantial non-empty line on page 1."""
    try:
        for line in text.split("\n"):
            cleaned = line.strip()
            if not cleaned or len(cleaned) < 6:
                continue
            if _is_title_junk(cleaned):
                continue
            # Skip lines that look like affiliations, emails, dates
            if re.match(r"^\d", cleaned):  # starts with number
                continue
            if "@" in cleaned:
                continue
            title = re.sub(r"\s+", " ", cleaned)
            if len(title) > 300:
                title = title[:300].rsplit(" ", 1)[0]
            return title
    except Exception:
        pass
    return None


def _extract_title_from_filename(file_path: str) -> str:
    """Last resort: clean the filename into a title."""
    name = Path(file_path).stem
    # Remove DOI-like prefixes
    name = re.sub(r"^10\.\d+[\-\/]", "", name)
    # Replace underscores and hyphens with spaces
    name = re.sub(r"[_\-]+", " ", name)
    # Remove file-like suffixes
    name = re.sub(r"\s*\(\d+\)\s*$", "", name)
    return name.strip().title() if name.strip() else Path(file_path).stem


# ── Authors extraction ───────────────────────────────────────────────────────

# Words that commonly appear near authors but are NOT author names
_AUTHOR_BLACKLIST = {
    "abstract", "introduction", "received", "accepted", "published",
    "revised", "available", "online", "january", "february", "march",
    "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "university", "department", "faculty",
    "institute", "school", "college", "laboratory", "lab", "center",
    "centre", "hospital", "corresponding", "author", "senior",
    "member", "professor", "associate", "assistant", "dr", "mr", "mrs",
    "ms", "digital", "object", "identifier", "doi", "ieee", "acm",
    "springer", "elsevier", "wiley", "taylor", "francis",
    "computer", "science", "engineering", "technology", "research",
    "paper", "article", "journal", "volume", "issue", "pages",
    "copyright", "rights", "reserved", "open", "access", "keywords",
    "key", "words", "email", "e-mail", "tel", "fax", "phone",
    "address", "pakistan", "india", "china", "usa", "turkey",
    "germany", "france", "japan", "korea", "brazil", "iran",
    "recommendation", "approach", "hybrid", "method", "system",
    "model", "network", "algorithm", "learning", "deep", "neural",
    "machine", "artificial", "intelligence", "natural", "language",
    "processing", "based", "using", "toward", "towards",
    "measures", "centrality", "ranking", "evaluation", "analysis",
    "classification", "detection", "recognition", "generation",
    "information", "retrieval", "application", "framework",
    "results", "conclusion", "discussion", "methodology",
    "section", "figure", "table", "equation", "reference",
    "citation", "index", "measure", "gpt", "bert",
    "writing", "makalesi", "değerlendirmesi", "yapay", "zeka",
    "dil", "modeli", "araştırma", "yazımında",
    "turkish", "international", "national", "conference", "proceedings",
    "transactions", "letters", "review", "survey",
    "software", "collaborative", "implementing", "includes",
    "relationships", "inspects", "quality", "publishing",
    "filtering", "content", "repositories", "traditional",
    "networks", "recommender", "citation", "difficult", "searching",
    "knowledge", "approaches", "implemented", "papers",
    "san", "francisco", "new", "york", "london", "tokyo", "beijing",
    "attribution", "license", "creative", "commons", "tech",
    "scholar", "inappropriate", "fabrication", "prevent",
    "publication", "british", "medical", "american",
    "website", "development", "optimization", "introduction",
    "causal", "productions", "editorial",
}

# Additional patterns that indicate a span is NOT a person's name
_AUTHOR_JUNK_PATTERNS = [
    r"@",                            # email
    r"www\.",                        # url
    r"http",                         # url
    r"^\d+$",                        # just numbers
    r"^\(.+\)$",                     # parenthetical
    r"\bvol\b",
    r"\bissue\b",
    r"\bpp\b",
    r"\bpages?\b",
]


def _clean_author_name(raw: str) -> str:
    """Clean a raw author name: strip superscript digits, CJK chars, symbols, newlines."""
    # Remove newlines
    cleaned = raw.replace("\n", " ").replace("\r", " ")
    # Normalize Unicode typographic ligatures common in LaTeX-generated PDFs
    # e.g. 'Geoﬀrey' (U+FB00 ﬀ) → 'Geoffrey', 'ﬁ' → 'fi', 'ﬂ' → 'fl'
    _ligature_map = {
        '\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl',
        '\ufb03': 'ffi', '\ufb04': 'ffl', '\ufb05': 'st', '\ufb06': 'st',
    }
    for lig, repl in _ligature_map.items():
        cleaned = cleaned.replace(lig, repl)
    # Remove CJK characters and their surrounding parentheses — e.g. "(饶翔)" or "（刘怡娜）"
    # This handles cases like: Xiang Rao1,2*(饶翔)
    cleaned = re.sub(r"[（(][\u4e00-\u9fff\u3000-\u303f\uff00-\uffef·\s]+[）)]", "", cleaned)
    cleaned = re.sub(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+", "", cleaned)
    # Remove superscript digits and common footnote markers
    cleaned = re.sub(r"[0-9*†‡§¶∥⊥#]+", "", cleaned)
    # Remove non-letter/non-space chars except period (for initials) and hyphen
    cleaned = re.sub(r"[^\w\s\.\-'À-ÿ]", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Strip leading "And " or "and " prefix
    cleaned = re.sub(r"^(?:And|AND|and)\s+", "", cleaned).strip()
    return cleaned


def _is_valid_author_name(name: str) -> bool:
    """Check if a string looks like a real person's name."""
    name = name.strip()
    if not name or len(name) < 3:
        return False
    if len(name) > 60:
        return False

    # Use original-case words for some checks
    original_words = name.split()
    if not original_words:
        return False

    # Check against blacklist (use lowered words)
    lower_words = name.lower().split()
    blacklisted_count = sum(1 for w in lower_words if w.rstrip(".,;:") in _AUTHOR_BLACKLIST)
    if blacklisted_count > len(lower_words) * 0.5:
        return False

    # Check junk patterns
    for pattern in _AUTHOR_JUNK_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return False

    # Name should have 2-6 words
    word_count = len(original_words)
    if word_count < 2 or word_count > 6:
        return False

    # At least one word should start with uppercase (use ORIGINAL case words!)
    has_upper = any(w[0].isupper() for w in original_words if w)
    if not has_upper:
        return False

    # Most words should be alpha (allow periods for initials like "J.")
    alpha_words = sum(1 for w in original_words if re.match(r"^[A-Za-zÀ-ÿ\.\-']+$", w))
    if alpha_words < len(original_words) * 0.7:
        return False

    return True


def _strip_punct(word: str) -> str:
    """Strip leading/trailing punctuation from a word for comparison."""
    return re.sub(r"^[^\w]+|[^\w]+$", "", word)


def _is_line_in_title(line: str, title_lower: str) -> bool:
    """Return True if the line's words are largely a subset of the title words."""
    if not line.strip() or not title_lower:
        return False
    # Strip punctuation from words before comparing
    line_words = {_strip_punct(w) for w in line.lower().strip().split()}
    # Remove very short words (articles/prepositions)
    sig_line_words = {w for w in line_words if len(w) > 2}
    if not sig_line_words:
        return False
    title_words = {_strip_punct(w) for w in title_lower.split()}
    overlap = sig_line_words & title_words
    return len(overlap) >= min(3, len(sig_line_words))


def _find_author_region(first_page_text: str, title: str) -> str:
    """
    Extract the text region between the title and the abstract.
    This is where author names typically appear in academic papers.

    Key improvements over previous version:
    - Multi-line title support: scan past continuation title lines
    - One-author-per-line + email format: skip email lines that immediately
      follow a valid author name instead of terminating the region
    - Title-fragment bleed removal: strip prefix lines that belong to the title
    """
    lines = first_page_text.split("\n")
    title_lower = (title or "").lower().strip()
    title_significant_words = {w for w in title_lower.split() if len(w) > 3}

    # ── Step 1: Find where the title ENDS (handle multi-line titles) ──────────
    start_idx = 0
    if title_lower:
        # Strip punctuation from title words to handle cases like "Dropout:" matching "Dropout"
        title_first_words = {_strip_punct(w) for w in title_lower.split()[:5]}
        title_match_idx = -1
        for i, line in enumerate(lines[:20]):
            line_words = {_strip_punct(w) for w in line.lower().strip().split()}
            if title_first_words and len(title_first_words & line_words) >= min(3, len(title_first_words)):
                title_match_idx = i
                break

        if title_match_idx >= 0:
            # Advance past any continuation lines that are still part of the title
            j = title_match_idx + 1
            while j < min(len(lines), title_match_idx + 8):
                candidate = lines[j].strip()
                if not candidate:
                    j += 1
                    continue
                if _is_line_in_title(candidate, title_lower):
                    j += 1  # this line is still the title — skip it
                else:
                    break
            start_idx = j

    # ── Step 2: Scan forward to find abstract / end of author block ───────────
    end_idx = len(lines)
    last_author_line_idx = start_idx  # tracks last line that looked like author

    i = start_idx
    while i < len(lines):
        line_stripped = lines[i].strip()
        line_lower = line_stripped.lower()

        # Abstract / summary header — hard stop
        if re.match(r"^(abstract|summary|a\s*b\s*s\s*t\s*r\s*a\s*c\s*t)\s*[:\-—.]?", line_lower):
            end_idx = i
            break

        # Funding / acknowledgment lines — hard stop
        if any(marker in line_lower for marker in [
            "supported by", "funded by", "in part by", "this work was",
            "this research", "this study", "acknowledge", "grant no",
            "under grant", "financial support", "scholarship",
        ]):
            end_idx = i
            break

        # Email line — SMART handling:
        # In one-per-line format (e.g. srivastava14a), email lines appear
        # directly after author names. Skip them and keep scanning.
        # Only terminate if the email is not adjacent to an author-like line.
        if "@" in line_lower and "." in line_lower:
            # Check if the previous non-empty line could be an author name
            prev_content = ""
            for k in range(i - 1, max(start_idx - 1, i - 4), -1):
                if lines[k].strip():
                    prev_content = lines[k].strip()
                    break
            # If the previous line looks like a person name (2-4 words, capitalised),
            # treat this email line as an affiliation-marker and skip it.
            prev_cleaned = _clean_author_name(prev_content)
            if prev_content and _is_valid_author_name(prev_cleaned):
                # Skip email line — it belongs to the author just parsed
                i += 1
                continue
            else:
                # Email with no adjacent author — likely affiliation block; stop
                end_idx = i
                break

        i += 1

    # ── Step 3: Apply cap to avoid pulling in too many affiliation lines ───────
    # We allow up to 20 lines (was 12) to handle papers with many authors
    end_idx = min(end_idx, start_idx + 20)
    region_lines = lines[start_idx:end_idx]

    # ── Step 4: Strip leading lines that are still title fragments ─────────────
    # e.g. if the title ended mid-line and start_idx is one line too early
    cleaned_region_lines = []
    skipping_title = True
    for line in region_lines:
        if skipping_title and _is_line_in_title(line, title_lower):
            continue  # discard — it's still part of the title
        skipping_title = False
        cleaned_region_lines.append(line)

    region = "\n".join(cleaned_region_lines)

    # Fallback: use first 15 lines if region is empty
    if not region.strip():
        region = "\n".join(lines[:15])
    return region


def _extract_authors_by_line(first_page_text: str, title: str) -> list[str]:
    """
    Parse author names from comma/and-separated lines in the author region.
    Handles both mixed-case and ALL-CAPS names common in academic papers.
    Also handles one-author-per-line format (e.g. srivastava14a).

    e.g. 'WALEED WAHEED, MUHAMMAD IMRAN, BASIT RAZA'
    e.g. 'Oğuzhan KATAR, Dilek ÖZKAN, Özal YILDIRIM'
    e.g. 'Nitish Srivastava\nGeoffrey Hinton\n...' (one per line)
    """
    try:
        region = _find_author_region(first_page_text, title)
        if not region.strip():
            return []

        authors = []
        seen = set()

        for line in region.split("\n"):
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Skip lines that are clearly not author lines
            line_lower = line.lower()
            if any(skip in line_lower for skip in [
                "department", "university", "faculty", "school",
                "institute", "college", "laboratory", "lab",
                "@", "doi", "http", "abstract",
                "received", "accepted", "published", "supported",
                "corresponding", "copyright", "ieee", "acm",
                "this work", "this paper", "this study",
                "funded by", "in part by", "supported by", "grant",
                "scholarship", "acknowledge", "financial",
                "to prevent", "to improve", "to enhance", "to propose",
                "we present", "we propose", "we introduce",
                "road", "street", "avenue", "blvd", "floor",
                "p.o. box", "zip", "postal",
            ]):
                continue

            # Check if line looks like a list of names
            # Split by commas, "and", semicolons
            parts = re.split(r"\s*,\s*|\s+and\s+|\s*;\s*", line)

            valid_names_in_line = []
            for part in parts:
                cleaned = _clean_author_name(part)
                if not cleaned or not _is_valid_author_name(cleaned):
                    continue
                # Reject if the "name" looks like a sentence fragment
                cleaned_lower = cleaned.lower()
                if any(frag in cleaned_lower for frag in [
                    "by the", "in part", "of the", "for the", "with the",
                    "to the", "from the", "on the", "at the",
                    "prevent", "improve", "propose", "present",
                    "enhance", "support", "acknowledge",
                    "innovation", "science", "foundation",
                    "publication", "fabricat",
                ]):
                    continue
                # Title-case ALL-CAPS names for display
                if cleaned == cleaned.upper() and len(cleaned) > 3:
                    cleaned = cleaned.title()
                valid_names_in_line.append(cleaned)

            # If at least 2 valid names on a line, it's definitely an author line
            if len(valid_names_in_line) >= 2:
                for name in valid_names_in_line:
                    if name.lower() not in seen:
                        seen.add(name.lower())
                        authors.append(name)
            elif len(valid_names_in_line) == 1:
                # FIX: Accept single-name lines unconditionally (not just when
                # authors already exists). This handles "one author per line" format.
                # Guard: ensure the line contains ONLY the name (not mixed with text)
                name = valid_names_in_line[0]
                # Remove the cleaned name from the raw line and see what's left
                line_without_name = re.sub(re.escape(name), "", line, flags=re.IGNORECASE).strip(" ,;()[]")
                # If >15 chars remain after removing the name, it's not a name-only line
                if len(line_without_name) > 15:
                    continue
                if name.lower() not in seen:
                    seen.add(name.lower())
                    authors.append(name)

        return authors[:20]  # cap at 20 authors
    except Exception as e:
        logger.debug(f"Line-based author extraction failed: {e}")
        return []


def _extract_authors_spacy(first_page_text: str, title: str) -> list[str]:
    """
    Extract authors using spaCy NER to find PERSON entities in the author region.
    """
    try:
        nlp = _get_spacy()
        if nlp is None:
            return []

        author_region = _find_author_region(first_page_text, title)

        # Use spaCy NER on the author region
        doc = nlp(author_region)
        authors = []
        seen = set()

        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = _clean_author_name(ent.text)
                if _is_valid_author_name(name) and name.lower() not in seen:
                    seen.add(name.lower())
                    # Title-case ALL-CAPS names
                    if name == name.upper() and len(name) > 3:
                        name = name.title()
                    authors.append(name)

        return authors[:20]

    except Exception as e:
        logger.debug(f"spaCy author extraction failed: {e}")
        return []


def _extract_authors_regex(first_page_text: str, title: str) -> list[str]:
    """
    Fallback author extraction using regex patterns.
    Look for comma/and-separated names in the region between title and abstract.
    """
    try:
        lines = first_page_text.split("\n")
        title_lower = (title or "").lower().strip()

        start_idx = 0
        end_idx = min(len(lines), 25)  # limit search to first 25 lines

        # Find title end
        if title_lower:
            title_first_words = set(title_lower.split()[:4])
            for i, line in enumerate(lines):
                line_words = set(line.lower().strip().split())
                if title_first_words and len(title_first_words & line_words) >= min(2, len(title_first_words)):
                    start_idx = i + 1
                    break

        # Find abstract start
        for i in range(start_idx, min(len(lines), 30)):
            if re.match(r"^\s*(abstract|summary)\b", lines[i].strip(), re.IGNORECASE):
                end_idx = i
                break

        # Limit author region
        end_idx = min(end_idx, start_idx + 15)
        author_region = " ".join(lines[start_idx:end_idx])

        # Pattern: capitalized words that look like names (2-4 words each)
        # Handles: "John Smith, Jane Doe and Bob Lee"
        # Also handles: "JOHN SMITH, JANE DOE" (all-caps names)
        name_pattern = re.compile(
            r"\b([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ]\.?\s*)*(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+){1,3})\b"
        )
        # Also try all-caps pattern: "OĞUZHAN KATAR"
        allcaps_pattern = re.compile(
            r"\b([A-ZÀ-Ÿ]{2,}(?:\s+[A-ZÀ-Ÿ]{2,}){1,3})\b"
        )

        authors = []
        seen = set()

        for pattern in [name_pattern, allcaps_pattern]:
            for match in pattern.finditer(author_region):
                name = match.group(1).strip()
                name = re.sub(r"\s+", " ", name)
                # For all-caps, title-case them
                if name == name.upper() and len(name) > 3:
                    name = name.title()
                if _is_valid_author_name(name) and name.lower() not in seen:
                    seen.add(name.lower())
                    authors.append(name)

        return authors[:20]

    except Exception as e:
        logger.debug(f"Regex author extraction failed: {e}")
        return []


def _extract_authors_from_metadata(doc: fitz.Document) -> list[str]:
    """Try to get authors from PDF metadata."""
    try:
        meta = doc.metadata
        if meta and meta.get("author"):
            author_str = meta["author"].strip()
            if author_str and len(author_str) > 2:
                # Split by common delimiters
                raw_names = re.split(r"[,;]|\band\b", author_str)
                authors = []
                for name in raw_names:
                    name = name.strip()
                    if _is_valid_author_name(name):
                        authors.append(name)
                if authors:
                    return authors
    except Exception:
        pass
    return []


# ── Non-person phrase detection ─────────────────────────────────────────────

# Phrases/words that definitively identify a string as NOT a person name.
# These are institution, geography, and domain tokens that sometimes slip through.
_NON_PERSON_TOKENS = {
    # Institution types
    "university", "institute", "college", "school", "faculty", "department",
    "laboratory", "lab", "center", "centre", "hospital", "clinic",
    "academy", "polytechnic", "conservatory", "seminary",
    "division", "section", "unit", "group", "bureau", "agency",
    "foundation", "corporation", "company", "inc", "ltd", "llc",
    # Geography
    "china", "india", "usa", "uk", "germany", "france", "japan", "korea",
    "brazil", "iran", "pakistan", "turkey", "russia", "australia",
    "canada", "italy", "spain", "mexico", "netherlands", "sweden",
    "norway", "denmark", "finland", "switzerland", "austria", "belgium",
    "poland", "czech", "greece", "portugal", "romania", "hungary",
    "egypt", "nigeria", "kenya", "saudi", "arabia", "emirates",
    "singapore", "malaysia", "indonesia", "thailand", "vietnam",
    "taiwan", "hongkong", "israel", "jordan", "morocco", "ethiopia",
    "california", "texas", "york", "london", "beijing", "shanghai",
    "tokyo", "paris", "berlin", "moscow", "toronto", "montreal",
    "sydney", "melbourne", "singapore", "zurich", "amsterdam",
    "ontario", "quebec", "wuhan", "nanjing", "beijing", "chengdu",
    # Domain/research keywords
    "engineering", "technology", "science", "physics", "chemistry",
    "biology", "medicine", "mathematics", "computing", "informatics",
    "petroleum", "electrical", "mechanical", "civil", "chemical",
    "catalysis", "utilization", "simulation", "processing",
    # Publication entities
    "journal", "proceedings", "conference", "workshop", "symposium",
    "transactions", "letters", "review", "nature", "science", "cell",
    # Common false positives from title fragments
    "equations", "networks", "systems", "methods", "models",
    "algorithm", "learning", "neural", "quantum", "classical",
    "seepage", "reservoir", "informed", "solvers", "carbon",
    "dioxide", "dioxide", "low", "high",
}


def _validate_author_list(authors: list[str]) -> list[str]:
    """
    Post-extraction validation filter.
    Removes any entry that is clearly not a personal human name:
    - Contains institution/geography/domain tokens
    - Is too short or too long
    - Contains numeric strings
    - Fails the existing _is_valid_author_name check
    """
    clean = []
    for name in authors:
        if not _is_valid_author_name(name):
            continue
        # Check every word in the name against the non-person token set
        name_words = name.lower().split()
        if any(w.rstrip(".,;:") in _NON_PERSON_TOKENS for w in name_words):
            logger.debug(f"Filtering non-person: {name!r}")
            continue
        # Reject single-word names (person names need first+last at minimum)
        if len(name_words) == 1:
            continue
        clean.append(name)
    return clean


def _extract_authors(first_page_text: str, title: str, doc: fitz.Document) -> list[str]:
    """
    Extract authors using multiple strategies, best result wins.
    Priority: PDF metadata > Line parser > spaCy NER > Regex fallback
    All results pass through _validate_author_list before being returned.
    """
    # 1. Try PDF metadata first (most reliable when available)
    authors = _extract_authors_from_metadata(doc)
    if authors:
        authors = _validate_author_list(authors)
        if authors:
            logger.debug(f"Authors from PDF metadata: {authors}")
            return authors

    # 2. Try line-based comma-separated name parser (best for academic papers)
    authors = _extract_authors_by_line(first_page_text, title)
    if authors:
        authors = _validate_author_list(authors)
        if authors:
            logger.debug(f"Authors from line parser: {authors}")
            return authors

    # 3. Try spaCy NER
    authors = _extract_authors_spacy(first_page_text, title)
    if authors:
        authors = _validate_author_list(authors)
        if authors:
            logger.debug(f"Authors from spaCy NER: {authors}")
            return authors

    # 4. Regex fallback — most prone to contamination, validate strictly
    authors = _extract_authors_regex(first_page_text, title)
    if authors:
        authors = _validate_author_list(authors)
        if authors:
            logger.debug(f"Authors from regex: {authors}")
            return authors

    return []


# ── Email extraction ─────────────────────────────────────────────────────────

def _extract_emails(text: str) -> list[str]:
    """Regex scan for email addresses, deduplicated."""
    try:
        pattern = r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b"
        emails = re.findall(pattern, text)
        return list(dict.fromkeys(emails))  # deduplicate preserving order
    except Exception as e:
        logger.debug(f"Email extraction failed: {e}")
        return []


# ── Abstract extraction ──────────────────────────────────────────────────────

def _extract_abstract(full_text: str) -> str:
    """
    Search for "Abstract" / "ABSTRACT" section header.
    Capture text until next section header.
    Multiple strategies with fallbacks.
    """
    try:
        # Strategy 1: Find "Abstract" header and capture until next section
        # The abstract header can be on its own line or at the start of a line
        abstract_patterns = [
            # "Abstract" on its own line, content follows
            re.compile(
                r"(?:^|\n)\s*(?:ABSTRACT|Abstract|abstract)\s*[:\-—.]?\s*\n"
                r"(.*?)"
                r"(?:\n\s*(?:Keywords?|Key\s*words?|KEYWORDS?|INDEX TERMS|"
                r"Introduction|INTRODUCTION|1\.?\s+Introduction|I\.?\s+Introduction|"
                r"Background|BACKGROUND|Related Work|RELATED WORK|"
                r"Methodology|METHODOLOGY|Methods?|METHODS?|"
                r"Literature Review|LITERATURE REVIEW|"
                r"Problem Statement|PROBLEM STATEMENT|"
                r"Results?|RESULTS?|Conclusions?|CONCLUSIONS?|"
                r"1\s*[\.\\)]\s|I\s*[\.\\)]\s|"
                r"2\.\s|II\.?\s)\s*)",
                re.DOTALL,
            ),
            # "Abstract" followed by content on same line or next line
            re.compile(
                r"(?:^|\n)\s*(?:ABSTRACT|Abstract|abstract)\s*[:\-—.]\s*"
                r"(.*?)"
                r"(?:\n\s*(?:Keywords?|Key\s*words?|KEYWORDS?|INDEX TERMS|"
                r"Introduction|INTRODUCTION|1\.?\s+Introduction|I\.?\s+Introduction|"
                r"Background|BACKGROUND|Related Work|RELATED WORK|"
                r"Literature Review|LITERATURE REVIEW)\s*)",
                re.DOTALL,
            ),
            # Just find "Abstract" and grab text until double newline or section
            re.compile(
                r"(?:ABSTRACT|Abstract|abstract)\s*[:\-—.]?\s*\n?"
                r"(.*?)"
                r"(?:\n\s*\n\s*\n|\n\s*(?:Keywords?|Key\s*words?|Introduction|"
                r"1\.?\s|2\.\s|I\.?\s|II\.?\s)\s*)",
                re.DOTALL,
            ),
        ]

        for pattern in abstract_patterns:
            match = pattern.search(full_text)
            if match:
                abstract = match.group(1).strip()
                abstract = re.sub(r"\s+", " ", abstract)
                # Sanity check: abstract should be > 50 chars and < 5000 chars
                if 50 < len(abstract) < 5000:
                    return abstract

        # Strategy 2: Find "abstract" word and grab everything until next section
        idx = -1
        for marker in ["ABSTRACT", "Abstract", "abstract"]:
            idx = full_text.find(marker)
            if idx >= 0:
                break

        if idx >= 0:
            after = full_text[idx + len("abstract"):]
            after = after.lstrip(":—-. \n\t")

            # Find the end: next section header
            section_headers = [
                r"\n\s*(?:Keywords?|Key\s*words?|KEYWORDS?|INDEX\s*TERMS)\s*",
                r"\n\s*(?:Introduction|INTRODUCTION)\s*",
                r"\n\s*(?:1\.?\s+[A-Z]|I\.?\s+[A-Z])",
                r"\n\s*(?:2\.\s+[A-Z]|II\.?\s+[A-Z])",
                r"\n\s*(?:Background|BACKGROUND|Related\s*Work|RELATED\s*WORK)\s*",
                r"\n\s*(?:Methodology|METHODOLOGY|Methods?|METHODS?)\s*",
                r"\n\s*(?:Literature\s*Review|LITERATURE\s*REVIEW)\s*",
                r"\n\s*(?:Problem\s*Statement|PROBLEM\s*STATEMENT)\s*",
                r"\n\s*(?:Results?|RESULTS?|Conclusions?|CONCLUSIONS?)\s*",
                r"\n\s*[A-Z][A-Z\s]{5,}\n",  # ALL-CAPS section headers
            ]

            end_pos = len(after)
            for header_pat in section_headers:
                m = re.search(header_pat, after)
                if m:
                    end_pos = min(end_pos, m.start())

            # Also cap at 3000 chars
            end_pos = min(end_pos, 3000)
            abstract = after[:end_pos].strip()
            abstract = re.sub(r"\s+", " ", abstract)

            if len(abstract) > 50:
                return abstract

    except Exception as e:
        logger.debug(f"Abstract extraction failed: {e}")

    # Fallback: no abstract found — try to use the first paragraph of body text
    # Only used when no abstract marker was found at all
    try:
        lines = full_text.split("\n")
        # Find the first substantial paragraph after line 8
        # (skip title, authors, affiliations)
        paragraph = []
        collecting = False
        # Non-abstract openers to reject
        _bad_para_starts = (
            "in this section", "figure", "table", "fig.", "tab.",
            "contents", "copyright", "doi:", "volume", "issue",
            "received", "accepted", "published", "editor",
        )
        for i, line in enumerate(lines[8:], start=8):
            stripped = line.strip()
            if not collecting and len(stripped) > 60 and not _is_title_junk(stripped):
                # Reject if starts with non-abstract opener
                if any(stripped.lower().startswith(bad) for bad in _bad_para_starts):
                    continue
                collecting = True
                paragraph.append(stripped)
            elif collecting:
                if stripped:
                    paragraph.append(stripped)
                else:
                    if len(" ".join(paragraph)) > 150:
                        break
                    # Short paragraph, keep looking
                    paragraph.clear()
                    collecting = False

        if paragraph:
            abstract = " ".join(paragraph)
            abstract = re.sub(r"\s+", " ", abstract)
            if len(abstract) > 50:
                return abstract[:2000]
    except Exception:
        pass

    return ""


# ── Full text extraction ─────────────────────────────────────────────────────

def _extract_full_text_pymupdf(file_path: str) -> tuple[str, int]:
    """Extract all text from PDF using PyMuPDF. Returns (text, page_count)."""
    try:
        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            text = page.get_text()
            if text:
                pages.append(text)
        page_count = len(doc)
        doc.close()
        full_text = "\n\n".join(pages)
        # Clean hyphenation artifacts
        full_text = re.sub(r"(\w)-\n(\w)", r"\1\2", full_text)
        # Normalize whitespace
        full_text = re.sub(r"[ \t]+", " ", full_text)
        return full_text, page_count
    except Exception as e:
        logger.warning(f"PyMuPDF text extraction failed for {file_path}: {e}")
        return "", 0


def _extract_full_text_pdfplumber(file_path: str) -> tuple[str, int]:
    """Fallback text extraction using pdfplumber."""
    try:
        pages = []
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        full_text = "\n\n".join(pages)
        full_text = re.sub(r"(\w)-\n(\w)", r"\1\2", full_text)
        full_text = re.sub(r"[ \t]+", " ", full_text)
        return full_text, page_count
    except Exception as e:
        logger.warning(f"pdfplumber text extraction failed for {file_path}: {e}")
        return "", 0


# ── Keyword extraction ───────────────────────────────────────────────────────

# Academic boilerplate words that should never be keywords
_KEYWORD_STOP_WORDS = {
    "et", "al", "fig", "figure", "table", "vol", "pp", "page", "pages",
    "doi", "issn", "isbn", "http", "https", "www", "com", "org",
    "university", "department", "journal", "conference", "proceedings",
    "ieee", "acm", "springer", "elsevier", "wiley",
    "author", "corresponding", "manuscript", "received", "accepted",
    "published", "copyright", "rights", "reserved", "license",
    "section", "chapter", "paper", "article", "study", "research",
    "result", "results", "conclusion", "conclusions", "discussion",
    "introduction", "background", "abstract", "method", "methods",
    "methodology", "reference", "references", "bibliography",
    "acknowledgment", "acknowledgments", "funding", "grant",
    "year", "new", "use", "used", "using", "based", "approach",
    "proposed", "propose", "present", "presented", "show", "shown",
    "finally", "also", "however", "therefore", "moreover",
}


def _clean_text_for_keywords(text: str, abstract: str = "") -> str:
    """
    Clean raw text before feeding to KeyBERT/TF-IDF.
    Strips references, URLs, emails, numeric-heavy lines, and boilerplate.
    """
    # Strip everything after "References" / "Bibliography" section
    text = re.split(
        r"\n\s*(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*\n",
        text, maxsplit=1
    )[0]

    # Remove emails and URLs
    text = re.sub(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)
    text = re.sub(r"\bdoi\s*[:.]?\s*10\.\S+", "", text, flags=re.IGNORECASE)

    # Remove lines that are mostly numbers (page numbers, table data)
    lines = text.split("\n")
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        alpha_chars = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 0 and alpha_chars < len(stripped) * 0.4:
            continue  # skip numeric-heavy lines
        clean_lines.append(stripped)

    text = " ".join(clean_lines)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_valid_keyword(kw: str) -> bool:
    """Filter out garbage keywords from KeyBERT/TF-IDF output."""
    kw = kw.strip()
    if not kw or len(kw) < 3:
        return False
    # Reject if >5 words (too long to be a meaningful keyphrase)
    words = kw.split()
    if len(words) > 4:
        return False
    # Reject if contains standalone year-like numbers ("2022", "2019")
    if re.search(r"\b(19|20)\d{2}\b", kw):
        return False
    # Reject if any word is a pure number
    if any(re.match(r"^\d+$", w) for w in words):
        return False
    # Reject concatenated OCR artifacts (long words without spaces, >25 chars)
    if any(len(w) > 25 for w in words):
        return False
    # Reject if >50% of words are stop words
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    combined_stops = ENGLISH_STOP_WORDS | _KEYWORD_STOP_WORDS
    stop_count = sum(1 for w in words if w.lower() in combined_stops)
    if stop_count > len(words) * 0.5:
        return False
    # Reject if mostly non-alpha characters
    alpha = sum(1 for c in kw if c.isalpha() or c == ' ')
    if alpha < len(kw) * 0.7:
        return False
    return True


def _extract_keywords_from_text(full_text: str) -> list[str]:
    """
    Try to extract explicitly listed keywords from the paper text.
    Many papers have a "Keywords:" or "Key words:" section.
    """
    try:
        # Look for "Keywords:" or "Key words:" section
        kw_patterns = [
            re.compile(
                r"(?:Keywords?|Key\s*words?|INDEX\s*TERMS)\s*[:\-—.]\s*"
                r"(.*?)(?:\n\s*\n|\n\s*(?:1\.?\s|I\.?\s|Introduction|INTRODUCTION))",
                re.IGNORECASE | re.DOTALL,
            ),
            re.compile(
                r"(?:Keywords?|Key\s*words?)\s*[:\-—.]\s*(.*?)(?:\.\s*\n|\n\s*\n)",
                re.IGNORECASE | re.DOTALL,
            ),
        ]

        for pattern in kw_patterns:
            match = pattern.search(full_text)
            if match:
                kw_text = match.group(1).strip()
                # Split by comma, semicolon, or bullet
                raw_kws = re.split(r"[,;•·\|]|\band\b", kw_text)
                keywords = []
                for kw in raw_kws:
                    kw = kw.strip().strip(".")
                    if kw and 2 < len(kw) < 50 and not re.match(r"^\d+$", kw):
                        keywords.append(kw.lower())
                if keywords:
                    return keywords[:15]
    except Exception:
        pass
    return []


def _extract_keywords_keybert(text: str, top_n: int = 10) -> list[str]:
    """Extract keywords using KeyBERT with all-MiniLM-L6-v2."""
    try:
        model = _get_keybert()
        if model is None:
            return []
        # Clean input text and limit length
        input_text = text[:5000]
        keywords = model.extract_keywords(
            input_text,
            keyphrase_ngram_range=(1, 3),
            stop_words="english",
            top_n=top_n * 2,  # extract more, then filter
            use_mmr=True,
            diversity=0.7,  # higher diversity to avoid near-duplicate keywords
        )
        # Filter by score threshold AND validity
        return [
            kw[0] for kw in keywords
            if kw[1] >= 0.25 and _is_valid_keyword(kw[0])
        ][:top_n]
    except Exception as e:
        logger.debug(f"KeyBERT keyword extraction failed: {e}")
        return []


def _extract_keywords_tfidf(text: str, top_n: int = 10) -> list[str]:
    """Fallback keyword extraction using TF-IDF."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        # Build extended stop words list
        custom_stops = list(TfidfVectorizer(stop_words="english").get_stop_words())
        custom_stops.extend(_KEYWORD_STOP_WORDS)

        vectorizer = TfidfVectorizer(
            max_features=top_n * 3,
            stop_words=custom_stops,
            ngram_range=(1, 2),
            max_df=0.95,
            min_df=1,
            token_pattern=r"(?u)\b[a-zA-Z]{2,}\b",  # alpha-only tokens, min 2 chars
        )
        tfidf_matrix = vectorizer.fit_transform([text[:5000]])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]

        # Sort by score descending
        ranked = sorted(zip(feature_names, scores), key=lambda x: x[1], reverse=True)
        return [
            word for word, score in ranked[:top_n * 2]
            if score > 0 and _is_valid_keyword(word)
        ][:top_n]
    except Exception as e:
        logger.debug(f"TF-IDF keyword extraction failed: {e}")
        return []


def _extract_domain_keywords(text: str) -> list[str]:
    """Scan text for domain-specific keywords from the dictionary."""
    found_domains = []
    text_lower = text.lower()
    try:
        for domain, terms in DOMAIN_KEYWORDS.items():
            match_count = sum(1 for term in terms if term in text_lower)
            if match_count >= 2:  # At least 2 matching terms
                found_domains.append(domain)
    except Exception as e:
        logger.debug(f"Domain keyword extraction failed: {e}")
    return found_domains


# ── NER extraction ───────────────────────────────────────────────────────────

def _extract_ner_entities(text: str) -> list[str]:
    """Extract PERSON, ORG, GPE entities using spaCy + custom patterns."""
    entities = []
    try:
        nlp = _get_spacy()
        if nlp is None:
            return []

        # Process first 10000 chars for efficiency
        doc = nlp(text[:10000])
        seen = set()
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE") and len(ent.text.strip()) > 1:
                normalized = ent.text.strip()
                if normalized.lower() not in seen:
                    seen.add(normalized.lower())
                    entities.append(normalized)

        # Custom pattern matching for technologies, datasets, model names
        tech_patterns = [
            r"\b(GPT-\d+|BERT|RoBERTa|XLNet|T5|DALL-E|Stable Diffusion)\b",
            r"\b(TensorFlow|PyTorch|Keras|Scikit-learn|OpenCV)\b",
            r"\b(ImageNet|CIFAR-\d+|MNIST|COCO|SQuAD|GLUE)\b",
            r"\b(ResNet-?\d*|VGG-?\d*|LSTM|GRU|CNN|RNN|GAN)\b",
            r"\b(Transformer|YOLO|U-Net|EfficientNet|MobileNet)\b",
        ]
        for pattern in tech_patterns:
            matches = re.findall(pattern, text[:10000], re.IGNORECASE)
            for m in matches:
                if m.lower() not in seen:
                    seen.add(m.lower())
                    entities.append(m)

    except Exception as e:
        logger.debug(f"NER extraction failed: {e}")
    return entities[:50]  # Cap at 50 entities


# ── Main extraction function ─────────────────────────────────────────────────

def extract_paper_metadata(file_path: str) -> Optional[dict]:
    """
    Extract all metadata from a PDF file.
    Returns a dict ready for Elasticsearch indexing, or None on total failure.
    """
    file_path = str(Path(file_path).resolve())
    logger.info(f"Extracting metadata from: {file_path}")

    try:
        # ── File metadata ────────────────────────────────────────────────
        file_stat = os.stat(file_path)
        file_size_bytes = file_stat.st_size
        file_size_human = _human_readable_size(file_size_bytes)
        last_modified = datetime.fromtimestamp(
            file_stat.st_mtime, tz=timezone.utc
        ).isoformat()
        sha256_hash = _compute_sha256(file_path)
        file_name = Path(file_path).name

        # ── Full text extraction (PyMuPDF primary, pdfplumber fallback) ──
        full_text, page_count = _extract_full_text_pymupdf(file_path)
        if not full_text.strip():
            logger.info(f"PyMuPDF returned empty text, trying pdfplumber for {file_name}")
            full_text, page_count = _extract_full_text_pdfplumber(file_path)

        if not full_text.strip():
            logger.warning(f"No text extracted from {file_name} — possibly scanned PDF")

        # ── Open document for structured extraction ──────────────────────
        doc = fitz.open(file_path)
        first_page_text = doc[0].get_text() if len(doc) > 0 else ""
        first_two_pages_text = ""
        for i in range(min(2, len(doc))):
            first_two_pages_text += doc[i].get_text() + "\n"

        # ── Title ────────────────────────────────────────────────────────
        title = _extract_title_from_metadata(doc)
        if not title:
            title = _extract_title_pymupdf(doc)
        if not title:
            title = _extract_title_fallback(first_page_text)
        if not title:
            title = _extract_title_from_filename(file_path)

        # ── Authors ──────────────────────────────────────────────────────
        authors = _extract_authors(first_page_text, title, doc)

        # Close the document
        doc.close()

        # ── Emails ───────────────────────────────────────────────────────
        emails = _extract_emails(first_two_pages_text)

        # ── Abstract ─────────────────────────────────────────────────────
        abstract = _extract_abstract(full_text)

        # ── Explicit keywords from paper ─────────────────────────────────
        explicit_keywords = _extract_keywords_from_text(full_text)

        # ── Generated keywords (KeyBERT → TF-IDF fallback) ──────────────
        # Feed cleaned text: title + abstract + cleaned body (no refs/boilerplate)
        cleaned_body = _clean_text_for_keywords(full_text, abstract)
        keyword_input = f"{title or ''} {abstract} {cleaned_body[:3000]}"
        generated_keywords = _extract_keywords_keybert(keyword_input)
        if not generated_keywords:
            logger.info(f"KeyBERT failed for {file_name}, falling back to TF-IDF")
            generated_keywords = _extract_keywords_tfidf(keyword_input)

        # Merge: explicit keywords first, then generated (deduped)
        keywords = list(explicit_keywords)
        seen_kw = set(kw.lower() for kw in keywords)
        for kw in generated_keywords:
            if kw.lower() not in seen_kw:
                seen_kw.add(kw.lower())
                keywords.append(kw)

        # ── Domain keywords ──────────────────────────────────────────────
        domain_keywords = _extract_domain_keywords(full_text)

        # ── NER entities ─────────────────────────────────────────────────
        ner_entities = _extract_ner_entities(full_text)

        # ── Build result ─────────────────────────────────────────────────
        result = {
            "title": title or file_name,
            "authors": authors,
            "emails": emails,
            "abstract": abstract,
            "keywords": keywords,
            "domain_keywords": domain_keywords,
            "ner_entities": ner_entities,
            "full_text": full_text,
            "file_name": file_name,
            "file_path": str(Path(file_path).relative_to(Path(file_path).parent.parent)),
            "file_size_bytes": file_size_bytes,
            "file_size_human": file_size_human,
            "page_count": page_count,
            "sha256_hash": sha256_hash,
            "date_indexed": datetime.now(timezone.utc).isoformat(),
            "last_modified": last_modified,
        }

        logger.info(
            f"✅ Extracted: {title} | {len(authors)} authors | "
            f"{len(keywords)} keywords | {len(domain_keywords)} domains | "
            f"{page_count} pages | {file_size_human}"
        )
        return result

    except Exception as e:
        logger.error(f"❌ Failed to extract metadata from {file_path}: {e}", exc_info=True)
        return None
