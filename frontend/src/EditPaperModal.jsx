import React, { useState, useEffect, useCallback } from "react";
import "./styles/EditPaperModal.css";

const EditPaperModal = ({ isOpen, paper, adminToken, onClose, onSaveSuccess }) => {
    const [formData, setFormData] = useState({
        title: "",
        authors: "",
        abstract: "",
        keywords: "",
        domain_keywords: "",
    });
    const [originalData, setOriginalData] = useState({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [successMsg, setSuccessMsg] = useState("");

    // Initialize form when paper changes
    useEffect(() => {
        if (paper && isOpen) {
            const initial = {
                title: paper.title || "",
                authors: (paper.authors || []).join(", "),
                abstract: paper.abstract || "",
                keywords: (paper.keywords || []).join(", "),
                domain_keywords: (paper.domain_keywords || []).join(", "),
            };
            setFormData(initial);
            setOriginalData(initial);
            setError("");
            setSuccessMsg("");
        }
    }, [paper, isOpen]);

    const isDirty = useCallback(() => {
        return Object.keys(originalData).some(
            (key) => formData[key] !== originalData[key]
        );
    }, [formData, originalData]);

    const handleChange = (field, value) => {
        setFormData((prev) => ({ ...prev, [field]: value }));
        setError("");
        setSuccessMsg("");
    };

    const handleReset = () => {
        setFormData({ ...originalData });
        setError("");
        setSuccessMsg("");
    };

    const handleSave = async () => {
        if (!isDirty()) return;
        setSaving(true);
        setError("");
        setSuccessMsg("");

        // Build update payload — only send changed fields
        const payload = {};
        if (formData.title !== originalData.title) {
            payload.title = formData.title;
        }
        if (formData.authors !== originalData.authors) {
            payload.authors = formData.authors
                .split(",")
                .map((a) => a.trim())
                .filter(Boolean);
        }
        if (formData.abstract !== originalData.abstract) {
            payload.abstract = formData.abstract;
        }
        if (formData.keywords !== originalData.keywords) {
            payload.keywords = formData.keywords
                .split(",")
                .map((k) => k.trim())
                .filter(Boolean);
        }
        if (formData.domain_keywords !== originalData.domain_keywords) {
            payload.domain_keywords = formData.domain_keywords
                .split(",")
                .map((dk) => dk.trim())
                .filter(Boolean);
        }

        try {
            const res = await fetch(
                `http://localhost:8000/api/admin/papers/${paper.id}`,
                {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json",
                        Authorization: `Bearer ${adminToken}`,
                    },
                    body: JSON.stringify(payload),
                }
            );

            const data = await res.json();

            if (data.success) {
                setSuccessMsg("Paper updated successfully!");
                setOriginalData({ ...formData });
                // Notify parent to update the card in-place
                if (onSaveSuccess) {
                    onSaveSuccess(paper.id, {
                        title: formData.title,
                        authors: formData.authors
                            .split(",")
                            .map((a) => a.trim())
                            .filter(Boolean),
                        abstract: formData.abstract,
                        keywords: formData.keywords
                            .split(",")
                            .map((k) => k.trim())
                            .filter(Boolean),
                        domain_keywords: formData.domain_keywords
                            .split(",")
                            .map((dk) => dk.trim())
                            .filter(Boolean),
                    });
                }
            } else {
                setError(data.message || "Failed to update paper");
            }
        } catch (err) {
            setError("Network error. Please try again.");
            console.error("Edit paper error:", err);
        } finally {
            setSaving(false);
        }
    };

    if (!isOpen || !paper) return null;

    return (
        <div className="edit-modal-overlay" onClick={onClose}>
            <div className="edit-modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="edit-modal-header">
                    <h2>
                        <i className="fas fa-edit"></i> Edit Paper
                    </h2>
                    <button className="edit-modal-close" onClick={onClose}>
                        ×
                    </button>
                </div>

                {error && (
                    <div className="edit-modal-alert error">
                        <i className="fas fa-exclamation-circle"></i> {error}
                    </div>
                )}
                {successMsg && (
                    <div className="edit-modal-alert success">
                        <i className="fas fa-check-circle"></i> {successMsg}
                    </div>
                )}

                <div className="edit-modal-body">
                    {/* Editable fields */}
                    <div className="edit-field">
                        <label>Title</label>
                        <input
                            type="text"
                            value={formData.title}
                            onChange={(e) => handleChange("title", e.target.value)}
                        />
                    </div>

                    <div className="edit-field">
                        <label>Authors <span className="field-hint">(comma-separated)</span></label>
                        <input
                            type="text"
                            value={formData.authors}
                            onChange={(e) => handleChange("authors", e.target.value)}
                        />
                    </div>

                    <div className="edit-field">
                        <label>Abstract</label>
                        <textarea
                            rows={5}
                            value={formData.abstract}
                            onChange={(e) => handleChange("abstract", e.target.value)}
                        />
                    </div>

                    <div className="edit-field">
                        <label>Keywords <span className="field-hint">(comma-separated)</span></label>
                        <input
                            type="text"
                            value={formData.keywords}
                            onChange={(e) => handleChange("keywords", e.target.value)}
                        />
                    </div>

                    <div className="edit-field">
                        <label>Domain Keywords <span className="field-hint">(comma-separated)</span></label>
                        <input
                            type="text"
                            value={formData.domain_keywords}
                            onChange={(e) => handleChange("domain_keywords", e.target.value)}
                        />
                    </div>

                    {/* Read-only fields */}
                    <div className="edit-readonly-section">
                        <h3>Read-Only Fields</h3>
                        <div className="edit-readonly-grid">
                            <div className="edit-readonly-item">
                                <span className="readonly-label">File Name</span>
                                <span className="readonly-value">{paper.file_name || "—"}</span>
                            </div>
                            <div className="edit-readonly-item">
                                <span className="readonly-label">File Size</span>
                                <span className="readonly-value">{paper.file_size_human || paper.size_mb ? `${paper.size_mb} MB` : "—"}</span>
                            </div>
                            <div className="edit-readonly-item">
                                <span className="readonly-label">Pages</span>
                                <span className="readonly-value">{paper.page_count || "—"}</span>
                            </div>
                            {/* <div className="edit-readonly-item">
                                <span className="readonly-label">Year</span>
                                <span className="readonly-value">{paper.year || "—"}</span>
                            </div> */}
                        </div>
                    </div>
                </div>

                <div className="edit-modal-footer">
                    <button
                        className="edit-btn edit-btn-reset"
                        onClick={handleReset}
                        disabled={!isDirty()}
                    >
                        <i className="fas fa-undo"></i> Reset Changes
                    </button>
                    <button className="edit-btn edit-btn-cancel" onClick={onClose}>
                        <i className="fas fa-times"></i> Cancel
                    </button>
                    <button
                        className="edit-btn edit-btn-save"
                        onClick={handleSave}
                        disabled={!isDirty() || saving}
                    >
                        {saving ? (
                            <>
                                <i className="fas fa-spinner fa-spin"></i> Saving...
                            </>
                        ) : (
                            <>
                                <i className="fas fa-save"></i> Save
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default EditPaperModal;
