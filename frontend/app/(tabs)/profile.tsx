import { useQuery } from "@tanstack/react-query";
import { useRouter, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

const TIER_LABELS: Record<string, string> = {
  free_girl: "LADIES · FREE",
  trial_male: "FREE TRIAL MONTH",
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
  useFocusEffect(
    useCallback(() => {
      refresh();
    }, [refresh]),
  );
  const { data: tickets } = useQuery({ queryKey: ["mine-tickets"], queryFn: () => api.myTickets() });
  const { data: reservations } = useQuery({
    queryKey: ["mine-reservations"],
    queryFn: () => api.myReservations(),
  });

  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function onWithdraw() {
    try {
      const res = await api.withdraw(user?.wallet_balance ?? 0);
      await refresh();
      setMsg({ ok: true, text: `Sent $${res.net.toFixed(2)} (fee $${res.fee.toFixed(2)}) to your bank.` });
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
          <View style={styles.tierBadge}>
            <Text style={styles.tierText}>{TIER_LABELS[user?.membership_tier ?? ""] ?? user?.membership_tier?.toUpperCase()}</Text>
          </View>
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

        <Pressable testID="logout-btn" onPress={signOut} style={styles.logout}>
          <FeatherIcon name="log-out" size={16} color={colors.brandSecondary} />
          <Text style={styles.logoutText}>Sign out</Text>
        </Pressable>
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
  empty: { color: colors.muted, paddingVertical: spacing.md, textAlign: "center" },
  logout: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    paddingVertical: spacing.lg,
  },
  logoutText: { color: colors.brandSecondary, fontSize: 14, fontWeight: "700" },
});
