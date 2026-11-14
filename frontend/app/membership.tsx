import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
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
  const [renewBusy, setRenewBusy] = useState(false);
  const [yearly, setYearly] = useState(false);
  const { data: sub, refetch: refetchSub } = useQuery({
    queryKey: ["subscription"], queryFn: api.subscription, enabled: !!user && user.role !== "admin" && user.role !== "venue_owner",
  });
  // start the Gold toggle on the member's current billing so nobody switches by accident
  useEffect(() => {
    if (sub?.active && sub.level === "gold") setYearly(sub.interval === "year");
  }, [sub?.active, sub?.level, sub?.interval]);

  async function onChange() {
    setBusy(true);
    setMsg(null);
    try {
      if (selected === "bronze" && bronzeFree) {
        await api.upgrade(selected);
        await refresh();
        await refetchSub();
        setMsg({ ok: true, text: "You're on free Bronze. Your monthly plan has been cancelled." });
        return;
      }
      await startCheckout({ kind: "membership", level: selected, interval: selected === "gold" && yearly ? "year" : "month" }, router);
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Try again" });
    } finally {
      setBusy(false);
    }
  }

  async function toggleRenewal() {
    if (!sub) return;
    setRenewBusy(true);
    setMsg(null);
    try {
      await api.setRenewal(sub.cancel_at_period_end ? "resume" : "cancel");
      await refetchSub();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Try again" });
    } finally {
      setRenewBusy(false);
    }
  }

  const interval = selected === "gold" && yearly ? "year" : "month";
  const onPlan = !!sub?.active && sub.level === selected && sub.interval === interval;
  const trial = selected === "bronze" && !!sub?.trial_available;
  const renewDate = sub?.renews_at ? new Date(sub.renews_at).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" }) : "";

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
        {sub?.active && sub.level ? (
          <View style={styles.subCard} testID="subscription-card">
            <Text style={styles.subTitle}>
              {LEVEL_INFO[sub.level as Level].label} · {sub.status === "trialing" ? "free trial" : sub.status === "past_due" ? "payment due" : sub.interval === "year" ? "yearly" : "monthly"}
            </Text>
            <Text style={styles.subText} testID="subscription-renewal">
              {sub.cancel_at_period_end
                ? `Ends on ${renewDate}. You won't be charged again.`
                : sub.status === "trialing"
                  ? `Free until ${renewDate}, then $${LEVEL_INFO[sub.level as Level].price}/month.`
                  : `Renews automatically on ${renewDate}${sub.interval === "year" ? " (yearly)" : ""}.`}
            </Text>
            {sub.manageable ? (
              <Pressable testID="subscription-toggle-btn" onPress={toggleRenewal} disabled={renewBusy} style={styles.subBtn}>
                <Text style={styles.subBtnText}>{renewBusy ? "Updating…" : sub.cancel_at_period_end ? "Keep my plan" : "Cancel auto-renew"}</Text>
              </Pressable>
            ) : (
              <Text style={styles.subText} testID="subscription-manage-note">To change auto-renew, message your concierge.</Text>
            )}
          </View>
        ) : null}
        {ORDER.map((lvl) => {
          const info = LEVEL_INFO[lvl];
          const isCurrent = lvl === current;
          const isSel = lvl === selected;
          const price = lvl === "bronze" && bronzeFree ? "Free for women"
            : lvl === "bronze" && sub?.trial_available ? `7 days free, then $${info.price}/mo` : `$${info.price}/mo`;
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
              {lvl === "gold" && isSel ? (
                <View style={styles.billing} testID="gold-billing-toggle">
                  {([false, true] as const).map((y) => (
                    <Pressable
                      key={String(y)}
                      testID={y ? "gold-yearly" : "gold-monthly"}
                      onPress={() => setYearly(y)}
                      style={[styles.billOpt, yearly === y && { borderColor: info.color, backgroundColor: colors.surfaceSecondary }]}
                    >
                      <Text style={styles.billTitle}>{y ? "$1,490/year" : `$${info.price}/month`}</Text>
                      <Text style={styles.billSub}>{y ? "2 months free" : "Billed monthly"}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
            </Pressable>
          );
        })}
        {msg ? <Text testID="membership-msg" style={{ color: msg.ok ? colors.success : colors.error }}>{msg.text}</Text> : null}
        {!business ? (
          <LuxButton
            testID="membership-change-btn"
            label={
              busy ? "Opening checkout…"
                : onPlan ? "Your current plan"
                  : selected === "bronze" && bronzeFree ? "Switch to free Bronze"
                    : trial ? "Start 7-day free trial"
                      : interval === "year" ? "Subscribe · $1,490/year"
                        : `Subscribe · $${LEVEL_INFO[selected].price}/month`
            }
            disabled={onPlan || (selected === current && selected === "bronze" && bronzeFree)}
            onPress={onChange}
            loading={busy}
          />
        ) : null}
        <Text style={styles.hint}>Secure card billing by Stripe · renews {interval === "year" ? "yearly" : "monthly"} · cancel anytime.</Text>
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
  subCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.brandPrimary },
  subTitle: { color: colors.onSurface, fontSize: 16, fontWeight: "800" },
  subText: { color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 19 },
  subBtn: { minHeight: 44, alignSelf: "flex-start", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  subBtnText: { color: colors.onSurface, fontSize: 13, fontWeight: "700" },
  billing: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  billOpt: { flex: 1, minHeight: 56, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, padding: spacing.sm, justifyContent: "center" },
  billTitle: { color: colors.onSurface, fontSize: 14, fontWeight: "800" },
  billSub: { color: colors.muted, fontSize: 11 },
});
