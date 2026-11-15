import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, EventRequest } from "@/src/api";
import { DealCard } from "@/src/deal-card";
import { colors, radius, spacing } from "@/src/theme";

export default function HostEvent() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { data: ev } = useQuery({ queryKey: ["event", id], queryFn: () => api.getEvent(id!) });
  const { data, isLoading } = useQuery({ queryKey: ["host-event", id], queryFn: () => api.hostEventDetail(id!), refetchInterval: 8000 });
  const decide = useMutation({
    mutationFn: (v: { rid: string; action: "approve" | "decline" }) => api.decideRequest(v.rid, v.action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["host-event", id] });
      qc.invalidateQueries({ queryKey: ["host-events"] });
      qc.invalidateQueries({ queryKey: ["event", id] });
    },
  });
  const pending = (data?.requests ?? []).filter((r) => r.status === "pending");

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="host-event-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title} numberOfLines={1}>{ev?.title ?? "Event"}</Text>
        <Pressable testID="host-live-btn" onPress={() => router.push(`/host/live/${id}`)} style={styles.iconBtn}>
          <FeatherIcon name="activity" size={18} color={colors.brandPrimary} />
        </Pressable>
        <Pressable testID="host-scan-btn" onPress={() => router.push("/checkin")} style={styles.iconBtn}>
          <FeatherIcon name="maximize" size={18} color={colors.brandPrimary} />
        </Pressable>
      </View>
      {isLoading || !data ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.lg }}>
          {ev ? (
            <DealCard eventId={id!} spotsLeft={(ev.capacity ?? 200) - ev.tickets_sold} upcoming={new Date(ev.date) > new Date()} />
          ) : null}
          <Section title={`Requests & waitlist (${pending.length})`}>
            {pending.length === 0 ? <Text style={styles.muted}>Nobody waiting.</Text> : null}
            {pending.map((r) => (
              <RequestRow key={r.id} r={r} busy={decide.isPending} onDecide={(action) => decide.mutate({ rid: r.id, action })} />
            ))}
            {decide.error ? <Text style={styles.err} testID="decide-error">{decide.error.message}</Text> : null}
          </Section>

          <Section title={`Guest list (${data.guests.reduce((a, g) => a + g.quantity, 0)})`}>
            {data.guests.length === 0 ? <Text style={styles.muted}>No tickets yet.</Text> : null}
            {data.guests.map((g) => (
              <View key={g.ticket_id} style={styles.row} testID={`guest-${g.ticket_id}`}>
                <Text style={styles.name}>{g.name}{g.quantity > 1 ? ` +${g.quantity - 1}` : ""}</Text>
                <Text style={[styles.pill, g.checked_in ? styles.pillOk : styles.pillWait]}>{g.checked_in ? "IN" : "#" + g.ticket_id.slice(0, 8).toUpperCase()}</Text>
              </View>
            ))}
          </Section>

          <Section title={`Table bookings (${data.tables.length})`}>
            {data.tables.length === 0 ? <Text style={styles.muted}>No tables booked yet.</Text> : null}
            {data.tables.map((t) => (
              <View key={t.id} style={styles.row} testID={`host-table-${t.id}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{t.table_id} · {t.section}</Text>
                  <Text style={styles.muted}>{t.user_name} · party of {t.party_size}</Text>
                </View>
                <Text style={styles.money}>${t.min_spend.toFixed(0)}</Text>
              </View>
            ))}
          </Section>
        </ScrollView>
      )}
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function RequestRow({ r, busy, onDecide }: { r: EventRequest; busy: boolean; onDecide: (a: "approve" | "decline") => void }) {
  return (
    <View style={styles.req} testID={`request-${r.id}`}>
      <View style={styles.rowBetween}>
        <Text style={styles.name}>{r.user_name}{r.quantity > 1 ? ` +${r.quantity - 1}` : ""}</Text>
        <Text style={[styles.pill, r.kind === "waitlist" ? styles.pillWait : styles.pillGold]}>
          {r.kind === "waitlist" ? "WAITLIST" : "APPROVAL"} · {r.user_level.toUpperCase()}
        </Text>
      </View>
      {r.note ? <Text style={styles.muted}>“{r.note}”</Text> : null}
      <View style={styles.actions}>
        <Pressable testID={`approve-${r.id}`} disabled={busy} onPress={() => onDecide("approve")} style={[styles.act, { backgroundColor: colors.success }]}>
          <Text style={[styles.actText, { color: colors.onSuccess }]}>Approve</Text>
        </Pressable>
        <Pressable testID={`decline-${r.id}`} disabled={busy} onPress={() => onDecide("decline")} style={[styles.act, { backgroundColor: colors.surfaceTertiary }]}>
          <Text style={styles.actText}>Decline</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700", flex: 1, textAlign: "center" },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  cardTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  muted: { color: colors.muted, fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider, gap: spacing.sm },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  money: { color: colors.brandPrimary, fontSize: 15, fontWeight: "800" },
  req: { paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider, gap: spacing.xs },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  act: { flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  actText: { color: colors.onSurface, fontWeight: "700" },
  pill: { fontSize: 10, fontWeight: "800", letterSpacing: 1, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm, overflow: "hidden" },
  pillOk: { backgroundColor: colors.success, color: colors.onSuccess },
  pillWait: { backgroundColor: colors.surfaceTertiary, color: colors.onSurfaceTertiary },
  pillGold: { backgroundColor: colors.brandTertiary, color: colors.brandPrimary },
});
