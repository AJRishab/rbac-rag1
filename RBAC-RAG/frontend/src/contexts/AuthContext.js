import React, {
  createContext, useContext, useEffect, useMemo, useState, useCallback,
} from 'react';
import { supabase } from '@/lib/supabaseClient';
import { api } from '@/lib/api';

const AuthContext = createContext(null);

// `api` and `supabase` are stable module-scoped references, and the useState
// setter is stable by React contract — intentionally not in dependency arrays.

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);

  const refreshMe = useCallback(async () => {
    // Fetch the matching profiles row (role/status/must_change_password).
    try {
      const { data } = await api.get('/auth/me');
      setUser(data);
      return data;
    } catch (err) {
      console.warn('[auth] /auth/me failed — clearing session', err?.response?.status || err?.message);
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    // Hydrate from an existing Supabase session on first mount, then fetch /me.
    (async () => {
      const { data } = await supabase.auth.getSession();
      if (data?.session) await refreshMe();
      if (!cancelled) setInitializing(false);
    })();

    // React to sign-in / sign-out / token-refresh events from Supabase.
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) refreshMe();
      else setUser(null);
    });

    return () => {
      cancelled = true;
      listener.subscription.unsubscribe();
    };
  }, [refreshMe]);

  const login = useCallback(async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    const me = await refreshMe();
    if (!me) {
      throw new Error(
        'Signed in, but the server could not load your profile. ' +
        'Check that SUPABASE_URL is set correctly and the backend is running.',
      );
    }
    return me;
  }, [refreshMe]);

  const register = useCallback(async (email, password) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: "https://rbac-rag-nine.vercel.app/auth/callback",
      },
    });
    if (error) throw error;
    return { ok: true, email };
  }, []);

  const changePassword = useCallback(async (newPassword) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
    // Clear the forced-change flag on the profile via the backend.
    await api.post('/auth/change-password');
    return refreshMe();
  }, [refreshMe]);

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
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
