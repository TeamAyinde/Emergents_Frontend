import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text, View } from "react-native";

import { api, NightTotals } from "./api";
import { colors, radius, spacing } from "./theme";

type Key = "arrived" | "show_rate" | "revenue";
const ROWS: { key: Key; label: string; fmt: (v: number | null, n: NightTotals) => string }[] = [
  { key: "arrived", label: "Guests in", fmt: (v, n) => `${v ?? 0} of ${n.sold}` },
  { key: "show_rate", label: "Show-up rate", fmt: (v) => (v == null ? "—" : `${v}%`) },
  { key: "revenue", label: "Your revenue", fmt: (v) => `$${(v ?? 0).toLocaleString("en", { maximumFractionDigits: 2 })}` },
];

/** Host: after the night, totals compared with the venue's previous 4 events. */
export function SummaryCard({ eventId }: { eventId: string }) {
  const { data } = useQuery({ queryKey: ["event-summary", eventId], queryFn: () => api.eventSummary(eventId) });
  if (!data) return null;
  const { night, baseline, change } = data;

  return (
    <View style={styles.card} testID="summary-card">
      <Text style={styles.title}>Night summary</Text>
      <Text style={styles.sub}>
        {baseline ? `Compared with your last ${data.compared} event${data.compared > 1 ? "s" : ""}` : "Your first event here — trends start next time"}
        {data.peak ? ` · peak ${data.peak}` : ""}
      </Text>
      {ROWS.map((r) => {
        const c = change[r.key];
        return (
          <View key={r.key} style={styles.row} testID={`summary-${r.key}`}>
            <Text style={styles.label}>{r.label}</Text>
            <Text style={styles.value}>{r.fmt(night[r.key], night)}</Text>
            {baseline ? <Text style={styles.base}>avg {r.fmt(baseline[r.key], baseline)}</Text> : null}
            {c != null ? (
              <Text style={[styles.chg, { color: c > 0 ? colors.success : c < 0 ? colors.error : colors.muted }]}>
                {c > 0 ? `+${c}` : c}%
              </Text>
            ) : null}
          </View>
        );
      })}
      <View style={styles.row}>
        <Text style={styles.label}>Tables · no-shows</Text>
        <Text style={styles.value}>{night.tables} · {night.no_shows}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs, borderTopWidth: 0.5, borderTopColor: colors.divider },
  label: { color: colors.muted, fontSize: 13, flex: 1 },
  value: { color: colors.onSurface, fontSize: 15, fontWeight: "800" },
  base: { color: colors.muted, fontSize: 12, minWidth: 64, textAlign: "right" },
  chg: { fontSize: 13, fontWeight: "800", minWidth: 44, textAlign: "right" },
});
