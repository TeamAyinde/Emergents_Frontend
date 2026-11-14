import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

export default function CheckIn() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [ticketId, setTicketId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const canScan = user?.role === "promoter" || user?.role === "venue_owner" || user?.role === "admin";

  async function submit() {
    if (!ticketId.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const t = await api.checkInTicket(ticketId.trim());
      setResult({ ok: true, msg: `${t.event_title} · qty ${t.quantity}` });
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="checkin-close" onPress={() => router.back()} style={styles.closeBtn}>
          <FeatherIcon name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Check-in</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.body}>
        {!canScan ? (
          <View style={styles.restricted}>
            <FeatherIcon name="lock" size={32} color={colors.brandPrimary} />
            <Text style={styles.restrictedTitle}>Staff only</Text>
            <Text style={styles.restrictedText}>Only promoters, venues and admins can scan guests.</Text>
          </View>
        ) : (
          <>
            <Text style={styles.hint}>{"Type the code under the guest's QR (e.g. #32993EB1) or the full ticket ID."}</Text>
            <TextInput
              testID="checkin-input"
              value={ticketId}
              onChangeText={setTicketId}
              placeholder="ticket id"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.input}
            />
            <LuxButton
              testID="checkin-submit"
              label={busy ? "Checking…" : "Check in guest"}
              onPress={submit}
              loading={busy}
            />
            {result && (
              <View style={[styles.result, { borderColor: result.ok ? colors.success : colors.error }]} testID="checkin-result">
                <FeatherIcon
                  name={result.ok ? "check-circle" : "x-circle"}
                  size={24}
                  color={result.ok ? colors.success : colors.error}
                />
                <Text style={styles.resultText}>{result.msg}</Text>
              </View>
            )}
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
  },
  closeBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  body: { flex: 1, padding: spacing.lg, gap: spacing.lg },
  hint: { color: colors.muted, fontSize: 14 },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    color: colors.onSurface, fontSize: 16, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  result: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.lg, borderWidth: 1.5,
  },
  resultText: { color: colors.onSurface, fontSize: 14, flex: 1 },
  restricted: { alignItems: "center", gap: spacing.md, paddingTop: spacing["3xl"] },
  restrictedTitle: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  restrictedText: { color: colors.muted, fontSize: 14, textAlign: "center", paddingHorizontal: spacing.xl },
});
