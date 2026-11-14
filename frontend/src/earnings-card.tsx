import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text, View } from "react-native";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

const SOURCE: Record<string, string> = { ticket: "Tickets", table: "Tables", reservation: "Reservations" };

/** Host Studio: bookings, what Nocturne owes the venue and what has been paid out. */
export function EarningsCard() {
  const { data } = useQuery({ queryKey: ["host-earnings"], queryFn: api.hostEarnings });
  if (!data) return null;
  const sources = Object.entries(data.by_source);
  return (
    <View style={styles.card} testID="earnings-card">
      <Text style={styles.title}>Earnings</Text>
      <View style={styles.row}>
        <Stat label="Owed to you" value={data.owed} testID="earnings-owed" />
        <Stat label="Paid out" value={data.paid} testID="earnings-paid" />
      </View>
      {sources.length ? (
        sources.map(([k, v]) => (
          <View key={k} style={styles.line}>
            <Text style={styles.lineText}>{SOURCE[k] ?? k} · {v.count}</Text>
            <Text style={styles.lineValue}>${v.amount.toFixed(2)}</Text>
          </View>
        ))
      ) : (
        <Text style={styles.muted}>Your bookings and earnings will show here.</Text>
      )}
      {data.recent.slice(0, 5).map((r) => (
        <View key={r.id} style={styles.line}>
          <Text style={styles.muted} numberOfLines={1}>
            {new Date(r.created_at).toLocaleDateString("en", { month: "short", day: "numeric" })} · {SOURCE[r.source] ?? r.source} · {r.venue_name}
          </Text>
          <Text style={[styles.lineValue, { color: r.status === "paid" ? colors.success : colors.onSurface }]}>
            ${r.amount.toFixed(2)}
          </Text>
        </View>
      ))}
    </View>
  );
}

function Stat({ label, value, testID }: { label: string; value: number; testID: string }) {
  return (
    <View style={{ flex: 1 }} testID={testID}>
      <Text style={styles.value}>${value.toFixed(2)}</Text>
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  row: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.xs },
  value: { color: colors.brandPrimary, fontSize: 22, fontWeight: "800" },
  muted: { color: colors.muted, fontSize: 13, flexShrink: 1 },
  line: { flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  lineText: { color: colors.onSurfaceSecondary, fontSize: 14 },
  lineValue: { color: colors.onSurface, fontSize: 14, fontWeight: "700" },
});
