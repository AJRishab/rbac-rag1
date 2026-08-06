// frontend/src/lib/api.js

import axios from "axios";
import { supabase } from "@/lib/supabaseClient";

// Read the backend URL from .env
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(
  /\/$/,
  ""
);

export const API_BASE = `${BACKEND_URL}/api`;

// True if the JWT's `exp` (seconds) has already passed. Used to distinguish a
// genuinely expired/revoked session from an arbitrary backend 401.
function _tokenExpired(token) {
  if (!token) return false;
  try {
    const payload = token.split(".")[1];
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/"))
    );
    return typeof json.exp === "number" && json.exp * 1000 <= Date.now();
  } catch {
    return false;
  }
}

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
});

// Attach the Supabase access token to every request
api.interceptors.request.use(
  async (config) => {
    const { data, error } = await supabase.auth.getSession();

    if (error) {
      return config;
    }

    const token = data?.session?.access_token;

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Handle responses
api.interceptors.response.use(
  (response) => {
    return response;
  },

  async (error) => {
    if (error?.response?.status === 401) {
      // Only clear the session on a genuine auth failure — an expired access
      // token or the identity endpoint (/auth/me) rejecting it. A plain 401
      // from another endpoint (non-auth errors, backend quirks) must NOT log
      // the user out without an explicit logout.
      const url = error?.config?.url || "";
      const { data } = await supabase.auth.getSession();
      const token = data?.session?.access_token;
      const isExpired = _tokenExpired(token);
      const isIdentityCheck = url.includes("/auth/me");

      if (isExpired || isIdentityCheck) {
        await supabase.auth.signOut();
      }
    }

    return Promise.reject(error);
  }
);
