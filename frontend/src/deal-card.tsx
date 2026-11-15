import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

const PCTS = [10, 20, 30, 50];
const HOURS = [1, 2, 4, 8];

function timeLeft(iso: string | null) {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
  return mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`;
}

/** Host: one-tap price drop for waitlisted guests when the event still has room; expires after the chosen time. */
export function DealCard({ eventId, spotsLeft, upcoming }: { eventId: string; spotsLeft: number; upcoming: boolean }) {
  const qc = useQueryClient();
  const [hours, setHours] = useState(2);
  const { data: live } = useQuery({ queryKey: ["host-live", eventId], queryFn: () => api.hostLive(eventId), refetchInterval: 15000 });
  const send = useMutation({
    mutationFn: (pct: number) => api.sendDeal(eventId, pct, hours),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["host-live", eventId] }),
  });
  if (!live || !upcoming) return null;
  const d = live.deal;

  return (
    <View style={styles.card} testID="deal-card">
      <Text style={styles.title}>Last-minute deal</Text>
      {d ? (
        <Text style={styles.sub} testID="deal-sent">
          {d.pct}% off sent to {d.sent_to} waitlisted guest{d.sent_to === 1 ? "" : "s"} ·{" "}
          {d.expired ? "expired" : `ends in ${timeLeft(d.expires_at)}`}
        </Text>
      ) : live.waitlist === 0 ? (
        <Text style={styles.sub}>Nobody on the waitlist yet.</Text>
      ) : spotsLeft <= 0 ? (
        <Text style={styles.sub}>The event is full. Deals unlock when spots open up.</Text>
      ) : (
        <>
          <Text style={styles.sub}>
            {spotsLeft} spot{spotsLeft === 1 ? "" : "s"} open · {live.waitlist} on the waitlist. Each guest gets the discount on the spots they asked for.
          </Text>
          <Text style={styles.label}>Deal lasts</Text>
          <View style={styles.row}>
            {HOURS.map((h) => (
              <Pressable key={h} testID={`deal-hours-${h}`} onPress={() => setHours(h)} style={[styles.chip, hours === h && styles.chipOn]}>
                <Text style={[styles.chipText, hours === h && styles.chipTextOn]}>{h}h</Text>
              </Pressable>
            ))}
          </View>
          <Text style={styles.label}>Discount</Text>
          <View style={styles.row}>
            {PCTS.map((p) => (
              <Pressable key={p} testID={`deal-${p}`} disabled={send.isPending} onPress={() => send.mutate(p)} style={styles.btn}>
                <Text style={styles.btnText}>{p}% off</Text>
              </Pressable>
            ))}
          </View>
          {send.error ? <Text style={styles.err}>{send.error.message}</Text> : null}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.brandPrimary },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 13 },
  label: { color: colors.muted, fontSize: 11, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase", marginTop: spacing.xs },
  row: { flexDirection: "row", gap: spacing.sm },
  chip: {
    flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.borderStrong,
  },
  chipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { color: colors.muted, fontWeight: "700", fontSize: 13 },
  chipTextOn: { color: colors.brandPrimary },
  btn: { flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  btnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
});
