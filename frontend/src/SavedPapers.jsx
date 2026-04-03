import React from "react";

const SavedPapers = ({ savedPapers, onRemove, onClose, onViewPdf, getDownloadFilename }) => {
  return (
    <div className="saved-papers">
      <div className="saved-papers-header">
        <h2>Saved Papers</h2>
        <button className="close-saved-button" onClick={onClose}>
          <i className="fas fa-times"></i>
        </button>
      </div>
      {savedPapers.length > 0 ? (
        savedPapers.map((paper, index) => (
          <div key={index} className="saved-paper-item">
            <h3 className="saved-paper-title">{paper.title}</h3>
            <div className="saved-paper-meta">
              {paper.authors?.length > 0 && (
                <span>
                  <i className="fas fa-user"></i> {paper.authors.join(", ")}
                </span>
              )}
              {/* {paper.year && (
                <span>
                  <i className="fas fa-calendar"></i> {paper.year}
                </span>
              )} */}
              {paper.size_mb && (
                <span>
                  <i className="fas fa-file-alt"></i> {paper.size_mb} MB
                </span>
              )}
            </div>
            {paper.fileUrl && (
              <div className="document-links">
                <button
                  className="card-view-btn"
                  onClick={() => onViewPdf(paper)}
                  aria-label={`View PDF: ${paper.title}`}
                >
                  <i className="fas fa-eye" aria-hidden="true" style={{ marginRight: "6px" }}></i> View
                </button>

                <a
                  href={paper.fileUrl}
                  download={getDownloadFilename(paper)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="view-link"
                  aria-label={`Download: ${paper.title}`}
                >
                  <i className="fa fa-download" style={{ marginRight: "8px" }}></i> Download
                </a>

                <button
                  onClick={() => onRemove(paper.title)}
                  className="remove-saved-button"
                  aria-label={`Remove: ${paper.title}`}
                >
                  <i className="fas fa-trash-alt" aria-hidden="true" style={{ marginRight: "6px" }}></i> Remove
                </button>
              </div>
            )}
          </div>
        ))
      ) : (
        <div className="no-saved-papers">
          <i className="fas fa-bookmark"></i>
          <p>No saved papers yet.</p>
        </div>
      )}
    </div>
  );
};

export default SavedPapers;