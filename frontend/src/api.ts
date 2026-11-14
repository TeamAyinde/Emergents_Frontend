import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const KEY = "nocturne_token";

async function setItem(value: string) {
  if (Platform.OS === "web") {
    try {
      window.localStorage.setItem(KEY, value);
    } catch {}
    return;
  }
  await SecureStore.setItemAsync(KEY, value);
}
async function getItem(): Promise<string | null> {
  if (Platform.OS === "web") {
    try {
      return window.localStorage.getItem(KEY);
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(KEY);
}
async function remove() {
  if (Platform.OS === "web") {
    try {
      window.localStorage.removeItem(KEY);
    } catch {}
    return;
  }
  await SecureStore.deleteItemAsync(KEY);
}

export const tokenStore = { setItem, getItem, remove };

const API_BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: "guest" | "promoter" | "venue_owner" | "admin";
  membership_tier: string;
  referral_code: string;
  wallet_balance: number;
};

export type Venue = {
  id: string;
  name: string;
  city: string;
  state: string;
  category: string;
  image_url: string;
  rating: number;
  price_range: string;
  description: string;
};

export type EventItem = {
  id: string;
  title: string;
  venue_id: string;
  venue_name: string;
  city: string;
  date: string;
  price: number;
  image_url: string;
  description: string;
  tags: string[];
  tickets_sold: number;
};

export type Ticket = {
  id: string;
  event_id: string;
  event_title: string;
  event_date: string;
  venue_name: string;
  user_id: string;
  promoter_id: string | null;
  quantity: number;
  total_paid: number;
  platform_fee: number;
  promoter_earning: number;
  checked_in: boolean;
  created_at: string;
};

export type Reservation = {
  id: string;
  venue_id: string;
  venue_name: string;
  user_id: string;
  date: string;
  party_size: number;
  service_type: string;
  base_price: number;
  platform_fee: number;
  total: number;
  status: string;
  notes: string;
  created_at: string;
};

export type PromoterStats = {
  total_earnings: number;
  tickets_sold: number;
  guests_checked_in: number;
  referral_code: string;
  rank: number;
};

export type LeaderboardEntry = {
  user_id: string;
  full_name: string;
  earnings: number;
  tickets_sold: number;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenStore.getItem();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let msg = "Request failed";
    try {
      const data = await response.json();
      const detail = data?.detail;
      msg = typeof detail === "string" ? detail : Array.isArray(detail) ? "Please check your inputs" : msg;
    } catch {}
    throw new Error(msg);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  register: (body: {
    email: string;
    password: string;
    full_name: string;
    role: User["role"];
    membership_tier: string;
  }) =>
    request<{ access_token: string; user: User }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),

  listEvents: () => request<EventItem[]>("/events?upcoming=true"),
  getEvent: (id: string) => request<EventItem>(`/events/${id}`),

  listVenues: (q?: string) =>
    request<Venue[]>(`/venues${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  getVenue: (id: string) => request<Venue>(`/venues/${id}`),

  purchaseTicket: (body: {
    event_id: string;
    promoter_code?: string;
    quantity: number;
  }) =>
    request<Ticket>("/tickets/purchase", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  myTickets: () => request<Ticket[]>("/tickets/mine"),
  checkInTicket: (id: string) =>
    request<Ticket>(`/tickets/${encodeURIComponent(id)}/checkin`, { method: "POST" }),

  createReservation: (body: {
    venue_id: string;
    date: string;
    party_size: number;
    service_type: string;
    base_price: number;
    notes?: string;
  }) =>
    request<Reservation>("/reservations", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  myReservations: () => request<Reservation[]>("/reservations/mine"),

  promoterStats: () => request<PromoterStats>("/promoter/stats"),
  leaderboard: () => request<LeaderboardEntry[]>("/promoter/leaderboard"),
  withdraw: (amount: number) =>
    request<{ withdrawn: number; fee: number; net: number }>(
      "/promoter/withdraw",
      { method: "POST", body: JSON.stringify({ amount }) },
    ),
};
