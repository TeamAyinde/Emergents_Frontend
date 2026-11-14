import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import type { Venue } from "./api";
import { FeaturedBadge } from "./featured-badge";
import { startCheckout } from "./payments";
import { colors, radius, spacing } from "./theme";

const PLANS = [
  { plan: "week" as const, label: "7 days", price: 49 },
  { plan: "month" as const, label: "30 days", price: 149 },
];

/** Host Studio card: pay to pin a venue (and its events) to the top of the directory and feed. */
export function BoostCard({ venue }: { venue: Venue }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const until = venue.featured && venue.featured_until ? new Date(venue.featured_until) : null;

  async function buy(plan: "week" | "month") {
    setErr("");
    setBusy(plan);
    try {
      await startCheckout({ kind: "boost", venue_id: venue.id, plan }, router);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Try again");
    } finally {
      setBusy(null);
    }
  }

  return (
    <View style={styles.card} testID={`boost-card-${venue.id}`}>
      <View style={styles.row}>
        <FeatherIcon name="zap" size={16} color={colors.brandPrimary} />
        <Text style={styles.name} numberOfLines={1}>{venue.name}</Text>
        {until ? <FeaturedBadge /> : null}
      </View>
      <Text style={styles.sub}>
        {until
          ? `Featured until ${until.toLocaleDateString("en", { month: "short", day: "numeric" })}. Extend to stay on top.`
          : "Pin this venue and its events to the top of the directory and feed."}
      </Text>
      <View style={styles.row}>
        {PLANS.map((p) => (
          <Pressable
            key={p.plan}
            testID={`boost-${p.plan}-${venue.id}`}
            disabled={!!busy}
            onPress={() => buy(p.plan)}
            style={[styles.plan, busy && busy !== p.plan && { opacity: 0.5 }]}
          >
            <Text style={styles.planPrice}>{busy === p.plan ? "Opening…" : `$${p.price}`}</Text>
            <Text style={styles.planLabel}>{p.label}</Text>
          </Pressable>
        ))}
      </View>
      {err ? <Text style={styles.err}>{err}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.brandPrimary },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  name: { color: colors.onSurface, fontSize: 16, fontWeight: "800", flex: 1 },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  plan: {
    flex: 1, minHeight: 56, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center",
  },
  planPrice: { color: colors.brandPrimary, fontSize: 18, fontWeight: "900" },
  planLabel: { color: colors.onSurfaceSecondary, fontSize: 12 },
  err: { color: colors.error, fontSize: 13 },
});
