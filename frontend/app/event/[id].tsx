import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";
import { useAuth } from "@/src/auth-context";
import { canAccess, Level, LEVEL_INFO } from "@/src/levels";
import { TableMap } from "@/src/table-map";
import { startCheckout } from "@/src/payments";
import { SpotlightCard } from "@/src/spotlight-card";

export default function EventDetails() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [qty, setQty] = useState(1);
  const [code, setCode] = useState("");
  const { user, refresh } = useAuth();
  const lvl = (user?.level ?? "bronze") as Level;

  const { data: ev, isLoading } = useQuery({ queryKey: ["event", id], queryFn: () => api.getEvent(id!) });
  const { data: guests } = useQuery({ queryKey: ["guests", id], queryFn: () => api.eventGuests(id!) });
  const { data: myReqs } = useQuery({ queryKey: ["mine-requests"], queryFn: () => api.myRequests() });
  const { data: myTickets } = useQuery({ queryKey: ["mine-tickets"], queryFn: () => api.myTickets() });
  const myTicket = myTickets?.find((t) => t.event_id === id);
  const pendingReq = myReqs?.find((r) => r.event_id === id && r.status === "pending");
  const approvedReq = myReqs?.find((r) => r.event_id === id && r.status === "approved");
  const buy = useMutation({
    mutationFn: async () => {
      const promoter_code = code.trim() || undefined;
      const res = await api.joinEvent(id!, { promoter_code, quantity: qty });
      if (res.result === "payment_required") {
        await startCheckout({ kind: "ticket", event_id: id!, quantity: qty, promoter_code }, router);
      }
      return res;
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["mine-tickets"] });
      qc.invalidateQueries({ queryKey: ["mine-requests"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["guests", id] });
      refresh();
      if (res.result === "ticket" && res.ticket) router.replace(`/ticket/${res.ticket.id}`);
    },
  });

  if (isLoading || !ev) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const gross = ev.price * qty;
  const discount = gross * LEVEL_INFO[lvl].discount;
  const base = gross - discount;
  const fee = base * 0.15;
  const locked = !canAccess(lvl, ev.min_level);
  const total = base + fee;
  const d = new Date(ev.date);
  const credit = Math.min(user?.credit_balance ?? 0, total);
  const maxQty = Math.min(8, 1 + (ev.plus_one_limit ?? 7));
  const left = Math.max(0, (ev.capacity ?? 200) - ev.tickets_sold);
  const soldOut = left < qty;
  const due = total - credit;
  const payLabel = due > 0 ? `Pay $${due.toFixed(2)} · Card` : "Get ticket";
  const joinLabel = approvedReq
    ? `Approved · ${payLabel}`
    : ev.approval_required ? "Request to join" : soldOut ? "Join waitlist" : payLabel;
  const outcome = buy.data?.result === "pending" || (pendingReq && pendingReq.kind === "approval")
    ? "Request sent. The host will approve you soon — your ticket appears in Profile."
    : buy.data?.result === "waitlisted" || (pendingReq && pendingReq.kind === "waitlist")
      ? "You're on the waitlist. If a spot opens, the host will add you."
      : "";

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: 280 }}>
        <View style={styles.hero}>
          <Image source={ev.image_url} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient
            colors={["rgba(9,9,11,0.5)", "transparent", "rgba(9,9,11,1)"]}
            locations={[0, 0.4, 1]}
            style={StyleSheet.absoluteFill}
          />
          <Pressable
            testID="event-back"
            onPress={() => router.back()}
            style={[styles.back, { top: insets.top + spacing.sm }]}
          >
            <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroBottom}>
            <View style={styles.tagsRow}>
              {ev.tags.map((t) => (
                <View key={t} style={styles.tag}>
                  <Text style={styles.tagText}>{t}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.title}>{ev.title}</Text>
            <Text style={styles.venue}>{ev.venue_name} · {ev.city}</Text>
          </View>
        </View>

        <View style={styles.body}>
          <View style={styles.infoRow}>
            <InfoChip icon="calendar" label={d.toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric" })} />
            <InfoChip icon="clock" label={d.toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" })} />
            <InfoChip icon="dollar-sign" label={`From $${ev.price}`} />
            <InfoChip icon="users" label={left > 0 ? `${left} spots left` : "Sold out"} />
            {ev.approval_required ? <InfoChip icon="shield" label="Host approval" /> : null}
          </View>

          <Text style={styles.sectionTitle}>About</Text>
          <Text style={styles.description}>{ev.description}</Text>

          {guests && guests.count > 0 ? (
            <View style={styles.guests} testID="whos-going">
              <View style={styles.avatars}>
                {guests.names.slice(0, 5).map((n, i) => (
                  <View key={n + i} style={[styles.avatar, { marginLeft: i === 0 ? 0 : -10 }]}>
                    <Text style={styles.avatarText}>{n[0]}</Text>
                  </View>
                ))}
              </View>
              <Text style={styles.guestsText}>
                {guests.visible && guests.names.length
                  ? `${guests.names.slice(0, 3).join(", ")}${guests.count > 3 ? ` +${guests.count - 3} going` : " going"}`
                  : `${guests.count} going`}
              </Text>
            </View>
          ) : null}

          {ev.has_tables && !locked ? <TableMap eventId={ev.id} userLevel={lvl} /> : null}
          {(user?.role === "promoter" || user?.role === "admin") && new Date(ev.date) > new Date() ? <SpotlightCard eventId={ev.id} active={ev.spotlight} /> : null}

          <Text style={styles.sectionTitle}>{ev.plus_one_limit > 0 ? `Tickets (you + up to ${maxQty - 1})` : "Tickets (just you)"}</Text>
          <View style={styles.qtyRow}>
            <Pressable testID="qty-minus" onPress={() => setQty(Math.max(1, qty - 1))} style={styles.qtyBtn}>
              <Text style={styles.qtyBtnText}>−</Text>
            </Pressable>
            <Text style={styles.qtyValue} testID="qty-value">{qty}</Text>
            <Pressable testID="qty-plus" onPress={() => setQty(Math.min(maxQty, qty + 1))} style={styles.qtyBtn}>
              <Text style={styles.qtyBtnText}>+</Text>
            </Pressable>
          </View>

          <Text style={styles.sectionTitle}>Promoter code (optional)</Text>
          <TextInput
            testID="promoter-code"
            value={code}
            onChangeText={setCode}
            placeholder="e.g. MARCO1"
            placeholderTextColor={colors.muted}
            autoCapitalize="characters"
            style={styles.input}
          />

          <View style={styles.breakdown}>
            <Row label="Tickets" value={`$${gross.toFixed(2)}`} />
            {discount > 0 ? <Row label={`${LEVEL_INFO[lvl].label} discount`} value={`−$${discount.toFixed(2)}`} /> : null}
            <Row label="Platform fee (15%)" value={`$${fee.toFixed(2)}`} />
            {credit > 0 ? <Row label="Reward credit" value={`−$${credit.toFixed(2)}`} /> : null}
            <View style={styles.sep} />
            <Row label="Total" value={`$${(total - credit).toFixed(2)}`} bold />
            <Text style={styles.pointsHint} testID="points-hint">
              Earn {Math.round((total - credit) * ({ bronze: 1, silver: 1.5, gold: 2 } as const)[lvl])} reward points
            </Text>
            <Text style={styles.secureHint}>Secure card payment by Stripe</Text>
          </View>
        </View>
      </ScrollView>

      <View style={[styles.sticky, { paddingBottom: insets.bottom + spacing.md }]}>
        {buy.error ? (
          <Text testID="buy-error" style={{ color: colors.error, marginBottom: spacing.sm }}>
            {buy.error.message}
          </Text>
        ) : null}
        {outcome ? <Text testID="join-outcome" style={{ color: colors.success, marginBottom: spacing.sm }}>{outcome}</Text> : null}
        {locked ? (
          <LuxButton
            testID="unlock-event-btn"
            label={`Unlock with ${LEVEL_INFO[ev.min_level as Level].label}`}
            onPress={() => router.push("/membership")}
          />
        ) : myTicket ? (
          <LuxButton testID="view-my-ticket-btn" label="You're going · View ticket" onPress={() => router.push(`/ticket/${myTicket.id}`)} />
        ) : outcome ? null : (
          <LuxButton
            testID="buy-ticket-btn"
            label={buy.isPending ? "Processing…" : joinLabel}
            onPress={() => buy.mutate()}
            loading={buy.isPending}
          />
        )}
      </View>
    </View>
  );
}

function InfoChip({ icon, label }: { icon: string; label: string }) {
  return (
    <View style={styles.chip}>
      <FeatherIcon name={icon as any} size={13} color={colors.brandPrimary} />
      <Text style={styles.chipText}>{label}</Text>
    </View>
  );
}
function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <View style={styles.rRow}>
      <Text style={[styles.rLabel, bold && styles.rBold]}>{label}</Text>
      <Text style={[styles.rValue, bold && styles.rBold]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  guests: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  avatars: { flexDirection: "row" },
  avatar: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: colors.brandTertiary, borderWidth: 2, borderColor: colors.surface,
    alignItems: "center", justifyContent: "center",
  },
  avatarText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "800" },
  guestsText: { color: colors.onSurfaceSecondary, fontSize: 13, flex: 1 },
  pointsHint: { color: colors.brandPrimary, fontSize: 12, fontWeight: "700", marginTop: spacing.xs },
  secureHint: { color: colors.muted, fontSize: 11 },
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 420 },
  back: {
    position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20,
    backgroundColor: "rgba(9,9,11,0.5)", alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  heroBottom: { position: "absolute", bottom: spacing.lg, left: spacing.lg, right: spacing.lg },
  tagsRow: { flexDirection: "row", gap: spacing.xs, marginBottom: spacing.sm },
  tag: { backgroundColor: colors.brandSecondary, paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.sm },
  tagText: { color: colors.onBrandSecondary, fontSize: 10, fontWeight: "700", letterSpacing: 0.5 },
  title: { color: colors.onSurface, fontSize: 32, fontWeight: "800", lineHeight: 36 },
  venue: { color: colors.muted, fontSize: 14, marginTop: spacing.xs },
  body: { padding: spacing.lg, gap: spacing.lg },
  infoRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
  },
  chipText: { color: colors.onSurface, fontSize: 12, fontWeight: "600" },
  sectionTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  description: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 22 },
  qtyRow: { flexDirection: "row", alignItems: "center", gap: spacing.xl, alignSelf: "center" },
  qtyBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  qtyBtnText: { color: colors.onSurface, fontSize: 22, fontWeight: "700" },
  qtyValue: { color: colors.onSurface, fontSize: 28, fontWeight: "800", minWidth: 40, textAlign: "center" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    color: colors.onSurface, fontSize: 16,
  },
  breakdown: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.border, gap: spacing.sm,
  },
  rRow: { flexDirection: "row", justifyContent: "space-between" },
  rLabel: { color: colors.muted, fontSize: 14 },
  rValue: { color: colors.onSurface, fontSize: 14 },
  rBold: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  sep: { height: 0.5, backgroundColor: colors.divider, marginVertical: spacing.xs },
  sticky: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: "rgba(9,9,11,0.95)", borderTopWidth: 1, borderTopColor: colors.border,
    padding: spacing.lg,
  },
});
