import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Ticket } from "./api";
import { useAuth } from "./auth-context";
import { canAccess, Level } from "./levels";
import { colors, radius, spacing } from "./theme";

const DAY_MS = 12 * 60 * 60 * 1000;

/** Event-day prompt on a ticket: VIP tables still open for this guest's level. */
export function TableUpsell({ ticket }: { ticket: Ticket }) {
  const router = useRouter();
  const { user } = useAuth();
  const startsIn = new Date(ticket.event_date).getTime() - Date.now();
  const eventDay = startsIn > 0 && startsIn <= DAY_MS && !ticket.checked_in;
  const { data: tables } = useQuery({
    queryKey: ["event-tables", ticket.event_id],
    queryFn: () => api.eventTables(ticket.event_id),
    enabled: eventDay,
  });
  const { data: mine } = useQuery({ queryKey: ["my-tables"], queryFn: api.myTables, enabled: eventDay });
  if (!eventDay || !tables || !mine) return null;
  if (mine.some((b) => b.event_id === ticket.event_id && b.status === "confirmed")) return null;
  const lvl = (user?.level ?? "bronze") as Level;
  const open = tables.filter((t) => !t.booked && canAccess(lvl, t.min_level as Level));
  if (!open.length) return null;
  const from = Math.min(...open.map((t) => t.min_spend));

  return (
    <Pressable testID="table-upsell" onPress={() => router.push(`/event/${ticket.event_id}`)} style={styles.card}>
      <View style={styles.icon}>
        <FeatherIcon name="star" size={18} color={colors.brandPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>Make it a VIP night</Text>
        <Text style={styles.sub}>
          {open.length} table{open.length > 1 ? "s" : ""} still open tonight · from ${from.toLocaleString("en")} min spend
        </Text>
      </View>
      <FeatherIcon name="chevron-right" size={18} color={colors.muted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 64, padding: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary,
  },
  icon: {
    width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surfaceTertiary,
  },
  title: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  sub: { color: colors.muted, fontSize: 13, marginTop: 2 },
});
