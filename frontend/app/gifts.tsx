import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { LEVEL_INFO } from "@/src/levels";
import { startCheckout } from "@/src/payments";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";
import { GiftRow } from "@/src/gift-row";

/** Buy a Silver or Gold month for a friend, share the code, or redeem one. */
export default function Gifts() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const [level, setLevel] = useState<"silver" | "gold">("gold");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [code, setCode] = useState("");
  const { data: gifts } = useQuery({ queryKey: ["my-gifts"], queryFn: api.myGifts });

  const buy = useMutation({
    mutationFn: () =>
      startCheckout({ kind: "gift", level, recipient_email: email.trim() || undefined, note: note.trim() || undefined }, router),
  });
  const redeem = useMutation({
    mutationFn: () => api.redeemGift(code),
    onSuccess: () => {
      setCode("");
      refresh();
      qc.invalidateQueries();
    },
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="gifts-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/profile"))} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Gift a membership</Text>
        <View style={{ width: 44 }} />
      </View>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: insets.bottom + spacing["3xl"] }}
      >
        <Text style={styles.section}>Give one month</Text>
        <View style={styles.row}>
          {(["silver", "gold"] as const).map((l) => (
            <Pressable
              key={l}
              testID={`gift-level-${l}`}
              onPress={() => setLevel(l)}
              style={[styles.opt, level === l && { borderColor: LEVEL_INFO[l].color }]}
            >
              <Text style={[styles.optTitle, { color: LEVEL_INFO[l].color }]}>{LEVEL_INFO[l].label}</Text>
              <Text style={styles.muted}>${LEVEL_INFO[l].price} · 1 month</Text>
            </Pressable>
          ))}
        </View>
        <TextInput
          testID="gift-email-input"
          value={email}
          onChangeText={setEmail}
          placeholder="Friend's email (we'll send them the code)"
          placeholderTextColor={colors.muted}
          keyboardType="email-address"
          autoCapitalize="none"
          style={styles.input}
        />
        <TextInput
          testID="gift-note-input"
          value={note}
          onChangeText={setNote}
          placeholder="Add a note (optional)"
          placeholderTextColor={colors.muted}
          maxLength={200}
          style={styles.input}
        />
        {buy.error ? <Text style={styles.err}>{buy.error.message}</Text> : null}
        <LuxButton
          testID="gift-buy-btn"
          label={buy.isPending ? "Opening checkout…" : `Pay $${LEVEL_INFO[level].price} · Gift ${LEVEL_INFO[level].label}`}
          onPress={() => buy.mutate()}
          loading={buy.isPending}
        />
        <Text style={styles.muted}>You will get a gift code to share. It stays valid until it is redeemed.</Text>

        {gifts?.length ? <Text style={styles.section}>Your gifts</Text> : null}
        {gifts?.map((g) => <GiftRow key={g.id} gift={g} />)}

        <Text style={styles.section}>Got a gift?</Text>
        <View style={styles.row}>
          <TextInput
            testID="gift-redeem-input"
            value={code}
            onChangeText={(t) => setCode(t.toUpperCase())}
            placeholder="GIFT-XXXXXX"
            placeholderTextColor={colors.muted}
            autoCapitalize="characters"
            style={[styles.input, { flex: 1 }]}
          />
          <Pressable
            testID="gift-redeem-btn"
            disabled={code.trim().length < 4 || redeem.isPending}
            onPress={() => redeem.mutate()}
            style={[styles.redeemBtn, (code.trim().length < 4 || redeem.isPending) && { opacity: 0.5 }]}
          >
            <Text style={styles.redeemText}>{redeem.isPending ? "…" : "Redeem"}</Text>
          </Pressable>
        </View>
        {redeem.error ? <Text style={styles.err} testID="gift-redeem-error">{redeem.error.message}</Text> : null}
        {redeem.data ? (
          <Text style={styles.ok} testID="gift-redeem-success">
            Enjoy {LEVEL_INFO[redeem.data.level as "silver"].label} until {new Date(redeem.data.until).toLocaleDateString("en", { month: "short", day: "numeric" })}.
          </Text>
        ) : null}
      </ScrollView>
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
  section: { color: colors.onSurface, fontSize: 18, fontWeight: "800", marginTop: spacing.sm },
  row: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  opt: { flex: 1, minHeight: 64, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, padding: spacing.md, justifyContent: "center" },
  optTitle: { fontSize: 16, fontWeight: "800" },
  input: {
    minHeight: 48, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface, paddingHorizontal: spacing.md, fontSize: 15,
  },
  muted: { color: colors.muted, fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
  ok: { color: colors.success, fontSize: 13 },
  gift: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  code: { color: colors.brandPrimary, fontSize: 16, fontWeight: "900", letterSpacing: 1 },
  shareBtn: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  redeemBtn: { minHeight: 48, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.brandPrimary, justifyContent: "center" },
  redeemText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "800" },
});
