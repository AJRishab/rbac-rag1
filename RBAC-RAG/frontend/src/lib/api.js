// frontend/src/lib/api.js

import axios from "axios";
import { supabase } from "@/lib/supabaseClient";

// Read the backend URL from .env
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(
  /\/$/,
  ""
);

export const API_BASE = `${BACKEND_URL}/api`;

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
      await supabase.auth.signOut();
    }

    return Promise.reject(error);
  }
);
