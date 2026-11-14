import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";

const BLOCKS = [100, 500, 1000];

export default function Rewards() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["rewards"], queryFn: () => api.rewards() });
  const redeem = useMutation({
    mutationFn: (p: number) => api.redeem(p),
    onSuccess: (r) => {
      qc.setQueryData(["rewards"], r);
      refresh();
    },
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="rewards-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Rewards</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading || !data ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data.history}
          keyExtractor={(h) => h.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.sm }}
          ListHeaderComponent={
            <View style={{ gap: spacing.md, marginBottom: spacing.md }}>
              <View style={styles.hero}>
                <Text style={styles.eyebrow}>YOUR POINTS</Text>
                <Text style={styles.big} testID="rewards-points">{data.points.toLocaleString()}</Text>
                <Text style={styles.sub}>
                  Earning {data.multiplier}× per $1 · {data.points_per_dollar_credit * 5} points = $5 credit
                </Text>
                <Text style={styles.credit} testID="rewards-credit">Credit balance ${data.credit_balance.toFixed(2)} · applied automatically to tickets</Text>
              </View>
              <View style={styles.blocks}>
                {BLOCKS.map((b) => (
                  <Pressable
                    key={b}
                    testID={`redeem-${b}`}
                    disabled={data.points < b || redeem.isPending}
                    onPress={() => redeem.mutate(b)}
                    style={[styles.block, data.points < b && { opacity: 0.4 }]}
                  >
                    <Text style={styles.blockPts}>{b} pts</Text>
                    <Text style={styles.blockVal}>${(b / data.points_per_dollar_credit).toFixed(0)} credit</Text>
                  </Pressable>
                ))}
              </View>
              {redeem.isSuccess ? <Text style={styles.ok} testID="redeem-msg">Redeemed. Your credit is ready.</Text> : null}
              {redeem.error ? <Text style={styles.err}>{redeem.error.message}</Text> : null}
              <Text style={styles.sub}>Gold earns 2×, Silver 1.5× on tickets, tables, reservations and luxe bookings.</Text>
              <Text style={styles.section}>History</Text>
            </View>
          }
          ListEmptyComponent={<Text style={styles.sub}>Book anything to start earning.</Text>}
          renderItem={({ item }) => (
            <View style={styles.row}>
              <Text style={styles.reason} numberOfLines={1}>{item.reason}</Text>
              <Text style={[styles.pts, item.points < 0 && { color: colors.muted }]}>
                {item.points > 0 ? "+" : ""}{item.points}
              </Text>
            </View>
          )}
        />
      )}
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
  hero: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.xl, borderWidth: 1, borderColor: colors.brandPrimary, gap: 4 },
  eyebrow: { color: colors.onBrandTertiary, fontSize: 11, letterSpacing: 2, fontWeight: "700" },
  big: { color: colors.brandPrimary, fontSize: 44, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  credit: { color: colors.onSurface, fontSize: 13, fontWeight: "700", marginTop: spacing.xs },
  blocks: { flexDirection: "row", gap: spacing.sm },
  block: { flex: 1, minHeight: 64, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  blockPts: { color: colors.onSurface, fontSize: 15, fontWeight: "800" },
  blockVal: { color: colors.brandPrimary, fontSize: 12, fontWeight: "700" },
  ok: { color: colors.success, fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
  section: { color: colors.onSurface, fontSize: 18, fontWeight: "800", marginTop: spacing.sm },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.md, borderBottomWidth: 0.5, borderBottomColor: colors.divider, gap: spacing.md },
  reason: { color: colors.onSurfaceSecondary, fontSize: 14, flex: 1 },
  pts: { color: colors.brandPrimary, fontSize: 15, fontWeight: "800" },
});
