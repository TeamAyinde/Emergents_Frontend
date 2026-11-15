import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

/** Door staff home: their venues' events with one tap to scan or watch the live counter. */
export default function DoorDuty() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, refetch, isRefetching } = useQuery({ queryKey: ["door-duty"], queryFn: api.doorDuty });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="door-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/profile"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Door duty</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data?.events ?? []}
          keyExtractor={(e) => e.id}
          onRefresh={refetch}
          refreshing={isRefetching}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}
          ListHeaderComponent={
            <View style={{ gap: spacing.md, marginBottom: spacing.sm }}>
              <Text style={styles.muted}>
                {data?.venues.length ? `You're on the door team at ${data.venues.join(", ")}.` : "You're not on any door team yet."}
              </Text>
              {data?.venues.length ? <LuxButton testID="door-scan-btn" label="Scan tickets" onPress={() => router.push("/checkin")} /> : null}
            </View>
          }
          ListEmptyComponent={data?.venues.length ? <Text style={styles.muted}>No upcoming events at your venues.</Text> : null}
          renderItem={({ item }) => (
            <Pressable testID={`duty-event-${item.id}`} onPress={() => router.push(`/host/live/${item.id}`)} style={styles.card}>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{item.title}</Text>
                <Text style={styles.muted}>
                  {new Date(item.date).toLocaleString("en", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                  {" · "}{item.venue_name}
                </Text>
                <Text style={styles.muted}>{item.tickets_sold} / {item.capacity} tickets</Text>
              </View>
              <View style={styles.live}>
                <FeatherIcon name="activity" size={16} color={colors.brandPrimary} />
                <Text style={styles.liveText}>Live</Text>
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700", flex: 1, textAlign: "center" },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  name: { color: colors.onSurface, fontSize: 16, fontWeight: "700" },
  muted: { color: colors.muted, fontSize: 13, marginTop: 2 },
  live: { alignItems: "center", gap: 2 },
  liveText: { color: colors.brandPrimary, fontSize: 11, fontWeight: "800" },
});
