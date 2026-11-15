import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

const BAR_H = 120;

/** Live door counter for hosts on event night — refreshes every 5 seconds. */
export default function HostLive() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, error, refetch, isRefetching } = useQuery({
    queryKey: ["host-live", id], queryFn: () => api.hostLive(id!), refetchInterval: 5000,
  });

  const pct = data && data.capacity ? Math.min(100, Math.round((100 * data.checked_in) / data.capacity)) : 0;
  const top = Math.max(1, ...(data?.by_hour ?? []).map((h) => h.count));
  const fmtHour = (s: string) => new Date(s).toLocaleTimeString("en", { hour: "numeric" });
  const fmtTime = (s: string) => new Date(s).toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="live-back" onPress={() => (router.canGoBack() ? router.back() : router.replace(data?.is_staff_view ? "/door" : "/host"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>{data?.title ?? "Live door"}</Text>
        <Pressable testID="live-scan-btn" onPress={() => router.push("/checkin")} style={styles.iconBtn}>
          <FeatherIcon name="maximize" size={18} color={colors.brandPrimary} />
        </Pressable>
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : !data ? (
        <Text style={[styles.muted, { textAlign: "center", marginTop: spacing["2xl"] }]}>{error?.message ?? "Couldn't load"}</Text>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brandPrimary} />}
        >
          <View style={styles.hero}>
            <View style={styles.liveRow}>
              <View style={styles.dot} />
              <Text style={styles.liveText}>LIVE · updates every 5s</Text>
            </View>
            <Text style={styles.count} testID="live-count">{data.checked_in}</Text>
            <Text style={styles.muted}>guests through the door</Text>
            <View style={styles.track}>
              <View style={[styles.fill, { width: `${pct}%` }]} />
            </View>
            <Text style={styles.muted} testID="live-capacity">{pct}% of {data.capacity} capacity</Text>
          </View>

          <View style={styles.stats}>
            <Stat label="Tickets" value={data.tickets_sold} />
            <Stat label="Still to arrive" value={Math.max(0, data.tickets_sold - data.checked_in)} />
            <Stat label="Waitlist" value={data.waitlist} />
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Arrivals by hour</Text>
            {data.by_hour.length === 0 ? (
              <Text style={styles.muted}>No check-ins yet. Scan the first ticket to get started.</Text>
            ) : (
              <View style={styles.chart} testID="arrivals-chart">
                {data.by_hour.map((h) => (
                  <View key={h.hour} style={styles.barCol}>
                    <Text style={styles.barVal}>{h.count}</Text>
                    <View style={[styles.bar, { height: Math.max(4, (BAR_H * h.count) / top) }]} />
                    <Text style={styles.barLabel}>{fmtHour(h.hour)}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Latest arrivals</Text>
            {data.recent.length === 0 ? <Text style={styles.muted}>Nobody yet.</Text> : null}
            {data.recent.map((a, i) => (
              <View key={a.at + i} style={styles.row}>
                <Text style={styles.name}>{a.name}{a.quantity > 1 ? ` +${a.quantity - 1}` : ""}</Text>
                <Text style={styles.muted}>{fmtTime(a.at)}</Text>
              </View>
            ))}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statVal}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700", flex: 1, textAlign: "center" },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  hero: {
    alignItems: "center", gap: spacing.xs, padding: spacing.xl, borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.brandPrimary,
  },
  liveRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  liveText: { color: colors.success, fontSize: 11, fontWeight: "800", letterSpacing: 1.5 },
  count: { color: colors.onSurface, fontSize: 72, fontWeight: "800", lineHeight: 80 },
  track: { alignSelf: "stretch", height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden", marginTop: spacing.sm },
  fill: { height: 8, backgroundColor: colors.brandPrimary },
  stats: { flexDirection: "row", gap: spacing.sm },
  stat: { flex: 1, alignItems: "center", padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  statVal: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  statLabel: { color: colors.muted, fontSize: 11, marginTop: 2, textAlign: "center" },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  cardTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  chart: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, minHeight: BAR_H + 40 },
  barCol: { flex: 1, alignItems: "center", gap: 4, maxWidth: 56 },
  bar: { alignSelf: "stretch", borderTopLeftRadius: 6, borderTopRightRadius: 6, backgroundColor: colors.brandPrimary },
  barVal: { color: colors.onSurface, fontSize: 12, fontWeight: "700" },
  barLabel: { color: colors.muted, fontSize: 11 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  muted: { color: colors.muted, fontSize: 13 },
});
