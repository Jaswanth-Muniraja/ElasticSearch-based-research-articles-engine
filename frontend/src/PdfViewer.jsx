// PdfViewer.jsx
import React, { useState, useEffect } from "react";
import "./styles/App.css";

/**
 * Converts a download URL to a view URL so the browser renders the PDF
 * inline instead of triggering a file save.
 *
 * The backend serves two separate endpoints:
 *   /api/papers/download/{id}  → Content-Disposition: attachment (download)
 *   /api/papers/view/{id}      → Content-Disposition: inline   (in-page render)
 */
function toViewUrl(fileUrl) {
    if (!fileUrl) return fileUrl;
    return fileUrl.replace("/api/papers/download/", "/api/papers/view/");
}

export default function PdfViewer({ fileUrl, title, onBack, getDownloadFilename }) {
    const viewUrl = toViewUrl(fileUrl);

    const [status, setStatus] = useState("loading"); // "loading" | "ready" | "error"

    // Reset status whenever the PDF URL changes (user clicked View on a different card)
    useEffect(() => {
        setStatus("loading");
    }, [viewUrl]);

    return (
        <div className="pdf-viewer-container">
            {/* ── Header ───────────────────────────────────────────────── */}
            <div className="pdf-viewer-header">
                <button
                    className="pdf-back-btn"
                    onClick={onBack}
                    aria-label="Back to search results"
                >
                    <i className="fas fa-arrow-left" aria-hidden="true"></i>
                    Back to Results
                </button>
                {title && (
                    <h2 className="pdf-viewer-title" title={title}>
                        <i className="fas fa-file-pdf" aria-hidden="true"></i>
                        {title}
                    </h2>
                )}
            </div>

            {/* ── PDF Body ─────────────────────────────────────────────── */}
            <div className="pdf-iframe-wrapper">
                {/* Loading overlay — shown until the iframe fires onLoad */}
                {status === "loading" && (
                    <div className="pdf-status-overlay pdf-loading-overlay" role="status">
                        <div className="pdf-spinner" aria-hidden="true"></div>
                        <span>Loading document…</span>
                    </div>
                )}

                {/* Error state — shown if the iframe fires onError */}
                {status === "error" && (
                    <div className="pdf-status-overlay pdf-error-overlay" role="alert">
                        <i className="fas fa-exclamation-triangle" aria-hidden="true"></i>
                        <p>Could not load the PDF. The file may be unavailable.</p>
                        <a
                            href={fileUrl}
                            download={getDownloadFilename({ fileUrl, title })}
                            className="pdf-download-fallback-btn"
                        >
                            <i className="fas fa-download"></i> Download instead
                        </a>
                    </div>
                )}

                {/* force remount on URL change so onLoad fires for each new PDF */}
                <iframe
                    key={viewUrl}
                    src={viewUrl}
                    className="pdf-iframe"
                    title={title || "PDF Document"}
                    aria-label={`PDF viewer: ${title || "document"}`}
                    style={{ visibility: status === "ready" ? "visible" : "hidden" }}
                    onLoad={() => setStatus("ready")}
                    onError={() => setStatus("error")}
                />
            </div>
        </div>
    );
}
