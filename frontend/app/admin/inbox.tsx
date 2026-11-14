import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { LEVEL_INFO, Level } from "@/src/levels";
import { colors, radius, spacing } from "@/src/theme";

export default function ConciergeInbox() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["admin-threads"],
    queryFn: () => api.adminThreads(),
    refetchInterval: 5000,
  });
  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="inbox-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Concierge inbox</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(t) => t.member_id}
          onRefresh={refetch}
          refreshing={isRefetching}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, gap: spacing.sm }}
          ListEmptyComponent={<Text style={styles.empty}>No member requests yet.</Text>}
          renderItem={({ item }) => {
            const info = LEVEL_INFO[(item.member_level as Level) ?? "bronze"];
            return (
              <Pressable testID={`thread-${item.member_id}`} onPress={() => router.push(`/admin/thread/${item.member_id}?name=${encodeURIComponent(item.member_name)}`)} style={styles.row}>
                <View style={[styles.avatar, { borderColor: info.color }]}>
                  <Text style={[styles.avatarText, { color: info.color }]}>{item.member_name[0]?.toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.rowTop}>
                    <Text style={styles.name} numberOfLines={1}>{item.member_name}</Text>
                    <Text style={[styles.level, { color: info.color }]}>{info.label.toUpperCase()}</Text>
                  </View>
                  <Text style={styles.last} numberOfLines={1}>{item.last_text}</Text>
                </View>
                {item.unread > 0 ? (
                  <View style={styles.badge}><Text style={styles.badgeText}>{item.unread}</Text></View>
                ) : null}
              </Pressable>
            );
          }}
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
  empty: { color: colors.muted, textAlign: "center", paddingTop: spacing["2xl"] },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg, padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  avatar: { width: 44, height: 44, borderRadius: 22, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  avatarText: { fontSize: 18, fontWeight: "800" },
  rowTop: { flexDirection: "row", justifyContent: "space-between", gap: spacing.sm },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700", flex: 1 },
  level: { fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  last: { color: colors.muted, fontSize: 13, marginTop: 2 },
  badge: { minWidth: 22, height: 22, borderRadius: 11, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center", paddingHorizontal: 6 },
  badgeText: { color: colors.onBrandSecondary, fontSize: 12, fontWeight: "800" },
});
