import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { Level, LEVEL_INFO } from "@/src/levels";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";
import { startCheckout } from "@/src/payments";

const ORDER: Level[] = ["bronze", "silver", "gold"];

export default function Membership() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, refresh } = useAuth();
  const current = (user?.level ?? "bronze") as Level;
  const [selected, setSelected] = useState<Level>(current === "gold" ? "gold" : current === "silver" ? "gold" : "silver");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const business = user?.role === "admin" || user?.role === "venue_owner";
  const bronzeFree = user?.membership_tier === "free_girl";

  async function onChange() {
    setBusy(true);
    setMsg(null);
    try {
      if (ORDER.indexOf(selected) > ORDER.indexOf(current)) {
        await startCheckout({ kind: "membership", level: selected }, router);
        return;
      }
      await api.upgrade(selected);
      await refresh();
      setMsg({ ok: true, text: `You've moved to ${LEVEL_INFO[selected].label}.` });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Try again" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="membership-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="x" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Membership</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"], gap: spacing.md }}>
        <Text style={styles.title}>Bronze, Silver or Gold</Text>
        <Text style={styles.subtitle}>
          Higher tiers unlock the most exclusive venues and luxury services, lower fees and ticket discounts.
        </Text>
        {business ? (
          <Text style={styles.note} testID="membership-business-note">Business accounts already have full Gold access.</Text>
        ) : null}
        {ORDER.map((lvl) => {
          const info = LEVEL_INFO[lvl];
          const isCurrent = lvl === current;
          const isSel = lvl === selected;
          const price = lvl === "bronze" && bronzeFree ? "Free for women" : `$${info.price}/mo`;
          return (
            <Pressable
              key={lvl}
              testID={`level-card-${lvl}`}
              onPress={() => setSelected(lvl)}
              style={[styles.card, isSel && { borderColor: info.color, backgroundColor: colors.surfaceTertiary }]}
            >
              <View style={styles.cardHead}>
                <View style={[styles.medal, { borderColor: info.color }]}>
                  <FeatherIcon name="award" size={18} color={info.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.cardTitle, { color: info.color }]}>{info.label}</Text>
                  <Text style={styles.price}>{price}</Text>
                </View>
                {isCurrent ? <Text style={styles.current} testID={`level-current-${lvl}`}>CURRENT</Text> : null}
              </View>
              {info.perks.map((p) => (
                <View key={p} style={styles.perk}>
                  <FeatherIcon name="check" size={14} color={info.color} />
                  <Text style={styles.perkText}>{p}</Text>
                </View>
              ))}
            </Pressable>
          );
        })}
        {msg ? <Text testID="membership-msg" style={{ color: msg.ok ? colors.success : colors.error }}>{msg.text}</Text> : null}
        {!business ? (
          <LuxButton
            testID="membership-change-btn"
            label={
              busy ? "Updating…"
                : selected === current ? "Your current plan"
                  : ORDER.indexOf(selected) > ORDER.indexOf(current)
                    ? `Pay $${LEVEL_INFO[selected].price} · Upgrade to ${LEVEL_INFO[selected].label}`
                    : `Switch to ${LEVEL_INFO[selected].label}`
            }
            disabled={selected === current}
            onPress={onChange}
            loading={busy}
          />
        ) : null}
        <Text style={styles.hint}>Secure card payment by Stripe · billed for 30 days of access.</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 28, fontWeight: "800" },
  subtitle: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  note: { color: colors.brandPrimary, fontSize: 13 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1.5, borderColor: colors.border, gap: spacing.sm },
  cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.xs },
  medal: { width: 40, height: 40, borderRadius: 20, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontSize: 20, fontWeight: "800" },
  price: { color: colors.onSurface, fontSize: 14, fontWeight: "700" },
  current: { color: colors.onSurface, fontSize: 10, fontWeight: "800", letterSpacing: 1, backgroundColor: colors.surfaceTertiary, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm, overflow: "hidden" },
  perk: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  perkText: { color: colors.onSurfaceSecondary, fontSize: 13 },
  hint: { color: colors.muted, fontSize: 12, textAlign: "center" },
});
