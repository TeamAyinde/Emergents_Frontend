import { useQuery } from "@tanstack/react-query";
import { useRouter, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { openLegal } from "@/src/legal";
import { DeleteAccountRow } from "@/src/delete-account";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";
import { Level, LEVEL_INFO } from "@/src/levels";
import { InviteRow } from "@/src/invite-row";

const TIER_LABELS: Record<string, string> = {
  free_girl: "LADIES FREE",
  trial_male: "7 DAYS FREE",
  member: "MEMBER",
  premium: "PREMIUM",
  venue: "VENUE PARTNER",
  corporate: "CORPORATE",
};

export default function Profile() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, signOut, refresh } = useAuth();
  const balance = user?.wallet_balance ?? 0;
  const canWithdraw = balance > 2;
  const isStaff = user?.role === "promoter" || user?.role === "venue_owner" || user?.role === "admin";
  const lvl = (user?.level ?? "bronze") as Level;
  useFocusEffect(
    useCallback(() => {
      refresh();
    }, [refresh]),
  );
  const { data: tickets } = useQuery({ queryKey: ["mine-tickets"], queryFn: () => api.myTickets() });
  const { data: duty } = useQuery({ queryKey: ["door-duty"], queryFn: api.doorDuty });
  const { data: reservations } = useQuery({
    queryKey: ["mine-reservations"],
    queryFn: () => api.myReservations(),
  });
  const { data: luxe } = useQuery({ queryKey: ["mine-partner-bookings"], queryFn: () => api.myPartnerBookings() });
  const { data: myTables } = useQuery({ queryKey: ["mine-tables"], queryFn: () => api.myTables() });
  const { data: myReqs } = useQuery({ queryKey: ["mine-requests"], queryFn: () => api.myRequests() });
  const pendingReqs = (myReqs ?? []).filter((r) => r.status !== "approved");
  const [optBusy, setOptBusy] = useState(false);
  async function toggleOptIn(v: boolean) {
    setOptBusy(true);
    try {
      await api.updatePrefs(v);
      await refresh();
    } finally {
      setOptBusy(false);
    }
  }

  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function onWithdraw() {
    try {
      const res = await api.withdraw(user?.wallet_balance ?? 0);
      await refresh();
      setMsg({
        ok: true,
        text: res.status === "paid"
          ? `$${res.net.toFixed(2)} sent to your bank (fee $${res.fee.toFixed(2)}). It lands in 1–3 business days.`
          : `Payout of $${res.net.toFixed(2)} requested (fee $${res.fee.toFixed(2)}). Link your bank under Bank payouts for automatic transfers.`,
      });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Try again" });
    }
  }

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: insets.bottom + spacing["3xl"],
          paddingHorizontal: spacing.lg,
          gap: spacing.lg,
        }}
      >
        <View style={styles.header}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{user?.full_name?.[0]?.toUpperCase() ?? "N"}</Text>
          </View>
          <Text style={styles.name} testID="profile-name">{user?.full_name}</Text>
          <Text style={styles.email}>{user?.email}</Text>
          <Pressable testID="profile-level-badge" onPress={() => router.push("/membership")} style={[styles.tierBadge, { borderColor: LEVEL_INFO[lvl].color }]}>
            <Text style={[styles.tierText, { color: LEVEL_INFO[lvl].color }]}>
              {LEVEL_INFO[lvl].label.toUpperCase()} MEMBER{TIER_LABELS[user?.membership_tier ?? ""] && user?.membership_tier !== "member" && lvl === "bronze" ? ` · ${TIER_LABELS[user?.membership_tier ?? ""]}` : ""}
            </Text>
          </Pressable>
          {user?.gift_level && user?.gift_until ? (
            <Text style={styles.giftLine} testID="profile-gift-status">
              🎁 Gifted {LEVEL_INFO[user.gift_level as Level].label} until{" "}
              {new Date(user.gift_until).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })}
            </Text>
          ) : null}
          {user?.role === "guest" || user?.role === "promoter" ? (
            <Pressable testID="manage-membership-btn" onPress={() => router.push("/membership")}>
              <Text style={styles.upgradeLink}>{lvl === "gold" ? "Manage membership" : "Upgrade membership →"}</Text>
            </Pressable>
          ) : null}
        </View>

        {isStaff ? (
        <View style={styles.wallet}>
          <View>
            <Text style={styles.walletLabel}>WALLET BALANCE</Text>
            <Text style={styles.walletValue} testID="wallet-balance">
              ${user?.wallet_balance?.toFixed(2) ?? "0.00"}
            </Text>
            <Text style={styles.walletHint}>{canWithdraw ? "$2 fee per withdrawal" : "Earn over $2 to withdraw"}</Text>
          </View>
          <LuxButton
            testID="withdraw-btn"
            label="Withdraw"
            onPress={onWithdraw}
            disabled={!canWithdraw}
            style={{ width: 130 }}
          />
        </View>
        ) : null}

        <InviteRow />

        <Pressable testID="email-prefs-btn" onPress={() => router.push("/email-settings")} style={styles.prefRow}>
          <View style={styles.rowIcon}>
            <FeatherIcon name="bell" size={16} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>Notifications</Text>
            <Text style={styles.rowSub}>Phone alerts and emails you get</Text>
          </View>
          <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
        </Pressable>

        <Pressable testID="gifts-btn" onPress={() => router.push("/gifts")} style={styles.prefRow}>
          <View style={styles.rowIcon}>
            <FeatherIcon name="gift" size={16} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>Gifts</Text>
            <Text style={styles.rowSub}>Gift a month of Silver or Gold, or redeem a code</Text>
          </View>
          <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
        </Pressable>

        {isStaff && user?.role !== "admin" ? (
          <Pressable testID="bank-payouts-btn" onPress={() => router.push("/payout-settings")} style={styles.prefRow}>
            <View style={styles.rowIcon}>
              <FeatherIcon name="briefcase" size={16} color={colors.brandPrimary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>Bank payouts</Text>
              <Text style={styles.rowSub}>Get your earnings sent to your bank</Text>
            </View>
            <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        ) : null}

        {msg ? (
          <Text testID="withdraw-msg" style={{ color: msg.ok ? colors.success : colors.error, fontSize: 13 }}>
            {msg.text}
          </Text>
        ) : null}

        <View>
          <Text style={styles.sectionTitle}>My Tickets</Text>
          <FlatList
            data={tickets ?? []}
            keyExtractor={(t) => t.id}
            scrollEnabled={false}
            ItemSeparatorComponent={() => <View style={styles.sep} />}
            ListEmptyComponent={<Text style={styles.empty}>No tickets yet. Browse events to grab one.</Text>}
            renderItem={({ item }) => (
              <Pressable
                testID={`ticket-row-${item.id}`}
                onPress={() => router.push(`/ticket/${item.id}`)}
                style={styles.row}
              >
                <View style={styles.rowIcon}>
                  <FeatherIcon name="file-text" size={16} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={1}>{item.event_title}</Text>
                  <Text style={styles.rowSub}>
                    {new Date(item.event_date).toLocaleDateString()} · {item.venue_name}
                  </Text>
                </View>
                <View style={[styles.statusBadge, item.checked_in && styles.checkedBadge]}>
                  <Text style={styles.statusText}>{item.checked_in ? "USED" : "LIVE"}</Text>
                </View>
              </Pressable>
            )}
          />
        </View>

        <View>
          <Text style={styles.sectionTitle}>Reservations</Text>
          <FlatList
            data={reservations ?? []}
            keyExtractor={(r) => r.id}
            scrollEnabled={false}
            ItemSeparatorComponent={() => <View style={styles.sep} />}
            ListEmptyComponent={<Text style={styles.empty}>No reservations yet.</Text>}
            renderItem={({ item }) => (
              <View style={styles.row}>
                <View style={styles.rowIcon}>
                  <FeatherIcon name="calendar" size={16} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>{item.venue_name}</Text>
                  <Text style={styles.rowSub}>
                    {new Date(item.date).toLocaleDateString()} · party of {item.party_size} · {item.service_type}
                  </Text>
                </View>
                <Text style={styles.rowPrice}>${item.total.toFixed(0)}</Text>
              </View>
            )}
          />
        </View>

        <View>
          <Text style={styles.sectionTitle}>Luxe Requests</Text>
          {(luxe ?? []).length === 0 ? (
            <Text style={styles.empty}>No hotel, car or yacht requests yet.</Text>
          ) : (
            (luxe ?? []).map((b) => (
              <View key={b.id} style={styles.row} testID={`luxe-row-${b.id}`}>
                <View style={styles.rowIcon}>
                  <FeatherIcon name="star" size={16} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={1}>{b.partner_name}</Text>
                  <Text style={styles.rowSub}>
                    {new Date(b.date).toLocaleDateString()} · ${b.total.toFixed(0)} · {b.status}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>

        <View>
          <Text style={styles.sectionTitle}>Tables & Requests</Text>
          {(myTables ?? []).length === 0 && pendingReqs.length === 0 ? (
            <Text style={styles.empty}>No table bookings or pending requests.</Text>
          ) : null}
          {(myTables ?? []).map((t) => (
            <View key={t.id} style={styles.row} testID={`my-table-${t.id}`}>
              <View style={styles.rowIcon}>
                <FeatherIcon name="grid" size={16} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle} numberOfLines={1}>{t.event_title} · {t.table_id}</Text>
                <Text style={styles.rowSub}>{t.section} · party of {t.party_size} · ${t.total.toFixed(0)}</Text>
              </View>
            </View>
          ))}
          {pendingReqs.map((r) => (
            <View key={r.id} style={styles.row} testID={`my-request-${r.id}`}>
              <View style={styles.rowIcon}>
                <FeatherIcon name="clock" size={16} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle} numberOfLines={1}>{r.event_title}</Text>
                <Text style={styles.rowSub}>
                  {r.status === "declined" ? "Declined by host" : r.kind === "waitlist" ? "On the waitlist" : "Waiting for host approval"}
                </Text>
              </View>
            </View>
          ))}
        </View>

        <View style={styles.rewardsRow}>
          <Pressable testID="rewards-btn" onPress={() => router.push("/rewards")} style={styles.rewardsCard}>
            <FeatherIcon name="star" size={18} color={colors.brandPrimary} />
            <Text style={styles.rewardsValue} testID="profile-points">{user?.points ?? 0}</Text>
            <Text style={styles.rowSub}>Reward points{(user?.credit_balance ?? 0) > 0 ? ` · $${user?.credit_balance.toFixed(2)} credit` : ""}</Text>
          </Pressable>
          <Pressable testID="perks-btn" onPress={() => router.push("/perks")} style={styles.rewardsCard}>
            <FeatherIcon name="gift" size={18} color={colors.brandPrimary} />
            <Text style={styles.rewardsValue}>Perks</Text>
            <Text style={styles.rowSub}>Members wallet</Text>
          </Pressable>
        </View>

        <Pressable testID="concierge-btn" onPress={() => router.push("/concierge")} style={styles.prefRow}>
          <View style={styles.rowIcon}>
            <FeatherIcon name="message-circle" size={16} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>Personal concierge</Text>
            <Text style={styles.rowSub}>Jets, villas, tables, anything — just ask.</Text>
          </View>
          <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
        </Pressable>

        {duty?.venues.length ? (
          <Pressable testID="door-duty-btn" onPress={() => router.push("/door")} style={styles.prefRow}>
            <View style={styles.rowIcon}>
              <FeatherIcon name="maximize" size={16} color={colors.brandPrimary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>Door duty</Text>
              <Text style={styles.rowSub}>Scan tickets at {duty.venues.join(", ")}</Text>
            </View>
            <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        ) : null}

        {user?.role === "venue_owner" || user?.role === "admin" ? (
          <Pressable testID="host-studio-btn" onPress={() => router.push("/host")} style={styles.prefRow}>
            <View style={styles.rowIcon}>
              <FeatherIcon name="calendar" size={16} color={colors.brandPrimary} />
            </View>
            <Text style={[styles.rowTitle, { flex: 1 }]}>Host Studio</Text>
            <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        ) : null}

        <View style={styles.prefRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>Journal & member deals emails</Text>
            <Text style={styles.rowSub}>Nightlife, travel and luxury news plus invites.</Text>
          </View>
          <Switch
            testID="marketing-optin-switch"
            value={!!user?.marketing_opt_in}
            disabled={optBusy}
            onValueChange={toggleOptIn}
            trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
          />
        </View>

        {user?.role === "admin" ? (
          <Pressable testID="admin-dashboard-btn" onPress={() => router.push("/admin")} style={styles.prefRow}>
            <View style={styles.rowIcon}>
              <FeatherIcon name="bar-chart-2" size={16} color={colors.brandPrimary} />
            </View>
            <Text style={[styles.rowTitle, { flex: 1 }]}>Admin dashboard</Text>
            <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        ) : null}

        <Pressable testID="help-support-btn" onPress={() => router.push("/support")} style={styles.prefRow}>
          <View style={styles.rowIcon}>
            <FeatherIcon name="life-buoy" size={16} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.rowTitle}>Help & support</Text>
            <Text style={styles.rowSub}>Report a problem · Support & FAQ</Text>
          </View>
          <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
        </Pressable>

        <Pressable testID="privacy-policy-btn" onPress={() => openLegal("privacy")} style={styles.prefRow}>
          <View style={styles.rowIcon}>
            <FeatherIcon name="shield" size={16} color={colors.brandPrimary} />
          </View>
          <Text style={[styles.rowTitle, { flex: 1 }]}>Privacy policy</Text>
          <FeatherIcon name="external-link" size={16} color={colors.muted} />
        </Pressable>

        <Pressable testID="logout-btn" onPress={signOut} style={styles.logout}>
          <FeatherIcon name="log-out" size={16} color={colors.brandSecondary} />
          <Text style={styles.logoutText}>Sign out</Text>
        </Pressable>

        <DeleteAccountRow />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { alignItems: "center", gap: spacing.sm, paddingTop: spacing.lg },
  avatar: {
    width: 80, height: 80, borderRadius: 40, backgroundColor: colors.brandTertiary,
    borderWidth: 2, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center",
  },
  avatarText: { color: colors.brandPrimary, fontSize: 36, fontWeight: "800" },
  name: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  email: { color: colors.muted, fontSize: 13 },
  tierBadge: {
    paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: colors.brandPrimary,
  },
  tierText: { color: colors.brandPrimary, fontSize: 10, letterSpacing: 1.5, fontWeight: "700" },
  wallet: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    padding: spacing.lg, borderWidth: 1, borderColor: colors.border,
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
  },
  walletLabel: { color: colors.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700" },
  walletValue: { color: colors.brandPrimary, fontSize: 30, fontWeight: "800", marginTop: 4 },
  walletHint: { color: colors.muted, fontSize: 11 },
  sectionTitle: { color: colors.onSurface, fontSize: 20, fontWeight: "800", marginBottom: spacing.md },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.md, gap: spacing.md },
  rowIcon: {
    width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  rowTitle: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  rowSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  rowPrice: { color: colors.brandPrimary, fontSize: 15, fontWeight: "700" },
  statusBadge: {
    paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm,
    backgroundColor: colors.brandSecondary,
  },
  checkedBadge: { backgroundColor: colors.surfaceTertiary },
  statusText: { color: colors.onBrandSecondary, fontSize: 10, letterSpacing: 1, fontWeight: "700" },
  sep: { height: 0.5, backgroundColor: colors.divider },
  rewardsRow: { flexDirection: "row", gap: spacing.md },
  rewardsCard: {
    flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: 4,
    borderWidth: 1, borderColor: colors.brandPrimary,
  },
  rewardsValue: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  upgradeLink: { color: colors.brandPrimary, fontSize: 13, fontWeight: "700", paddingVertical: spacing.md, minHeight: 44 },
  giftLine: { color: colors.onSurfaceSecondary, fontSize: 13, marginTop: spacing.xs },
  prefRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border,
  },
  empty: { color: colors.muted, paddingVertical: spacing.md, textAlign: "center" },
  logout: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    paddingVertical: spacing.lg,
  },
  logoutText: { color: colors.brandSecondary, fontSize: 14, fontWeight: "700" },
});
