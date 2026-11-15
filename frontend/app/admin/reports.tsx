import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

/** Admin: problem reports from members, newest first. */
export default function AdminReports() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [status, setStatus] = useState<"open" | "resolved">("open");
  const { data, isLoading, refetch, isRefetching } = useQuery({ queryKey: ["admin-reports", status], queryFn: () => api.adminReports(status) });
  const update = useMutation({
    mutationFn: ({ id, s }: { id: string; s: "open" | "resolved" }) => api.setReportStatus(id, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-reports"] }),
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="reports-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/admin"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Problem reports</Text>
        <View style={{ width: 44 }} />
      </View>
      <View style={styles.tabs}>
        {(["open", "resolved"] as const).map((s) => (
          <Pressable key={s} testID={`reports-tab-${s}`} onPress={() => setStatus(s)} style={[styles.tab, status === s && styles.tabOn]}>
            <Text style={[styles.tabText, status === s && styles.tabTextOn]}>{s === "open" ? "Open" : "Resolved"}</Text>
          </Pressable>
        ))}
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(r) => r.id}
          onRefresh={refetch}
          refreshing={isRefetching}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing.xl }}
          ListEmptyComponent={<Text style={styles.muted}>{status === "open" ? "No open reports. 🎉" : "Nothing resolved yet."}</Text>}
          renderItem={({ item }) => (
            <View style={styles.card} testID={`report-${item.id}`}>
              <Text style={styles.cat}>{item.category.toUpperCase()}{item.context ? ` · from ${item.context}` : ""}</Text>
              <Text style={styles.msg}>{item.message}</Text>
              <Text style={styles.muted}>{item.user_name || "Member"} · {item.user_email} · {new Date(item.created_at).toLocaleString()}</Text>
              <Pressable testID={`report-toggle-${item.id}`} disabled={update.isPending}
                onPress={() => update.mutate({ id: item.id, s: item.status === "open" ? "resolved" : "open" })} style={styles.btn}>
                <Text style={styles.btnText}>{item.status === "open" ? "Mark resolved" : "Reopen"}</Text>
              </Pressable>
            </View>
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
  tabs: { flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg },
  tab: { flex: 1, height: 44, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.borderStrong },
  tabOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  tabText: { color: colors.muted, fontWeight: "700" },
  tabTextOn: { color: colors.brandPrimary },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  cat: { color: colors.brandPrimary, fontSize: 11, fontWeight: "800", letterSpacing: 1 },
  msg: { color: colors.onSurface, fontSize: 15, lineHeight: 21 },
  muted: { color: colors.muted, fontSize: 12 },
  btn: { alignSelf: "flex-start", height: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, justifyContent: "center", backgroundColor: colors.brandPrimary },
  btnText: { color: colors.onBrandPrimary, fontWeight: "800" },
});
