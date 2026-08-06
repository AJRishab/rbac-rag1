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

  // Capacitor Android App Links: when the app is opened via
  // https://rbac-rag-nine.vercel.app/auth/callback, the WebView does NOT
  // navigate there — Capacitor delivers the URL through the `appUrlOpen`
  // event instead. Parse the Supabase session tokens from that URL and set
  // the session (this fires onAuthStateChange → refreshMe above).
  useEffect(() => {
    let active = true;
    let unsub = null;

    (async () => {
      try {
        const { Capacitor } = await import('@capacitor/core');
        const { App } = await import('@capacitor/app');
        if (!Capacitor.isNativePlatform()) return;

        const handleCallback = async (url) => {
          try {
            const parsed = new URL(url);
            if (!parsed.pathname.endsWith('/auth/callback')) return;

            const hash = new URLSearchParams(parsed.hash.replace(/^#/, ''));
            const access_token = hash.get('access_token');
            const refresh_token = hash.get('refresh_token');
            if (access_token && refresh_token) {
              const { error } = await supabase.auth.setSession({ access_token, refresh_token });
              if (error) console.warn('[auth] deep-link setSession failed', error?.message);
            }
          } catch (err) {
            console.warn('[auth] failed to process deep-link callback', err);
          }
        };

        // Handle both a cold launch via the deep link and warm-link events.
        const launch = await App.getLaunchUrl();
        if (launch?.url && active) handleCallback(launch.url);

        const { listener } = await App.addListener('appUrlOpen', ({ url }) => {
          if (active) handleCallback(url);
        });
        unsub = listener.remove;
      } catch {
        // Capacitor plugins unavailable (plain browser) — ignore.
      }
    })();

    return () => {
      active = false;
      if (typeof unsub === 'function') unsub();
    };
  }, []);

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
