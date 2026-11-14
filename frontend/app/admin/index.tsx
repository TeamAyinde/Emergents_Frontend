import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Share, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, PARTNER_LABELS } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

export default function AdminDashboard() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [exportMsg, setExportMsg] = useState("");
  const isAdmin = user?.role === "admin";

  const { data: o } = useQuery({ queryKey: ["admin-overview"], queryFn: () => api.adminOverview(), enabled: isAdmin });
  const { data: bookings } = useQuery({ queryKey: ["admin-pb"], queryFn: () => api.adminPartnerBookings(), enabled: isAdmin });
  const { data: articles } = useQuery({ queryKey: ["admin-articles"], queryFn: () => api.adminArticles(), enabled: isAdmin });
  const setStatus = useMutation({
    mutationFn: (v: { id: string; status: "confirmed" | "declined" }) => api.setPartnerBookingStatus(v.id, v.status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-pb"] });
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
    },
  });

  async function onExport() {
    setExportMsg("");
    try {
      const csv = await api.exportMembersCsv();
      const rows = Math.max(0, csv.trim().split("\n").length - 1);
      if (Platform.OS === "web") {
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "nocturne-members.csv";
        link.click();
        URL.revokeObjectURL(url);
      } else {
        await Share.share({ message: csv, title: "nocturne-members.csv" });
      }
      setExportMsg(`Exported ${rows} opted-in members.`);
    } catch (e) {
      setExportMsg(e instanceof Error ? e.message : "Export failed");
    }
  }

  if (!isAdmin) {
    return (
      <View style={[styles.root, styles.center]}>
        <Text style={styles.muted}>Admins only.</Text>
      </View>
    );
  }

  const r = o?.revenue;
  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="admin-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Admin</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"], gap: spacing.lg }}>
        {!o ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : (
          <>
            <View style={styles.revCard} testID="admin-revenue">
              <Text style={styles.eyebrow}>PLATFORM REVENUE</Text>
              <Text style={styles.big}>${o.revenue_total.toFixed(2)}</Text>
              <RevRow label="Ticket fees (after promoters)" v={r!.ticket_fees} />
              <RevRow label="Reservation fees" v={r!.reservation_fees} />
              <RevRow label="Luxe concierge fees" v={r!.partner_fees} />
              <RevRow label="Withdrawal fees" v={r!.withdrawal_fees} />
              <RevRow label="Membership MRR (est.)" v={r!.membership_mrr_estimate} />
            </View>
            <View style={styles.statsRow}>
              <Stat label="Members" value={`${o.members_total}`} testID="admin-members" />
              <Stat label="Opted in" value={`${o.members_opted_in}`} testID="admin-optedin" />
              <Stat label="Pending" value={`${o.pending_partner_requests}`} testID="admin-pending" />
            </View>
            <View style={styles.statsRow}>
              <Stat label="Bronze" value={`${o.members_by_level.bronze}`} testID="admin-bronze" />
              <Stat label="Silver" value={`${o.members_by_level.silver}`} testID="admin-silver" />
              <Stat label="Gold" value={`${o.members_by_level.gold}`} testID="admin-gold" />
            </View>
          </>
        )}

        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardTitle}>Concierge & hosting</Text>
          </View>
          <Pressable testID="admin-inbox-btn" onPress={() => router.push("/admin/inbox")} style={styles.listRow}>
            <FeatherIcon name="message-circle" size={18} color={colors.brandPrimary} />
            <Text style={[styles.rowTitle, { flex: 1 }]}>Concierge inbox</Text>
            <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
          <Pressable testID="admin-host-btn" onPress={() => router.push("/host")} style={styles.listRow}>
            <FeatherIcon name="calendar" size={18} color={colors.brandPrimary} />
            <Text style={[styles.rowTitle, { flex: 1 }]}>All events · Host Studio</Text>
            <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
          </Pressable>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Member list</Text>
          <Text style={styles.muted}>
            Download names, emails, phones and cities of members who agreed to marketing. Import into your newsletter tool.
          </Text>
          <LuxButton testID="export-members-btn" label="Export CSV" onPress={onExport} />
          {exportMsg ? <Text testID="export-msg" style={styles.okText}>{exportMsg}</Text> : null}
        </View>

        <View style={styles.card}>
          <View style={styles.rowBetween}>
            <Text style={styles.cardTitle}>Journal</Text>
            <Pressable testID="new-article-btn" onPress={() => router.push("/admin/compose")} style={styles.smallBtn}>
              <FeatherIcon name="edit-3" size={14} color={colors.onBrandPrimary} />
              <Text style={styles.smallBtnText}>New issue</Text>
            </Pressable>
          </View>
          {(articles ?? []).map((a) => (
            <Pressable key={a.id} testID={`admin-article-${a.id}`} onPress={() => router.push(`/admin/compose?id=${a.id}`)} style={styles.listRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle} numberOfLines={1}>{a.title}</Text>
                <Text style={styles.rowSub}>{a.category} · {new Date(a.created_at).toLocaleDateString()}</Text>
              </View>
              <Text style={[styles.pill, a.published ? styles.pillOk : styles.pillDraft]}>{a.published ? "LIVE" : "DRAFT"}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Luxe booking requests</Text>
          {(bookings ?? []).length === 0 ? <Text style={styles.muted}>No requests yet.</Text> : null}
          {(bookings ?? []).map((b) => (
            <View key={b.id} style={styles.bookingRow} testID={`admin-booking-${b.id}`}>
              <Text style={styles.rowTitle}>{b.partner_name}</Text>
              <Text style={styles.rowSub}>
                {PARTNER_LABELS[b.category] ?? b.category} · {b.user_name} · {new Date(b.date).toLocaleDateString()} · {b.units} {b.price_unit}(s) · {b.guests} guests
              </Text>
              <Text style={styles.rowSub}>Total ${b.total.toFixed(2)} · your fee ${b.platform_fee.toFixed(2)}</Text>
              {b.notes ? <Text style={styles.rowSub}>“{b.notes}”</Text> : null}
              {b.status === "requested" ? (
                <View style={styles.actions}>
                  <Pressable testID={`confirm-${b.id}`} onPress={() => setStatus.mutate({ id: b.id, status: "confirmed" })} style={[styles.actBtn, { backgroundColor: colors.success }]}>
                    <Text style={[styles.actText, { color: colors.onSuccess }]}>Confirm</Text>
                  </Pressable>
                  <Pressable testID={`decline-${b.id}`} onPress={() => setStatus.mutate({ id: b.id, status: "declined" })} style={[styles.actBtn, { backgroundColor: colors.surfaceTertiary }]}>
                    <Text style={styles.actText}>Decline</Text>
                  </Pressable>
                </View>
              ) : (
                <Text style={[styles.pill, b.status === "confirmed" ? styles.pillOk : styles.pillDraft, { alignSelf: "flex-start" }]}>
                  {b.status.toUpperCase()}
                </Text>
              )}
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

function RevRow({ label, v }: { label: string; v: number }) {
  return (
    <View style={styles.revRow}>
      <Text style={styles.revLabel}>{label}</Text>
      <Text style={styles.revValue}>${v.toFixed(2)}</Text>
    </View>
  );
}
function Stat({ label, value, testID }: { label: string; value: string; testID: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  revCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.brandPrimary, gap: spacing.xs },
  eyebrow: { color: colors.onBrandTertiary, fontSize: 11, letterSpacing: 2, fontWeight: "700" },
  big: { color: colors.brandPrimary, fontSize: 34, fontWeight: "800", marginBottom: spacing.sm },
  revRow: { flexDirection: "row", justifyContent: "space-between" },
  revLabel: { color: colors.onBrandTertiary, fontSize: 13 },
  revValue: { color: colors.onSurface, fontSize: 13, fontWeight: "700" },
  statsRow: { flexDirection: "row", gap: spacing.sm },
  stat: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  statLabel: { color: colors.muted, fontSize: 10, letterSpacing: 1, fontWeight: "700", textTransform: "uppercase" },
  statValue: { color: colors.onSurface, fontSize: 22, fontWeight: "800", marginTop: 4 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.md },
  cardTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  okText: { color: colors.success, fontSize: 13 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  smallBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, height: 36, borderRadius: radius.pill },
  smallBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "700" },
  listRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider },
  rowTitle: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  rowSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  pill: { fontSize: 10, fontWeight: "800", letterSpacing: 1, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm, overflow: "hidden" },
  pillOk: { backgroundColor: colors.success, color: colors.onSuccess },
  pillDraft: { backgroundColor: colors.surfaceTertiary, color: colors.onSurfaceTertiary },
  bookingRow: { paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider, gap: 4 },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  actBtn: { flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  actText: { color: colors.onSurface, fontWeight: "700" },
});
