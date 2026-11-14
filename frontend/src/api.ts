import * as SecureStore from "expo-secure-store";
import { fetch as expoFetch } from "expo/fetch";
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
  marketing_opt_in: boolean;
  level: "bronze" | "silver" | "gold";
  phone?: string | null;
  city?: string | null;
};

export type SignUpBody = {
  email: string;
  password: string;
  full_name: string;
  role: User["role"];
  membership_tier: string;
  phone?: string;
  city?: string;
  marketing_opt_in: boolean;
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
  min_level: string;
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
  min_level: string;
  capacity: number;
  approval_required: boolean;
  plus_one_limit: number;
  guest_list_visible: boolean;
  has_tables: boolean;
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
  register: (body: SignUpBody) =>
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

  upgrade: (level: string) =>
    request<User>("/membership/upgrade", { method: "POST", body: JSON.stringify({ level }) }),

  conciergeMessages: () => request<ChatMessage[]>("/concierge/messages"),
  conciergeUnread: () => request<{ unread: number }>("/concierge/unread"),
  sendConcierge: (text: string) =>
    request<ChatMessage>("/concierge/messages", { method: "POST", body: JSON.stringify({ text }) }),
  adminThreads: () => request<ChatThread[]>("/admin/concierge/threads"),
  adminThreadMessages: (memberId: string) => request<ChatMessage[]>(`/admin/concierge/${memberId}/messages`),
  adminReply: (memberId: string, text: string) =>
    request<ChatMessage>(`/admin/concierge/${memberId}/messages`, { method: "POST", body: JSON.stringify({ text }) }),

  eventTables: (eventId: string) => request<EventTable[]>(`/events/${eventId}/tables`),
  bookTable: (eventId: string, tableId: string, party_size: number) =>
    request<TableBooking>(`/events/${eventId}/tables/${tableId}/book`, { method: "POST", body: JSON.stringify({ party_size }) }),
  myTables: () => request<TableBooking[]>("/table-bookings/mine"),
  joinEvent: (eventId: string, body: { quantity: number; promoter_code?: string; note?: string }) =>
    request<JoinResult>(`/events/${eventId}/join`, { method: "POST", body: JSON.stringify(body) }),
  myRequests: () => request<EventRequest[]>("/event-requests/mine"),
  eventGuests: (eventId: string) => request<{ count: number; visible: boolean; names: string[] }>(`/events/${eventId}/guests`),

  hostVenues: () => request<Venue[]>("/host/venues"),
  createVenue: (body: { name: string; city: string; category: string; image_url: string; description: string }) =>
    request<Venue>("/host/venues", { method: "POST", body: JSON.stringify(body) }),
  hostEvents: () => request<HostEvent[]>("/host/events"),
  hostEventDetail: (id: string) => request<HostEventDetail>(`/host/events/${id}`),
  createEvent: (body: Record<string, unknown>) =>
    request<EventItem>("/events", { method: "POST", body: JSON.stringify(body) }),
  decideRequest: (id: string, action: "approve" | "decline") =>
    request<EventRequest>(`/host/requests/${id}`, { method: "POST", body: JSON.stringify({ action }) }),
  updatePrefs: (marketing_opt_in: boolean) =>
    request<User>("/me/preferences", { method: "PATCH", body: JSON.stringify({ marketing_opt_in }) }),

  listPartners: (category?: string) =>
    request<Partner[]>(`/partners${category ? `?category=${category}` : ""}`),
  getPartner: (id: string) => request<Partner>(`/partners/${id}`),
  requestPartnerBooking: (body: { partner_id: string; date: string; units: number; guests: number; notes?: string }) =>
    request<PartnerBooking>("/partner-bookings", { method: "POST", body: JSON.stringify(body) }),
  myPartnerBookings: () => request<PartnerBooking[]>("/partner-bookings/mine"),

  listArticles: () => request<Article[]>("/journal"),
  getArticle: (id: string) => request<Article>(`/journal/${id}`),

  adminOverview: () => request<AdminOverview>("/admin/overview"),
  adminArticles: () => request<Article[]>("/admin/journal"),
  createArticle: (body: ArticleInput) =>
    request<Article>("/admin/journal", { method: "POST", body: JSON.stringify(body) }),
  updateArticle: (id: string, body: ArticleInput) =>
    request<Article>(`/admin/journal/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  adminPartnerBookings: () => request<PartnerBooking[]>("/admin/partner-bookings"),
  setPartnerBookingStatus: (id: string, status: "confirmed" | "declined") =>
    request<PartnerBooking>(`/admin/partner-bookings/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  exportMembersCsv: async () => {
    const token = await tokenStore.getItem();
    const res = await fetch(`${API_BASE}/admin/members/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Export failed");
    return res.text();
  },
  streamDraft: async (topic: string, category: string, onChunk: (full: string) => void) => {
    const token = await tokenStore.getItem();
    const res = await expoFetch(`${API_BASE}/admin/journal/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ topic, category }),
    });
    if (!res.ok || !res.body) throw new Error("Draft failed");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let full = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      full += decoder.decode(value, { stream: true });
      onChunk(full);
    }
    return full;
  },
};

