import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { startCheckout } from "./payments";
import { colors, radius, spacing } from "./theme";

const PLANS = [
  { plan: "3days" as const, label: "3 days", price: 39 },
  { plan: "week" as const, label: "7 days", price: 79 },
];

/** Promoters pay to pin one event to the very top of the home feed. */
export function SpotlightCard({ eventId, active }: { eventId: string; active?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  async function buy(plan: "3days" | "week") {
    setErr("");
    setBusy(plan);
    try {
      await startCheckout({ kind: "spotlight", event_id: eventId, plan }, router);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Try again");
    } finally {
      setBusy(null);
    }
  }

  return (
    <View style={styles.card} testID="spotlight-card">
      <View style={styles.row}>
        <FeatherIcon name="zap" size={16} color={colors.brandPrimary} />
        <Text style={styles.title}>{active ? "Spotlighted — extend it" : "Spotlight this event"}</Text>
      </View>
      <Text style={styles.sub}>Pin it to the top of the home feed for every guest and fill the list faster.</Text>
      <View style={styles.row}>
        {PLANS.map((p) => (
          <Pressable
            key={p.plan}
            testID={`spotlight-${p.plan}`}
            disabled={!!busy}
            onPress={() => buy(p.plan)}
            style={[styles.plan, busy && busy !== p.plan && { opacity: 0.5 }]}
          >
            <Text style={styles.price}>{busy === p.plan ? "Opening…" : `$${p.price}`}</Text>
            <Text style={styles.label}>{p.label}</Text>
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
  title: { color: colors.onSurface, fontSize: 16, fontWeight: "800", flex: 1 },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  plan: {
    flex: 1, minHeight: 56, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center",
  },
  price: { color: colors.brandPrimary, fontSize: 18, fontWeight: "900" },
  label: { color: colors.onSurfaceSecondary, fontSize: 12 },
  err: { color: colors.error, fontSize: 13 },
});
