import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, ReportCategory } from "@/src/api";
import { openLegal } from "@/src/legal";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

const CATS: { key: ReportCategory; label: string }[] = [
  { key: "bug", label: "Something's broken" },
  { key: "payment", label: "Payment" },
  { key: "booking", label: "Ticket or booking" },
  { key: "concierge", label: "Concierge chat" },
  { key: "account", label: "Account & privacy" },
  { key: "other", label: "Other" },
];

/** Help & support: report a problem, see past reports, open privacy policy / support page. */
export default function Support() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const params = useLocalSearchParams<{ context?: string | string[] }>();
  const context = Array.isArray(params.context) ? params.context[0] : params.context;
  const [category, setCategory] = useState<ReportCategory>(context === "concierge" ? "concierge" : "bug");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const { data: mine } = useQuery({ queryKey: ["my-reports"], queryFn: api.myReports });
  const send = useMutation({
    mutationFn: () => api.sendReport({ category, message: message.trim(), context: context ?? "profile" }),
    onSuccess: () => {
      setMessage("");
      setSent(true);
      qc.invalidateQueries({ queryKey: ["my-reports"] });
    },
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="support-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/profile"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Help & support</Text>
        <View style={{ width: 44 }} />
      </View>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"] }}>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Report a problem</Text>
          <Text style={styles.muted}>Tell us what happened and we'll follow up, usually within one business day.</Text>
          <View style={styles.chips}>
            {CATS.map((c) => (
              <Pressable key={c.key} testID={`report-cat-${c.key}`} onPress={() => setCategory(c.key)} style={[styles.chip, category === c.key && styles.chipOn]}>
                <Text style={[styles.chipText, category === c.key && styles.chipTextOn]}>{c.label}</Text>
              </Pressable>
            ))}
          </View>
          <TextInput
            testID="report-message"
            value={message}
            onChangeText={(t) => { setMessage(t); setSent(false); }}
            placeholder="What went wrong? Include the event or booking if it helps."
            placeholderTextColor={colors.muted}
            multiline
            maxLength={2000}
            style={styles.input}
          />
          <LuxButton testID="report-submit" label="Send report" onPress={() => send.mutate()} loading={send.isPending}
            disabled={message.trim().length < 5} />
          {send.error ? <Text style={styles.err}>{send.error.message}</Text> : null}
          {sent ? <Text style={styles.ok} testID="report-sent">Thanks — your report was sent. We'll be in touch.</Text> : null}
        </View>

        {mine && mine.length ? (
          <View style={styles.card} testID="my-reports">
            <Text style={styles.cardTitle}>Your reports</Text>
            {mine.map((r) => (
              <View key={r.id} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={2}>{r.message}</Text>
                  <Text style={styles.muted}>{CATS.find((c) => c.key === r.category)?.label} · {new Date(r.created_at).toLocaleDateString()}</Text>
                </View>
                <Text style={[styles.pill, r.status === "resolved" ? styles.pillOk : styles.pillOpen]}>{r.status === "resolved" ? "RESOLVED" : "OPEN"}</Text>
              </View>
            ))}
          </View>
        ) : null}

        <View style={styles.card}>
          <Pressable testID="open-support-page" onPress={() => openLegal("support")} style={styles.link}>
            <FeatherIcon name="help-circle" size={18} color={colors.brandPrimary} />
            <Text style={[styles.rowTitle, { flex: 1 }]}>Support & FAQ</Text>
            <FeatherIcon name="external-link" size={16} color={colors.muted} />
          </Pressable>
          <Pressable testID="open-privacy" onPress={() => openLegal("privacy")} style={styles.link}>
            <FeatherIcon name="shield" size={18} color={colors.brandPrimary} />
            <Text style={[styles.rowTitle, { flex: 1 }]}>Privacy policy</Text>
            <FeatherIcon name="external-link" size={16} color={colors.muted} />
          </Pressable>
        </View>
      </ScrollView>
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
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, borderWidth: 1, borderColor: colors.border },
  cardTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  muted: { color: colors.muted, fontSize: 13 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { paddingHorizontal: spacing.md, height: 44, borderRadius: radius.pill, justifyContent: "center", borderWidth: 1, borderColor: colors.borderStrong },
  chipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { color: colors.muted, fontWeight: "700", fontSize: 13 },
  chipTextOn: { color: colors.brandPrimary },
  input: {
    minHeight: 120, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 15, textAlignVertical: "top",
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  err: { color: colors.error, fontSize: 13 },
  ok: { color: colors.success, fontSize: 13, fontWeight: "700" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider },
  rowTitle: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  pill: { fontSize: 10, fontWeight: "800", letterSpacing: 1, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm, overflow: "hidden" },
  pillOk: { backgroundColor: colors.success, color: colors.onSuccess },
  pillOpen: { backgroundColor: colors.brandTertiary, color: colors.brandPrimary },
  link: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 48 },
});
