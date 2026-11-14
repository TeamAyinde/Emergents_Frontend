import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";
import { BoostCard } from "@/src/boost-card";

export default function HostStudio() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, refetch, isRefetching } = useQuery({ queryKey: ["host-events"], queryFn: () => api.hostEvents() });
  const { data: venues } = useQuery({ queryKey: ["host-venues"], queryFn: () => api.hostVenues() });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="host-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Host Studio</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(e) => e.id}
          onRefresh={refetch}
          refreshing={isRefetching}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}
          ListHeaderComponent={
            <View style={{ gap: spacing.md, marginBottom: spacing.sm }}>
              <LuxButton testID="host-new-event-btn" label="Post a new event" onPress={() => router.push("/host/new-event")} />
              <Text style={styles.muted}>
                {venues?.length ? `Your venues: ${venues.map((v) => v.name).join(", ")}` : "Add your venue when you post your first event."}
              </Text>
              {venues?.length ? <Text style={styles.section}>Featured boosts</Text> : null}
              {venues?.map((v) => <BoostCard key={v.id} venue={v} />)}
              <Text style={styles.section}>Your events</Text>
            </View>
          }
          ListEmptyComponent={<Text style={styles.muted}>No events yet.</Text>}
          renderItem={({ item }) => (
            <Pressable testID={`host-event-${item.id}`} onPress={() => router.push(`/host/event/${item.id}`)} style={styles.card}>
              <View style={styles.rowBetween}>
                <Text style={styles.cardTitle} numberOfLines={1}>{item.title}</Text>
                {item.pending_requests > 0 ? (
                  <View style={styles.badge}><Text style={styles.badgeText}>{item.pending_requests} pending</Text></View>
                ) : null}
              </View>
              <Text style={styles.muted}>
                {item.venue_name} · {new Date(item.date).toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric" })}
              </Text>
              <View style={styles.stats}>
                <Stat label="Sold" value={`${item.tickets_sold}/${item.capacity}`} />
                <Stat label="In" value={`${item.checked_in}`} />
                <Stat label="Tables" value={`${item.tables_booked}/${item.tables_total}`} />
                <Stat label="Gross" value={`$${(item.tickets_sold * item.price).toFixed(0)}`} />
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  section: { color: colors.onSurface, fontSize: 18, fontWeight: "800", marginTop: spacing.sm },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.xs, borderWidth: 1, borderColor: colors.border },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  cardTitle: { color: colors.onSurface, fontSize: 16, fontWeight: "800", flex: 1 },
  badge: { backgroundColor: colors.brandSecondary, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 3 },
  badgeText: { color: colors.onBrandSecondary, fontSize: 11, fontWeight: "800" },
  stats: { flexDirection: "row", marginTop: spacing.sm },
  statLabel: { color: colors.muted, fontSize: 10, letterSpacing: 1, fontWeight: "700", textTransform: "uppercase" },
  statValue: { color: colors.onSurface, fontSize: 15, fontWeight: "800", marginTop: 2 },
});
