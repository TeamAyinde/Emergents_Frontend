import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text, View } from "react-native";

import { api, MonthStats } from "./api";
import { colors, radius, spacing } from "./theme";

/** Host Studio: which discount levels converted best across all past deals. */
export function DealLeaderboard() {
  const { data } = useQuery({ queryKey: ["deal-leaderboard"], queryFn: api.dealLeaderboard });
  if (!data || data.length === 0) return null;
  return (
    <View style={styles.card} testID="deal-leaderboard">
      <Text style={styles.title}>Deal performance</Text>
      <Text style={styles.sub}>Which price drops waitlisted guests actually bought</Text>
      {data.map((d, i) => (
        <View key={d.pct} style={styles.row} testID={`deal-level-${d.pct}`}>
          <Text style={[styles.rank, i === 0 && styles.best]}>{i === 0 ? "★" : i + 1}</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{d.pct}% off</Text>
            <Text style={styles.sub}>
              {d.deals} deal{d.deals === 1 ? "" : "s"} · {d.buyers}/{d.sent_to} bought · {d.tickets} tickets
            </Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.value}>{d.conversion}%</Text>
            <Text style={styles.sub}>${d.revenue.toLocaleString("en", { maximumFractionDigits: 0 })}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

const ROWS: { key: keyof MonthStats & ("arrived" | "revenue" | "show_rate" | "rating"); label: string }[] = [
  { key: "arrived", label: "Guests" },
  { key: "revenue", label: "Revenue" },
  { key: "show_rate", label: "Show-up" },
  { key: "rating", label: "Rating" },
];

function fmt(k: string, v: number | null) {
  if (v == null) return "—";
  if (k === "revenue") return `$${v.toLocaleString("en", { maximumFractionDigits: 0 })}`;
  if (k === "show_rate") return `${v}%`;
  if (k === "rating") return `${v.toFixed(1)}★`;
  return String(v);
}

/** Host Studio: this month so far vs last month, per venue. */
export function MonthReportCard() {
  const { data } = useQuery({ queryKey: ["host-report"], queryFn: () => api.hostReport() });
  if (!data || data.length === 0) return null;
  return (
    <View style={styles.card} testID="month-report">
      <Text style={styles.title}>{data[0].month} so far</Text>
      <Text style={styles.sub}>Compared with last month · full report emailed on the 1st</Text>
      {data.map((r) => (
        <View key={r.venue_id} style={{ gap: spacing.xs, marginTop: spacing.sm }}>
          <Text style={styles.name}>{r.venue_name} · {r.current.events} event{r.current.events === 1 ? "" : "s"}</Text>
          <View style={styles.grid}>
            {ROWS.map(({ key, label }) => {
              const c = r.change[key];
              return (
                <View key={key} style={styles.cell} testID={`report-${r.venue_id}-${key}`}>
                  <Text style={styles.value}>{fmt(key, r.current[key])}</Text>
                  <Text style={styles.sub}>{label}</Text>
                  {c != null ? (
                    <Text style={[styles.chg, { color: c > 0 ? colors.success : c < 0 ? colors.error : colors.muted }]}>{c > 0 ? `+${c}` : c}%</Text>
                  ) : null}
                </View>
              );
            })}
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.xs, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 12 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider },
  rank: { width: 24, textAlign: "center", color: colors.muted, fontSize: 15, fontWeight: "800" },
  best: { color: colors.brandPrimary },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  value: { color: colors.onSurface, fontSize: 16, fontWeight: "800" },
  grid: { flexDirection: "row", gap: spacing.sm },
  cell: { flex: 1, alignItems: "center", paddingVertical: spacing.sm, borderRadius: radius.md, backgroundColor: colors.surface },
  chg: { fontSize: 12, fontWeight: "800", marginTop: 2 },
});
