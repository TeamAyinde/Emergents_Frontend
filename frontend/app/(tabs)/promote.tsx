import { useQuery } from "@tanstack/react-query";
import QRCode from "react-native-qrcode-svg";
import {
  ActivityIndicator,
  FlatList,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

export default function Promote() {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const isPromoter = user?.role === "promoter" || user?.role === "venue_owner" || user?.role === "admin";

  const { data: stats, isLoading } = useQuery({
    queryKey: ["promoter-stats"],
    queryFn: () => api.promoterStats(),
    enabled: !!isPromoter,
  });
  const { data: board } = useQuery({
    queryKey: ["leaderboard"],
    queryFn: () => api.leaderboard(),
  });

  const code = user?.referral_code ?? "—";
  const shareLink = `https://nocturne.app/r/${code}`;

  async function onShare() {
    try {
      await Share.share({ message: `Join me on Nocturne — use my code ${code} to unlock perks: ${shareLink}` });
    } catch {}
  }

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingHorizontal: spacing.lg,
          paddingBottom: insets.bottom + spacing["3xl"],
          gap: spacing.lg,
        }}
      >
        <View>
          <Text style={styles.eyebrow}>PROMOTER STUDIO</Text>
          <Text style={styles.title}>Your earnings</Text>
        </View>

        {!isPromoter ? (
          <View style={styles.upgrade}>
            <Text style={styles.upgradeTitle}>Earn with every guest</Text>
            <Text style={styles.upgradeText}>
              Upgrade to a Promoter account to receive 40% of the platform fee on every ticket sold through your code.
            </Text>
          </View>
        ) : isLoading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : (
          <>
            <View style={styles.statsRow}>
              <Stat label="Total earned" value={`$${stats?.total_earnings?.toFixed(2) ?? "0.00"}`} testID="stat-earnings" accent />
              <Stat label="Tickets sold" value={`${stats?.tickets_sold ?? 0}`} testID="stat-tickets" />
            </View>
            <View style={styles.statsRow}>
              <Stat label="Checked in" value={`${stats?.guests_checked_in ?? 0}`} testID="stat-checkin" />
              <Stat label="Rank" value={`#${stats?.rank ?? "—"}`} testID="stat-rank" />
            </View>

            <View style={styles.qrCard}>
              <Text style={styles.qrLabel}>YOUR REFERRAL CODE</Text>
              <Text style={styles.qrCode} testID="referral-code">{code}</Text>
              <View style={styles.qrBox}>
                <QRCode value={shareLink} size={160} backgroundColor="#ffffff" color="#000000" />
              </View>
              <LuxButton testID="share-code-btn" label="Share link" onPress={onShare} icon={<FeatherIcon name="share-2" color="#1A0A00" size={16} />} />
              <Text style={styles.qrHint}>You earn 40% of the platform fee on every ticket sold with this code.</Text>
            </View>
          </>
        )}

        <View>
          <Text style={styles.sectionTitle}>Leaderboard</Text>
          <FlatList
            data={board ?? []}
            keyExtractor={(i) => i.user_id}
            scrollEnabled={false}
            ItemSeparatorComponent={() => <View style={styles.sep} />}
            renderItem={({ item, index }) => (
              <View style={styles.row} testID={`leaderboard-row-${index}`}>
                <Text style={styles.rank}>{index + 1}</Text>
                <Text style={styles.rowName}>{item.full_name}</Text>
                <Text style={styles.rowEarn}>${item.earnings.toFixed(2)}</Text>
              </View>
            )}
            ListEmptyComponent={<Text style={styles.empty}>No promoters yet — be the first.</Text>}
          />
        </View>
      </ScrollView>
    </View>
  );
}

function Stat({ label, value, testID, accent }: { label: string; value: string; testID: string; accent?: boolean }) {
  return (
    <View style={[styles.stat, accent && styles.statAccent]} testID={testID}>
      <Text style={[styles.statLabel, accent && { color: colors.onBrandTertiary }]}>{label}</Text>
      <Text style={[styles.statValue, accent && { color: colors.brandPrimary }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  eyebrow: { color: colors.brandPrimary, fontSize: 11, letterSpacing: 2, fontWeight: "700" },
  title: { color: colors.onSurface, fontSize: 28, fontWeight: "800", marginTop: 4 },
  upgrade: {
    backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.brandPrimary,
  },
  upgradeTitle: { color: colors.onBrandTertiary, fontSize: 18, fontWeight: "700" },
  upgradeText: { color: colors.onBrandTertiary, fontSize: 14, marginTop: spacing.xs, lineHeight: 20 },
  statsRow: { flexDirection: "row", gap: spacing.md },
  stat: {
    flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    padding: spacing.lg, borderWidth: 1, borderColor: colors.border,
  },
  statAccent: { backgroundColor: colors.brandTertiary, borderColor: colors.brandPrimary },
  statLabel: { color: colors.muted, fontSize: 11, letterSpacing: 1, fontWeight: "600", textTransform: "uppercase" },
  statValue: { color: colors.onSurface, fontSize: 26, fontWeight: "800", marginTop: spacing.xs },
  qrCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    padding: spacing.xl, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", gap: spacing.md,
  },
  qrLabel: { color: colors.muted, fontSize: 11, letterSpacing: 2, fontWeight: "700" },
  qrCode: { color: colors.brandPrimary, fontSize: 32, fontWeight: "800", letterSpacing: 2 },
  qrBox: { padding: spacing.md, backgroundColor: "#fff", borderRadius: radius.md },
  qrHint: { color: colors.muted, fontSize: 12, textAlign: "center", lineHeight: 18 },
  sectionTitle: { color: colors.onSurface, fontSize: 20, fontWeight: "800", marginBottom: spacing.md },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.md, gap: spacing.md },
  rank: { color: colors.brandPrimary, fontSize: 16, fontWeight: "800", width: 28 },
  rowName: { flex: 1, color: colors.onSurface, fontSize: 15 },
  rowEarn: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  sep: { height: 0.5, backgroundColor: colors.divider },
  empty: { color: colors.muted, paddingVertical: spacing.lg, textAlign: "center" },
});
