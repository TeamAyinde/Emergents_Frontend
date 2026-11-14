import { useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, PaymentStatus } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

const MAX_POLLS = 15;

/** Stripe sends guests back here; we confirm the payment with our server before showing success. */
export default function PaymentResult() {
  const { session_id, cancelled, tx } = useLocalSearchParams<{ session_id?: string; cancelled?: string; tx?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const [st, setSt] = useState<PaymentStatus | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [err, setErr] = useState("");
  const polls = useRef(0);

  useEffect(() => {
    if (cancelled) {
      if (tx) api.cancelPayment(tx).catch(() => {});
      refresh();
      return;
    }
    if (!session_id) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const s = await api.paymentStatus(session_id);
        if (stop) return;
        setSt(s);
        if (s.status !== "pending") {
          qc.invalidateQueries();
          refresh();
          return;
        }
      } catch (e) {
        if (stop) return;
        const m = e instanceof Error ? e.message : "Could not check payment";
        setErr(m);
        if (m === "Payment not found") {
          setTimedOut(true);
          return;
        }
      }
      polls.current += 1;
      if (polls.current >= MAX_POLLS) {
        setTimedOut(true);
        return;
      }
      timer = setTimeout(poll, 2000);
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [session_id, cancelled, tx, qc, refresh]);

  const notFound = err === "Payment not found" || (!cancelled && !session_id);
  const status = cancelled ? "cancelled" : notFound ? "missing" : st?.status ?? "pending";

  function goToResult() {
    if (st?.kind === "ticket" && st.result_id) router.replace(`/ticket/${st.result_id}`);
    else if (st?.kind === "boost") router.replace("/host");
    else if (st?.kind === "spotlight") router.replace("/(tabs)");
    else if (st?.kind === "gift") router.replace("/gifts");
    else router.replace("/(tabs)/profile");
  }

  async function backOut() {
    if (session_id && status === "pending") await api.cancelPayment(session_id).catch(() => {});
    router.replace("/(tabs)");
  }

  const view = {
    paid: {
      icon: "check-circle", color: colors.success,
      title: st?.kind === "membership" && st.amount === 0 ? "Free trial started" : "Payment confirmed",
      text: st ? (st.amount === 0 ? st.label : `${st.label} · $${st.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`) : "",
    },
    pending: { icon: "clock", color: colors.brandPrimary, title: timedOut ? "Still confirming…" : "Confirming payment…",
      text: timedOut ? "Your bank is taking a moment. If you paid, your booking will appear in Profile shortly." : "This takes a few seconds." },
    cancelled: { icon: "x-circle", color: colors.muted, title: "Payment cancelled", text: "No charge was made. You can try again any time." },
    missing: { icon: "help-circle", color: colors.muted, title: "Payment not found", text: "We couldn't find this checkout. Your bookings are always listed in Profile." },
    expired: { icon: "x-circle", color: colors.muted, title: "Checkout expired", text: "No charge was made. Please start again." },
    failed: { icon: "alert-triangle", color: colors.error, title: "We couldn't complete your booking",
      text: `${st?.error ?? "Something went wrong"}. Our team has been notified and will refund you in full.` },
  }[status];

  return (
    <View style={[styles.root, { paddingTop: insets.top + spacing["2xl"], paddingBottom: insets.bottom + spacing.xl }]}>
      <View style={styles.center} testID={`payment-status-${status}`}>
        {status === "pending" && !timedOut ? (
          <ActivityIndicator size="large" color={colors.brandPrimary} />
        ) : (
          <View style={[styles.badge, { borderColor: view.color }]}>
            <FeatherIcon name={view.icon as any} size={36} color={view.color} />
          </View>
        )}
        <Text style={styles.title}>{view.title}</Text>
        <Text style={styles.text}>{view.text}</Text>
        {err && status === "pending" && !notFound ? <Text style={styles.err}>{err}</Text> : null}
        {status === "paid" && st?.kind === "membership" ? (
          <Text style={styles.text}>Your new perks are live now — enjoy.</Text>
        ) : null}
      </View>
      <View style={{ gap: spacing.sm }}>
        {status === "paid" ? (
          <LuxButton
            testID="payment-continue-btn"
            label={st?.kind === "ticket" ? "View my ticket" : st?.kind === "membership" ? "Go to my profile" : st?.kind === "boost" ? "Back to Host Studio" : st?.kind === "spotlight" ? "See it on the feed" : st?.kind === "gift" ? "Get the gift code" : "See my booking"}
            onPress={goToResult}
          />
        ) : (
          <LuxButton testID="payment-home-btn" label="Back to Nocturne" variant="secondary" onPress={backOut} />
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: spacing.xl, justifyContent: "space-between" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md },
  badge: { width: 80, height: 80, borderRadius: radius.pill, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  title: { color: colors.onSurface, fontSize: 26, fontWeight: "800", textAlign: "center" },
  text: { color: colors.onSurfaceSecondary, fontSize: 15, lineHeight: 22, textAlign: "center" },
  err: { color: colors.error, fontSize: 13 },
});
