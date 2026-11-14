import { useQuery } from "@tanstack/react-query";
import * as Linking from "expo-linking";
import { useFocusEffect, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useCallback, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

/** Promoters & venue owners link a bank through Stripe Connect for automatic payouts. */
export default function PayoutSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data, isLoading, refetch } = useQuery({ queryKey: ["connect-status"], queryFn: api.connectStatus });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useFocusEffect(useCallback(() => { refetch(); }, [refetch]));

  async function connect() {
    setErr("");
    setBusy(true);
    try {
      if (Platform.OS === "web") {
        const { url } = await api.connectOnboard({ origin_url: window.location.origin });
        window.location.href = url;
        return;
      }
      const returnUrl = Linking.createURL("payout-settings");
      const { url } = await api.connectOnboard({ origin_url: process.env.EXPO_PUBLIC_BACKEND_URL as string, return_url: returnUrl });
      await WebBrowser.openAuthSessionAsync(url, returnUrl);
      await refetch();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not open Stripe");
    } finally {
      setBusy(false);
    }
  }

  const state = !data ? null : !data.available ? "unavailable" : data.payouts_enabled ? "ready" : data.connected ? "incomplete" : "none";

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="payout-settings-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/profile"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Bank payouts</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading || !state ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"] }}>
          <View style={styles.card} testID={`payout-state-${state}`}>
            <FeatherIcon
              name={state === "ready" ? "check-circle" : state === "unavailable" ? "clock" : "briefcase"}
              size={28}
              color={state === "ready" ? colors.success : colors.brandPrimary}
            />
            <Text style={styles.title}>
              {state === "ready" ? "Your bank is linked" : state === "incomplete" ? "Finish your Stripe setup"
                : state === "unavailable" ? "Coming soon" : "Get paid automatically"}
            </Text>
            <Text style={styles.text}>
              {state === "ready"
                ? "Withdrawals and venue payouts are sent straight to your bank through Stripe. They usually land in 1–3 business days."
                : state === "incomplete"
                  ? "Stripe still needs a few details before it can send money to your bank."
                  : state === "unavailable"
                    ? "Automatic bank payouts switch on as soon as Nocturne connects its Stripe account. Until then, payouts are sent manually by our team."
                    : "Link your bank securely with Stripe. Nocturne never sees your bank details."}
            </Text>
          </View>
          {err ? <Text style={styles.err} testID="payout-error">{err}</Text> : null}
          {state === "none" || state === "incomplete" ? (
            <LuxButton
              testID="connect-bank-btn"
              label={busy ? "Opening Stripe…" : state === "none" ? "Link my bank with Stripe" : "Continue setup"}
              onPress={connect}
              loading={busy}
            />
          ) : null}
          <Text style={styles.hint}>A $2 fee applies per withdrawal. Venue earnings are paid out by Nocturne on a regular schedule.</Text>
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
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, gap: spacing.md, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  text: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 21 },
  err: { color: colors.error, fontSize: 13 },
  hint: { color: colors.muted, fontSize: 12, lineHeight: 18 },
});
