import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

/** Host Studio: what guests said after their night. */
export function HostFeedbackCard() {
  const { data } = useQuery({ queryKey: ["host-feedback"], queryFn: api.hostFeedback });
  if (!data) return null;
  return (
    <View style={styles.card} testID="host-feedback-card">
      <View style={styles.head}>
        <Text style={styles.title}>Guest feedback</Text>
        {data.average != null ? (
          <View style={styles.avg} testID="host-feedback-avg">
            <FeatherIcon name="star" size={14} color={colors.brandPrimary} />
            <Text style={styles.avgText}>{data.average.toFixed(1)} · {data.count}</Text>
          </View>
        ) : null}
      </View>
      {data.items.length === 0 ? <Text style={styles.muted}>Ratings from your guests will appear here the day after each event.</Text> : null}
      {data.items.slice(0, 10).map((f) => (
        <View key={f.id} style={styles.item} testID={`host-feedback-${f.id}`}>
          <View style={styles.head}>
            <Text style={styles.stars}>{"★".repeat(f.rating)}<Text style={styles.dim}>{"★".repeat(5 - f.rating)}</Text></Text>
            <Text style={styles.muted}>{new Date(f.created_at).toLocaleDateString("en", { month: "short", day: "numeric" })}</Text>
          </View>
          {f.comment ? <Text style={styles.comment}>“{f.comment}”</Text> : null}
          <Text style={styles.muted} numberOfLines={1}>{f.guest} · {f.event_title}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  avg: { flexDirection: "row", alignItems: "center", gap: 4 },
  avgText: { color: colors.onSurface, fontSize: 14, fontWeight: "700" },
  item: { borderTopWidth: 0.5, borderTopColor: colors.divider, paddingTop: spacing.sm, gap: 4 },
  stars: { color: colors.brandPrimary, fontSize: 14, letterSpacing: 1 },
  dim: { color: colors.border },
  comment: { color: colors.onSurface, fontSize: 14, lineHeight: 20 },
  muted: { color: colors.muted, fontSize: 12 },
});
