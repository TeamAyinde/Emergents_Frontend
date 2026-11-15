import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

const PCTS = [10, 20, 30, 50];

/** Host: one-tap price drop for waitlisted guests when the event still has room. */
export function DealCard({ eventId, spotsLeft, upcoming }: { eventId: string; spotsLeft: number; upcoming: boolean }) {
  const qc = useQueryClient();
  const { data: live } = useQuery({ queryKey: ["host-live", eventId], queryFn: () => api.hostLive(eventId), refetchInterval: 15000 });
  const send = useMutation({
    mutationFn: (pct: number) => api.sendDeal(eventId, pct),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["host-live", eventId] }),
  });
  if (!live || !upcoming) return null;

  return (
    <View style={styles.card} testID="deal-card">
      <Text style={styles.title}>Last-minute deal</Text>
      {live.deal ? (
        <Text style={styles.sub} testID="deal-sent">
          {live.deal.pct}% off sent to {live.deal.sent_to} waitlisted guest{live.deal.sent_to === 1 ? "" : "s"}.
        </Text>
      ) : live.waitlist === 0 ? (
        <Text style={styles.sub}>Nobody on the waitlist yet.</Text>
      ) : spotsLeft <= 0 ? (
        <Text style={styles.sub}>The event is full. Deals unlock when spots open up.</Text>
      ) : (
        <>
          <Text style={styles.sub}>
            {spotsLeft} spot{spotsLeft === 1 ? "" : "s"} open · {live.waitlist} on the waitlist. Send them a price drop with one tap.
          </Text>
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
  row: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  btn: { flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  btnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
});
