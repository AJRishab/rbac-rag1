// Axios instance with base URL + JWT bearer.
//
// Storage: JWT is kept in localStorage so a user survives a full page reload.
// httpOnly cookies would be safer against XSS but require server-side session
// state + CSRF protection, which is out of v1 scope. We mitigate XSS the way
// React does by default (auto-escaping) and by never rendering untrusted HTML.
// On any 401 from the server we drop the token immediately.
import axios from 'axios';

// Empty string = same-origin (Hugging Face Space). Local .env sets http://localhost:8000.
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
export const API_BASE = `${BACKEND_URL}/api`;

const TOKEN_KEY = 'sentry_token';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
});

let _token = null;

function _safeGet() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch (err) {
    // Access to localStorage can throw in incognito / storage-partitioned
    // contexts. We fall back to in-memory only in that case.
    console.warn('[auth] localStorage.getItem failed', err);
    return null;
  }
}

function _safeSet(value) {
  try {
    if (value == null) localStorage.removeItem(TOKEN_KEY);
    else localStorage.setItem(TOKEN_KEY, value);
  } catch (err) {
    console.warn('[auth] localStorage write failed', err);
  }
}

export function setAuthToken(token) {
  _token = token;
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    _safeSet(token);
  } else {
    delete api.defaults.headers.common['Authorization'];
    _safeSet(null);
  }
}

export function getStoredToken() {
  return _safeGet();
}

// Hydrate on module load if a token exists
const existing = _safeGet();
if (existing) {
  _token = existing;
  api.defaults.headers.common['Authorization'] = `Bearer ${existing}`;
}

export function getAuthToken() {
  return _token;
}

// Global 401 handler — drop stale token so the app forces re-login.
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      setAuthToken(null);
    }
    return Promise.reject(err);
  },
);
