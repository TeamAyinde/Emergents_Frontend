import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, EmailPrefs, PushPrefs } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";

type Row<K> = { key: K; title: string; sub: string };

const PUSH_ROWS: Row<keyof PushPrefs>[] = [
  { key: "event_night", title: "Event night alerts", sub: "2 hours before doors, ticket ready to scan" },
  { key: "updates", title: "Guest list & bookings", sub: "Approvals, new requests, tables and reservations" },
  { key: "concierge", title: "Concierge replies", sub: "When your lifestyle manager answers" },
  { key: "sales", title: "Sales through your link", sub: "The moment someone buys with your code" },
];

const ROWS: Row<keyof EmailPrefs>[] = [
  { key: "reminders", title: "Event reminders", sub: "Your QR ticket the day before" },
  { key: "receipts", title: "Renewal receipts", sub: "Each time Silver or Gold renews" },
  { key: "feedback", title: "Rate your night", sub: "The morning after, earn bonus points" },
  { key: "offers", title: "Member offers", sub: "Exclusive discounts and perks" },
  { key: "newsletter", title: "Newsletter", sub: "Lifestyle stories and new venues" },
];

/** One labelled switch row. */
function PrefRow({ id, title, sub, value, onChange }: { id: string; title: string; sub: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Pressable testID={`pref-row-${id}`} onPress={() => onChange(!value)} style={styles.row}
      accessibilityRole="switch" accessibilityState={{ checked: value }}>
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.sub}>{sub}</Text>
      </View>
      <Switch
        testID={`pref-${id}`}
        value={value}
        onValueChange={onChange}
        trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
        thumbColor={colors.onSurface}
        {...({ activeThumbColor: colors.onSurface } as object)}
      />
    </Pressable>
  );
}

/** Members choose which phone alerts and emails they get. Booking confirmations are always sent. */
export default function EmailSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { user } = useAuth();
  const { data, isLoading } = useQuery({ queryKey: ["email-prefs"], queryFn: api.emailPrefs });
  const { data: push, isLoading: pushLoading } = useQuery({ queryKey: ["push-prefs"], queryFn: api.pushPrefs });
  const save = useMutation({
    mutationFn: api.saveEmailPrefs,
    onMutate: (p) => qc.setQueryData(["email-prefs"], p),
    onError: () => qc.invalidateQueries({ queryKey: ["email-prefs"] }),
  });
  const savePush = useMutation({
    mutationFn: api.savePushPrefs,
    onMutate: (p) => qc.setQueryData(["push-prefs"], p),
    onError: () => qc.invalidateQueries({ queryKey: ["push-prefs"] }),
  });
  const sells = user?.role === "promoter" || user?.role === "venue_owner" || user?.role === "admin";

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="email-settings-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/profile"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Notifications</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading || pushLoading || !data || !push ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing["2xl"] }}>
          <Text style={styles.section}>Phone alerts</Text>
          {PUSH_ROWS.filter((r) => r.key !== "sales" || sells).map((r) => (
            <PrefRow key={r.key} id={`push-${r.key}`} title={r.title} sub={r.sub} value={push[r.key]}
              onChange={(v) => savePush.mutate({ ...push, [r.key]: v })} />
          ))}
          {savePush.error ? <Text style={styles.err}>{savePush.error.message}</Text> : null}
          <Text style={styles.hintSmall}>Phone alerts need notifications allowed for the app in your phone settings.</Text>
          <Text style={[styles.section, { marginTop: spacing.lg }]}>Emails</Text>
          {ROWS.map((r) => (
            <PrefRow key={r.key} id={r.key} title={r.title} sub={r.sub} value={data[r.key]}
              onChange={(v) => save.mutate({ ...data, [r.key]: v })} />
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
  hintSmall: { color: colors.muted, fontSize: 12 },
  section: { color: colors.muted, fontSize: 12, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase", marginBottom: spacing.xs },
});
