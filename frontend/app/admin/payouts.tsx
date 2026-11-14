import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, Alert, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

/** Admin: what Nocturne owes venues and promoters, and mark payouts as sent. */
export default function Payouts() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { data, isLoading, error, refetch, isRefetching } = useQuery({ queryKey: ["admin-payouts"], queryFn: api.adminPayouts });
  const settle = useMutation({ mutationFn: api.settleVenue, onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-payouts"] }) });
  const markPaid = useMutation({ mutationFn: api.markWithdrawalPaid, onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-payouts"] }) });
  const busy = settle.isPending || markPaid.isPending;
  const actionError = (settle.error || markPaid.error)?.message;

  function confirm(text: string, run: () => void) {
    if (Platform.OS === "web") {
      if (window.confirm(text)) run();
      return;
    }
    Alert.alert("Confirm payout", text, [{ text: "Cancel", style: "cancel" }, { text: "Confirm", onPress: run }]);
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="payouts-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/admin"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Payouts</Text>
        <View style={{ width: 44 }} />
      </View>
      {error ? (
        <View style={{ padding: spacing.lg, gap: spacing.md }}>
          <Text style={styles.warn} testID="payouts-error">{error.message}</Text>
          <Pressable testID="payouts-retry" onPress={() => refetch()} style={styles.btn}><Text style={styles.btnText}>Try again</Text></Pressable>
        </View>
      ) : isLoading || !data ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["2xl"] }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={() => { refetch(); }} tintColor={colors.brandPrimary} />}
        >
          <View style={styles.statsRow}>
            <Stat label="Collected by card" value={`$${data.card_payments_total.toFixed(2)}`} testID="payouts-collected" />
            <Stat label="Owed to venues" value={`$${data.venues_owed_total.toFixed(2)}`} testID="payouts-owed" />
          </View>
          {data.refunds_needed > 0 ? (
            <Text style={styles.warn} testID="payouts-refunds">
              {data.refunds_needed} paid booking(s) could not be completed — refund them from your Stripe dashboard.
            </Text>
          ) : null}

          {actionError ? <Text style={styles.warn} testID="payouts-action-error">{actionError}</Text> : null}
          <Text style={styles.section}>Venues</Text>
          {data.venues.length === 0 ? <Text style={styles.muted}>Nothing owed right now.</Text> : null}
          {data.venues.map((v) => (
            <View key={v.venue_id} style={styles.row} testID={`payout-venue-${v.venue_id}`}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{v.venue_name}</Text>
                <Text style={styles.muted}>{v.items} booking(s) · ${v.owed.toFixed(2)}</Text>
              </View>
              <Pressable testID={`settle-${v.venue_id}`} disabled={busy}
                onPress={() => confirm(`Mark $${v.owed.toFixed(2)} as paid to ${v.venue_name}?`, () => settle.mutate(v.venue_id))}
                style={[styles.btn, busy && { opacity: 0.5 }]}>
                <Text style={styles.btnText}>Mark paid</Text>
              </Pressable>
            </View>
          ))}

          <Text style={styles.section}>Promoter withdrawals</Text>
          {data.withdrawals.length === 0 ? <Text style={styles.muted}>No pending withdrawals.</Text> : null}
          {data.withdrawals.map((w) => (
            <View key={w.id} style={styles.row} testID={`withdrawal-${w.id}`}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>{w.user_name || "Promoter"}</Text>
                <Text style={styles.muted}>Send ${w.net.toFixed(2)} (kept ${w.fee.toFixed(2)} fee)</Text>
              </View>
              <Pressable testID={`mark-paid-${w.id}`} disabled={busy}
                onPress={() => confirm(`Mark $${w.net.toFixed(2)} as sent to ${w.user_name || "this promoter"}?`, () => markPaid.mutate(w.id))}
                style={[styles.btn, busy && { opacity: 0.5 }]}>
                <Text style={styles.btnText}>Mark sent</Text>
              </Pressable>
            </View>
          ))}
          <Text style={styles.hint}>
            Card payments land in your Stripe balance and pay out to your business bank account or debit card.
            Send venue and promoter payouts, then mark them here to keep the books straight.
          </Text>
        </ScrollView>
      )}
    </View>
  );
}

function Stat({ label, value, testID }: { label: string; value: string; testID: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  statsRow: { flexDirection: "row", gap: spacing.md },
  stat: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: 4 },
  statValue: { color: colors.brandPrimary, fontSize: 22, fontWeight: "800" },
  section: { color: colors.onSurface, fontSize: 18, fontWeight: "800", marginTop: spacing.md },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  rowTitle: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  muted: { color: colors.muted, fontSize: 13 },
  warn: { color: colors.error, fontSize: 13 },
  btn: { minHeight: 44, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, justifyContent: "center" },
  btnText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "700" },
  hint: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: spacing.lg },
});
