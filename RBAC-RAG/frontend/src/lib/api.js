// Axios instance with base URL + Supabase session bearer token.
//
// The auth token is owned by Supabase (supabase-js persists + auto-refreshes
// the session). We don't store a token in localStorage ourselves — a request
// interceptor pulls the current session's access_token and attaches it as a
// Bearer token to every call to the FastAPI backend. On any 401 we sign the
// Supabase session out so the app returns to login.
import axios from 'axios';
import { supabase } from '@/lib/supabaseClient';

// Empty string = same-origin (Hugging Face Space). Local .env sets http://localhost:8000.
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || '').replace(/\/$/, '');
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 120_000,
});

// Attach the current Supabase session's access_token as a Bearer token.
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Drop the Supabase session on any 401 so the app forces re-login.
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    if (err?.response?.status === 401) {
      await supabase.auth.signOut();
    }
    return Promise.reject(err);
  },
);

