import React, { useState, useEffect } from "react";
import { signInWithEmailAndPassword, createUserWithEmailAndPassword } from "firebase/auth";
import { auth } from "./firebase";
import "./styles/LoginModal.css";

const LoginModal = ({ isOpen, onClose, onAdminLogin }) => {
  const [isLoginForm, setIsLoginForm] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");

  // Reset to login form and clear fields when modal opens
  useEffect(() => {
    if (isOpen) {
      setIsLoginForm(true);
      setEmail("");
      setPassword("");
      setConfirmPassword("");
      setError("");
    }
  }, [isOpen]);

  // Clear fields when toggling between login and signup
  const toggleForm = (toLogin) => {
    setIsLoginForm(toLogin);
    setEmail("");
    setPassword("");
    setConfirmPassword("");
    setError("");
  };

  if (!isOpen) return null;

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await signInWithEmailAndPassword(auth, email, password);

      // Silently try admin login with the same credentials
      try {
        const res = await fetch("http://localhost:8000/api/admin/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        const data = await res.json();
        if (data.success && data.token && onAdminLogin) {
          onAdminLogin(data.token);
        }
      } catch {
        // Silently ignore — not an admin user
      }

      onClose();
    } catch (err) {
      if (err.code === "auth/invalid-credential") {
        setError("Invalid Email or Password");
      } else {
        setError(err.message);
      }
    }
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    try {
      await createUserWithEmailAndPassword(auth, email, password);
      setEmail("");
      setPassword("");
      setConfirmPassword("");
      onClose();
    } catch (err) {
      if (err.code === "auth/email-already-in-use") {
        setError("Email is already registered");
      } else if (err.code === "auth/invalid-email") {
        setError("Invalid email format");
      } else {
        setError(err.message);
      }
    }
  };

  // Function to render label characters dynamically
  const renderLabelChars = (labelText) => {
    return labelText.split("").map((char, index) => (
      <span key={index} className="label-char" style={{ "--index": index }}>
        {char}
      </span>
    ));
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <button className="modal-close" onClick={onClose}>
          ×
        </button>
        {isLoginForm ? (
          <div className="card">
            <a className="login">Login</a>
            {error && <p className="error-message">{error}</p>}
            <div className="wave-group">
              <input
                required
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <span className="bar"></span>
              <label className="label">{renderLabelChars("Email")}</label>
            </div>
            <div className="wave-group">
              <input
                required
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <span className="bar"></span>
              <label className="label">{renderLabelChars("Password")}</label>
            </div>
            <button className="enter" onClick={handleLogin}>
              Enter
            </button>
            <p className="toggle-form">
              Don't have an account?{" "}
              <a href="#" onClick={() => toggleForm(false)}>
                Signup
              </a>
            </p>
          </div>
        ) : (
          <div className="card">
            <a className="login">SignUp</a>
            {error && <p className="error-message">{error}</p>}
            <div className="wave-group">
              <input
                required
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <span className="bar"></span>
              <label className="label">{renderLabelChars("Email")}</label>
            </div>
            <div className="wave-group">
              <input
                required
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <span className="bar"></span>
              <label className="label">{renderLabelChars("Password")}</label>
            </div>
            <div className="wave-group">
              <input
                required
                type="password"
                className="input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              <span className="bar"></span>
              <label className="label">{renderLabelChars("Confirm Password")}</label>
            </div>
            <button className="enter" onClick={handleSignup}>
              Sign Up
            </button>
            <p className="toggle-form">
              Already have an account?{" "}
              <a href="#" onClick={() => toggleForm(true)}>
                Login
              </a>
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default LoginModal;