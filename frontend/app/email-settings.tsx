import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, EmailPrefs } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

const ROWS: { key: keyof EmailPrefs; title: string; sub: string }[] = [
  { key: "reminders", title: "Event reminders", sub: "Your QR ticket the day before" },
  { key: "receipts", title: "Renewal receipts", sub: "Each time Silver or Gold renews" },
  { key: "feedback", title: "Rate your night", sub: "The morning after, earn bonus points" },
  { key: "offers", title: "Member offers", sub: "Exclusive discounts and perks" },
  { key: "newsletter", title: "Newsletter", sub: "Lifestyle stories and new venues" },
];

/** Members choose which emails they get. Booking confirmations are always sent. */
export default function EmailSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["email-prefs"], queryFn: api.emailPrefs });
  const save = useMutation({
    mutationFn: api.saveEmailPrefs,
    onMutate: (p) => qc.setQueryData(["email-prefs"], p),
    onError: () => qc.invalidateQueries({ queryKey: ["email-prefs"] }),
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="email-settings-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/profile"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Email preferences</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading || !data ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing["2xl"] }}>
          {ROWS.map((r) => (
            <Pressable
              key={r.key}
              testID={`pref-row-${r.key}`}
              onPress={() => save.mutate({ ...data, [r.key]: !data[r.key] })}
              style={styles.row}
              accessibilityRole="switch"
              accessibilityState={{ checked: data[r.key] }}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.title}>{r.title}</Text>
                <Text style={styles.sub}>{r.sub}</Text>
              </View>
              <Switch
                testID={`pref-${r.key}`}
                value={data[r.key]}
                onValueChange={(v) => save.mutate({ ...data, [r.key]: v })}
                trackColor={{ true: colors.brandPrimary, false: colors.surfaceTertiary }}
                thumbColor={colors.onSurface}
                {...({ activeThumbColor: colors.onSurface } as object)}
              />
            </Pressable>
          ))}
          {save.error ? <Text style={styles.err}>{save.error.message}</Text> : null}
          <Text style={styles.hint}>Ticket and booking confirmations are always sent so you can get in.</Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 64, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  title: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  sub: { color: colors.muted, fontSize: 13, marginTop: 2 },
  err: { color: colors.error, fontSize: 13 },
  hint: { color: colors.muted, fontSize: 12, marginTop: spacing.md },
});
