import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { api, setAuthToken, getStoredToken } from '@/lib/api';

const AuthContext = createContext(null);

// `api` is a module-scoped axios singleton, `setAuthToken` and `getStoredToken`
// are module-scoped functions, and setState functions from useState are stable
// by React contract. They intentionally do not appear in dependency arrays.

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await api.get('/auth/me');
      setUser(data);
      return data;
    } catch (err) {
      console.warn('[auth] /auth/me failed — clearing session', err?.response?.status || err?.message);
      setUser(null);
      setAuthToken(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const t = getStoredToken();
      if (t) await refreshMe();
      if (!cancelled) setInitializing(false);
    })();
    return () => { cancelled = true; };
  }, [refreshMe]);

  const login = useCallback(async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    setAuthToken(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const register = useCallback(async (email, password) => {
    const { data } = await api.post('/auth/register', { email, password });
    return data;
  }, []);

  const changePassword = useCallback(async (currentPassword, newPassword) => {
    const { data } = await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    setAuthToken(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({
    user, initializing, login, register, logout, refreshMe, changePassword,
  }), [user, initializing, login, register, logout, refreshMe, changePassword]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
