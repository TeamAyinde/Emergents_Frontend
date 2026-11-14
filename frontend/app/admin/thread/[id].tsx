import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { ChatView } from "@/src/chat-view";
import { colors, spacing } from "@/src/theme";

export default function AdminThread() {
  const { id, name } = useLocalSearchParams<{ id: string; name?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const load = useCallback(async () => {
    const m = await api.adminThreadMessages(id!);
    qc.invalidateQueries({ queryKey: ["admin-threads"] });
    return m;
  }, [id, qc]);
  const send = useCallback(async (t: string) => {
    await api.adminReply(id!, t);
    qc.invalidateQueries({ queryKey: ["admin-threads"] });
  }, [id, qc]);
  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="thread-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{name ?? "Member request"}</Text>
        <View style={{ width: 44 }} />
      </View>
      <ChatView
        load={load}
        send={send}
        mine={(m) => m.sender === "concierge"}
        placeholder="Reply as concierge…"
        emptyText="No messages yet."
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
});
