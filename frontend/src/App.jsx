// App.jsx
import React, { useState, useEffect, useRef } from "react";
import vitapLogo from "./assets/vitap_logo.png";
import axios from "axios";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { auth, db } from "./firebase";
import { collection, doc, setDoc, getDoc, updateDoc, arrayUnion, arrayRemove } from "firebase/firestore";
import "./styles/App.css";
import LoginButton from "./LoginButton.jsx";
import LoginModal from "./LoginModal.jsx";
import SavedPapers from "./SavedPapers.jsx";
import EditPaperModal from "./EditPaperModal.jsx";
import PdfViewer from "./PdfViewer.jsx";

export default function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [facets, setFacets] = useState({ subjects: [], year: [], size_mb: [] });
  const [selectedSubjects, setSelectedSubjects] = useState([]);
  const [yearRange, setYearRange] = useState({ from: "", to: "" });
  const [sizeRange, setSizeRange] = useState({ from: "", to: "" });
  const [selectedAuthors, setSelectedAuthors] = useState([]);
  const [selectedSizes, setSelectedSizes] = useState([]);
  const [authorSearch, setAuthorSearch] = useState("");
  const [subjectSearch, setSubjectSearch] = useState("");
  const [authorSuggestions, setAuthorSuggestions] = useState([]);
  const [isSubjectDropdownOpen, setIsSubjectDropdownOpen] = useState(false);
  const [isAuthorDropdownOpen, setIsAuthorDropdownOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const [expandedAbstracts, setExpandedAbstracts] = useState({});
  const [yearError, setYearError] = useState(null);
  const [sizeError, setSizeError] = useState(null);
  const [minLoadingTimeout, setMinLoadingTimeout] = useState(null);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState("");
  const [isUserDropdownOpen, setIsUserDropdownOpen] = useState(false);
  const [savedPapers, setSavedPapers] = useState([]);
  const [showSavedPapers, setShowSavedPapers] = useState(false);
  const [userName, setUserName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminToken, setAdminToken] = useState(null);
  const [editingPaper, setEditingPaper] = useState(null);
  const [viewingPdf, setViewingPdf] = useState(null); // { fileUrl, title }
  const [isFiltersOpen, setIsFiltersOpen] = useState(true);
  const dropdownRef = useRef(null);

  const resultsPerPage = 5;

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      setUser(currentUser);
      setAuthError("");
      if (currentUser) {
        try {
          const userDocRef = doc(db, "users", currentUser.uid);
          const userDoc = await getDoc(userDocRef);
          if (userDoc.exists()) {
            const userData = userDoc.data();
            setSavedPapers(userData.savedPapers || []);
            setUserName(userData.name || currentUser.email.split("@")[0]);
          } else {
            await setDoc(userDocRef, { savedPapers: [], name: currentUser.email.split("@")[0] });
            setSavedPapers([]);
            setUserName(currentUser.email.split("@")[0]);
          }
        } catch (error) {
          console.error("Error fetching user data:", error);
        }

        // Restore admin session from stored token
        try {
          const storedToken = localStorage.getItem("adminToken");
          if (storedToken) {
            const verifyRes = await fetch("http://localhost:8000/api/admin/verify", {
              headers: { Authorization: `Bearer ${storedToken}` },
            });
            const verifyData = await verifyRes.json();
            if (verifyData.success) {
              setIsAdmin(true);
              setAdminToken(storedToken);
            } else {
              localStorage.removeItem("adminToken");
              setIsAdmin(false);
              setAdminToken(null);
            }
          }
        } catch {
          // Silently ignore token verify failures
        }
      } else {
        setSavedPapers([]);
        setUserName("");
        setIsAdmin(false);
        setAdminToken(null);
        localStorage.removeItem("adminToken");
      }
    });
    return () => unsubscribe();
  }, []);



  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsUserDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const debounce = (func, delay) => {
    let timeoutId;
    return (...args) => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => func(...args), delay);
    };
  };

  const validateFilters = () => {
    let isValid = true;
    setYearError(null);
    setSizeError(null);

    const { from: yearFrom, to: yearTo } = yearRange;
    if (
      (yearFrom && (yearFrom.length !== 4 || isNaN(yearFrom))) ||
      (yearTo && (yearTo.length !== 4 || isNaN(yearTo)))
    ) {
      setYearError("Please enter valid 4-digit years");
      isValid = false;
    } else if (yearFrom && yearTo && parseInt(yearFrom) > parseInt(yearTo)) {
      setYearError("End year must be after start year");
      isValid = false;
    }

    const { from: sizeFrom, to: sizeTo } = sizeRange;
    const sizeFacetMax =
      facets.size_mb.length > 0
        ? Math.max(...facets.size_mb.map((s) => parseFloat(s.key) + 1))
        : 0;

    if (
      (sizeFrom && (isNaN(sizeFrom) || parseFloat(sizeFrom) < 0)) ||
      (sizeTo && (isNaN(sizeTo) || parseFloat(sizeTo) < 0)) ||
      (sizeFrom && sizeTo && parseFloat(sizeFrom) > parseFloat(sizeTo)) ||
      (sizeTo && parseFloat(sizeTo) > sizeFacetMax)
    ) {
      setSizeError(`Invalid size range (0 - ${sizeFacetMax} MB)`);
      isValid = false;
    }

    return isValid;
  };

  const resetFilters = () => {
    setSelectedSubjects([]);
    setYearRange({ from: "", to: "" });
    setSizeRange({ from: "", to: "" });
    setSelectedAuthors([]);
    setSelectedSizes([]);
    setSubjectSearch("");
    setAuthorSearch("");
  };

  const handleSearch = async (page = 1, isNewSearch = false) => {
    if (!query.trim()) return;

    if (isNewSearch) {
      resetFilters();
      setCurrentPage(1);
      setResults([]);
      setFacets({ subjects: [], year: [], size_mb: [] });
      setTotalResults(0);
      setExpandedAbstracts({});
      setAuthorSuggestions([]);
      setViewingPdf(null);       // exit PDF viewer on new search
      setShowSavedPapers(false); // exit saved papers on new search
    }

    if (!isNewSearch && !validateFilters()) {
      setResults([]);
      setTotalResults(0);
      setLoading(false);
      return;
    }

    let computedSizeRange = null;
    if (selectedSizes.length > 0) {
      const sizeNumbers = selectedSizes.map((s) => parseFloat(s));
      computedSizeRange = {
        from: Math.min(...sizeNumbers),
        to: Math.max(...sizeNumbers) + 1,
      };
    } else if (sizeRange.from || sizeRange.to) {
      computedSizeRange = {
        from: sizeRange.from ? parseFloat(sizeRange.from) : null,
        to: sizeRange.to ? parseFloat(sizeRange.to) : null,
      };
    }

    const filtersToUse = {
      subjects: selectedSubjects,
      yearRange: yearRange.from || yearRange.to
        ? {
          from: yearRange.from ? parseInt(yearRange.from) : null,
          to: yearRange.to ? parseInt(yearRange.to) : null,
        }
        : null,
      sizeRange: computedSizeRange,
      authors: selectedAuthors,
    };

    setLoading(true);
    setHasSearched(true);
    if (!isNewSearch) setCurrentPage(page);

    if (minLoadingTimeout) {
      clearTimeout(minLoadingTimeout);
    }

    try {
      const response = await axios.post("http://localhost:8000/api/search", {
        query,
        filters: filtersToUse,
        page,
        size: resultsPerPage,
      });

      const searchResults = response.data.results || [];
      setResults(searchResults);
      setTotalResults(response.data.total || 0);

      if (searchResults.length > 0) {
        setFacets({
          subjects: response.data.facets?.subjects || [],
          year: response.data.facets?.year || [],
          size_mb: response.data.facets?.size_mb || [],
        });

        const allAuthors = [];
        searchResults.forEach((result) => {
          if (result.authors && Array.isArray(result.authors)) {
            result.authors.forEach((author) => {
              if (!allAuthors.some((a) => a.key === author)) {
                allAuthors.push({ key: author, doc_count: 1 });
              } else {
                allAuthors.find((a) => a.key === author).doc_count += 1;
              }
            });
          }
        });
        setAuthorSuggestions(allAuthors);
      } else {
        setAuthorSuggestions([]);
      }
    } catch (error) {
      console.error("Search error:", error);
      setResults([]);
      setTotalResults(0);
      setAuthorSuggestions([]);
    } finally {
      setMinLoadingTimeout(
        setTimeout(() => {
          setLoading(false);
          setMinLoadingTimeout(null);
        }, 450)
      );
    }
  };

  const debouncedSearch = debounce((page) => handleSearch(page, false), 500);

  useEffect(() => {
    if (hasSearched && query.trim() !== "") {
      debouncedSearch(currentPage);
    }
  }, [selectedSubjects, yearRange, sizeRange, selectedAuthors, selectedSizes]);

  const filterAuthors = () => {
    if (!results.length) {
      setAuthorSuggestions([]);
      return;
    }

    const allAuthors = [];
    results.forEach((result) => {
      if (result.authors && Array.isArray(result.authors)) {
        result.authors.forEach((author) => {
          if (!allAuthors.some((a) => a.key === author)) {
            allAuthors.push({ key: author, doc_count: 1 });
          } else {
            allAuthors.find((a) => a.key === author).doc_count += 1;
          }
        });
      }
    });

    if (!authorSearch.trim()) {
      setAuthorSuggestions(allAuthors);
      return;
    }

    const searchTerm = authorSearch.toLowerCase();
    const filtered = allAuthors.filter((author) =>
      author.key.toLowerCase().includes(searchTerm)
    );
    setAuthorSuggestions(filtered);
  };

  useEffect(() => {
    if (isAuthorDropdownOpen) {
      filterAuthors();
    }
  }, [authorSearch, isAuthorDropdownOpen, results]);

  const handleAuthorSelect = (author) => {
    setSelectedAuthors((prev) =>
      prev.includes(author.key)
        ? prev.filter((a) => a !== author.key)
        : [...prev, author.key]
    );
  };

  const handleSubjectSelect = (subject) => {
    setSelectedSubjects((prev) =>
      prev.includes(subject.key)
        ? prev.filter((s) => s !== subject.key)
        : [...prev, subject.key]
    );
  };

  const handleSizeSelect = (sizeKey) => {
    setSelectedSizes((prev) =>
      prev.includes(sizeKey) ? prev.filter((s) => s !== sizeKey) : [...prev, sizeKey]
    );
    setSizeRange({ from: "", to: "" });
  };

  const toggleAbstract = (index) => {
    setExpandedAbstracts((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const toggleSubjectsDropdown = () => {
    setIsSubjectDropdownOpen(!isSubjectDropdownOpen);
    if (!isSubjectDropdownOpen) {
      setIsAuthorDropdownOpen(false);
    }
  };

  const toggleAuthorsDropdown = () => {
    setIsAuthorDropdownOpen(!isAuthorDropdownOpen);
    if (!isAuthorDropdownOpen) {
      setIsSubjectDropdownOpen(false);
    }
  };

  const filteredSubjects =
    subjectSearch.trim() !== ""
      ? facets.subjects.filter((subject) =>
        subject.key.toLowerCase().includes(subjectSearch.toLowerCase())
      )
      : facets.subjects;

  const totalPages = Math.ceil(totalResults / resultsPerPage);
  const goToNextPage = () => {
    if (currentPage < totalPages) handleSearch(currentPage + 1, false);
  };

  const goToPreviousPage = () => {
    if (currentPage > 1) handleSearch(currentPage - 1, false);
  };

  const renderPageNumbers = () => {
    const pageNumbers = [];
    const maxPagesToShow = 5;
    const halfRange = Math.floor(maxPagesToShow / 2);

    let startPage = Math.max(1, currentPage - halfRange);
    let endPage = Math.min(totalPages, currentPage + halfRange);

    if (currentPage <= halfRange) {
      endPage = Math.min(totalPages, maxPagesToShow);
    }
    if (currentPage + halfRange >= totalPages) {
      startPage = Math.max(1, totalPages - maxPagesToShow + 1);
    }

    if (startPage > 1) {
      pageNumbers.push(
        <button
          key={1}
          onClick={() => handleSearch(1, false)}
          className="pagination-button page-number"
        >
          1
        </button>
      );
      if (startPage > 2) {
        pageNumbers.push(<span key="start-ellipsis" className="ellipsis">…</span>);
      }
    }

    for (let i = startPage; i <= endPage; i++) {
      pageNumbers.push(
        <button
          key={i}
          onClick={() => handleSearch(i, false)}
          className={`pagination-button page-number ${i === currentPage ? "active" : ""}`}
        >
          {i}
        </button>
      );
    }

    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        pageNumbers.push(<span key="end-ellipsis" className="ellipsis">…</span>);
      }
      pageNumbers.push(
        <button
          key={totalPages}
          onClick={() => handleSearch(totalPages, false)}
          className="pagination-button page-number"
        >
          {totalPages}
        </button>
      );
    }

    return pageNumbers;
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter") {
      handleSearch(1, true);
    }
  };

  const highlightMatch = (text, searchTerm) => {
    if (!searchTerm.trim()) return text;

    const regex = new RegExp(`(${searchTerm.trim()})`, "gi");
    const parts = text.split(regex);

    return parts.map((part, index) => {
      if (part.toLowerCase() === searchTerm.toLowerCase()) {
        return (
          <strong key={index} style={{ backgroundColor: "#ffffc7" }}>
            {part}
          </strong>
        );
      }
      return part;
    });
  };

  useEffect(() => {
    return () => {
      if (minLoadingTimeout) {
        clearTimeout(minLoadingTimeout);
      }
    };
  }, [minLoadingTimeout]);

  const handleLoginClick = () => {
    setIsLoginModalOpen(true);
  };

  const handleLogout = async () => {
    try {
      await signOut(auth);
      setResults([]);
      setHasSearched(false);
      setQuery("");
      resetFilters();
      setIsLoginModalOpen(false);
      setIsUserDropdownOpen(false);
      setSavedPapers([]);
      setShowSavedPapers(false);
    } catch (err) {
      console.error("Logout error:", err);
    }
  };

  const handleSavePaper = async (article) => {
    if (!user) {
      setAuthError("Please login to save papers");
      setIsLoginModalOpen(true);
      return;
    }

    if (savedPapers.some((paper) => paper.title === article.title)) {
      return;
    }

    try {
      const userDocRef = doc(db, "users", user.uid);
      await updateDoc(userDocRef, {
        savedPapers: arrayUnion(article),
      });
      setSavedPapers((prev) => [...prev, article]);
    } catch (error) {
      console.error("Error saving paper:", error);
      setAuthError("Failed to save paper");
      setIsLoginModalOpen(true);
    }
  };

  const handleRemoveSavedPaper = async (title) => {
    if (!user) return;

    try {
      const userDocRef = doc(db, "users", user.uid);
      const paperToRemove = savedPapers.find((paper) => paper.title === title);
      if (paperToRemove) {
        await updateDoc(userDocRef, {
          savedPapers: arrayRemove(paperToRemove),
        });
        setSavedPapers((prev) => prev.filter((paper) => paper.title !== title));
      }
    } catch (error) {
      console.error("Error removing paper:", error);
      setAuthError("Failed to remove paper");
      setIsLoginModalOpen(true);
    }
  };

  const handleViewSavedPapers = () => {
    setShowSavedPapers(true);
    setIsUserDropdownOpen(false);
  };

  const handleCloseSavedPapers = () => {
    setShowSavedPapers(false);
  };

  const toggleUserDropdown = () => {
    setIsUserDropdownOpen((prev) => !prev);
  };

  const handleCloseModal = () => {
    setIsLoginModalOpen(false);
    setAuthError("");
  };

  // ── Admin auth handlers ─────────────────────────────────────────────
  const handleAdminLogin = (token) => {
    setAdminToken(token);
    setIsAdmin(true);
    localStorage.setItem("adminToken", token);
  };

  const handleAdminLogout = () => {
    setAdminToken(null);
    setIsAdmin(false);
    localStorage.removeItem("adminToken");
  };

  // ── Paper edit handlers ─────────────────────────────────────────────
  const handleEditPaper = (paper) => {
    setEditingPaper(paper);
  };

  const handleEditSaveSuccess = (paperId, updatedFields) => {
    setResults((prev) =>
      prev.map((r) =>
        r.id === paperId ? { ...r, ...updatedFields } : r
      )
    );
  };

  const handleCloseEditModal = () => {
    setEditingPaper(null);
  };

  // ── PDF viewer handlers ─────────────────────────────────────────────
  const getDownloadFilename = (paper) => {
    if (!paper || !paper.title) return "paper.pdf";
    const cleanedTitle = paper.title
      .replace(/[^a-zA-Z0-9\s]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    // Use original filename from URL if possible, fallback to paper.pdf
    const originalFilename = paper.fileUrl ? paper.fileUrl.split("/").pop() : "paper.pdf";
    return `${cleanedTitle}_${originalFilename}`;
  };

  const handleViewPdf = (article) => {
    setShowSavedPapers(false); // close saved papers panel so PDF viewer renders
    setViewingPdf({ fileUrl: article.fileUrl, title: article.title });
  };

  const handleBackFromViewer = () => {
    setViewingPdf(null);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="app-header-bg"></div>
        <div style={{ backgroundColor: "white", padding: "10px", display: "inline-block", position: "relative", zIndex: 2 }}>
          <img
            src={vitapLogo}
            alt="VITAP Logo"
          />
        </div>
        <div className="header-content" style={{ position: "relative", zIndex: 2 }}>
          <h1>VITAP Research Hub</h1>
          <p>Discover academic publications from VITAP University</p>
        </div>
        <div className="header-login" style={{ position: "relative", zIndex: 10 }}>
          {!user && (
            <LoginButton onClick={handleLoginClick} />
          )}
        </div>
      </header>

      {user && (
        <div className="user-dropdown">
          <button
            className="user-profile-button"
            onClick={toggleUserDropdown}
          >
            <i className="fas fa-user"></i>
            {userName || user.email.split("@")[0]}
          </button>
          {isUserDropdownOpen && (
            <ul className="user-dropdown-menu">
              <li
                className="user-dropdown-item"
                onClick={handleViewSavedPapers}
              >
                <i className="fas fa-bookmark"></i> Saved
              </li>
              <li
                className="user-dropdown-item"
                onClick={handleLogout}
              >
                <i className="fas fa-sign-out-alt"></i> Logout
              </li>
            </ul>
          )}
        </div>
      )}

      <LoginModal
        isOpen={isLoginModalOpen}
        onClose={handleCloseModal}
        errorMessage={authError}
        onAdminLogin={handleAdminLogin}
      />

      <EditPaperModal
        isOpen={!!editingPaper}
        paper={editingPaper}
        adminToken={adminToken}
        onClose={handleCloseEditModal}
        onSaveSuccess={handleEditSaveSuccess}
      />

      <div className={`search-bar ${hasSearched ? "search-bar-top" : "search-bar-center"}`}>
        <div className="search-container">
          <input
            type="text"
            id="search-input"
            placeholder="Search papers, authors, keywords, or entities..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            style={{ color: "black" }}
          />
          <button id="search-button" onClick={() => handleSearch(1, true)} disabled={loading}>
            {loading ? (
              <i className="fas fa-spinner fa-spin"></i>
            ) : (
              <i className="fas fa-search"></i>
            )}
            {loading ? " Searching..." : " Search"}
          </button>
          {/* Live search typing indicator */}
          {/* {query.trim().length > 0 && !hasSearched && (
            <div className="search-typing-indicator">
              <i className="fas fa-search"></i>
              <span>Searching for: <strong>{query}</strong></span>
              <span className="typing-hint">Press Enter or click Search</span>
            </div>
          )}
          {query.trim().length > 0 && hasSearched && (
            <div className="search-active-query">
              <i className="fas fa-check-circle"></i>
              <span>Results for: <strong>{query}</strong></span>
              {totalResults > 0 && <span className="query-result-count">{totalResults} papers found</span>}
            </div>
          )} */}
        </div>

      </div>

      <main className="main-content">
        {showSavedPapers ? (
          <SavedPapers
            savedPapers={savedPapers}
            onRemove={handleRemoveSavedPaper}
            onClose={handleCloseSavedPapers}
            onViewPdf={handleViewPdf}
            getDownloadFilename={getDownloadFilename}
          />
        ) : viewingPdf ? (
          <PdfViewer
            fileUrl={viewingPdf.fileUrl}
            title={viewingPdf.title}
            onBack={handleBackFromViewer}
            getDownloadFilename={getDownloadFilename}
          />
        ) : hasSearched ? (
          <>
            {/* Filter toggle button — always visible */}
            <button
              className={`filter-toggle-btn ${isFiltersOpen ? "open" : "closed"}`}
              onClick={() => setIsFiltersOpen((prev) => !prev)}
              aria-expanded={isFiltersOpen}
              aria-controls="filters-panel"
              aria-label={isFiltersOpen ? "Close filters" : "Open filters"}
            >
              <i className={`fas fa-sliders-h`} aria-hidden="true"></i>
              <span>{isFiltersOpen ? "Filters ◂" : "Filters ▸"}</span>
            </button>

            <div
              id="filters-panel"
              className={`filters-sidebar${isFiltersOpen ? " filters-sidebar--closed" : " filters-sidebar--open"}`}
              aria-hidden={!isFiltersOpen}
            >
              <div className="filters scrollable-section">
                <div className="filter-header">
                  <h2><i className="fas fa-sliders-h"></i> Refine Search</h2>
                  {(selectedSubjects.length > 0 || selectedAuthors.length > 0 || yearRange.from || yearRange.to || sizeRange.from || sizeRange.to) && (
                    <span className="active-filter-badge">
                      {selectedSubjects.length + selectedAuthors.length + (yearRange.from || yearRange.to ? 1 : 0) + (sizeRange.from || sizeRange.to ? 1 : 0)} active
                    </span>
                  )}
                </div>
                <div className="filter-actions">
                  <button className="apply-filters-btn" onClick={() => handleSearch(1, true)}>
                    <i className="fas fa-filter"></i> Apply Filters
                  </button>
                  <button className="clear-filters-btn" onClick={resetFilters}>
                    <i className="fas fa-times"></i> Clear All
                  </button>
                </div>
                <div className="filter-content">
                  <div className="filter-group">
                    <label>
                      <i className="fas fa-book"></i> Subjects
                    </label>
                    <div className="dropdown-container">
                      <div className="dropdown-header" onClick={toggleSubjectsDropdown}>
                        <input
                          type="text"
                          placeholder="Search subjects..."
                          value={subjectSearch}
                          onChange={(e) => setSubjectSearch(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="subject-search-input"
                        />
                        <i className={`fas fa-chevron-${isSubjectDropdownOpen ? "up" : "down"}`}></i>
                      </div>

                      {isSubjectDropdownOpen && (
                        <ul className="subject-dropdown">
                          {filteredSubjects.length > 0 ? (
                            filteredSubjects.map((subject) => (
                              <li
                                key={subject.key}
                                className={`dropdown-item ${selectedSubjects.includes(subject.key) ? "selected" : ""
                                  }`}
                                onClick={() => handleSubjectSelect(subject)}
                              >
                                <span className="checkbox">
                                  {selectedSubjects.includes(subject.key) && (
                                    <i className="fas fa-check"></i>
                                  )}
                                </span>
                                {subjectSearch.trim() !== ""
                                  ? highlightMatch(subject.key, subjectSearch)
                                  : subject.key}{" "}
                                <span className="count">({subject.doc_count})</span>
                              </li>
                            ))
                          ) : (
                            <li className="no-results">No subjects match your search</li>
                          )}
                        </ul>
                      )}

                      {selectedSubjects.length > 0 && (
                        <div className="selected-subjects">
                          {selectedSubjects.map((subject) => (
                            <span key={subject} className="selected-subject-tag">
                              {subject}
                              <button onClick={() => handleSubjectSelect({ key: subject })}>
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* <div className="filter-group">
                  <label>
                    <i className="fas fa-calendar"></i> Publication Year
                  </label>
                  <div className="year-range">
                    <input
                      type="number"
                      placeholder="First"
                      value={yearRange.from}
                      onChange={(e) => setYearRange({ ...yearRange, from: e.target.value })}
                      className="year-input"
                      min="1900"
                      max="2100"
                    />
                    <input
                      type="number"
                      placeholder="Last"
                      value={yearRange.to}
                      onChange={(e) => setYearRange({ ...yearRange, to: e.target.value })}
                      className="year-input"
                      min="1900"
                      max="2100"
                    />
                  </div>
                  {yearError && <div className="error-message">{yearError}</div>}
                </div> */}

                  <div className="filter-group">
                    <label>
                      <i className="fas fa-file-alt"></i> File Size (MB)
                    </label>
                    <div className="year-range">
                      <input
                        type="number"
                        placeholder="Min"
                        value={sizeRange.from}
                        onChange={(e) => setSizeRange({ ...sizeRange, from: e.target.value })}
                        className="year-input"
                        min="0"
                        step="0.1"
                      />
                      <input
                        type="number"
                        placeholder="Max"
                        value={sizeRange.to}
                        onChange={(e) => setSizeRange({ ...sizeRange, to: e.target.value })}
                        className="year-input"
                        min="0"
                        step="0.1"
                      />
                    </div>
                    {sizeError && <div className="error-message">{sizeError}</div>}
                    {facets.size_mb.length > 0 && (
                      <div>
                        {facets.size_mb.map((size) => (
                          <div key={size.key} className="filter-item">
                            <input
                              type="checkbox"
                              checked={selectedSizes.includes(size.key)}
                              onChange={() => handleSizeSelect(size.key)}
                            />
                            <span>
                              {size.key} - {parseFloat(size.key) + 1} MB ({size.doc_count})
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="filter-group">
                    <label>
                      <i className="fas fa-user"></i> Authors
                    </label>
                    <div className="dropdown-container">
                      <div className="dropdown-header" onClick={toggleAuthorsDropdown}>
                        <input
                          type="text"
                          placeholder="Search authors..."
                          value={authorSearch}
                          onChange={(e) => setAuthorSearch(e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          className="subject-search-input"
                        />
                        <i className={`fas fa-chevron-${isAuthorDropdownOpen ? "up" : "down"}`}></i>
                      </div>

                      {isAuthorDropdownOpen && (
                        <ul className="subject-dropdown">
                          {authorSuggestions.length > 0 ? (
                            authorSuggestions.map((author) => (
                              <li
                                key={author.key}
                                className={`dropdown-item ${selectedAuthors.includes(author.key) ? "selected" : ""
                                  }`}
                                onClick={() => handleAuthorSelect(author)}
                              >
                                <span className="checkbox">
                                  {selectedAuthors.includes(author.key) && (
                                    <i className="fas fa-check"></i>
                                  )}
                                </span>
                                {highlightMatch(author.key, authorSearch)}{" "}
                                <span className="count">({author.doc_count})</span>
                              </li>
                            ))
                          ) : (
                            <li className="no-results">No authors available</li>
                          )}
                        </ul>
                      )}

                      {selectedAuthors.length > 0 && (
                        <div className="selected-subjects">
                          {selectedAuthors.map((author) => (
                            <span key={author} className="selected-subject-tag">
                              {author}
                              <button
                                onClick={() =>
                                  setSelectedAuthors(selectedAuthors.filter((a) => a !== author))
                                }
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>{/* end filters-sidebar */}

            <div className="results scrollable-section">
              <div className="results-header">
                <h2>Research Papers</h2>
                <div className="results-count">
                  {totalResults > 0 ? `Showing ${totalResults} results` : "No results found"}
                </div>
              </div>
              <div id="results-list">
                {loading ? (
                  <div className="loader-container">
                    <div className="loader">
                      <div>
                        <ul>
                          <li>
                            <svg fill="currentColor" viewBox="0 0 90 120">
                              <path d="M90,0 L90,120 L11,120 C4.92486775,120 0,115.075132 0,109 L0,11 C0,4.92486775 4.92486775,0 11,0 L90,0 Z M71.5,81 L18.5,81 C17.1192881,81 16,82.1192881 16,83.5 C16,84.8254834 17.0315359,85.9100387 18.3356243,85.9946823 L18.5,86 L71.5,86 C72.8807119,86 74,84.8807119 74,83.5 C74,82.1745166 72.9684641,81.0899613 71.6643757,81.0053177 L71.5,81 Z M71.5,57 L18.5,57 C17.1192881,57 16,58.1192881 16,59.5 C16,60.8254834 17.0315359,61.9100387 18.3356243,61.9946823 L18.5,62 L71.5,62 C72.8807119,62 74,60.8807119 74,59.5 C74,58.1192881 72.8807119,57 71.5,57 Z M71.5,33 L18.5,33 C17.1192881,33 16,34.1192881 16,35.5 C16,36.8254834 17.0315359,37.9100387 18.3356243,37.9946823 L18.5,38 L71.5,38 C72.8807119,38 74,36.8807119 74,35.5 C74,34.1192881 72.8807119,33 71.5,33 Z"></path>
                            </svg>
                          </li>
                          <li>
                            <svg fill="currentColor" viewBox="0 0 90 120">
                              <path d="M90,0 L90,120 L11,120 C4.92486775,120 0,115.075132 0,109 L0,11 C0,4.92486775 4.92486775,0 11,0 L90,0 Z M71.5,81 L18.5,81 C17.1192881,81 16,82.1192881 16,83.5 C16,84.8254834 17.0315359,85.9100387 18.3356243,85.9946823 L18.5,86 L71.5,86 C72.8807119,86 74,84.8807119 74,83.5 C74,82.1745166 72.9684641,81.0899613 71.6643757,81.0053177 L71.5,81 Z M71.5,57 L18.5,57 C17.1192881,57 16,58.1192881 16,59.5 C16,60.8254834 17.0315359,61.9100387 18.3356243,61.9946823 L18.5,62 L71.5,62 C72.8807119,62 74,60.8807119 74,59.5 C74,58.1192881 72.8807119,57 71.5,57 Z M71.5,33 L18.5,33 C17.1192881,33 16,34.1192881 16,35.5 C16,36.8254834 17.0315359,37.9100387 18.3356243,37.9946823 L18.5,38 L71.5,38 C72.8807119,38 74,36.8807119 74,35.5 C74,34.1192881 72.8807119,33 71.5,33 Z"></path>
                            </svg>
                          </li>
                          <li>
                            <svg fill="currentColor" viewBox="0 0 90 120">
                              <path d="M90,0 L90,120 L11,120 C4.92486775,120 0,115.075132 0,109 L0,11 C0,4.92486775 4.92486775,0 11,0 L90,0 Z M71.5,81 L18.5,81 C17.1192881,81 16,82.1192881 16,83.5 C16,84.8254834 17.0315359,85.9100387 18.3356243,85.9946823 L18.5,86 L71.5,86 C72.8807119,86 74,84.8807119 74,83.5 C74,82.1745166 72.9684641,81.0899613 71.6643757,81.0053177 L71.5,81 Z M71.5,57 L18.5,57 C17.1192881,57 16,58.1192881 16,59.5 C16,60.8254834 17.0315359,61.9100387 18.3356243,61.9946823 L18.5,62 L71.5,62 C72.8807119,62 74,60.8807119 74,59.5 C74,58.1192881 72.8807119,57 71.5,57 Z M71.5,33 L18.5,33 C17.1192881,33 16,34.1192881 16,35.5 C16,36.8254834 17.0315359,37.9100387 18.3356243,37.9946823 L18.5,38 L71.5,38 C72.8807119,38 74,36.8807119 74,35.5 C74,34.1192881 72.8807119,33 71.5,33 Z"></path>
                            </svg>
                          </li>
                          <li>
                            <svg fill="currentColor" viewBox="0 0 90 120">
                              <path d="M90,0 L90,120 L11,120 C4.92486775,120 0,115.075132 0,109 L0,11 C0,4.92486775 4.92486775,0 11,0 L90,0 Z M71.5,81 L18.5,81 C17.1192881,81 16,82.1192881 16,83.5 C16,84.8254834 17.0315359,85.9100387 18.3356243,85.9946823 L18.5,86 L71.5,86 C72.8807119,86 74,84.8807119 74,83.5 C74,82.1745166 72.9684641,81.0899613 71.6643757,81.0053177 L71.5,81 Z M71.5,57 L18.5,57 C17.1192881,57 16,58.1192881 16,59.5 C16,60.8254834 17.0315359,61.9100387 18.3356243,61.9946823 L18.5,62 L71.5,62 C72.8807119,62 74,60.8807119 74,59.5 C74,58.1192881 72.8807119,57 71.5,57 Z M71.5,33 L18.5,33 C17.1192881,33 16,34.1192881 16,35.5 C16,36.8254834 17.0315359,37.9100387 18.3356243,37.9946823 L18.5,38 L71.5,38 C72.8807119,38 74,36.8807119 74,35.5 C74,34.1192881 72.8807119,33 71.5,33 Z"></path>
                            </svg>
                          </li>
                          <li>
                            <svg fill="currentColor" viewBox="0 0 90 120">
                              <path d="M90,0 L90,120 L11,120 C4.92486775,120 0,115.075132 0,109 L0,11 C0,4.92486775 4.92486775,0 11,0 L90,0 Z M71.5,81 L18.5,81 C17.1192881,81 16,82.1192881 16,83.5 C16,84.8254834 17.0315359,85.9100387 18.3356243,85.9946823 L18.5,86 L71.5,86 C72.8807119,86 74,84.8807119 74,83.5 C74,82.1745166 72.9684641,81.0899613 71.6643757,81.0053177 L71.5,81 Z M71.5,57 L18.5,57 C17.1192881,57 16,58.1192881 16,59.5 C16,60.8254834 17.0315359,61.9100387 18.3356243,61.9946823 L18.5,62 L71.5,62 C72.8807119,62 74,60.8807119 74,59.5 C74,58.1192881 72.8807119,57 71.5,57 Z M71.5,33 L18.5,33 C17.1192881,33 16,34.1192881 16,35.5 C16,36.8254834 17.0315359,37.9100387 18.3356243,37.9946823 L18.5,38 L71.5,38 C72.8807119,38 74,36.8807119 74,35.5 C74,34.1192881 72.8807119,33 71.5,33 Z"></path>
                            </svg>
                          </li>
                          <li>
                            <svg fill="currentColor" viewBox="0 0 90 120">
                              <path d="M90,0 L90,120 L11,120 C4.92486775,120 0,115.075132 0,109 L0,11 C0,4.92486775 4.92486775,0 11,0 L90,0 Z M71.5,81 L18.5,81 C17.1192881,81 16,82.1192881 16,83.5 C16,84.8254834 17.0315359,85.9100387 18.3356243,85.9946823 L18.5,86 L71.5,86 C72.8807119,86 74,84.8807119 74,83.5 C74,82.1745166 72.9684641,81.0899613 71.6643757,81.0053177 L71.5,81 Z M71.5,57 L18.5,57 C17.1192881,57 16,58.1192881 16,59.5 C16,60.8254834 17.0315359,61.9100387 18.3356243,61.9946823 L18.5,62 L71.5,62 C72.8807119,62 74,60.8807119 74,59.5 C74,58.1192881 72.8807119,57 71.5,57 Z M71.5,33 L18.5,33 C17.1192881,33 16,34.1192881 16,35.5 C16,36.8254834 17.0315359,37.9100387 18.3356243,37.9946823 L18.5,38 L71.5,38 C72.8807119,38 74,36.8807119 74,35.5 C74,34.1192881 72.8807119,33 71.5,33 Z"></path>
                            </svg>
                          </li>
                        </ul>
                      </div>
                      <span>Loading</span>
                    </div>
                  </div>
                ) : results.length > 0 ? (
                  results.map((article, index) => (
                    <div key={index} className="result-item">
                      {/* {article.year && <div className="result-year">{article.year}</div>} */}
                      <h3 className="result-title">{article.title}</h3>
                      <div className="result-meta">
                        {article.authors?.length > 0 && (
                          <span>
                            <i className="fas fa-user"></i> {article.authors.join(", ")}
                          </span>
                        )}
                        {article.publisher && (
                          <span>
                            <i className="fas fa-building"></i> {article.publisher}
                          </span>
                        )}
                        {article.size_mb && (
                          <span>
                            <i className="fas fa-file-alt"></i> {article.size_mb} MB
                          </span>
                        )}
                      </div>
                      {article.abstract && (
                        <div className="abstract-container">
                          <p
                            className={`abstract ${expandedAbstracts[index] ? "expanded" : ""}`}
                          >
                            {article.abstract}
                          </p>
                          <button
                            className="toggle-abstract"
                            onClick={() => toggleAbstract(index)}
                          >
                            {expandedAbstracts[index] ? "Less" : "More"}
                          </button>
                        </div>
                      )}
                      <div className="keywords">
                        {article.keywords?.map((kw, i) => (
                          <span key={i} className="keyword">
                            {kw}
                          </span>
                        ))}
                      </div>
                      {article.fileUrl && (
                        <div className="document-links">

                          <button
                            className="card-view-btn"
                            onClick={() => handleViewPdf(article)}
                            aria-label={`View PDF: ${article.title}`}
                          >
                            <i className="fas fa-eye" aria-hidden="true" style={{ marginRight: "6px" }}></i> View
                          </button>

                          <a
                            href={article.fileUrl}
                            download={getDownloadFilename(article)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="view-link"
                            aria-label={`Download: ${article.title}`}
                          >
                            <i className="fa fa-download" style={{ marginRight: "8px" }}></i> Download
                          </a>

                          {isAdmin && (
                            <button
                              className="edit-card-btn"
                              onClick={() => handleEditPaper(article)}
                              title="Edit paper metadata"
                            >
                              <i className="fas fa-edit"></i> Edit
                            </button>
                          )}

                          <label htmlFor={`checkboxInput-${index}`} className="bookmark">
                            <input
                              type="checkbox"
                              id={`checkboxInput-${index}`}
                              checked={savedPapers.some((paper) => paper.title === article.title)}
                              onChange={() =>
                                savedPapers.some((paper) => paper.title === article.title)
                                  ? handleRemoveSavedPaper(article.title)
                                  : handleSavePaper(article)
                              }
                            />
                            <svg
                              width="15"
                              viewBox="0 0 50 70"
                              fill="none"
                              xmlns="http://www.w3.org/2000/svg"
                              className="svgIcon"
                            >
                              <path
                                d="M46 62.0085L46 3.88139L3.99609 3.88139L3.99609 62.0085L24.5 45.5L46 62.0085Z"
                                stroke="white"
                                strokeWidth="7"
                              ></path>
                            </svg>
                          </label>
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="no-results">
                    <i className="fas fa-search-minus"></i>
                    <p>No matching documents found for your search criteria</p>
                    <button onClick={resetFilters}>Clear filters</button>
                  </div>
                )}
              </div>

              {totalResults > 0 && (
                <div className="pagination enhanced-pagination">
                  <button
                    onClick={goToPreviousPage}
                    disabled={currentPage === 1}
                    className="pagination-button prev-button"
                    aria-label="Previous Page"
                  >
                    <i className="fas fa-chevron-left"></i>
                  </button>

                  <div className="page-numbers">{renderPageNumbers()}</div>

                  <button
                    onClick={goToNextPage}
                    disabled={currentPage === totalPages}
                    className="pagination-button next-button"
                    aria-label="Next Page"
                  >
                    <i className="fas fa-chevron-right"></i>
                  </button>
                </div>
              )}
            </div>
          </>
        ) : null}
      </main>
    </div >
  );
}