import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, PARTNER_LABELS } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";
import { useAuth } from "@/src/auth-context";
import { canAccess, Level, LEVEL_INFO } from "@/src/levels";


export default function PartnerDetails() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [units, setUnits] = useState(1);
  const [guests, setGuests] = useState("2");
  const [notes, setNotes] = useState("");
  const { user } = useAuth();
  const lvl = (user?.level ?? "bronze") as Level;
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i + 1);
    d.setHours(18, 0, 0, 0);
    return d;
  });
  const [day, setDay] = useState(0);

  const { data: p, isLoading } = useQuery({ queryKey: ["partner", id], queryFn: () => api.getPartner(id!) });
  const book = useMutation({
    mutationFn: () =>
      api.requestPartnerBooking({
        partner_id: id!,
        date: days[day].toISOString(),
        units,
        guests: Math.max(1, parseInt(guests || "1", 10) || 1),
        notes,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mine-partner-bookings"] }),
  });

  if (isLoading || !p) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const base = p.base_price * units;
  const fee = base * LEVEL_INFO[lvl].fee;
  const total = base + fee;
  const publicTotal = (p.public_price || p.base_price) * units;
  const savings = Math.max(0, publicTotal - total);
  const locked = !canAccess(lvl, p.min_level);
  const maxUnits = p.price_unit === "hour" ? 12 : 14;

  return (
    <View style={styles.root}>
      <KeyboardAwareScrollView bottomOffset={120} contentContainerStyle={{ paddingBottom: 220 }}>
        <View style={styles.hero}>
          <Image source={p.image_url} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient
            colors={["rgba(9,9,11,0.5)", "transparent", "rgba(9,9,11,1)"]}
            locations={[0, 0.4, 1]}
            style={StyleSheet.absoluteFill}
          />
          <Pressable testID="partner-back" onPress={() => router.back()} style={[styles.back, { top: insets.top + spacing.sm }]}>
            <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroBottom}>
            <Text style={styles.cat}>{(PARTNER_LABELS[p.category] ?? p.category).toUpperCase()} · VETTED PARTNER</Text>
            <Text style={styles.name}>{p.name}</Text>
            <Text style={styles.meta}>{p.city} · ★ {p.rating.toFixed(1)} · ${p.base_price}/{p.price_unit}</Text>
          </View>
        </View>

        <View style={styles.body}>
          <Text style={styles.description}>{p.description}</Text>

          <Text style={styles.sectionTitle}>Date</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {days.map((d, i) => (
              <Pressable key={i} testID={`partner-day-${i}`} onPress={() => setDay(i)} style={[styles.day, day === i && styles.dayOn]}>
                <Text style={styles.dow}>{d.toLocaleDateString("en", { weekday: "short" }).toUpperCase()}</Text>
                <Text style={[styles.dnum, day === i && { color: colors.brandPrimary }]}>{d.getDate()}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <Text style={styles.sectionTitle}>How many {p.price_unit}s?</Text>
          <View style={styles.qtyRow}>
            <Pressable testID="units-minus" onPress={() => setUnits(Math.max(1, units - 1))} style={styles.qtyBtn}>
              <Text style={styles.qtyBtnText}>−</Text>
            </Pressable>
            <Text style={styles.qtyValue} testID="units-value">{units}</Text>
            <Pressable testID="units-plus" onPress={() => setUnits(Math.min(maxUnits, units + 1))} style={styles.qtyBtn}>
              <Text style={styles.qtyBtnText}>+</Text>
            </Pressable>
          </View>

          <Text style={styles.sectionTitle}>Guests</Text>
          <TextInput testID="partner-guests" value={guests} onChangeText={setGuests} keyboardType="number-pad" style={styles.input} />

          <Text style={styles.sectionTitle}>Requests</Text>
          <TextInput
            testID="partner-notes"
            value={notes}
            onChangeText={setNotes}
            placeholder="Pickup address, occasion, catering, DJ…"
            placeholderTextColor={colors.muted}
            multiline
            style={[styles.input, { minHeight: 80 }]}
          />

          <View style={styles.breakdown}>
            <Row label={`${units} × $${p.base_price}`} value={`$${base.toFixed(2)}`} />
            <Row label={`Concierge fee (${LEVEL_INFO[lvl].label} ${Math.round(LEVEL_INFO[lvl].fee * 100)}%)`} value={`$${fee.toFixed(2)}`} />
            <View style={styles.sep} />
            <Row label="Estimated total" value={`$${total.toFixed(2)}`} bold />
            <Row label="Public rate" value={`$${publicTotal.toFixed(2)}`} />
            {savings > 0 ? (
              <Text testID="partner-savings" style={styles.savings}>You save ${savings.toFixed(2)} as a member</Text>
            ) : null}
            <Text style={styles.hint}>No charge now. Our concierge confirms availability first.</Text>
          </View>
        </View>
      </KeyboardAwareScrollView>

      <View style={[styles.sticky, { paddingBottom: insets.bottom + spacing.md }]}>
        {book.isSuccess ? (
          <Text testID="partner-request-success" style={styles.success}>
            Request sent. Our team will confirm shortly — track it in Profile.
          </Text>
        ) : null}
        {book.error ? <Text testID="partner-request-error" style={styles.error}>{book.error.message}</Text> : null}
        {locked ? (
          <LuxButton
            testID="unlock-partner-btn"
            label={`${LEVEL_INFO[p.min_level as Level].label} members only · Upgrade`}
            onPress={() => router.push("/membership")}
          />
        ) : (
        <LuxButton
          testID="partner-request-btn"
          label={book.isPending ? "Sending…" : book.isSuccess ? "Done" : "Request booking"}
          onPress={() => (book.isSuccess ? router.back() : book.mutate())}
          loading={book.isPending}
        />
        )}
      </View>
    </View>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <View style={styles.rRow}>
      <Text style={[styles.rLabel, bold && styles.rBold]}>{label}</Text>
      <Text style={[styles.rValue, bold && styles.rBold]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 360 },
  back: {
    position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20,
    backgroundColor: "rgba(9,9,11,0.5)", alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  heroBottom: { position: "absolute", bottom: spacing.lg, left: spacing.lg, right: spacing.lg },
  cat: { color: colors.brandPrimary, fontSize: 11, letterSpacing: 2, fontWeight: "700" },
  name: { color: colors.onSurface, fontSize: 30, fontWeight: "800", marginTop: 6 },
  meta: { color: colors.muted, fontSize: 13, marginTop: spacing.xs },
  body: { padding: spacing.lg, gap: spacing.lg },
  description: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 22 },
  sectionTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  day: {
    flexShrink: 0, width: 56, height: 64, borderRadius: radius.md, borderWidth: 1.5,
    borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center",
  },
  dayOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  dow: { color: colors.muted, fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  dnum: { color: colors.onSurface, fontSize: 20, fontWeight: "800" },
  qtyRow: { flexDirection: "row", alignItems: "center", gap: spacing.xl, alignSelf: "center" },
  qtyBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  qtyBtnText: { color: colors.onSurface, fontSize: 22, fontWeight: "700" },
  qtyValue: { color: colors.onSurface, fontSize: 28, fontWeight: "800", minWidth: 40, textAlign: "center" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14, color: colors.onSurface, fontSize: 16,
  },
  breakdown: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.border, gap: spacing.sm,
  },
  rRow: { flexDirection: "row", justifyContent: "space-between" },
  rLabel: { color: colors.muted, fontSize: 14 },
  rValue: { color: colors.onSurface, fontSize: 14 },
  rBold: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  sep: { height: 0.5, backgroundColor: colors.divider, marginVertical: spacing.xs },
  hint: { color: colors.muted, fontSize: 12, marginTop: spacing.xs },
  savings: { color: colors.success, fontSize: 13, fontWeight: "700" },
  sticky: {
    position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: "rgba(9,9,11,0.95)",
    borderTopWidth: 1, borderTopColor: colors.border, padding: spacing.lg,
  },
  success: { color: colors.success, marginBottom: spacing.sm },
  error: { color: colors.error, marginBottom: spacing.sm },
});