export type Partner = {
  id: string;
  name: string;
  category: string;
  city: string;
  image_url: string;
  description: string;
  base_price: number;
  price_unit: string;
  rating: number;
  public_price: number;
  min_level: string;
};

export type PartnerBooking = {
  id: string;
  partner_id: string;
  partner_name: string;
  category: string;
  user_id: string;
  user_name: string;
  date: string;
  units: number;
  guests: number;
  price_unit: string;
  base_price: number;
  platform_fee: number;
  total: number;
  status: "requested" | "confirmed" | "declined";
  notes: string;
  created_at: string;
  public_total: number;
  member_savings: number;
};

export type Article = {
  id: string;
  title: string;
  category: "nightlife" | "travel" | "luxury";
  cover_image: string;
  summary: string;
  body: string;
  published: boolean;
  created_at: string;
};

export type ArticleInput = Omit<Article, "id" | "created_at">;

export type AdminOverview = {
  members_total: number;
  members_opted_in: number;
  pending_partner_requests: number;
  members_by_level: { bronze: number; silver: number; gold: number };
  revenue: {
    ticket_fees: number;
    reservation_fees: number;
    partner_fees: number;
    withdrawal_fees: number;
    membership_mrr_estimate: number;
  };
  revenue_total: number;
};

export type ChatMessage = { id: string; member_id: string; sender: "member" | "concierge"; sender_name: string; text: string; created_at: string };
export type ChatThread = { member_id: string; member_name: string; member_level: string; last_text: string; last_at: string; unread: number };
export type EventTable = { id: string; name: string; section: string; capacity: number; min_spend: number; x: number; y: number; min_level: string; booked: boolean };
export type TableBooking = {
  id: string; event_id: string; event_title: string; event_date: string; venue_name: string; table_id: string; section: string;
  user_id: string; user_name: string; party_size: number; min_spend: number; platform_fee: number; total: number; status: string; created_at: string;
};
export type EventRequest = {
  id: string; event_id: string; event_title: string; user_id: string; user_name: string; user_level: string;
  quantity: number; kind: "approval" | "waitlist"; status: "pending" | "approved" | "declined"; note: string; created_at: string;
};
export type JoinResult = { result: "ticket" | "pending" | "waitlisted"; ticket: Ticket | null; request: EventRequest | null };
export type HostEvent = {
  id: string; title: string; venue_name: string; date: string; price: number; tickets_sold: number; capacity: number;
  approval_required: boolean; pending_requests: number; tables_booked: number; tables_total: number; checked_in: number;
};
export type HostEventDetail = {
  requests: EventRequest[];
  guests: { ticket_id: string; name: string; quantity: number; checked_in: boolean }[];
  tables: TableBooking[];
};

export const PARTNER_LABELS: Record<string, string> = {
  hotel: "Hotels",
  black_car: "Black Cars",
  limo: "Limousines",
  mansion: "Mansions",
  yacht: "Yachts",
  jet: "Private Jets",
  helicopter: "Helicopters",
  exotic_car: "Exotic Cars",
  chef: "Private Chefs",
  security: "Security",
};
